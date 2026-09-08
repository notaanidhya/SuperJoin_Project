from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
import uuid

class GroundingEvidence(BaseModel):
    page_number: int = Field(..., description='1-indexed page number where the fact appears')
    char_start: int = Field(..., description='Start character offset in page text')
    char_end: int = Field(..., description='End character offset in page text')
    section_header: Optional[str] = Field(None, description='Section breadcrumb or header')
    verbatim_quote: str = Field(..., description='Exact verbatim quote extracted from the document')
    context_window: Optional[str] = Field(None, description='Surrounding text context for verification')

class ExtractedTable(BaseModel):
    table_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    page_number: int
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    markdown_repr: str = Field(..., description='Clean Markdown representation of the table')
    bbox: Optional[Tuple[float, float, float, float]] = None

class DocumentChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str
    page_number: int
    chunk_index: int
    text: str
    section_header: Optional[str] = None
    is_table: bool = False
    table_metadata: Optional[Dict[str, Any]] = None
    char_start: int = 0
    char_end: int = 0
    token_count: int = 0

class ParsedPage(BaseModel):
    page_number: int
    raw_text: str
    cleaned_text: str
    detected_sections: List[str] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)

class ParsedDocument(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    filepath: str
    total_pages: int
    pages: List[ParsedPage] = Field(default_factory=list)
    chunks: List[DocumentChunk] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
