import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.pdf_parser import PDFParser
from app.services.chunker import SemanticChunker

def inspect_pdf(filepath: str, max_pages: int = 5):
    print(f"=== Inspecting PDF: {filepath} (Pages 1 to {max_pages}) ===")
    parser = PDFParser(extract_tables=True)
    doc = parser.parse_document(filepath, max_pages=max_pages)
    
    print(f"Total Pages in Doc: {doc.total_pages}")
    print(f"Pages Processed: {len(doc.pages)}")
    
    total_tables = sum(len(p.tables) for p in doc.pages)
    print(f"Total Tables Detected: {total_tables}")
    
    chunker = SemanticChunker(target_chunk_chars=1200, overlap_chars=150)
    chunks = chunker.chunk_document(doc)
    print(f"Total Chunks Generated: {len(chunks)}\n")
    
    for i, chunk in enumerate(chunks[:6]):
        print(f"--- Chunk #{chunk.chunk_index} | Page {chunk.page_number} | IsTable: {chunk.is_table} | Section: {chunk.section_header} ---")
        print(f"Offsets: [{chunk.char_start}:{chunk.char_end}] | Words: {chunk.token_count}")
        # Print snippet
        snippet = chunk.text[:300] + ("..." if len(chunk.text) > 300 else "")
        print(snippet)
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    sample = "starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf"
    inspect_pdf(sample, max_pages=5)
