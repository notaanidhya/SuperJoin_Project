import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection
from app.services.grounding_validator import GroundingValidator

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()
cursor.execute("""
    SELECT f.fact_id, f.chunk_id, f.verbatim_quote, c.text as chunk_text
    FROM facts f
    JOIN document_chunks c ON f.chunk_id = c.chunk_id
    WHERE f.grounding_verified = 0
    LIMIT 3
""")
rows = cursor.fetchall()
validator = GroundingValidator()

for r in rows:
    quote = r["verbatim_quote"]
    text = r["chunk_text"]
    print("--- QUOTE ---")
    print(repr(quote))
    print("--- CHUNK TEXT SAMPLE ---")
    print(repr(text[:300]))
    is_grounded, offset = validator.verify_grounding(quote, text)
    print(f"Validator result: {is_grounded}, offset: {offset}")
    # Let's test if normalized whitespace matches
    import re
    q_words = re.findall(r'\S+', quote)
    t_words = re.findall(r'\S+', text)
    print(f"Quote words: {q_words}")
    print(f"Are all quote words in text? {all(w in text for w in q_words)}")
conn.close()
