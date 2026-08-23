import io
import os
import zipfile
import json
import uuid
import pytest
from sqlmodel import Session, select
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.models import (
    IngestionBatch, BatchStatus, Document, DocumentStatus,
    ProcessingJob, ProcessingStep, JobStatus
)
from app.services.batch import BatchService
from app.services.pipeline import DocumentProcessingService
from app.services.parser import MockParser, MultiFormatParser

client = TestClient(app)

@pytest.fixture(autouse=True)
def set_celery_mode_for_async_tests(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "PROCESSING_MODE", "celery")

def test_multi_file_upload_batch(session: Session, monkeypatch):
    """Verifies multi-file batch creation and aggregate progress tracking."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = BatchService(session)

    files = [
        ("motor_spec_1.pdf", b"%PDF-1.4 motor 1 specs", "application/pdf"),
        ("motor_spec_2.pdf", b"%PDF-1.4 motor 2 specs", "application/pdf"),
        ("products.csv", b"SKU,Name,Voltage\nB-01,Batch Motor,230V\n", "text/csv"),
    ]

    res = service.create_batch_from_files(files, batch_name="Test_MultiFile_Batch")
    
    assert "batch_id" in res
    assert res["status"] in (BatchStatus.processing, BatchStatus.completed)
    assert res["total_files"] == 3
    assert res["accepted_count"] == 3
    assert res["rejected_count"] == 0

    batch_id = res["batch_id"]
    batch = session.get(IngestionBatch, batch_id)
    assert batch is not None
    assert batch.name == "Test_MultiFile_Batch"
    assert batch.total_files == 3

    # Verify associated documents and jobs carry batch_id
    docs = session.exec(select(Document).where(Document.batch_id == batch_id)).all()
    jobs = session.exec(select(ProcessingJob).where(ProcessingJob.batch_id == batch_id)).all()
    assert len(docs) == 3
    assert len(jobs) == 3


def test_zip_archive_upload_batch(session: Session, monkeypatch):
    """Verifies ZIP archive unpacking and multi-format document batch ingestion."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = BatchService(session)

    # Construct in-memory ZIP archive with PDF, CSV, and JSON files
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("datasheet.pdf", b"%PDF-1.4 zipped pdf content")
        zf.writestr("catalog.csv", b"SKU,Brand,Name\nZIP-01,BrandZ,Zip Product\n")
        zf.writestr("feed.json", json.dumps([{"sku": "JSON-99", "name": "JSON Motor"}]).encode("utf-8"))
        zf.writestr("__MACOSX/._datasheet.pdf", b"hidden macOS metadata")  # Should be filtered out

    zip_bytes = zip_buffer.getvalue()
    res = service.create_batch_from_zip(zip_bytes, filename="catalog_archive.zip")

    assert res["total_files"] == 3
    assert res["accepted_count"] == 3
    assert res["rejected_count"] == 0

    batch_id = res["batch_id"]
    batch_status = service.get_batch_status(batch_id)
    assert batch_status["total_files"] == 3
    assert len(batch_status["documents"]) == 3


