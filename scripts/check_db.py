import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()
cursor.execute("SELECT count(*) as cnt FROM facts")
print(f"Total facts in DB: {cursor.fetchone()['cnt']}")

cursor.execute("SELECT fact_id, page_number, subject, predicate, object_value, period, verbatim_quote FROM facts LIMIT 10")
for r in cursor.fetchall():
    print(f"p.{r['page_number']} | [{r['subject']}] {r['predicate']} = {r['object_value']} ({r['period']})")
    print(f"  Evidence: {r['verbatim_quote'][:80]}...")
conn.close()
