import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_api_stats():
    """Verify stats endpoint returns valid aggregate knowledge layer metrics."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_documents" in data
    assert "total_facts" in data
    assert "grounding_rate_percent" in data
    assert "total_relationships" in data
    assert data["total_documents"] >= 3
    assert data["total_facts"] >= 500
    assert data["grounding_rate_percent"] >= 90.0

def test_api_documents_list():
    """Verify document list endpoint returns ingested documents."""
    response = client.get("/api/documents")
    assert response.status_code == 200
    docs = response.json()
    assert isinstance(docs, list)
    assert len(docs) >= 3
    first = docs[0]
    assert "filename" in first
    assert "fact_count" in first
    assert "grounding_rate" in first

def test_api_facts_list_and_filter():
    """Verify fact listing, search filter, and pagination."""
    response = client.get("/api/facts?limit=10&grounding_verified=true")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) <= 10
    for item in data["items"]:
        assert item["grounding_verified"] is True
        assert item["verbatim_quote"] is not None

def test_api_fact_detail_with_chunk():
    """Verify individual fact retrieval includes source chunk text and character offset."""
    list_res = client.get("/api/facts?limit=1")
    fact_id = list_res.json()["items"][0]["fact_id"]

    response = client.get(f"/api/facts/{fact_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["fact_id"] == fact_id
    assert "chunk_text" in detail
    assert "verbatim_quote" in detail

def test_api_relationships_list():
    """Verify relationships endpoint returns classified pairs with explanations."""
    response = client.get("/api/relationships")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    rel = data["items"][0]
    assert "relationship" in rel
    assert "explanation" in rel
    assert "fact_a" in rel
    assert "fact_b" in rel

def test_api_showcase_canonical():
    """Verify the 4 canonical showcase cases are available via API."""
    response = client.get("/api/showcase")
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 4
    categories = [c["category"] for c in cases]
    assert "corroborates" in categories
    assert "contradicts" in categories
    assert "reconciles" in categories
    assert "failure_analysis" in categories

def test_api_ui_served():
    """Verify the root endpoint serves the Inspection UI."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Fact Knowledge Layer | Superjoin" in response.text

def test_api_upload_schema():
    """Verify upload endpoint handles PDF and returns extracted facts and discovered relationships."""
    test_pdf = Path("starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf")
    if not test_pdf.exists():
        return
    try:
        with open(test_pdf, "rb") as f:
            response = client.post(
                "/api/documents/upload?max_pages=1",
                files={"file": ("test_upload.pdf", f, "application/pdf")}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "extracted_facts" in data
        assert "discovered_relationships" in data
        assert isinstance(data["extracted_facts"], list)
        assert isinstance(data["discovered_relationships"], list)
    finally:
        from app.database import get_connection
        from app.services.fact_store import FactStore
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT document_id FROM documents WHERE filename = 'test_upload.pdf'")
        rows = c.fetchall()
        conn.close()
        store = FactStore()
        for (doc_id,) in rows:
            store.delete_document(doc_id)

