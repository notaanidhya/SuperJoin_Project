import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.schemas import DocumentChunk
from app.services.llm_client import GeminiClient
from app.services.fact_extractor import FactExtractor

chunk = DocumentChunk(
    document_id="test_doc",
    page_number=5,
    chunk_index=0,
    text="In FY24, Delhivery reported revenue from operations of Rs. 8,142 Cr, an increase of 13% YoY. EBITDA was Rs. 127 Cr.",
    char_start=0,
    char_end=120
)

client = GeminiClient()
for model_name in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.7-flash"]:
    print(f"\n--- Testing {model_name} ---", flush=True)
    client.model = model_name
    extractor = FactExtractor(client=client)
    try:
        facts = extractor.extract_facts_from_chunks([chunk])
        print(f"SUCCESS with {model_name}: {len(facts)} facts extracted (all grounded: {all(f.grounding_verified for f in facts)})", flush=True)
        for f in facts:
            print(f"  [{f.subject}] {f.predicate} = {f.object_value}", flush=True)
        break
    except Exception as e:
        print(f"FAILED with {model_name}: {e}", flush=True)
