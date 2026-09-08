from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query
from app.database import get_connection
from app.services.fact_store import FactStore
from app.services.relationship_engine import RelationshipEngine

router = APIRouter(prefix="/api/relationships", tags=["Relationships"])

class ClassifyPairRequest(BaseModel):
    fact_a_id: str
    fact_b_id: str

@router.get("")
def list_relationships(
    relationship_type: Optional[str] = Query(None, description="Filter by: corroborates, contradicts, reconciles, unrelated"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0)
):
    """Retrieve classified cross-document relationships with full evidence pairs."""
    conn = get_connection()
    c = conn.cursor()

    conditions = []
    params = []

    if relationship_type:
        conditions.append("r.relationship = ?")
        params.append(relationship_type.lower())
    else:
        # Default: exclude unrelated unless specifically asked
        conditions.append("r.relationship != 'unrelated'")

    if min_confidence is not None:
        conditions.append("r.confidence >= ?")
        params.append(min_confidence)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Count
    c.execute(f"SELECT count(*) as cnt FROM relationships r {where_clause}", tuple(params))
    total_count = c.fetchone()["cnt"]

    # Fetch
    sql = f"""
        SELECT r.*,
               f1.subject as s1, f1.predicate as pred1, f1.object_value as val1, f1.period as per1, f1.verbatim_quote as q1, f1.page_number as p1, d1.filename as doc1,
               f2.subject as s2, f2.predicate as pred2, f2.object_value as val2, f2.period as per2, f2.verbatim_quote as q2, f2.page_number as p2, d2.filename as doc2
        FROM relationships r
        JOIN facts f1 ON r.fact_a_id = f1.fact_id
        JOIN documents d1 ON f1.document_id = d1.document_id
        JOIN facts f2 ON r.fact_b_id = f2.fact_id
        JOIN documents d2 ON f2.document_id = d2.document_id
        {where_clause}
        ORDER BY r.confidence DESC, r.created_at DESC
        LIMIT ? OFFSET ?
    """
    c.execute(sql, tuple(params + [limit, skip]))
    rows = c.fetchall()
    conn.close()

    return {
        "total": total_count,
        "limit": limit,
        "skip": skip,
        "items": [
            {
                "id": f"{r['fact_a_id']}_{r['fact_b_id']}",
                "relationship": r["relationship"],
                "confidence": r["confidence"],
                "explanation": r["explanation"],
                "reconciliation_context": r["reconciliation_context"],
                "detected_by": r["detected_by"],
                "fact_a": {
                    "fact_id": r["fact_a_id"],
                    "document": r["doc1"],
                    "page_number": r["p1"],
                    "subject": r["s1"],
                    "predicate": r["pred1"],
                    "object_value": r["val1"],
                    "period": r["per1"],
                    "verbatim_quote": r["q1"]
                },
                "fact_b": {
                    "fact_id": r["fact_b_id"],
                    "document": r["doc2"],
                    "page_number": r["p2"],
                    "subject": r["s2"],
                    "predicate": r["pred2"],
                    "object_value": r["val2"],
                    "period": r["per2"],
                    "verbatim_quote": r["q2"]
                }
            }
            for r in rows
        ]
    }

@router.post("/classify-pair")
def classify_pair_on_demand(req: ClassifyPairRequest):
    """Run real-time reasoning and classification between any two arbitrary facts."""
    store = FactStore()
    engine = RelationshipEngine()

    fact_a = store.get_fact_by_id(req.fact_a_id)
    fact_b = store.get_fact_by_id(req.fact_b_id)

    if not fact_a or not fact_b:
        raise HTTPException(status_code=404, detail="One or both facts were not found in the database.")

    # Get filenames
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT document_id, filename FROM documents WHERE document_id IN (?, ?)", (fact_a.document_id, fact_b.document_id))
    doc_map = {row["document_id"]: row["filename"] for row in c.fetchall()}
    conn.close()

    doc_a_name = doc_map.get(fact_a.document_id, "Document A")
    doc_b_name = doc_map.get(fact_b.document_id, "Document B")

    rel = engine.classify_pair(fact_a, fact_b, doc_a_name=doc_a_name, doc_b_name=doc_b_name)
    store.save_relationship(rel)

    return {
        "fact_a_id": rel.fact_a_id,
        "fact_b_id": rel.fact_b_id,
        "relationship": rel.relationship.value,
        "confidence": rel.confidence,
        "explanation": rel.explanation,
        "reconciliation_context": rel.reconciliation_context,
        "detected_by": rel.detected_by
    }
