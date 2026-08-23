import uuid
import os
import sys
import json
import hashlib
import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event

from app.models import (
    Document, DocumentStatus, ProcessingJob, ProcessingStep,
    JobStatus, StepStatus, CacheEntry, CacheType
)
from app.services.document import DocumentService
from app.services.pipeline import (
    DocumentProcessingService, ParsingStage,
    TransientProcessingError, NonRetryableProcessingError
)
from app.services.parser import DocumentParser, DoclingParser, MockParser
from app.services.storage import get_storage_service
from app.workers.tasks.document_processing import process_document_task


# 1. Docling Unavailable -> Clear Failure
def test_docling_unavailable_failure():
    # Hide docling module imports using unittest patch
    with patch.dict(sys.modules, {"docling.document_converter": None}):
        with pytest.raises(ImportError) as exc:
            DoclingParser()
        assert "Docling library is not installed" in str(exc.value)

# 2. Content Hash Determinism
def test_content_hash_determinism():
    parsed_output_1 = {
        "pages": [{"page_number": 1, "text": "Content A"}],
        "metadata": {"title": "Title A"}
    }
    # Out of order keys in identical dict
    parsed_output_2 = {
        "metadata": {"title": "Title A"},
        "pages": [{"page_number": 1, "text": "Content A"}]
    }

    str_1 = json.dumps(parsed_output_1, sort_keys=True, separators=(",", ":"))
    str_2 = json.dumps(parsed_output_2, sort_keys=True, separators=(",", ":"))

    hash_1 = hashlib.sha256(str_1.encode("utf-8")).hexdigest()
    hash_2 = hashlib.sha256(str_2.encode("utf-8")).hexdigest()

    assert hash_1 == hash_2

# 3. Page/Table/Image Representation
def test_page_table_image_representation():
    parser = MockParser()
    res = parser.parse(b"%PDF-1.4 synthetic file")
    
    assert "pages" in res
    assert len(res["pages"]) == 2
    
    p1 = res["pages"][0]
    assert p1["page_number"] == 1
    assert "MX-500" in p1["text"]
    assert len(p1["tables"]) == 0

    p2 = res["pages"][1]
    assert p2["page_number"] == 2
    assert len(p2["tables"]) == 1
    assert p2["tables"][0]["headers"] == ["Specification", "Value"]
    assert p2["tables"][0]["rows"][0] == ["Voltage", "230 V"]
    assert len(p2["images"]) == 1
    assert p2["images"][0]["label"] == "motor_wiring"

# 4. Cache Hit & Miss based on parser version
def test_cache_hit_and_miss_parser_version(session: Session):
    storage = get_storage_service()
    
    # Setup document
    doc_id = uuid.uuid4()
    storage_key = f"documents/original/{doc_id}.pdf"
    storage.upload_file(b"%PDF-1.4 test bytes", storage_key)
    
    doc = Document(
        id=doc_id,
        filename="motor.pdf",
        storage_backend="local",
        storage_key=storage_key,
        file_hash=f"hash_{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=100
    )
    job = ProcessingJob(id=uuid.uuid4(), total_items=1, status=JobStatus.queued, current_stage="parsing")
    step = ProcessingStep(id=uuid.uuid4(), job_id=job.id, document_id=doc_id, stage="parsing", status="queued")
    
    session.add(doc)
    session.add(job)
    session.add(step)
    session.commit()

    # Define custom mocked parser class to verify execution counts
    class VersionedMockParser(DocumentParser):
        def __init__(self, version):
            self.version = version
            self.call_count = 0
        def parse(self, file_content):
            self.call_count += 1
            return {"pages": [{"page_number": 1, "text": "Mock"}], "metadata": {}}

    parser_v1 = VersionedMockParser("1.0.0")
    processor = DocumentProcessingService(session, parser=parser_v1)
    
    # 1st Run (Cache Miss)
    processor.process_document(doc_id, job.id, step.id)
    assert parser_v1.call_count == 1
    
    # Re-fetch document status
    session.refresh(doc)
    assert doc.status == DocumentStatus.processed
    assert doc.parser_version == "1.0.0"

    # Setup new job/step to verify cache hit
    job2 = ProcessingJob(id=uuid.uuid4(), total_items=1, status=JobStatus.queued, current_stage="parsing")
    step2 = ProcessingStep(id=uuid.uuid4(), job_id=job2.id, document_id=doc_id, stage="parsing", status="queued")
    session.add(job2)
    session.add(step2)
    session.commit()

    # 2nd Run (Same Version -> Cache Hit)
    parser_v1_retry = VersionedMockParser("1.0.0")
    processor_retry = DocumentProcessingService(session, parser=parser_v1_retry)
    processor_retry.process_document(doc_id, job2.id, step2.id)
    
    # Parse should NOT be called again due to cache lookup hit
    assert parser_v1_retry.call_count == 0
    session.refresh(step2)
    assert step2.status == StepStatus.completed

    # Setup 3rd job/step for changed version
    job3 = ProcessingJob(id=uuid.uuid4(), total_items=1, status=JobStatus.queued, current_stage="parsing")
    step3 = ProcessingStep(id=uuid.uuid4(), job_id=job3.id, document_id=doc_id, stage="parsing", status="queued")
    session.add(job3)
    session.add(step3)
    session.commit()

    # 3rd Run (Changed Version -> Cache Miss/Reparse)
    parser_v2 = VersionedMockParser("2.0.0")
    processor_v2 = DocumentProcessingService(session, parser=parser_v2)
    processor_v2.process_document(doc_id, job3.id, step3.id)
    
    assert parser_v2.call_count == 1
    session.refresh(doc)
    assert doc.parser_version == "2.0.0"

