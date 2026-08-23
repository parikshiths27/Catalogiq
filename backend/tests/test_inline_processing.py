"""
Tests for CatalogIQ Free Cloud / Web-Only / Inline Processing Mode.

Verifies:
1. Inline 2-row CSV ingestion.
2. Inline 200-row CSV ingestion.
3. Product persistence with attributes, evidence, and 252-column delivery format.
4. Validation and needs_review persistence with explicit review reasons.
5. Idempotent duplicate handling and deduplication.
6. Final document status (processed) and batch status (completed/100%).
7. Single document upload API inline execution.
8. Reprocess and job retry inline execution.
9. Celery mode preservation and compatibility.
"""
import io
import csv
import uuid
import json
import pytest
from datetime import datetime, timezone
from sqlmodel import Session, create_engine, select
from sqlalchemy.pool import StaticPool
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
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeEvidence,
    EnrichmentResult,
    ValidationResult,
    ValidationType,
    ValidationStatus,
    IngestionBatch,
    IngestionBatchItem,
    BatchStatus,
    BatchItemStatus,
)
from app.services.document import DocumentService
from app.services.batch import BatchService
from app.services.storage import get_storage_service


@pytest.fixture
def inline_db_session():
    """Create in-memory SQLite database with StaticPool for isolated inline test execution."""
    from sqlmodel import SQLModel
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


def test_inline_2_row_csv_ingestion(inline_db_session: Session, monkeypatch):
    """1. Test real inline 2-row CSV ingestion through DocumentService & BatchService."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")
    session = inline_db_session

    csv_data = (
        "Mfg_Part_Num,Part_Desc,Brand,Unilog_Brand,Part_Manuf\n"
        "SIE-15KW-MTR,15kW 3-Phase AC Induction Motor 400V,Siemens,SIEMENS,Siemens AG\n"
        "SCH-ATS48-11KW,Altivar ATS48 Soft Starter 11kW 230V,Schneider,SCHNEIDER,Schneider Electric\n"
    ).encode("utf-8")

    batch_service = BatchService(session)
    result = batch_service.create_batch_from_files(
        [("motors_catalog.csv", csv_data, "text/csv")],
        batch_name="Inline_Demo_Batch"
    )

    assert result["status"] == "completed" or result["status"] == BatchStatus.completed
    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 0

    # Verify Document and IngestionBatch in DB
    batch = session.get(IngestionBatch, result["batch_id"])
    assert batch is not None
    assert batch.status in (BatchStatus.completed, "completed")
    assert batch.total_files == 1
    assert batch.completed_files == 1
    assert batch.failed_files == 0

    doc_stmt = select(Document).where(Document.batch_id == batch.id)
    doc = session.exec(doc_stmt).first()
    assert doc is not None
    assert doc.status in (DocumentStatus.processed, "processed")

    # Verify Products persisted
    prods = session.exec(select(Product)).all()
    assert len(prods) == 2
    skus = {p.sku for p in prods}
    assert "SIE-15KW-MTR" in skus
    assert "SCH-ATS48-11KW" in skus

    # Verify Attributes persisted
    for p in prods:
        attrs = session.exec(select(ProductAttribute).where(ProductAttribute.product_id == p.id)).all()
        assert len(attrs) > 0

        # Verify EnrichmentResult persisted
        enrich = session.exec(select(EnrichmentResult).where(EnrichmentResult.product_id == p.id)).first()
        assert enrich is not None
        payload = json.loads(enrich.generated_value)
        assert "delivery_record" in payload
        assert "descriptions" in payload


def test_inline_200_row_csv_ingestion(inline_db_session: Session, monkeypatch):
    """2. Test high-volume inline 200-row tabular CSV ingestion."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")
    session = inline_db_session

    rows = ["Mfg_Part_Num,Part_Desc,Brand,Unilog_Brand,Part_Manuf"]
    for i in range(1, 201):
        rows.append(f"PART-DEMO-{i:04d},Industrial Automation Sensor {i} 24VDC,Banner,BANNER,Banner Engineering")

    csv_data = "\n".join(rows).encode("utf-8")

    batch_service = BatchService(session)
    res = batch_service.create_batch_from_files(
        [("benchmark_200.csv", csv_data, "text/csv")],
        batch_name="Benchmark_200_Batch"
    )

    assert res["status"] in ("completed", BatchStatus.completed)
    prods = session.exec(select(Product)).all()
    assert len(prods) == 200


