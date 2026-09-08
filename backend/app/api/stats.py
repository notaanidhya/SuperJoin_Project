from fastapi import APIRouter
from app.database import get_connection

router = APIRouter(prefix="/api/stats", tags=["Stats"])

@router.get("")
def get_stats():
    """Retrieve aggregate statistics of documents, facts, and relationships in the knowledge layer."""
    conn = get_connection()
    c = conn.cursor()

    # Documents
    c.execute("SELECT count(*) as cnt FROM documents")
    total_docs = c.fetchone()["cnt"]

    # Facts
    c.execute("SELECT count(*) as total, sum(CASE WHEN grounding_verified = 1 THEN 1 ELSE 0 END) as grounded FROM facts")
    fact_row = c.fetchone()
    total_facts = fact_row["total"] or 0
    grounded_facts = fact_row["grounded"] or 0
    grounding_rate = round((grounded_facts / total_facts * 100), 1) if total_facts > 0 else 0.0

    # Relationships breakdown
    c.execute("SELECT relationship, count(*) as cnt FROM relationships GROUP BY relationship")
    rel_rows = c.fetchall()
    rel_counts = {r["relationship"]: r["cnt"] for r in rel_rows}
    total_relationships = sum(rel_counts.values())

    conn.close()

    return {
        "total_documents": total_docs,
        "total_facts": total_facts,
        "grounded_facts": grounded_facts,
        "grounding_rate_percent": grounding_rate,
        "total_relationships": total_relationships,
        "relationship_breakdown": rel_counts,
        "model_in_use": "gemini-3.5-flash-lite",
        "embedding_model": "all-MiniLM-L6-v2"
    }
