"""
Regression tests for durable intermediate JSON storage and retrieval.
Verifies that parsed document representations survive local filesystem resets (Render Free tier).
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.db.session import get_session
from app.models import Document, DocumentStatus


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_get_parsed_document_from_durable_postgres_metadata(client: TestClient, session: Session):
    """
    Test that intermediate JSON is returned directly from PostgreSQL metadata
    even when no local storage file exists on disk (simulating a Render container restart).
    """
    doc_id = uuid.uuid4()
    mock_parsed_data = {
        "document_id": str(doc_id),
        "content_hash": "abc123hash",
        "parser": {"name": "CSVParser", "version": "1.0.0"},
        "pages": [
            {
                "page_number": 1,
                "text": "Header 1, Header 2\nVal 1, Val 2",
                "tables": [[["Header 1", "Header 2"], ["Val 1", "Val 2"]]],
                "images": [],
            }
        ],
        "metadata": {"total_rows": 1},
    }

    doc = Document(
        id=doc_id,
        filename="test_catalog.csv",
        storage_backend="local",
        storage_key="documents/uploads/test_catalog.csv",
        file_hash="dummy_hash_1",
        mime_type="text/csv",
        file_size=1024,
        status=DocumentStatus.processed,
        parser_name="CSVParser",
        parser_version="1.0.0",
        parsed_storage_key=f"documents/parsed/{doc_id}.json",
        metadata_json={"intermediate_json": mock_parsed_data},
    )
    session.add(doc)
    session.commit()

    res = client.get(f"/api/v1/documents/{doc_id}/parsed")
    assert res.status_code == 200
    data = res.json()
    assert data["content_hash"] == "abc123hash"
    assert data["parser"]["name"] == "CSVParser"
    assert len(data["pages"]) == 1
    assert data["pages"][0]["tables"][0][0] == ["Header 1", "Header 2"]


def test_get_parsed_document_not_found(client: TestClient):
    """Test 404 is returned when document ID does not exist."""
    fake_id = uuid.uuid4()
    res = client.get(f"/api/v1/documents/{fake_id}/parsed")
    assert res.status_code == 404
    assert f"Document with ID {fake_id} not found" in res.json()["detail"]


def test_get_parsed_document_unparsed_status(client: TestClient, session: Session):
    """Test 400 is returned when document is in uploaded or failed status."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        filename="unparsed.pdf",
        storage_backend="local",
        storage_key="documents/uploads/unparsed.pdf",
        file_hash="dummy_hash_2",
        mime_type="application/pdf",
        file_size=2048,
        status=DocumentStatus.uploaded,
    )
    session.add(doc)
    session.commit()

    res = client.get(f"/api/v1/documents/{doc_id}/parsed")
    assert res.status_code == 400
    assert "uploaded" in res.json()["detail"]