def test_batch_partial_failure_isolation(session: Session, monkeypatch):
    """Verifies that an invalid/corrupt file in a batch does not abort other valid files."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = BatchService(session)

    files = [
        ("valid_1.pdf", b"%PDF-1.4 valid pdf content", "application/pdf"),
        ("corrupt_file.pdf", b"INVALID_CORRUPT_BYTES_NOT_PDF", "application/pdf"),  # Will fail magic byte check
        ("valid_data.csv", b"SKU,Name\nCSV-01,Valid Motor\n", "text/csv"),
    ]

    res = service.create_batch_from_files(files, batch_name="Partial_Failure_Batch")

    assert res["total_files"] == 3
    assert res["accepted_count"] == 2
    assert res["rejected_count"] == 1
    assert res["rejected"][0]["filename"] == "corrupt_file.pdf"
    assert "Invalid PDF format" in res["rejected"][0]["error"]

    batch_id = res["batch_id"]
    batch_status = service.get_batch_status(batch_id)
    assert batch_status["failed_files"] == 1
    assert batch_status["total_files"] == 3


def test_batch_api_upload_and_status(session: Session, monkeypatch):
    """Verifies FastAPI POST /api/v1/documents/upload-batch and GET /api/v1/documents/batches/{batch_id}."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    app.dependency_overrides[get_session] = lambda: session

    # Construct multi-file multipart request payload
    files_payload = [
        ("files", ("spec1.pdf", io.BytesIO(b"%PDF-1.4 spec 1"), "application/pdf")),
        ("files", ("spec2.csv", io.BytesIO(b"SKU,Name\nS2,Spec 2 Motor\n"), "text/csv")),
    ]

    response = client.post(
        "/api/v1/documents/upload-batch",
        files=files_payload,
        data={"batch_name": "API_Test_Batch"}
    )

    assert response.status_code == 201
    data = response.json()
    assert "batch_id" in data
    assert data["batch_name"] == "API_Test_Batch"
    assert data["total_files"] == 2
    assert data["accepted_count"] == 2

    batch_id = data["batch_id"]

    # Poll status endpoint
    status_response = client.get(f"/api/v1/documents/batches/{batch_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["batch_id"] == batch_id
    assert status_data["total_files"] == 2
    assert len(status_data["documents"]) == 2
    app.dependency_overrides.clear()


def test_zip_safety_path_traversal_and_nested_zip(session: Session, monkeypatch):
    """Verifies that path traversal attempts and nested ZIPs inside archive are handled safely."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = BatchService(session)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../../etc/passwd.pdf", b"%PDF-1.4 path traversal pdf")
        zf.writestr("nested.zip", b"PK\x03\x04nested zip bytes")
        zf.writestr("valid.pdf", b"%PDF-1.4 valid pdf")

    zip_bytes = zip_buffer.getvalue()
    res = service.create_batch_from_zip(zip_bytes, filename="security_test.zip")

    # Path traversal member ../../etc/passwd.pdf is blocked; nested zip is skipped; valid.pdf is accepted
    assert res["total_files"] == 1
    assert res["accepted_count"] == 1


def test_zip_file_count_limit_exceeded(session: Session, monkeypatch):
    """Verifies that archives exceeding MAX_ARCHIVE_FILES are rejected cleanly."""
    monkeypatch.setattr("app.core.config.settings.MAX_ARCHIVE_FILES", 2)
    service = BatchService(session)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("f1.pdf", b"%PDF-1.4 pdf 1")
        zf.writestr("f2.csv", b"a,b\n1,2")
        zf.writestr("f3.txt", b"txt 3")

    zip_bytes = zip_buffer.getvalue()
    with pytest.raises(ValueError) as exc:
        service.create_batch_from_zip(zip_bytes, filename="too_many_files.zip")
    assert "exceeding limit of 2" in str(exc.value)


def test_new_document_creates_batch_item_and_job(session: Session, monkeypatch):
    """Verifies that uploading a new document creates IngestionBatchItem, Document, and ProcessingJob."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService
    from app.models import IngestionBatchItem, BatchItemStatus

    doc_service = DocumentService(session)
    res = doc_service.upload_document(
        file_content=b"%PDF-1.4 unique content 1",
        filename="unique1.pdf",
        mime_type="application/pdf"
    )

    batch_id = res["batch_id"]
    doc_id = res["document_id"]
    job_id = res["job_id"]

    stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id)
    items = session.exec(stmt).all()
    assert len(items) == 1
    item = items[0]
    assert item.document_id == doc_id
    assert item.job_id == job_id
    assert item.status == BatchItemStatus.queued
    assert item.cached is False


def test_cached_processed_document_marks_batch_item_completed(session: Session, monkeypatch):
    """Verifies that uploading an already processed file creates a new Batch & BatchItem with cached=True and status=completed."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService
    from app.models import IngestionBatchItem, BatchItemStatus

    doc_service = DocumentService(session)
    file_bytes = b"%PDF-1.4 completed doc content"

    # First upload
    res1 = doc_service.upload_document(file_bytes, "completed_doc.pdf", "application/pdf")
    doc_id = res1["document_id"]

    # Mark document as processed
    doc = session.get(Document, doc_id)
    doc.status = DocumentStatus.processed
    session.add(doc)
    session.commit()

    # Second upload of exact same content in a NEW batch
    batch_service = BatchService(session)
    res2 = batch_service.create_batch_from_files([("completed_doc.pdf", file_bytes, "application/pdf")], batch_name="CacheHit_Batch")

    batch_id_2 = res2["batch_id"]
    assert res2["accepted_count"] == 1

    # Verify IngestionBatchItem in second batch
    stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id_2)
    items = session.exec(stmt).all()
    assert len(items) == 1
    item = items[0]
    assert item.document_id == doc_id
    assert item.cached is True
    assert item.status == BatchItemStatus.completed

    # Verify batch status is immediately completed
    status2 = batch_service.get_batch_status(batch_id_2)
    assert status2["status"] == BatchStatus.completed
    assert status2["completed_files"] == 1


def test_cached_processing_document_reuses_existing_job(session: Session, monkeypatch):
    """Verifies uploading an actively processing document references existing job without duplicating Celery task."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService
    from app.models import IngestionBatchItem, BatchItemStatus

    doc_service = DocumentService(session)
    file_bytes = b"%PDF-1.4 active processing doc content"

    res1 = doc_service.upload_document(file_bytes, "active.pdf", "application/pdf")
    doc_id = res1["document_id"]
    job_id_1 = res1["job_id"]

    # Document is in parsing status
    doc = session.get(Document, doc_id)
    doc.status = DocumentStatus.parsing
    session.add(doc)
    session.commit()

    # Upload same file in second batch
    batch_service = BatchService(session)
    res2 = batch_service.create_batch_from_files([("active.pdf", file_bytes, "application/pdf")], batch_name="Processing_Cache_Batch")
    batch_id_2 = res2["batch_id"]

    stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id_2)
    items = session.exec(stmt).all()
    assert len(items) == 1
    item = items[0]
    assert item.document_id == doc_id
    assert item.job_id == job_id_1
    assert item.status == BatchItemStatus.processing
    assert item.cached is True


