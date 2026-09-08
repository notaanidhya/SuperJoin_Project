import os
import sys
import re
import time
import argparse
import functools
from pathlib import Path
from typing import List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print = functools.partial(print, flush=True)

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import init_db, get_connection
from app.models.schemas import DocumentChunk, ParsedDocument
from app.services.pdf_parser import PDFParser
from app.services.chunker import SemanticChunker
from app.services.fact_extractor import FactExtractor
from app.services.fact_store import FactStore

DATASET_PDFS = [
    "starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf",
    "starter-datasets/delhivery/02-delhivery-annual-report-fy24-excerpt.pdf",
    "starter-datasets/delhivery/01-delhivery-prospectus-2022-excerpt.pdf",
    "starter-datasets/india-macroeconomy/01-india-economic-survey-2024-25-excerpt.pdf",
    "starter-datasets/india-macroeconomy/02-rbi-annual-report-2024-25-excerpt.pdf",
    "starter-datasets/india-macroeconomy/03-imf-india-2025-article-iv-excerpt.pdf",
]

def is_noise_chunk(chunk: DocumentChunk) -> bool:
    """Structure-agnostic noise detection for arbitrary PDF chunks."""
    raw = chunk.text.strip()
    if len(raw) < 60:
        return True

    # Check for pure numeric noise (e.g. chart axis labels rendered as text)
    digits = sum(c.isdigit() for c in raw)
    if len(raw) > 0 and (digits / len(raw) > 0.75):
        words = [w for w in raw.split() if any(c.isalpha() for c in w)]
        if len(words) < 3:
            return True

    # Check for pure repetitive symbols or pagination markers
    if re.fullmatch(r"^(Page\s+\d+|[0-9\s\.\,\-\|\/]+|©.*)$", raw, re.IGNORECASE):
        return True

    return False

def get_already_processed_chunk_ids(db_path: str) -> set:
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT chunk_id FROM facts")
        rows = cursor.fetchall()
        conn.close()
        return {r["chunk_id"] for r in rows}
    except Exception:
        return set()

