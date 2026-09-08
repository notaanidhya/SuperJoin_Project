import sys
from pathlib import Path

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
from app.services.fact_store import FactStore

store = FactStore("data/fact_layer.db")

# Find candidate pairs for Delhivery Q4 Presentation against all other documents
target_doc_id = "55f771df0610a879"
pairs = store.find_candidate_pairs(target_doc_id=target_doc_id, top_k_per_fact=2, threshold=0.70)

print(f"Total High-Confidence Genuine Cross-Document Pairs (>= 0.70): {len(pairs)}")

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()

def get_filename(doc_id):
    cursor.execute("SELECT filename FROM documents WHERE document_id = ?", (doc_id,))
    row = cursor.fetchone()
    return row["filename"] if row else doc_id

seen = set()
count = 0
for f1, f2, score in pairs:
    key = tuple(sorted([f1.fact_id, f2.fact_id]))
    if key in seen:
        continue
    seen.add(key)
    count += 1
    fn1 = get_filename(f1.document_id)
    fn2 = get_filename(f2.document_id)
    if count <= 8:
        print(f"\n--- Candidate Pair #{count} (Score: {score:.3f}) ---")
        print(f"  [Doc 1: {fn1} p.{f1.page_number}] [{f1.subject}] {f1.predicate} = {f1.object_value} ({f1.period or 'N/A'})")
        print(f"  [Doc 2: {fn2} p.{f2.page_number}] [{f2.subject}] {f2.predicate} = {f2.object_value} ({f2.period or 'N/A'})")

conn.close()
