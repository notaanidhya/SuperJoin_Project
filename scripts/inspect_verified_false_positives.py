import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import get_connection
from app.services.grounding_validator import GroundingValidator
from app.utils.text_cleaning import normalize_unicode, clean_whitespace

conn = get_connection("data/fact_layer.db")
cursor = conn.cursor()
cursor.execute("""
    SELECT f.fact_id, f.subject, f.predicate, f.object_value, f.verbatim_quote, c.text as chunk_text
    FROM facts f
    JOIN document_chunks c ON f.chunk_id = c.chunk_id
    WHERE f.grounding_verified = 1
""")
rows = cursor.fetchall()
validator = GroundingValidator()

prefix_only_matches = []
normalized_matches = []

for r in rows:
    quote = r["verbatim_quote"]
    text = r["chunk_text"]
    if quote.lower() not in text.lower():
        # Check why it matched
        norm_q = clean_whitespace(normalize_unicode(quote)).lower()
        norm_t = clean_whitespace(normalize_unicode(text)).lower()
        if norm_q in norm_t:
            normalized_matches.append(r)
        else:
            prefix_only_matches.append(r)

print(f"Total checked: {len(rows)}")
print(f"Matched via unicode/whitespace normalization (Legitimate): {len(normalized_matches)}")
print(f"Matched ONLY via 25-char prefix fallback (Potential False Positives): {len(prefix_only_matches)}")

if prefix_only_matches:
    print("\nSample Prefix-Only Matches (first 5):")
    for p in prefix_only_matches[:5]:
        print(f"  [{p['subject']}] {p['predicate']} = {p['object_value']}")
        print(f"    Quote: '{p['verbatim_quote'][:80]}'")
        print(f"    Prefix[:25]: '{p['verbatim_quote'][:25]}'")
conn.close()
