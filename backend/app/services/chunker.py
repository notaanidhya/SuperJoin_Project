import re
from typing import List
from app.models.schemas import ParsedDocument, DocumentChunk

class SemanticChunker:
    """Splits ParsedDocument into grounded chunks with precise character offsets and page references."""

    def __init__(self, target_chunk_chars: int = 1500, overlap_chars: int = 200):
        self.target_chunk_chars = target_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk_document(self, doc: ParsedDocument) -> List[DocumentChunk]:
        all_chunks: List[DocumentChunk] = []
        chunk_idx = 0

        for page in doc.pages:
            section_header = page.detected_sections[0] if page.detected_sections else "General"

            # 1. First, create dedicated chunks for extracted tables
            for table in page.tables:
                table_text = f"### [TABLE] Page {page.page_number} - {section_header}\n\n{table.markdown_repr}"
                all_chunks.append(DocumentChunk(
                    chunk_id=f"{doc.document_id}_p{page.page_number}_c{chunk_idx}",
                    document_id=doc.document_id,
                    page_number=page.page_number,
                    chunk_index=chunk_idx,
                    text=table_text,
                    section_header=section_header,
                    is_table=True,
                    table_metadata={
                        "headers": table.headers,
                        "num_rows": len(table.rows)
                    },
                    char_start=0,
                    char_end=len(table.markdown_repr),
                    token_count=len(table_text.split())
                ))
                chunk_idx += 1

            # 2. Chunk narrative text with exact page offsets
            page_text = page.cleaned_text
            if not page_text:
                continue

            paragraphs = [p.strip() for p in re.split(r"\n\n+", page_text) if p.strip()]
            if not paragraphs:
                continue

            current_chunk_paragraphs = []
            current_len = 0
            current_start_offset = 0

            for para in paragraphs:
                para_len = len(para)
                if current_len + para_len > self.target_chunk_chars and current_chunk_paragraphs:
                    chunk_text = "\n\n".join(current_chunk_paragraphs)
                    chunk_start = page_text.find(current_chunk_paragraphs[0], current_start_offset)
                    if chunk_start == -1:
                        chunk_start = current_start_offset
                    chunk_end = chunk_start + len(chunk_text)

                    all_chunks.append(DocumentChunk(
                        chunk_id=f"{doc.document_id}_p{page.page_number}_c{chunk_idx}",
                        document_id=doc.document_id,
                        page_number=page.page_number,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        section_header=section_header,
                        is_table=False,
                        char_start=chunk_start,
                        char_end=chunk_end,
                        token_count=len(chunk_text.split())
                    ))
                    chunk_idx += 1

                    overlap_paras = []
                    overlap_len = 0
                    for p_rev in reversed(current_chunk_paragraphs):
                        if overlap_len + len(p_rev) <= self.overlap_chars:
                            overlap_paras.insert(0, p_rev)
                            overlap_len += len(p_rev)
                        else:
                            break

                    current_chunk_paragraphs = overlap_paras + [para]
                    current_len = sum(len(p) for p in current_chunk_paragraphs)
                    current_start_offset = chunk_start
                else:
                    current_chunk_paragraphs.append(para)
                    current_len += para_len

            if current_chunk_paragraphs:
                chunk_text = "\n\n".join(current_chunk_paragraphs)
                chunk_start = page_text.find(current_chunk_paragraphs[0], current_start_offset)
                if chunk_start == -1:
                    chunk_start = current_start_offset
                chunk_end = chunk_start + len(chunk_text)

                all_chunks.append(DocumentChunk(
                    chunk_id=f"{doc.document_id}_p{page.page_number}_c{chunk_idx}",
                    document_id=doc.document_id,
                    page_number=page.page_number,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    section_header=section_header,
                    is_table=False,
                    char_start=chunk_start,
                    char_end=chunk_end,
                    token_count=len(chunk_text.split())
                ))
                chunk_idx += 1

        doc.chunks = all_chunks
        return all_chunks