# 5. Force Reprocess Preserves Historical Processing Records
def test_force_reprocess_preserves_history(session: Session):
    # Register document
    service = DocumentService(session)
    res = service.upload_document(b"%PDF-1.4 file", "spec.pdf", "application/pdf")
    
    doc_id = res["document_id"]
    job_id_1 = res["job_id"]

    # Execute parsing stage
    parser = MockParser()
    processor = DocumentProcessingService(session, parser=parser)
    
    # Resolve step
    stmt = select(ProcessingStep).where(ProcessingStep.job_id == job_id_1)
    step1 = session.exec(stmt).one()
    processor.process_document(doc_id, job_id_1, step1.id)

    # Trigger force reprocess
    reprocess_res = service.force_reprocess(doc_id)
    job_id_2 = reprocess_res["job_id"]

    # Verify both jobs are present in DB histories
    assert job_id_1 != job_id_2
    
    job1_db = session.get(ProcessingJob, job_id_1)
    job2_db = session.get(ProcessingJob, job_id_2)

    assert job1_db is not None
    assert job2_db is not None
    assert len(session.exec(select(ProcessingJob)).all()) == 2

# 6. Worker Idempotency
def test_worker_idempotency(session: Session):
    storage = get_storage_service()
    doc_id = uuid.uuid4()
    storage_key = f"documents/original/{doc_id}.pdf"
    storage.upload_file(b"%PDF-1.4 spec test", storage_key)

    doc = Document(
        id=doc_id,
        filename="datasheet.pdf",
        storage_backend="local",
        storage_key=storage_key,
        file_hash=f"hash_{uuid.uuid4()}",
        mime_type="application/pdf",
        file_size=100
    )
    job = ProcessingJob(id=uuid.uuid4(), total_items=1, status=JobStatus.queued, current_stage="parsing")
    step = ProcessingStep(id=uuid.uuid4(), job_id=job.id, document_id=doc_id, stage="parsing", status="queued")
    
    session.add(doc)
    session.add(job)
    session.add(step)
    session.commit()

    # Trigger Celery task block synchronously via local environment variables env mock
    # Route DB operations in the Celery task to the test session's engine to avoid UndefinedTable errors
    with patch("app.workers.tasks.document_processing.get_parser", return_value=MockParser()):
        with patch("app.workers.tasks.document_processing.engine", session.bind):
            # Suppress the extraction task dispatch (we only test the parsing stage here)
            with patch("app.workers.tasks.document_processing.extract_document_task") as mock_extract:
                mock_extract.delay = lambda *a, **kw: None

                # Run 1
                process_document_task(str(doc_id), str(job.id), str(step.id))

                session.refresh(doc)
                session.refresh(job)
                session.refresh(step)
                assert doc.status == DocumentStatus.processed
                # Phase 4: job status is 'processing' after parsing (extraction stage is next)
                assert job.status in (JobStatus.completed, JobStatus.processing)

                # Run 2 on same processed IDs (idempotency: skip-to-extraction branch)
                process_document_task(str(doc_id), str(job.id), str(step.id))

                session.refresh(doc)
                assert doc.status == DocumentStatus.processed

# 7. Concurrent Duplicate Uploads
def test_concurrent_duplicate_uploads(session: Session, monkeypatch):
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = DocumentService(session)
    
    # Mock upload validation pass
    pdf_bytes = b"%PDF-1.4 file contents"
    
    # Trigger 1st upload
    res1 = service.upload_document(pdf_bytes, "test.pdf", "application/pdf", process_inline=False)
    
    # Simulate concurrency: 2nd upload hits commit at same time but catches IntegrityError
    # We mock commit to raise IntegrityError for test verification
    with patch.object(session, "commit", side_effect=IntegrityError("statement", {}, Exception("UniqueConstraint"))):
        res2 = service.upload_document(pdf_bytes, "test.pdf", "application/pdf", process_inline=False)
        
        # Verify 2nd concurrent upload gracefully falls back to the winner document details
        assert res1["document_id"] == res2["document_id"]
        assert res2["cached"] is True

# 8. Retryable vs Non-Retryable Parser Failures
def test_retryable_vs_non_retryable_failures(session: Session):
    # Setup doc
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    step_id = uuid.uuid4()
    
    doc = Document(
        id=doc_id, filename="doc.pdf", storage_backend="local",
        storage_key=f"documents/original/{doc_id}.pdf", file_hash=f"hash_{uuid.uuid4()}",
        mime_type="application/pdf", file_size=100
    )
    job = ProcessingJob(id=job_id, total_items=1, status=JobStatus.queued)
    step = ProcessingStep(id=step_id, job_id=job_id, document_id=doc_id, stage="parsing", status="queued")
    
    session.add(doc)
    session.add(job)
    session.add(step)
    session.commit()

    # Mock the get_storage_service helper globally inside pipeline to intercept all calls
    with patch("app.services.pipeline.get_storage_service") as mock_get_storage:
        mock_storage = MagicMock()
        mock_get_storage.return_value = mock_storage
        
        # 1. Transient/Retryable error: Mock storage download failure (timeout)
        mock_storage.download_file.side_effect = Exception("S3 Connection Timeout")
        processor = DocumentProcessingService(session, parser=MockParser())
        with pytest.raises(TransientProcessingError):
            processor.process_document(doc_id, job_id, step_id)

        # 2. Non-Retryable error: Invalid PDF magic bytes inside MockParser
        mock_storage.download_file.side_effect = None
        mock_storage.download_file.return_value = b"CORRUPT_BYTES_NOT_PDF"
        processor = DocumentProcessingService(session, parser=MockParser())
        with pytest.raises(NonRetryableProcessingError):
            processor.process_document(doc_id, job_id, step_id)
