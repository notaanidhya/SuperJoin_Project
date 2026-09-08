import pdfplumber
from typing import List, Optional, Tuple, Dict, Any
from app.models.schemas import ExtractedTable
from app.utils.text_cleaning import clean_table_cell

class TableExtractor:
    """Extracts structured tables from PDF pages using pdfplumber and converts to Markdown."""

    def __init__(self, min_rows: int = 2, min_cols: int = 2):
        self.min_rows = min_rows
        self.min_cols = min_cols

    def extract_tables_from_page(self, plumber_page, page_number: int) -> List[ExtractedTable]:
        raw_tables = plumber_page.extract_tables()
        extracted: List[ExtractedTable] = []

        if not raw_tables:
            return extracted

        for table_data in raw_tables:
            if not table_data or len(table_data) < self.min_rows:
                continue

            cleaned_table = []
            for row in table_data:
                cleaned_row = [clean_table_cell(cell) for cell in row]
                if any(cleaned_row):
                    cleaned_table.append(cleaned_row)

            if len(cleaned_table) < self.min_rows:
                continue

            max_cols = max(len(r) for r in cleaned_table)
            if max_cols < self.min_cols:
                continue

            standardized = []
            for r in cleaned_table:
                if len(r) < max_cols:
                    r = r + [""] * (max_cols - len(r))
                standardized.append(r)

            headers = standardized[0]
            data_rows = standardized[1:]

            non_empty_headers = [h for h in headers if h.strip()]
            if not non_empty_headers:
                headers = [f"Col {i+1}" for i in range(max_cols)]
                data_rows = standardized

            markdown_repr = self._to_markdown(headers, data_rows)

            extracted.append(ExtractedTable(
                page_number=page_number,
                headers=headers,
                rows=data_rows,
                markdown_repr=markdown_repr
            ))

        return extracted

    def _to_markdown(self, headers: List[str], rows: List[List[str]]) -> str:
        header_line = "| " + " | ".join(headers) + " |"
        separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        row_lines = ["| " + " | ".join(row) + " |" for row in rows]
        return "\n".join([header_line, separator_line] + row_lines)