def get_doc_fact_count(db_path: str, filename: str) -> int:
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) as cnt FROM facts f 
               JOIN documents d ON f.document_id = d.document_id 
               WHERE d.filename = ?""", 
            (filename,)
        )
        row = cursor.fetchone()
        conn.close()
        return row["cnt"] if row else 0
    except Exception:
        return 0

def main():
    parser = argparse.ArgumentParser(description="Universal multi-document batch ingestion runner")
    parser.add_argument("--batch-size", type=int, default=3, help="Chunks per LLM call (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and filter chunks without calling LLM")
    parser.add_argument("--max-pages-per-doc", type=int, default=None, help="Cap pages per document for testing")
    parser.add_argument("--max-chunks-per-doc", type=int, default=None, help="Cap chunks per document for testing")
    parser.add_argument("--pdf", type=str, default=None, help="Process a single PDF instead of entire starter dataset")
    parser.add_argument("--force-reindex", action="store_true", help="Reprocess chunks even if already indexed")
    parser.add_argument("--db-path", type=str, default="data/fact_layer.db", help="SQLite database path")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = str(project_root / args.db_path)
    init_db(db_path)

    pdf_files = [args.pdf] if args.pdf else [str(project_root / p) for p in DATASET_PDFS]

    print("=" * 80)
    print("UNIVERSAL PDF INGESTION & FACT EXTRACTION PIPELINE")
    print(f"Batch size: {args.batch_size} chunks/call | Mode: {'DRY RUN' if args.dry_run else 'LIVE EXTRACTION'}")
    print(f"Database:   {db_path}")
    print(f"Documents:  {len(pdf_files)} PDF(s)")
    print("=" * 80)

    pdf_parser = PDFParser(extract_tables=True)
    chunker = SemanticChunker(target_chunk_chars=1200, overlap_chars=150)
    extractor = None if args.dry_run else FactExtractor()
    store = FactStore(db_path=db_path)

    already_processed = set() if args.force_reindex else get_already_processed_chunk_ids(db_path)
    total_new_facts = 0
    total_api_calls = 0

    for doc_idx, pdf_path in enumerate(pdf_files, 1):
        if not os.path.exists(pdf_path):
            print(f"\n[!] Skipping missing file: {pdf_path}")
            continue

        filename = os.path.basename(pdf_path)
        existing_facts = get_doc_fact_count(db_path, filename)
        if existing_facts > 0 and not args.force_reindex and not args.dry_run:
            print(f"\n[{doc_idx}/{len(pdf_files)}] {filename} already indexed ({existing_facts} facts in DB). Skipping.")
            continue

        print(f"\n[{doc_idx}/{len(pdf_files)}] Parsing: {filename}")

        t0 = time.time()
        doc = pdf_parser.parse_document(pdf_path, max_pages=args.max_pages_per_doc)
        all_chunks = chunker.chunk_document(doc)
        parse_dur = time.time() - t0

        # Structure-agnostic pre-filtering
        useful_chunks = [c for c in all_chunks if not is_noise_chunk(c)]
        if args.max_chunks_per_doc:
            useful_chunks = useful_chunks[:args.max_chunks_per_doc]

        print(f"  Pages: {doc.total_pages} ({parse_dur:.1f}s) | Total Chunks: {len(all_chunks)} | "
              f"Substantive Chunks: {len(useful_chunks)} (Filtered {len(all_chunks) - len(useful_chunks)} noise)")

        if args.dry_run:
            est_calls = (len(useful_chunks) + args.batch_size - 1) // args.batch_size
            est_seconds = est_calls * 3.5
            print(f"  [Dry Run] Estimated API calls: {est_calls} (~{est_seconds:.0f}s)")
            continue

        # Save document & chunks metadata
        store.save_document(doc)

        # Filter out already processed chunks
        unprocessed_chunks = [c for c in useful_chunks if c.chunk_id not in already_processed]
        if len(unprocessed_chunks) < len(useful_chunks):
            print(f"  Resuming: {len(useful_chunks) - len(unprocessed_chunks)} chunks already in DB. Processing remaining {len(unprocessed_chunks)}...")

        if not unprocessed_chunks:
            print("  All chunks already indexed. Moving to next document.")
            continue

        # Process in batches
        batches = [unprocessed_chunks[i:i + args.batch_size] for i in range(0, len(unprocessed_chunks), args.batch_size)]
        doc_facts = []

        print(f"  Extracting facts across {len(batches)} batches (batch size {args.batch_size})...")
        for b_idx, batch in enumerate(batches, 1):
            batch_summary = f"Pages {[c.page_number for c in batch]}"
            facts = extractor.extract_facts_from_chunks(batch)
            total_api_calls += 1

            if facts:
                store.save_facts(facts)
                doc_facts.extend(facts)
                verified_count = sum(1 for f in facts if f.grounding_verified)
                print(f"    Batch [{b_idx}/{len(batches)}] {batch_summary} -> {len(facts)} facts ({verified_count} grounded)")
            else:
                print(f"    Batch [{b_idx}/{len(batches)}] {batch_summary} -> 0 facts")

        total_new_facts += len(doc_facts)
        print(f"  Done {filename}: {len(doc_facts)} new facts persisted.")

    print("\n" + "=" * 80)
    print("INGESTION COMPLETE SUMMARY")
    print("=" * 80)
    print(f"Total API Calls made: {total_api_calls}")
    print(f"Total New Facts extracted: {total_new_facts}")

    all_stored_facts = store.get_all_facts()
    print(f"Total Facts in Database:   {len(all_stored_facts)}")

    # Check cross-document candidate pairs
    print("\n" + "-" * 80)
    print("CROSS-DOCUMENT CANDIDATE PAIR DISCOVERY (Cosine Similarity >= 0.60):")
    print("-" * 80)

    # Gather document IDs in DB
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT document_id, filename, total_pages FROM documents")
    docs_in_db = cursor.fetchall()
    conn.close()

    total_pairs = 0
    seen_pairs = set()

    for doc_row in docs_in_db:
        d_id = doc_row["document_id"]
        candidates = store.find_candidate_pairs(target_doc_id=d_id, top_k_per_fact=2, threshold=0.60)
        for f1, f2, score in candidates:
            pair_key = tuple(sorted([f1.fact_id, f2.fact_id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            total_pairs += 1

            if total_pairs <= 10:  # Print top 10 previews
                print(f"Pair #{total_pairs} (Similarity: {score:.3f}):")
                print(f"  Doc A (p.{f1.page_number}): [{f1.subject}] {f1.predicate} = {f1.object_value} ({f1.period or 'N/A'})")
                print(f"  Doc B (p.{f2.page_number}): [{f2.subject}] {f2.predicate} = {f2.object_value} ({f2.period or 'N/A'})")
                print()

    print(f"Total Unique Cross-Document Candidate Pairs Found: {total_pairs}")
    print("=" * 80)

if __name__ == "__main__":
    main()
