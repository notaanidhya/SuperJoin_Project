import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.pdf_parser import PDFParser
from app.services.chunker import SemanticChunker
from app.services.fact_extractor import FactExtractor

def run_extraction_demo(pdf_path: str, max_pages: int = 4):
    print("=" * 80)
    print(f"Fact Extraction & Grounding Demo on: {pdf_path}")
    print("=" * 80)

    # 1. Parse PDF
    parser = PDFParser(extract_tables=True)
    doc = parser.parse_document(pdf_path, max_pages=max_pages)
    print(f"[Phase 1] Parsed {len(doc.pages)} pages.")

    # 2. Chunk
    chunker = SemanticChunker(target_chunk_chars=1200, overlap_chars=150)
    chunks = chunker.chunk_document(doc)
    print(f"[Phase 1] Created {len(chunks)} chunks.")

    # 3. Extract facts from selected chunks
    extractor = FactExtractor()
    all_facts = []

    # Process first 3 substantive chunks
    selected_chunks = [c for c in chunks if len(c.text.strip()) > 100][:3]
    print(f"[Phase 2] Extracting facts from {len(selected_chunks)} candidate chunks using Gemini...")

    for c in selected_chunks:
        print(f"\n--> Processing Chunk #{c.chunk_index} (Page {c.page_number}, Section: {c.section_header})")
        facts = extractor.extract_facts_from_chunk(c)
        all_facts.extend(facts)
        print(f"    Extracted {len(facts)} facts.")

    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(all_facts)} Total Facts Extracted & Grounded")
    print("=" * 80)

    for i, f in enumerate(all_facts, 1):
        grounding_str = "[VERIFIED]" if f.grounding_verified else "[UNVERIFIED]"
        print(f"\nFact #{i} {grounding_str}")
        print(f"  Subject:     {f.subject}")
        print(f"  Predicate:   {f.predicate}")
        print(f"  Value:       {f.object_value} (numeric: {f.numeric_value}, unit: {f.unit})")
        print(f"  Period:      {f.period} | Scope: {f.scope}")
        print(f"  Confidence:  {f.confidence:.2f}")
        print(f"  Evidence:    '{f.verbatim_quote}'")

if __name__ == "__main__":
    sample = "starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf"
    run_extraction_demo(sample, max_pages=4)
