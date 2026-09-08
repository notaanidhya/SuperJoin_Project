import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.fact import FactExtractionResponse
from app.models.schemas import DocumentChunk
from app.services.llm_client import GeminiClient
from app.services.fact_extractor import FactExtractor

print("Testing FactExtractor with gemini-3.8-flash...", flush=True)

chunk = DocumentChunk(
    document_id="test_doc",
    page_number=5,
    chunk_index=0,
    text="In FY24, Delhivery reported revenue from operations of Rs. 8,142 Cr, an increase of 13% YoY. EBITDA was Rs. 127 Cr.",
    char_start=0,
    char_end=120
)

# Temporarily test with gemini-3.8-flash
client = GeminiClient()
client.model = "gemini-3.8-flash"
extractor = FactExtractor(client=client)

facts = extractor.extract_facts_from_chunks([chunk])
print(f"Extracted {len(facts)} facts:", flush=True)
for f in facts:
    print(f"  [{f.subject}] {f.predicate} = {f.object_value} (grounded={f.grounding_verified}, quote='{f.verbatim_quote}')", flush=True)
