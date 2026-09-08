import sys
import json
from pathlib import Path
from collections import defaultdict, Counter

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

def audit():
    conn = get_connection("data/fact_layer.db")
    cursor = conn.cursor()

    print("=" * 80)
    print("DATABASE AUDIT & ANOMALY DETECTION REPORT")
    print("=" * 80)

    # 1. Documents in DB
    cursor.execute("""
        SELECT d.document_id, d.filename, d.total_pages, COUNT(f.fact_id) as fact_count
        FROM documents d
        LEFT JOIN facts f ON d.document_id = f.document_id
        GROUP BY d.document_id
    """)
    docs = cursor.fetchall()
    print(f"\n[1] REGISTERED DOCUMENTS ({len(docs)} found):")
    for d in docs:
        print(f"  - ID: {d['document_id'][:12]} | File: {d['filename']} | Pages: {d['total_pages']} | Facts: {d['fact_count']}")

    # 2. Check for Duplicate Filenames / Phantom Documents
    filenames = [d['filename'] for d in docs]
    fn_counts = Counter(filenames)
    duplicate_docs = [fn for fn, count in fn_counts.items() if count > 1]
    if duplicate_docs:
        print(f"\n[!] ANOMALY DETECTED: Multiple document entries for identical filenames:")
        for fn in duplicate_docs:
            print(f"      Filename: {fn}")
    else:
        print("\n[✓] Document uniqueness: All document filenames have 1:1 mapping.")

    # 3. Grounding Verification Rate
    cursor.execute("SELECT COUNT(*) as total, SUM(grounding_verified) as verified FROM facts")
    row = cursor.fetchone()
    total_facts = row['total']
    verified_facts = row['verified'] or 0
    unverified_facts = total_facts - verified_facts
    v_rate = (verified_facts / total_facts * 100) if total_facts else 0
    print(f"\n[2] GROUNDING INTEGRITY:")
    print(f"  - Total Facts:      {total_facts}")
    print(f"  - Verified Grounded: {verified_facts} ({v_rate:.1f}%)")
    print(f"  - Unverified Facts:  {unverified_facts} ({100 - v_rate:.1f}%)")

    # Sample unverified facts to inspect root cause
    if unverified_facts > 0:
        print("\n  Sample Unverified Facts (First 5):")
        cursor.execute("""
            SELECT f.fact_id, f.document_id, f.chunk_id, f.page_number, f.subject, f.predicate, 
                   f.object_value, f.verbatim_quote, c.text as chunk_text
            FROM facts f
            LEFT JOIN document_chunks c ON f.chunk_id = c.chunk_id
            WHERE f.grounding_verified = 0
            LIMIT 5
        """)
        unverified_samples = cursor.fetchall()
        for i, u in enumerate(unverified_samples, 1):
            quote = u['verbatim_quote']
            chunk_txt = u['chunk_text'] or ""
            print(f"    {i}. [{u['subject']}] {u['predicate']} = {u['object_value']} (p.{u['page_number']})")
            print(f"       Quote: '{quote[:80]}'")
            print(f"       In Assigned Chunk? {quote in chunk_txt}")
            # Check if quote is in ANY chunk of the document (leakage check)
            cursor.execute("SELECT chunk_id, page_number FROM document_chunks WHERE document_id = ? AND text LIKE ?", 
                           (u['document_id'], f"%{quote[:30]}%"))
            peer_chunk = cursor.fetchone()
            if peer_chunk and peer_chunk['chunk_id'] != u['chunk_id']:
                print(f"       [!] CROSS-CHUNK LEAKAGE: Quote found in different chunk #{peer_chunk['chunk_id']} (p.{peer_chunk['page_number']})!")
            elif not peer_chunk:
                print(f"       [!] HALLUCINATED/PARAPHRASED QUOTE: Quote fragment not found in document text.")

    # 4. Cross-Document Candidate Pair Quality & Self-Document Leakage
    print("\n[3] CROSS-DOCUMENT PAIR INTEGRITY & DATA LEAKAGE:")
    cursor.execute("""
        SELECT f1.document_id as doc1_id, d1.filename as fn1, f1.fact_id as fid1, f1.subject as s1, f1.predicate as p1, f1.object_value as v1,
               f2.document_id as doc2_id, d2.filename as fn2, f2.fact_id as fid2, f2.subject as s2, f2.predicate as p2, f2.object_value as v2
        FROM facts f1
        JOIN documents d1 ON f1.document_id = d1.document_id
        JOIN facts f2 ON f1.fact_id < f2.fact_id
        JOIN documents d2 ON f2.document_id = d2.document_id
        WHERE d1.filename = d2.filename AND f1.document_id != f2.document_id
    """)
    same_file_cross_doc_pairs = cursor.fetchall()
    if same_file_cross_doc_pairs:
        print(f"  [!] CRITICAL DATA LEAKAGE: {len(same_file_cross_doc_pairs)} pairs compare the SAME PDF under different document_ids!")
        print(f"      Example: {same_file_cross_doc_pairs[0]['fn1']} paired against itself!")
    else:
        print("  [✓] Zero same-file phantom pairs across different document IDs.")

    # 5. Numerical Parsing Anomalies
    print("\n[4] NUMERICAL PARSING & SCHEMA ANOMALIES:")
    cursor.execute("""
        SELECT COUNT(*) as count FROM facts 
        WHERE numeric_value IS NULL 
          AND (object_value GLOB '*[0-9]*') 
          AND fact_type IN ('financial_metric', 'operational_metric', 'macroeconomic_indicator')
    """)
    num_missing = cursor.fetchone()['count']
    print(f"  - Numerical facts with missing parsed float: {num_missing}")

    # Check for unit inconsistencies
    cursor.execute("SELECT unit, COUNT(*) as cnt FROM facts WHERE unit IS NOT NULL GROUP BY unit ORDER BY cnt DESC LIMIT 10")
    print("  - Top 10 Units in DB:")
    for u in cursor.fetchall():
        print(f"      {u['unit']}: {u['cnt']}")

    # Check confidence distribution
    cursor.execute("SELECT MIN(confidence), AVG(confidence), MAX(confidence) FROM facts")
    c_min, c_avg, c_max = cursor.fetchone()
    print(f"  - Confidence: Min={c_min:.2f}, Avg={c_avg:.2f}, Max={c_max:.2f}")

    conn.close()

if __name__ == "__main__":
    audit()
