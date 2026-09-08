import pytest
from app.models.schemas import DocumentChunk
from app.services.grounding_validator import GroundingValidator
from app.services.fact_extractor import FactExtractor

def test_grounding_validator_unit():
    chunk_text = "Delhivery reported revenue from operations of INR 8,109 Crore in FY24, representing 13% YoY growth."
    
    # Exact match
    valid, offset = GroundingValidator.verify_grounding("revenue from operations of INR 8,109 Crore", chunk_text)
    assert valid is True
    assert offset >= 0
    
    # Case variation & whitespace variation
    valid, offset = GroundingValidator.verify_grounding("REVENUE FROM OPERATIONS OF INR 8,109 CRORE", chunk_text)
    assert valid is True
    
    # Hallucinated quote
    valid, offset = GroundingValidator.verify_grounding("Delhivery acquired FedEx for 10 billion dollars", chunk_text)
    assert valid is False
    assert offset is None

def test_fact_extraction_live():
    chunk = DocumentChunk(
        document_id="test-doc-123",
        page_number=1,
        chunk_index=0,
        section_header="Corporate Details",
        text="Delhivery Limited was incorporated in 2011. The company reported full year revenue of INR 8,109 Crore for FY2023-24 with adjusted EBITDA of INR 127 Crore.",
        char_start=0,
        char_end=150,
        token_count=30
    )
    
    extractor = FactExtractor()
    facts = extractor.extract_facts_from_chunk(chunk)
    
    assert len(facts) > 0, "Expected at least one fact to be extracted from test chunk"
    
    for f in facts:
        assert f.subject.lower() in ["delhivery", "delhivery limited"]
        assert f.confidence >= 0.6
        assert len(f.verbatim_quote) > 0
        # Critical test: Grounding MUST be verified
        assert f.grounding_verified is True, f"Unverified quote extracted: {f.verbatim_quote}"
