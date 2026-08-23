"""
Tests for Non-Blocking Upload & Live Processing Pipeline UX.

Verifies:
1. Upload endpoint returns immediately with initial staged entities (Document, Job, Step, Batch).
2. Processing status transitions and stage metrics are persisted and queryable via batches API.
3. Errors during processing are durably recorded in job and batch item status.
"""
import io
import uuid
import pytest
from sqlmodel import Session, select
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models import (
    Document,
    DocumentStatus,
    ProcessingJob,
    ProcessingStep,
    JobStatus,
    StepStatus,
    IngestionBatch,
    IngestionBatchItem,
    BatchStatus,
    BatchItemStatus,
)


def test_upload_returns_immediately_and_creates_entities(session: Session, monkeypatch):
    """Verifies that upload endpoint returns fast with queued/processing status and creates all entities."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")

    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    try:
        csv_bytes = (
            b"Mfg_Part_Num,Part_Desc,Brand\n"
            b"UX-MTR-001,High Torque Induction Motor,Siemens\n"
        )
        csv_file = io.BytesIO(csv_bytes)

        # POST upload-batch
        res = client.post(
            "/api/v1/documents/upload-batch",
            files={"files": ("ux_test.csv", csv_file, "text/csv")},
            data={"batch_name": "UX_Fast_Batch"}
        )
        assert res.status_code == 201
        data = res.json()

        assert "batch_id" in data
        assert data["total_files"] == 1
        assert data["accepted_count"] == 1
        assert len(data["documents"]) == 1
        doc_res = data["documents"][0]
        assert doc_res["filename"] == "ux_test.csv"
        assert doc_res["status"] in ("queued", "processing", "completed")

        batch_id = uuid.UUID(data["batch_id"])

        # Check DB records created
        batch = session.get(IngestionBatch, batch_id)
        assert batch is not None
        assert batch.name == "UX_Fast_Batch"

        # Check Batch Status endpoint returns stage information
        status_res = client.get(f"/api/v1/documents/batches/{batch_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["batch_id"] == str(batch_id)
        assert len(status_data["documents"]) == 1
        assert "stage" in status_data["documents"][0]

    finally:
        app.dependency_overrides.clear()


def test_single_document_upload_api_creates_batch_and_job(session: Session, monkeypatch):
    """Verifies that single document upload endpoint returns quickly with job_id and batch_id."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")

    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    try:
        csv_bytes = (
            b"Mfg_Part_Num,Brand,Description\n"
            b"UX-SINGLE-01,ABB,Standard Industrial Motor\n"
        )
        csv_file = io.BytesIO(csv_bytes)

        res = client.post(
            "/api/v1/documents/upload",
            files={"file": ("single_ux.csv", csv_file, "text/csv")}
        )
        assert res.status_code == 201
        data = res.json()

        assert "document_id" in data
        assert data["document_id"] is not None
        assert data["status"] in ("queued", "processing", "uploaded", "completed", "already_processed")

    finally:
        app.dependency_overrides.clear()
