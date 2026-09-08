import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from app.database import get_connection
from app.services.pdf_parser import PDFParser
from app.services.chunker import SemanticChunker
from app.services.fact_extractor import FactExtractor
from app.services.fact_store import FactStore
from app.services.relationship_engine import RelationshipEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.get("")
def list_documents():
    """List all ingested documents and their statistics."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT d.document_id, d.filename, d.total_pages, d.created_at,
               COUNT(f.fact_id) as fact_count,
               SUM(CASE WHEN f.grounding_verified = 1 THEN 1 ELSE 0 END) as grounded_count
        FROM documents d
        LEFT JOIN facts f ON d.document_id = f.document_id
        GROUP BY d.document_id
        ORDER BY d.created_at DESC
    """)
    rows = c.fetchall()
    conn.close()

    return [
        {
            "document_id": r["document_id"],
            "filename": r["filename"],
            "total_pages": r["total_pages"],
            "created_at": r["created_at"],
            "fact_count": r["fact_count"],
            "grounded_count": r["grounded_count"] or 0,
            "grounding_rate": round((r["grounded_count"] or 0) / r["fact_count"] * 100, 1) if r["fact_count"] > 0 else 0.0
        }
        for r in rows
    ]

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    max_pages: Optional[int] = Query(None, description="Optional cap on pages to parse")
):
    """Upload an arbitrary PDF, extract structured facts with exact grounding, index embeddings, and discover cross-document relationships."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        parser = PDFParser(extract_tables=True)
        chunker = SemanticChunker(target_chunk_chars=1200, overlap_chars=150)
        extractor = FactExtractor()
        store = FactStore()

        # Parse & chunk
        doc = parser.parse_document(str(file_path), max_pages=max_pages)
        chunks = chunker.chunk_document(doc)
        store.save_document(doc)

        # Batch fact extraction
        batch_size = 3
        useful_chunks = [c for c in chunks if len(c.text.strip()) >= 60]
        batches = [useful_chunks[i:i + batch_size] for i in range(0, len(useful_chunks), batch_size)]

        all_facts = []
        for batch in batches:
            facts = extractor.extract_facts_from_chunks(batch)
            if facts:
                store.save_facts(facts)
                all_facts.extend(facts)

        grounded_count = sum(1 for f in all_facts if f.grounding_verified)

        # Cross-Document Relationship Discovery Phase
        discovered_relationships = []
        if all_facts:
            try:
                engine = RelationshipEngine()
                candidates = store.find_candidate_pairs(doc.document_id, top_k_per_fact=2, threshold=0.70)

                # Deduplicate candidates by fact ID pair
                seen_pairs = set()
                unique_candidates = []
                for fa, fb, score in candidates:
                    pair_key = (min(fa.fact_id, fb.fact_id), max(fa.fact_id, fb.fact_id))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        unique_candidates.append((fa, fb, score))

                # Build document name map
                conn = get_connection(store.db_path)
                c_cur = conn.cursor()
                c_cur.execute("SELECT document_id, filename FROM documents")
                doc_name_map = {r["document_id"]: r["filename"] for r in c_cur.fetchall()}
                conn.close()

                # Process candidates: Rule Fast-Path first (0 API tokens)
                non_fastpath = []
                for fa, fb, score in unique_candidates:
                    fast_rel = engine._check_fast_path(fa, fb)
                    if fast_rel:
                        discovered_relationships.append((fast_rel, fa, fb))
                        store.save_relationship(fast_rel)
                    else:
                        non_fastpath.append((fa, fb, score))

                # For non-fastpath, sort by similarity score and evaluate top 4
                non_fastpath.sort(key=lambda x: x[2], reverse=True)
                top_to_reason = non_fastpath[:4]

                for fa, fb, score in top_to_reason:
                    doc_a = doc_name_map.get(fa.document_id, doc.filename)
                    doc_b = doc_name_map.get(fb.document_id, "Other Document")
                    rel = engine.classify_pair(fa, fb, doc_a_name=doc_a, doc_b_name=doc_b)
                    store.save_relationship(rel)
                    discovered_relationships.append((rel, fa, fb))

            except Exception as ex:
                logger.error(f"Auto-reasoning during upload encountered error: {ex}")

        # Format relationships for API response
        formatted_relationships = [
            {
                "relationship": rel.relationship.value if hasattr(rel.relationship, "value") else str(rel.relationship),
                "confidence": rel.confidence,
                "explanation": rel.explanation,
                "reconciliation_context": rel.reconciliation_context,
                "detected_by": rel.detected_by,
                "fact_a": {
                    "document": doc_name_map.get(fa.document_id, doc.filename) if 'doc_name_map' in locals() else doc.filename,
                    "page_number": fa.page_number,
                    "subject": fa.subject,
                    "predicate": fa.predicate,
                    "object_value": fa.object_value,
                    "period": fa.period,
                    "verbatim_quote": fa.verbatim_quote
                },
                "fact_b": {
                    "document": doc_name_map.get(fb.document_id, "Other Document") if 'doc_name_map' in locals() else "Other Document",
                    "page_number": fb.page_number,
                    "subject": fb.subject,
                    "predicate": fb.predicate,
                    "object_value": fb.object_value,
                    "period": fb.period,
                    "verbatim_quote": fb.verbatim_quote
                }
            }
            for rel, fa, fb in discovered_relationships
        ]

        # Format extracted facts for API response
        formatted_facts = [
            {
                "fact_id": f.fact_id,
                "page_number": f.page_number,
                "subject": f.subject,
                "predicate": f.predicate,
                "object_value": f.object_value,
                "period": f.period,
                "verbatim_quote": f.verbatim_quote,
                "grounding_verified": f.grounding_verified
            }
            for f in all_facts
        ]

        return {
            "status": "success",
            "document_id": doc.document_id,
            "filename": doc.filename,
            "total_pages": doc.total_pages,
            "chunks_created": len(chunks),
            "facts_extracted": len(all_facts),
            "grounded_facts": grounded_count,
            "grounding_rate_percent": round(grounded_count / len(all_facts) * 100, 1) if all_facts else 0.0,
            "extracted_facts": formatted_facts,
            "discovered_relationships": formatted_relationships
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

