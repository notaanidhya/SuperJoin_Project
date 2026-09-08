import sys
from pathlib import Path
from collections import defaultdict

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()

# Check: Does any fact have a chunk that belongs to a different document?
cursor.execute("""
    SELECT f.fact_id, f.document_id as fact_doc_id, c.document_id as chunk_doc_id, 
           d.filename, f.verbatim_quote
    FROM facts f
    JOIN document_chunks c ON f.chunk_id = c.chunk_id
    JOIN documents d ON f.document_id = d.document_id
    WHERE f.document_id != c.document_id
""")
mismatched_chunks = cursor.fetchall()
print(f"Mismatched Fact-to-Chunk document IDs: {len(mismatched_chunks)}")

# Check: Does any fact have a chunk whose text doesn't contain the quote words?
cursor.execute("""
    SELECT f.fact_id, d.filename, f.page_number, f.verbatim_quote, c.text as chunk_text
    FROM facts f
    JOIN document_chunks c ON f.chunk_id = c.chunk_id
    JOIN documents d ON f.document_id = d.document_id
    WHERE f.grounding_verified = 1
""")
verified = cursor.fetchall()
print(f"Total Verified Facts checked: {len(verified)}")
corrupted_verified = 0
for v in verified:
    if v["verbatim_quote"] not in v["chunk_text"]:
        # Check if case-insensitive or whitespace
        if v["verbatim_quote"].lower() not in v["chunk_text"].lower():
            corrupted_verified += 1

print(f"False Positives in Verified Facts (quote not even case-insensitively in chunk): {corrupted_verified}")
conn.close()