def test_failed_document_retry_is_batch_linked(session: Session, monkeypatch):
    """Verifies uploading a failed document creates a new ProcessingJob and links BatchItem."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService
    from app.models import IngestionBatchItem, BatchItemStatus

    doc_service = DocumentService(session)
    file_bytes = b"%PDF-1.4 failed doc content"

    res1 = doc_service.upload_document(file_bytes, "failed.pdf", "application/pdf")
    doc_id = res1["document_id"]
    job_id_1 = res1["job_id"]

    # Mark document as failed
    doc = session.get(Document, doc_id)
    doc.status = DocumentStatus.failed
    session.add(doc)
    session.commit()

    # Re-upload failed doc in second batch
    batch_service = BatchService(session)
    res2 = batch_service.create_batch_from_files([("failed.pdf", file_bytes, "application/pdf")], batch_name="Retry_Batch")
    batch_id_2 = res2["batch_id"]

    stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id_2)
    items = session.exec(stmt).all()
    assert len(items) == 1
    item = items[0]
    assert item.document_id == doc_id
    assert item.job_id != job_id_1  # New retry job created!
    assert item.status == BatchItemStatus.queued
    assert item.cached is True


def test_same_document_can_appear_in_multiple_batches(session: Session, monkeypatch):
    """Verifies that a single Document can be associated with BatchItem records across multiple batches."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService
    from app.models import IngestionBatchItem

    doc_service = DocumentService(session)
    file_bytes = b"%PDF-1.4 multi batch document"

    res1 = doc_service.upload_document(file_bytes, "multi.pdf", "application/pdf")
    batch_id_1 = res1["batch_id"]
    doc_id = res1["document_id"]

    res2 = doc_service.upload_document(file_bytes, "multi.pdf", "application/pdf", batch_id=uuid.uuid4())
    batch_id_2 = res2["batch_id"]

    stmt = select(IngestionBatchItem).where(IngestionBatchItem.document_id == doc_id)
    items = session.exec(stmt).all()
    assert len(items) == 2
    batch_ids = {i.batch_id for i in items}
    assert batch_id_1 in batch_ids
    assert batch_id_2 in batch_ids


def test_batch_progress_counts_cached_items(session: Session, monkeypatch):
    """Verifies that cached completed items count properly towards batch completed & processed totals."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService

    doc_service = DocumentService(session)
    file1_bytes = b"%PDF-1.4 cached batch item 1"
    file2_bytes = b"%PDF-1.4 cached batch item 2"

    res1 = doc_service.upload_document(file1_bytes, "c1.pdf", "application/pdf")
    doc1 = session.get(Document, res1["document_id"])
    doc1.status = DocumentStatus.processed
    session.add(doc1)
    session.commit()

    batch_service = BatchService(session)
    res_batch = batch_service.create_batch_from_files([
        ("c1.pdf", file1_bytes, "application/pdf"),
        ("c2.pdf", file2_bytes, "application/pdf"),
    ], batch_name="Mixed_Cached_Batch")

    batch_id = res_batch["batch_id"]
    status = batch_service.get_batch_status(batch_id)

    assert status["total_files"] == 2
    assert status["completed_files"] == 1
    assert status["processing_files"] == 1
    assert status["processed_files"] == 1
    assert status["progress_percentage"] == 50.0


def test_batch_progress_updates_all_memberships_after_document_completion(session: Session, monkeypatch):
    """Verifies that document completion updates all parent BatchItems across historical batches."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService
    from app.workers.tasks.document_processing import _update_batch_progress_if_needed
    from app.models import IngestionBatchItem, BatchItemStatus

    doc_service = DocumentService(session)
    file_bytes = b"%PDF-1.4 shared document completion"

    res1 = doc_service.upload_document(file_bytes, "shared.pdf", "application/pdf")
    batch_id_1 = res1["batch_id"]
    doc_id = res1["document_id"]

    batch_service = BatchService(session)
    res2 = batch_service.create_batch_from_files([("shared.pdf", file_bytes, "application/pdf")], batch_name="Batch_2")
    batch_id_2 = res2["batch_id"]

    # Mark document processed and trigger batch sync
    doc = session.get(Document, doc_id)
    doc.status = DocumentStatus.processed
    session.add(doc)
    session.commit()

    _update_batch_progress_if_needed(session, doc)

    # Verify both BatchItems updated
    item1 = session.exec(select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id_1)).first()
    item2 = session.exec(select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id_2)).first()

    assert item1.status == BatchItemStatus.completed
    assert item2.status == BatchItemStatus.completed

    status1 = batch_service.get_batch_status(batch_id_1)
    status2 = batch_service.get_batch_status(batch_id_2)
    assert status1["status"] == BatchStatus.completed
    assert status2["status"] == BatchStatus.completed


