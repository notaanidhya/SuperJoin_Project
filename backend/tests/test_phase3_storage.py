import pytest
import tempfile
import os
from pathlib import Path
from app.database import init_db
from app.services.fact_store import FactStore
from app.models.schemas import ParsedDocument, DocumentChunk
from app.models.fact import ExtractedFact

@pytest.fixture
def temp_store(tmp_path):
    db_path = str(tmp_path / "test_fact_layer.db")
    init_db(db_path)
    return FactStore(db_path=db_path)

def test_document_and_facts_persistence(temp_store):
    doc = ParsedDocument(
        document_id="doc-101",
        filename="delhivery_q4.pdf",
        filepath="/path/delhivery_q4.pdf",
        total_pages=5,
        chunks=[
            DocumentChunk(
                chunk_id="chk-1",
                document_id="doc-101",
                page_number=1,
                chunk_index=0,
                text="Delhivery BSE Scrip Code: 543529",
                char_start=0,
                char_end=32
            )
        ]
    )
    temp_store.save_document(doc)

    facts = [
        ExtractedFact(
            fact_id="f-1",
            document_id="doc-101",
            chunk_id="chk-1",
            page_number=1,
            fact_type="corporate_governance",
            subject="Delhivery Limited",
            predicate="bse_scrip_code",
            object_value="543529",
            numeric_value=543529.0,
            verbatim_quote="Scrip Code: 543529",
            confidence=1.0,
            grounding_verified=True
        ),
        ExtractedFact(
            fact_id="f-2",
            document_id="doc-101",
            chunk_id="chk-1",
            page_number=1,
            fact_type="corporate_governance",
            subject="Madhulika Rawat",
            predicate="designation",
            object_value="Company Secretary and Compliance Officer",
            verbatim_quote="Company Secretary & Compliance Officer",
            confidence=0.95,
            grounding_verified=True
        )
    ]
    temp_store.save_facts(facts)

    retrieved = temp_store.get_facts_by_document("doc-101")
    assert len(retrieved) == 2
    assert retrieved[0].fact_id == "f-1"
    assert retrieved[0].numeric_value == 543529.0
    assert retrieved[1].subject == "Madhulika Rawat"

def test_semantic_vector_search(temp_store):
    facts = [
        ExtractedFact(
            fact_id="f-rev",
            document_id="doc-1",
            chunk_id="c-1",
            page_number=2,
            fact_type="financial_metric",
            subject="Delhivery Limited",
            predicate="annual_revenue",
            object_value="INR 8,109 Crore",
            numeric_value=8109.0,
            unit="INR Crore",
            period="FY24",
            verbatim_quote="revenue of INR 8,109 Crore in FY24",
            confidence=0.98,
            grounding_verified=True
        ),
        ExtractedFact(
            fact_id="f-kmp",
            document_id="doc-1",
            chunk_id="c-1",
            page_number=1,
            fact_type="corporate_governance",
            subject="Madhulika Rawat",
            predicate="company_secretary_and_compliance_officer",
            object_value="Madhulika Rawat",
            verbatim_quote="Madhulika Rawat, Company Secretary",
            confidence=0.95,
            grounding_verified=True
        )
    ]
    temp_store.save_facts(facts)

    # Search for compliance officer
    results = temp_store.search_similar_facts("Who is the company secretary or compliance head?", top_k=2)
    assert len(results) == 2
    top_fact, score = results[0]
    assert top_fact.fact_id == "f-kmp"
    assert score > 0.60

    # Search for revenue
    results_rev = temp_store.search_similar_facts("Delhivery annual operations revenue", top_k=2)
    assert results_rev[0][0].fact_id == "f-rev"
    assert results_rev[0][1] > 0.45

def test_cross_document_candidate_pairing(temp_store):
    # Doc A has annual revenue
    fact_a = ExtractedFact(
        fact_id="f-docA-rev",
        document_id="doc-A",
        chunk_id="c-a",
        page_number=5,
        fact_type="financial_metric",
        subject="Delhivery",
        predicate="revenue_from_operations",
        object_value="8,109 Cr",
        numeric_value=8109.0,
        period="FY24",
        verbatim_quote="revenue from operations 8,109 Cr",
        confidence=0.95,
        grounding_verified=True
    )
    # Doc B has full year revenue for same entity & period
    fact_b = ExtractedFact(
        fact_id="f-docB-rev",
        document_id="doc-B",
        chunk_id="c-b",
        page_number=12,
        fact_type="financial_metric",
        subject="Delhivery",
        predicate="full_year_revenue",
        object_value="8,109 Cr",
        numeric_value=8109.0,
        period="FY2023-24",
        verbatim_quote="full year revenue 8,109 Cr",
        confidence=0.95,
        grounding_verified=True
    )
    # Doc B has unrelated fact
    fact_b_unrelated = ExtractedFact(
        fact_id="f-docB-rbi",
        document_id="doc-B",
        chunk_id="c-b2",
        page_number=1,
        fact_type="macroeconomic_indicator",
        subject="Reserve Bank of India",
        predicate="policy_repo_rate",
        object_value="6.50%",
        numeric_value=6.5,
        period="2024",
        verbatim_quote="policy repo rate 6.50%",
        confidence=0.95,
        grounding_verified=True
    )

    temp_store.save_facts([fact_a, fact_b, fact_b_unrelated])

    # Find candidate pairs for Doc B against existing facts (Doc A)
    pairs = temp_store.find_candidate_pairs(target_doc_id="doc-B", threshold=0.70)
    
    assert len(pairs) >= 1
    # Verify the top pair links fact_b (Doc B) to fact_a (Doc A)
    matched_target_ids = [p[0].fact_id for p in pairs]
    matched_other_ids = [p[1].fact_id for p in pairs]
    
    assert "f-docB-rev" in matched_target_ids
    assert "f-docA-rev" in matched_other_ids
