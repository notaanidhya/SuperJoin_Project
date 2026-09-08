import logging
from typing import List, Optional
from app.models.schemas import DocumentChunk
from app.models.fact import ExtractedFact, FactExtractionResponse, RawExtractedFact
from app.services.llm_client import GeminiClient
from app.services.grounding_validator import GroundingValidator
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are an expert fact extraction engine. Your task is to extract atomic, verifiable facts "
    "(numerical, financial, operational, macroeconomic, or corporate governance) from the provided document chunks.\n\n"
    "CRITICAL RULES:\n"
    "1. ATOMIC FACTS: Each fact must represent a single, clear claim with one subject, one predicate, and one value.\n"
    "2. SOURCE CHUNK INDEX: Set source_chunk_index to the 0-indexed integer corresponding to the [CHUNK <index>] block from which the fact was extracted.\n"
    "3. VERBATIM QUOTE: The verbatim_quote MUST be an EXACT literal substring copied directly from that specific source chunk's text. Never paraphrase, summarize, or alter punctuation in the quote.\n"
    "4. NUMERICAL PRECISION: If the fact contains a number, extract the float into numeric_value and the unit into unit (e.g. INR Crore, %, million).\n"
    "5. TEMPORAL & SCOPE ANCHORING: Always extract the exact period (e.g. FY24, Q4 FY24, 2024-25) and scope (e.g. consolidated, standalone) if present.\n"
    "6. SIGNAL OVER NOISE: Extract verifiable substantive claims. Do not extract generic forward-looking disclaimers, copyright notices, or vague qualitative phrases."
)

class FactExtractor:
    """Extracts structured, grounded facts from DocumentChunks using Gemini."""

    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient()
        self.validator = GroundingValidator()

    def extract_facts_from_chunk(self, chunk: DocumentChunk) -> List[ExtractedFact]:
        """Extract facts from a single chunk (backwards compatible)."""
        return self.extract_facts_from_chunks([chunk])

    def extract_facts_from_chunks(self, chunks: List[DocumentChunk]) -> List[ExtractedFact]:
        """Extract facts from a batch of chunks in a single LLM call for high throughput."""
        valid_chunks = [c for c in chunks if c.text and len(c.text.strip()) >= 30]
        if not valid_chunks:
            return []

        # Construct multi-chunk prompt
        blocks = []
        for idx, chunk in enumerate(valid_chunks):
            content_type = "Table" if chunk.is_table else "Narrative Text"
            section = chunk.section_header if chunk.section_header else "General"
            blocks.append(
                f"[CHUNK {idx}]\n"
                f"Page: {chunk.page_number} | Section: {section} | Type: {content_type}\n"
                f"Text:\n{chunk.text}\n"
            )

        prompt = (
            "Extract all verifiable atomic facts from each chunk below. "
            "Make sure to attribute each fact to its source_chunk_index (0, 1, ...).\n\n"
            + "\n".join(blocks)
        )

        try:
            res: FactExtractionResponse = self.client.generate_structured(
                prompt=prompt,
                response_schema=FactExtractionResponse,
                system_instruction=SYSTEM_INSTRUCTION
            )
        except Exception as e:
            chunk_summary = ", ".join([f"p{c.page_number}#c{c.chunk_index}" for c in valid_chunks])
            logger.error(f"[FactExtractor] Batch LLM call failed for chunks [{chunk_summary}]: {type(e).__name__}: {e}")
            return []

        extracted_facts: List[ExtractedFact] = []
        for raw in res.facts:
            if raw.confidence < settings.confidence_threshold:
                continue

            # Resolve source chunk
            chunk_idx = raw.source_chunk_index
            if chunk_idx < 0 or chunk_idx >= len(valid_chunks):
                # Fallback search across valid_chunks for the quote
                matched_idx = 0
                for i, c in enumerate(valid_chunks):
                    if raw.verbatim_quote in c.text:
                        matched_idx = i
                        break
                chunk_idx = matched_idx

            target_chunk = valid_chunks[chunk_idx]
            is_grounded, offset = self.validator.verify_grounding(raw.verbatim_quote, target_chunk.text)

            # If not grounded in designated chunk, check peer chunks in the batch in case LLM misattributed index
            if not is_grounded:
                for alt_idx, alt_chunk in enumerate(valid_chunks):
                    if alt_idx == chunk_idx:
                        continue
                    alt_grounded, alt_offset = self.validator.verify_grounding(raw.verbatim_quote, alt_chunk.text)
                    if alt_grounded:
                        target_chunk = alt_chunk
                        is_grounded = True
                        offset = alt_offset
                        break

            fact = ExtractedFact(
                document_id=target_chunk.document_id,
                chunk_id=target_chunk.chunk_id,
                page_number=target_chunk.page_number,
                section_header=target_chunk.section_header,
                fact_type=raw.fact_type,
                subject=raw.subject,
                predicate=raw.predicate,
                object_value=raw.object_value,
                numeric_value=raw.numeric_value,
                unit=raw.unit,
                period=raw.period,
                scope=raw.scope,
                verbatim_quote=raw.verbatim_quote,
                confidence=raw.confidence,
                qualifiers=raw.qualifiers,
                grounding_verified=is_grounded,
                char_offset_in_chunk=offset
            )
            extracted_facts.append(fact)

        return extracted_facts
