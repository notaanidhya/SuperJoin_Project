import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()
cursor.execute("""
    SELECT f.verbatim_quote, c.text as chunk_text
    FROM facts f
    JOIN document_chunks c ON f.chunk_id = c.chunk_id
    WHERE f.verbatim_quote LIKE 'Our part truckload tonnage%'
    LIMIT 1
""")
r = cursor.fetchone()
q = r["verbatim_quote"]
t = r["chunk_text"]
print("FULL QUOTE:")
print(repr(q))
print("\nWHERE DOES PREFIX APPEAR IN TEXT?")
idx = t.lower().find(q[:25].lower())
print("SNIPPET IN CHUNK TEXT:")
print(repr(t[idx:idx + len(q) + 30]))
conn.close()
