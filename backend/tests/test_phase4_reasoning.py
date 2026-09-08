import pytest
from app.models.fact import ExtractedFact
from app.models.relationship import RelationshipType, FactRelationship
from app.services.relationship_engine import RelationshipEngine
from app.services.fact_store import FactStore
from app.database import init_db

@pytest.fixture
def test_engine():
    return RelationshipEngine()

@pytest.fixture
def temp_store(tmp_path):
    db_file = str(tmp_path / "test_reasoning.db")
    init_db(db_file)
    return FactStore(db_path=db_file)

def test_rule_fast_path_corroboration(test_engine):
    """Verifies that identical numbers and periods are classified via rule fast-path with zero API calls."""
    fact_a = ExtractedFact(
        document_id="doc_pres",
        chunk_id="c1",
        page_number=5,
        fact_type="operational_metric",
        subject="Delhivery",
        predicate="net_working_capital_days",
        object_value="31 days",
        numeric_value=31.0,
        unit="days",
        period="FY24",
        scope="consolidated",
        verbatim_quote="Sharp YoY reduction in NWC days from 38 to 31 days in FY24",
        confidence=1.0,
        grounding_verified=True
    )

    fact_b = ExtractedFact(
        document_id="doc_ar",
        chunk_id="c2",
        page_number=8,
        fact_type="operational_metric",
        subject="Delhivery",
        predicate="net_working_capital_cycle_days",
        object_value="31 days",
        numeric_value=31.0,
        unit="days",
        period="FY24",
        scope="consolidated",
        verbatim_quote="Net working capital cycle was reduced to 31 days in FY24",
        confidence=1.0,
        grounding_verified=True
    )

    rel = test_engine.classify_pair(fact_a, fact_b, "Earnings Presentation", "Annual Report")
    assert rel.relationship == RelationshipType.CORROBORATES
    assert rel.detected_by == "rule_heuristic"
    assert rel.confidence >= 0.95

def test_llm_unit_scale_reconciliation(test_engine):
    """Verifies that ₹127 Cr vs ₹1,266 Mn is correctly reconciled due to Crore vs Million unit conversion."""
    fact_a = ExtractedFact(
        document_id="doc_pres",
        chunk_id="c1",
        page_number=5,
        fact_type="financial_metric",
        subject="Delhivery",
        predicate="ebitda",
        object_value="Rs. 127 Cr",
        numeric_value=127.0,
        unit="INR Crore",
        period="FY24",
        scope="consolidated",
        verbatim_quote="FY24 EBITDA increased to Rs. 127 Cr",
        confidence=1.0,
        grounding_verified=True
    )

    fact_b = ExtractedFact(
        document_id="doc_ar",
        chunk_id="c2",
        page_number=4,
        fact_type="financial_metric",
        subject="Delhivery",
        predicate="ebitda",
        object_value="₹1,266Mn",
        numeric_value=1266.0,
        unit="INR Million",
        period="FY24",
        scope="consolidated",
        verbatim_quote="EBITDA for FY24 stood at ₹1,266Mn",
        confidence=1.0,
        grounding_verified=True
    )

    rel = test_engine.classify_pair(fact_a, fact_b, "Earnings Presentation", "Annual Report")
    assert rel.relationship in [RelationshipType.RECONCILES, RelationshipType.CORROBORATES]
    assert rel.confidence >= 0.70
    assert any(term in (rel.explanation + str(rel.reconciliation_context)).lower() 
               for term in ["crore", "million", "conversion", "rounding", "unit", "scale", "127"])

def test_llm_direct_contradiction(test_engine):
    """Verifies that direct incompatible numbers for the same entity and period return 'contradicts'."""
    fact_a = ExtractedFact(
        document_id="doc_a",
        chunk_id="c1",
        page_number=1,
        fact_type="financial_metric",
        subject="Delhivery",
        predicate="revenue_from_operations",
        object_value="Rs. 8,142 Cr",
        numeric_value=8142.0,
        unit="INR Crore",
        period="FY24",
        scope="consolidated",
        verbatim_quote="FY24 revenue from operations was Rs. 8,142 Cr",
        confidence=1.0,
        grounding_verified=True
    )

    fact_b = ExtractedFact(
        document_id="doc_b",
        chunk_id="c2",
        page_number=10,
        fact_type="financial_metric",
        subject="Delhivery",
        predicate="revenue_from_operations",
        object_value="Rs. 9,850 Cr",
        numeric_value=9850.0,
        unit="INR Crore",
        period="FY24",
        scope="consolidated",
        verbatim_quote="FY24 revenue from operations was Rs. 9,850 Cr",
        confidence=1.0,
        grounding_verified=True
    )

    rel = test_engine.classify_pair(fact_a, fact_b, "Report Alpha", "Report Beta")
    assert rel.relationship == RelationshipType.CONTRADICTS
    assert rel.confidence >= 0.70

def test_relationship_persistence(temp_store):
    """Verifies storing and retrieving relationships from SQLite."""
    fact_a = ExtractedFact(
        document_id="d1",
        chunk_id="c1",
        page_number=1,
        fact_type="financial_metric",
        subject="Entity",
        predicate="metric_a",
        object_value="100",
        numeric_value=100.0,
        unit="USD",
        period="2024",
        verbatim_quote="Metric is 100",
        confidence=1.0
    )
    fact_b = ExtractedFact(
        document_id="d2",
        chunk_id="c2",
        page_number=2,
        fact_type="financial_metric",
        subject="Entity",
        predicate="metric_a",
        object_value="100",
        numeric_value=100.0,
        unit="USD",
        period="2024",
        verbatim_quote="Metric is 100",
        confidence=1.0
    )
    temp_store.save_facts([fact_a, fact_b])

    rel = FactRelationship(
        fact_a_id=fact_a.fact_id,
        fact_b_id=fact_b.fact_id,
        relationship=RelationshipType.CORROBORATES,
        confidence=0.99,
        explanation="Both state metric_a is 100",
        reconciliation_context=None,
        detected_by="test"
    )

    temp_store.save_relationship(rel)

    stored = temp_store.get_relationships()
    assert len(stored) == 1
    assert stored[0].relationship == RelationshipType.CORROBORATES
    assert stored[0].fact_a_id == fact_a.fact_id
    assert stored[0].fact_b_id == fact_b.fact_id
