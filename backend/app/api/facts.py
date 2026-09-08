from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from app.database import get_connection

router = APIRouter(prefix="/api/facts", tags=["Facts"])

@router.get("")
def list_facts(
    document_id: Optional[str] = Query(None, description="Filter by Document ID"),
    page_number: Optional[int] = Query(None, description="Filter by Page Number"),
    grounding_verified: Optional[bool] = Query(None, description="Filter by grounding status"),
    query: Optional[str] = Query(None, description="Text search across fact attributes"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0)
):
    """Search and filter extracted facts across all ingested documents."""
    conn = get_connection()
    c = conn.cursor()

    conditions = []
    params = []

    if document_id:
        conditions.append("f.document_id = ?")
        params.append(document_id)
    if page_number is not None:
        conditions.append("f.page_number = ?")
        params.append(page_number)
    if grounding_verified is not None:
        conditions.append("f.grounding_verified = ?")
        params.append(1 if grounding_verified else 0)
    if query:
        conditions.append("(f.subject LIKE ? OR f.predicate LIKE ? OR f.object_value LIKE ? OR f.verbatim_quote LIKE ?)")
        q_wild = f"%{query}%"
        params.extend([q_wild, q_wild, q_wild, q_wild])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Count total
    c.execute(f"SELECT count(*) as cnt FROM facts f {where_clause}", tuple(params))
    total_count = c.fetchone()["cnt"]

    # Fetch rows
    sql = f"""
        SELECT f.*, d.filename as document_filename
        FROM facts f
        JOIN documents d ON f.document_id = d.document_id
        {where_clause}
        ORDER BY f.created_at DESC, f.page_number ASC
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
                "fact_id": r["fact_id"],
                "document_id": r["document_id"],
                "document_filename": r["document_filename"],
                "chunk_id": r["chunk_id"],
                "page_number": r["page_number"],
                "section_header": r["section_header"],
                "fact_type": r["fact_type"],
                "subject": r["subject"],
                "predicate": r["predicate"],
                "object_value": r["object_value"],
                "numeric_value": r["numeric_value"],
                "unit": r["unit"],
                "period": r["period"],
                "scope": r["scope"],
                "verbatim_quote": r["verbatim_quote"],
                "confidence": r["confidence"],
                "grounding_verified": bool(r["grounding_verified"]),
                "char_offset_in_chunk": r["char_offset_in_chunk"]
            }
            for r in rows
        ]
    }

@router.get("/{fact_id}")
def get_fact(fact_id: str):
    """Retrieve detailed metadata and chunk context for an individual fact."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        SELECT f.*, d.filename as document_filename, c.text as chunk_text
        FROM facts f
        JOIN documents d ON f.document_id = d.document_id
        LEFT JOIN document_chunks c ON f.chunk_id = c.chunk_id
        WHERE f.fact_id = ?
    """, (fact_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "fact_id": row["fact_id"],
        "document_id": row["document_id"],
        "document_filename": row["document_filename"],
        "chunk_id": row["chunk_id"],
        "chunk_text": row["chunk_text"],
        "page_number": row["page_number"],
        "section_header": row["section_header"],
        "fact_type": row["fact_type"],
        "subject": row["subject"],
        "predicate": row["predicate"],
        "object_value": row["object_value"],
        "numeric_value": row["numeric_value"],
        "unit": row["unit"],
        "period": row["period"],
        "scope": row["scope"],
        "verbatim_quote": row["verbatim_quote"],
        "confidence": row["confidence"],
        "grounding_verified": bool(row["grounding_verified"]),
        "char_offset_in_chunk": row["char_offset_in_chunk"]
    }
