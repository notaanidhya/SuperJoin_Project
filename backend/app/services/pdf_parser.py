import fitz
import pdfplumber
from pathlib import Path
from typing import List, Optional, Dict, Any
from app.models.schemas import ParsedDocument, ParsedPage, ExtractedTable
from app.services.table_extractor import TableExtractor
from app.utils.text_cleaning import clean_page_text

class PDFParser:
    """High-speed PDF parser combining PyMuPDF for text/sections and pdfplumber for tables."""

    def __init__(self, extract_tables: bool = True):
        self.extract_tables = extract_tables
        self.table_extractor = TableExtractor()

    def parse_document(self, filepath: str, max_pages: Optional[int] = None) -> ParsedDocument:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {filepath}")

        doc = fitz.open(filepath)
        total_pages = len(doc)
        pages_to_process = min(total_pages, max_pages) if max_pages else total_pages

        parsed_pages: List[ParsedPage] = []
        current_section = "Overview"

        plumber_doc = pdfplumber.open(filepath) if self.extract_tables else None

        try:
            for page_idx in range(pages_to_process):
                page_num = page_idx + 1
                page = doc[page_idx]

                text_blocks = page.get_text("blocks")
                page_text_pieces = []
                detected_sections = []

                page_rect = page.rect
                header_cutoff = page_rect.height * 0.05
                footer_cutoff = page_rect.height * 0.95

                for block in text_blocks:
                    if block[6] != 0:
                        continue

                    y0, y1, text = block[1], block[3], block[4].strip()
                    if not text:
                        continue

                    if y1 <= header_cutoff or y0 >= footer_cutoff:
                        continue

                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    if len(lines) == 1 and len(lines[0]) < 80:
                        first_line = lines[0]
                        if first_line.isupper() or any(first_line.startswith(p) for p in ["CHAPTER", "SECTION", "TABLE", "NOTE", "PART"]):
                            current_section = first_line
                            detected_sections.append(current_section)

                    page_text_pieces.append(text)

                raw_text = "\n\n".join(page_text_pieces)
                cleaned_text = clean_page_text(raw_text)

                tables: List[ExtractedTable] = []
                if plumber_doc and page_idx < len(plumber_doc.pages):
                    plumber_page = plumber_doc.pages[page_idx]
                    tables = self.table_extractor.extract_tables_from_page(plumber_page, page_num)

                parsed_pages.append(ParsedPage(
                    page_number=page_num,
                    raw_text=raw_text,
                    cleaned_text=cleaned_text,
                    detected_sections=detected_sections or [current_section],
                    tables=tables
                ))

        finally:
            doc.close()
            if plumber_doc:
                plumber_doc.close()

        import hashlib
        doc_id = hashlib.sha256(path.name.encode()).hexdigest()[:16]

        return ParsedDocument(
            document_id=doc_id,
            filename=path.name,
            filepath=str(path.resolve()),
            total_pages=total_pages,
            pages=parsed_pages,
            metadata={
                "processed_pages": pages_to_process,
                "has_tables": any(len(p.tables) > 0 for p in parsed_pages)
            }
        )
