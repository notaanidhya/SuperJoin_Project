import pytest
import os
from pathlib import Path
from app.services.pdf_parser import PDFParser
from app.services.chunker import SemanticChunker

DELHIVERY_SAMPLE = Path("starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf")
MACRO_SAMPLE = Path("starter-datasets/india-macroeconomy/01-india-economic-survey-2024-25-excerpt.pdf")

def test_delhivery_parsing_and_grounding():
    assert DELHIVERY_SAMPLE.exists(), f"File not found: {DELHIVERY_SAMPLE}"
    
    parser = PDFParser(extract_tables=True)
    # Parse first 10 pages for rapid verification
    parsed_doc = parser.parse_document(str(DELHIVERY_SAMPLE), max_pages=10)
    
    assert parsed_doc.total_pages == 27
    assert len(parsed_doc.pages) == 10
    
    # Check page numbers
    for idx, page in enumerate(parsed_doc.pages):
        assert page.page_number == idx + 1
        assert len(page.raw_text) > 0 or len(page.tables) > 0
    
    # Run Chunker
    chunker = SemanticChunker(target_chunk_chars=1200, overlap_chars=150)
    chunks = chunker.chunk_document(parsed_doc)
    
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.page_number >= 1
        assert chunk.page_number <= 10
        assert len(chunk.text.strip()) > 0
        assert chunk.token_count > 0
        
        # Grounding check: offsets within bounds
        assert chunk.char_start >= 0
        assert chunk.char_end >= chunk.char_start

def test_macroeconomy_tables_and_sections():
    assert MACRO_SAMPLE.exists(), f"File not found: {MACRO_SAMPLE}"
    
    parser = PDFParser(extract_tables=True)
    # Parse first 5 pages of Economic survey
    parsed_doc = parser.parse_document(str(MACRO_SAMPLE), max_pages=5)
    
    assert parsed_doc.total_pages == 89
    assert len(parsed_doc.pages) == 5
    
    chunker = SemanticChunker(target_chunk_chars=1200, overlap_chars=150)
    chunks = chunker.chunk_document(parsed_doc)
    assert len(chunks) > 0

    # If any table is extracted, verify markdown structure
    table_chunks = [c for c in chunks if c.is_table]
    for tc in table_chunks:
        assert "### [TABLE]" in tc.text
        assert "|" in tc.text
        assert "---" in tc.text

if __name__ == "__main__":
    pytest.main(["-v", __file__])
