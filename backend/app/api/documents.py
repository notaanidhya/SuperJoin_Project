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
    """Upload an arbitrary PDF, extract structured facts with exact grounding, and index embeddings."""
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

        return {
            "status": "success",
            "document_id": doc.document_id,
            "filename": doc.filename,
            "total_pages": doc.total_pages,
            "chunks_created": len(chunks),
            "facts_extracted": len(all_facts),
            "grounded_facts": grounded_count,
            "grounding_rate_percent": round(grounded_count / len(all_facts) * 100, 1) if all_facts else 0.0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