def test_single_file_upload_creates_one_batch_item(session: Session, monkeypatch):
    """Verifies POST /api/v1/documents/upload creates 1 IngestionBatch and 1 IngestionBatchItem."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.models import IngestionBatchItem

    app.dependency_overrides[get_session] = lambda: session

    files = [("file", ("single.pdf", io.BytesIO(b"%PDF-1.4 single file"), "application/pdf"))]
    response = client.post("/api/v1/documents/upload", files=files)
    assert response.status_code == 201
    data = response.json()

    batch_id = data["batch_id"]
    stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == uuid.UUID(batch_id))
    items = session.exec(stmt).all()
    assert len(items) == 1
    app.dependency_overrides.clear()


def test_multi_file_batch_creates_one_batch_item_per_input(session: Session, monkeypatch):
    """Verifies POST /api/v1/documents/upload-batch creates 1 IngestionBatchItem per input file."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.models import IngestionBatchItem

    app.dependency_overrides[get_session] = lambda: session
    files_payload = [
        ("files", ("f1.pdf", io.BytesIO(b"%PDF-1.4 f1"), "application/pdf")),
        ("files", ("f2.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")),
    ]
    res = client.post("/api/v1/documents/upload-batch", files=files_payload)
    assert res.status_code == 201
    data = res.json()

    batch_id = uuid.UUID(data["batch_id"])
    items = session.exec(select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id)).all()
    assert len(items) == 2
    app.dependency_overrides.clear()


def test_zip_batch_creates_one_batch_item_per_valid_document(session: Session, monkeypatch):
    """Verifies ZIP upload creates 1 IngestionBatchItem per valid extracted file."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.models import IngestionBatchItem

    service = BatchService(session)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("d1.pdf", b"%PDF-1.4 pdf 1")
        zf.writestr("d2.csv", b"x,y\n3,4")

    zip_bytes = zip_buffer.getvalue()
    res = service.create_batch_from_zip(zip_bytes, filename="zip_test.zip")
    batch_id = res["batch_id"]

    items = session.exec(select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id)).all()
    assert len(items) == 2


def test_partial_failure_with_cached_and_new_documents(session: Session, monkeypatch):
    """Verifies batch containing new files, cached files, and 1 corrupt file handles cached/new/rejected states cleanly."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    from app.services.document import DocumentService

    doc_service = DocumentService(session)
    cached_bytes = b"%PDF-1.4 cached pdf for partial failure test"

    # Pre-upload and process 1 document
    res_pre = doc_service.upload_document(cached_bytes, "cached_pre.pdf", "application/pdf")
    doc_pre = session.get(Document, res_pre["document_id"])
    doc_pre.status = DocumentStatus.processed
    session.add(doc_pre)
    session.commit()

    # Submit batch with: cached file, new valid file, and corrupt file
    batch_service = BatchService(session)
    files = [
        ("cached_pre.pdf", cached_bytes, "application/pdf"),
        ("new_valid.csv", b"SKU,Name\nN1,New Motor\n", "text/csv"),
        ("invalid_pdf.pdf", b"INVALID_CORRUPT_BYTES", "application/pdf"),
    ]

    res = batch_service.create_batch_from_files(files, batch_name="Mixed_Partial_Batch")

    assert res["total_files"] == 3
    assert res["accepted_count"] == 2
    assert res["rejected_count"] == 1
    assert res["rejected"][0]["filename"] == "invalid_pdf.pdf"

    batch_id = res["batch_id"]
    status = batch_service.get_batch_status(batch_id)
    assert status["total_files"] == 3
    assert status["completed_files"] == 1  # The cached file
    assert status["failed_files"] == 1     # The invalid file
    assert status["processing_files"] == 1 # The new file

