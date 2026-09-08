import sys
import hashlib
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection
from app.services.grounding_validator import GroundingValidator

def cleanup():
    db_path = "data/fact_layer.db"
    conn = get_connection(db_path)
    cursor = conn.cursor()

    print("=" * 80)
    print("DATABASE CLEANUP & RE-VALIDATION")
    print("=" * 80)

    # 1. Clean up duplicate / phantom documents
    cursor.execute("SELECT document_id, filename FROM documents")
    all_docs = cursor.fetchall()

    docs_by_fn = defaultdict(list)
    for d in all_docs:
        docs_by_fn[d["filename"]].append(d["document_id"])

    for filename, doc_ids in docs_by_fn.items():
        if len(doc_ids) > 1:
            # Deterministic canonical ID: sha256(filename)[:16]
            canonical_id = hashlib.sha256(filename.encode()).hexdigest()[:16]
            print(f"\n[Deduplicating] File: {filename} has {len(doc_ids)} IDs: {doc_ids}")
            print(f"  -> Canonical deterministic ID: {canonical_id}")

            # Ensure canonical document exists
            cursor.execute("SELECT total_pages, filepath FROM documents WHERE document_id IN ({})".format(
                ",".join("?" * len(doc_ids))
            ), doc_ids)
            doc_info = cursor.fetchone()
            total_pages = doc_info["total_pages"] if doc_info else 0
            filepath = doc_info["filepath"] if doc_info else ""

            cursor.execute("""
                INSERT OR REPLACE INTO documents (document_id, filename, filepath, total_pages, status)
                VALUES (?, ?, ?, ?, 'indexed')
            """, (canonical_id, filename, filepath, total_pages))

            # Re-point facts and chunks to canonical_id
            for old_id in doc_ids:
                if old_id == canonical_id:
                    continue
                cursor.execute("UPDATE facts SET document_id = ? WHERE document_id = ?", (canonical_id, old_id))
                cursor.execute("UPDATE document_chunks SET document_id = ? WHERE document_id = ?", (canonical_id, old_id))
                cursor.execute("DELETE FROM documents WHERE document_id = ?", (old_id,))
                print(f"  Merged old ID: {old_id} -> {canonical_id}")

    # Remove any empty documents without chunks or facts
    cursor.execute("""
        DELETE FROM documents 
        WHERE document_id NOT IN (SELECT DISTINCT document_id FROM facts)
          AND document_id NOT IN (SELECT DISTINCT document_id FROM document_chunks)
    """)
    conn.commit()

    # 2. Re-validate all facts with upgraded GroundingValidator
    validator = GroundingValidator()
    cursor.execute("""
        SELECT f.fact_id, f.verbatim_quote, c.text as chunk_text, f.grounding_verified
        FROM facts f
        JOIN document_chunks c ON f.chunk_id = c.chunk_id
    """)
    facts = cursor.fetchall()
    print(f"\n[Re-Validating Grounding] Auditing {len(facts)} facts with upgraded whitespace collapsing...")

    recovered = 0
    now_verified = 0
    now_unverified = 0

    for f in facts:
        is_grounded, offset = validator.verify_grounding(f["verbatim_quote"], f["chunk_text"])
        if is_grounded:
            now_verified += 1
            if not f["grounding_verified"]:
                recovered += 1
            cursor.execute("""
                UPDATE facts 
                SET grounding_verified = 1, char_offset_in_chunk = ? 
                WHERE fact_id = ?
            """, (offset, f["fact_id"]))
        else:
            now_unverified += 1
            cursor.execute("""
                UPDATE facts 
                SET grounding_verified = 0, char_offset_in_chunk = NULL 
                WHERE fact_id = ?
            """, (f["fact_id"],))

    conn.commit()
    conn.close()

    total = len(facts)
    print(f"  - Total Facts Re-checked: {total}")
    print(f"  - Recovered Grounded:     {recovered} previously unverified facts now verified!")
    print(f"  - Total Verified:         {now_verified} ({now_verified / total * 100:.1f}%)")
    print(f"  - Total Unverified:       {now_unverified} ({now_unverified / total * 100:.1f}%)")
    print("=" * 80)

if __name__ == "__main__":
    cleanup()
