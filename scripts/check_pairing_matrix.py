import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT d1.filename as fn1, d2.filename as fn2, count(*) as pair_count
    FROM facts f1
    JOIN documents d1 ON f1.document_id = d1.document_id
    JOIN facts f2 ON f1.fact_id < f2.fact_id
    JOIN documents d2 ON f2.document_id = d2.document_id
    GROUP BY d1.filename, d2.filename
""")
rows = cursor.fetchall()
print("FACT PAIRING MATRIX (All Combinations in DB):")
for r in rows:
    print(f"  {r['fn1']} <---> {r['fn2']}: {r['pair_count']} raw pairs")

conn.close()