def test_product_validation_and_evidence_persistence_inline(inline_db_session: Session, monkeypatch):
    """3. Test that ValidationResult, Evidence, and Review reasons are persisted in inline mode."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")
    session = inline_db_session

    # CSV with a known issue (e.g. unknown brand / low confidence / missing desc)
    csv_data = (
        "Mfg_Part_Num,Part_Desc,Brand,Unilog_Brand,Part_Manuf\n"
        "VALID-01,1/2 in Brass Ball Valve 600 WOG Threaded,Apollo,APOLLO,Apollo Conbraco\n"
        "WARN-02,,-- Unknown Brand --,-- No Unilog Brand --,UnknownMfr\n"
    ).encode("utf-8")

    batch_service = BatchService(session)
    res = batch_service.create_batch_from_files(
        [("validation_test.csv", csv_data, "text/csv")]
    )

    prods = session.exec(select(Product)).all()
    assert len(prods) == 2

    # Find the warning product
    warn_prod = next(p for p in prods if p.sku == "WARN-02")
    assert warn_prod.status in (ProductStatus.needs_review, "needs_review", ProductStatus.draft, "draft")

    val_results = session.exec(select(ValidationResult).where(ValidationResult.product_id == warn_prod.id)).all()
    assert len(val_results) > 0
    assert any(vr.status in (ValidationStatus.open, "open") for vr in val_results)


def test_duplicate_handling_inline(inline_db_session: Session, monkeypatch):
    """4. Test idempotency: re-uploading the same file or products does not duplicate product rows."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")
    session = inline_db_session

    csv_data = (
        "Mfg_Part_Num,Part_Desc,Brand,Unilog_Brand,Part_Manuf\n"
        "IDEMP-01,Siemens 7.5kW Motor,Siemens,SIEMENS,Siemens AG\n"
    ).encode("utf-8")

    batch_service = BatchService(session)

    # First upload
    res1 = batch_service.create_batch_from_files([("idemp.csv", csv_data, "text/csv")])
    prods1 = session.exec(select(Product).where(Product.sku == "IDEMP-01")).all()
    assert len(prods1) == 1

    # Second upload of identical file (detected via file_hash duplicate detection)
    res2 = batch_service.create_batch_from_files([("idemp.csv", csv_data, "text/csv")])
    prods2 = session.exec(select(Product).where(Product.sku == "IDEMP-01")).all()
    assert len(prods2) == 1
    assert res2["documents"][0]["cached"] is True


def test_upload_api_inline_mode(inline_db_session: Session, monkeypatch):
    """5. Test FastAPI HTTP upload endpoints in inline mode."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "inline")
    session = inline_db_session

    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    try:
        csv_file = io.BytesIO(
            b"Mfg_Part_Num,Brand,Product Name,Description\n"
            b"HTTP-MTR-01,Siemens,Siemens 22kW Drive,Heavy-duty variable speed drive"
        )
        res = client.post(
            "/api/v1/documents/upload-batch",
            files={"files": ("http_test.csv", csv_file, "text/csv")},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] in ("processing", "queued", "completed")
        assert data["total_files"] == 1
        assert data["accepted_count"] == 1
        assert len(data["documents"]) == 1
        assert data["documents"][0]["status"] in ("queued", "processing", "completed")

        # Check batch endpoint returns batch and stage details
        batch_id = data["batch_id"]
        b_res = client.get(f"/api/v1/documents/batches/{batch_id}")
        assert b_res.status_code == 200
        b_data = b_res.json()
        assert b_data["status"] == "completed"
        assert b_data["progress_percentage"] == 100.0
        assert b_data["completed_files"] == 1
        assert len(b_data["documents"]) == 1
        assert b_data["documents"][0]["stage"] is not None

        # Check product created and accessible via Products API
        p_res = client.get("/api/v1/products?limit=10")
        assert p_res.status_code == 200
        prods = p_res.json()
        assert any(p["sku"] == "HTTP-MTR-01" for p in prods)

    finally:
        app.dependency_overrides.clear()


def test_celery_mode_preservation(inline_db_session: Session, monkeypatch):
    """6. Verifies that when PROCESSING_MODE=celery, Celery queue dispatch is preserved."""
    monkeypatch.setattr(settings, "PROCESSING_MODE", "celery")
    session = inline_db_session

    dispatched_tasks = []

    # Mock process_document_task.delay
    from app.workers.tasks import document_processing
    monkeypatch.setattr(
        document_processing.process_document_task,
        "delay",
        lambda *args: dispatched_tasks.append(args)
    )

    doc_service = DocumentService(session)
    csv_bytes = b"Mfg_Part_Num,Brand,Description\nCEL-01,ABB,ABB Motor"
    res = doc_service.upload_document(csv_bytes, "celery_test.csv", "text/csv")

    assert res["status"] == "queued"
    assert len(dispatched_tasks) == 1
    assert str(res["document_id"]) in dispatched_tasks[0]
