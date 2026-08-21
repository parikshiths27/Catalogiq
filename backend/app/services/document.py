import uuid
import hashlib
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlmodel import Session, select, and_
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.constants import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    EXTENSION_TO_MIME_TYPE,
)
from app.models import (
    Document, DocumentStatus, ProcessingJob, ProcessingStep, 
    JobStatus, ProcessingStage, StepStatus
)
from app.services.storage import get_storage_service
from app.repositories import DocumentRepository

logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self, session: Session):
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.storage = get_storage_service()

    def validate_file(self, file_content: bytes, filename: str) -> None:
        """
        Validates file extension, size limit, and format-specific magic bytes.
        """
        # 1. Size validation
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(file_content) > max_bytes:
            raise ValueError(f"File size exceeds limit of {settings.MAX_UPLOAD_SIZE_MB}MB")
        if len(file_content) == 0:
            raise ValueError("File is empty")

        # 2. Extension validation
        _, ext = os.path.splitext(filename.lower())
        if ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
            raise ValueError(
                "Unsupported file type. Supported formats: PDF, DOCX, XLSX, CSV, TXT, JSON, XML, HTML, MD."
            )

        # 3. Format-specific magic bytes validation
        if ext == ".pdf" and not file_content.startswith(b"%PDF"):
            raise ValueError("Invalid PDF format. Magic bytes do not match %PDF signature.")
        elif ext in (".docx", ".xlsx") and not file_content.startswith(b"PK\x03\x04"):
            raise ValueError(f"Invalid {ext[1:].upper()} format. File is missing standard Office Open XML header signature.")

    def upload_document(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        batch_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Ingests a document, performs duplicate detection, saves it to storage,
        registers it in the database, and schedules the parsing task.
        Handles concurrency race conditions via PostgreSQL constraints.
        If batch_id is omitted, creates a 1-item IngestionBatch for aggregate tracking.
        """
        # Validate input
        self.validate_file(file_content, filename)

        # Compute SHA-256 hash
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Infer canonical MIME type if generic/missing
        _, ext = os.path.splitext(filename.lower())
        canonical_mime = EXTENSION_TO_MIME_TYPE.get(ext, mime_type or "application/octet-stream")

        # Ensure target IngestionBatch exists in database
        from app.models import IngestionBatch, BatchStatus
        batch = self.session.get(IngestionBatch, batch_id) if batch_id else None
        if not batch:
            batch_id = batch_id or uuid.uuid4()
            batch = IngestionBatch(
                id=batch_id,
                name=filename,
                status=BatchStatus.processing,
                total_files=1,
                processed_files=0,
                completed_files=0,
                failed_files=0,
                started_at=datetime.now(timezone.utc)
            )
            self.session.add(batch)
            self.session.flush()

        # Check for existing document in database
        existing_doc = self.doc_repo.get_by_file_hash(file_hash)
        if existing_doc:
            return self._handle_existing_document(existing_doc, batch_id=batch_id)

        # If new, create document, job, and step within a transaction block
        doc_id = uuid.uuid4()
        storage_key = f"documents/original/{doc_id}{ext}"
        
        # Write binary file to object storage
        self.storage.upload_file(file_content, storage_key)

        document = Document(
            id=doc_id,
            filename=filename,
            storage_backend=settings.STORAGE_PROVIDER,
            storage_key=storage_key,
            file_hash=file_hash,
            mime_type=canonical_mime,
            file_size=len(file_content),
            batch_id=batch_id,
            status=DocumentStatus.uploaded
        )

        job_id = uuid.uuid4()
        job = ProcessingJob(
            id=job_id,
            batch_id=batch_id,
            total_items=1,
            status=JobStatus.queued,
            current_stage="parsing"
        )

        step_id = uuid.uuid4()
        step = ProcessingStep(
            id=step_id,
            job_id=job_id,
            document_id=doc_id,
            stage=ProcessingStage.parsing,
            status=StepStatus.queued
        )

        self.session.add(document)
        self.session.add(job)
        self.session.add(step)
        self.session.flush()

        from app.models import IngestionBatchItem, BatchItemStatus
        batch_item = IngestionBatchItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            document_id=doc_id,
            job_id=job_id,
            status=BatchItemStatus.queued,
            cached=False
        )
        self.session.add(batch_item)

        try:
            self.session.commit()
        except IntegrityError:
            # Handle concurrent upload race condition gracefully by picking up the database winner
            self.session.rollback()
            # Clean up the file uploaded to storage since we're discarding this record
            try:
                self.storage.delete_file(storage_key)
            except Exception:
                pass
            winner_doc = self.doc_repo.get_by_file_hash(file_hash)
            if winner_doc:
                return self._handle_existing_document(winner_doc, batch_id=batch_id)
            raise

        self.session.refresh(document)
        self.session.refresh(job)

        from app.services.batch import BatchService
        BatchService(self.session).update_batch_progress(batch_id)

        # Trigger Celery worker task execution with inline fallback
        from app.workers.tasks.document_processing import process_document_task
        try:
            process_document_task.delay(str(doc_id), str(job_id), str(step_id))
        except Exception as err:
            logger.info(f"Worker queue dispatch bypassed ({err}), executing process_document_task directly.")
            process_document_task(str(doc_id), str(job_id), str(step_id))

        return {
            "document_id": document.id,
            "job_id": job.id,
            "batch_id": batch_id,
            "status": "queued",
            "cached": False
        }

    def force_reprocess(self, document_id: uuid.UUID) -> Dict[str, Any]:
        """
        Creates a new ProcessingJob and ProcessingStep, forcing reprocessing of an
        existing document, preserving all historical jobs/steps in the process log.
        """
        document = self.doc_repo.get_by_id(document_id)
        if not document:
            raise ValueError(f"Document with ID {document_id} not found")

        job_id = uuid.uuid4()
        job = ProcessingJob(
            id=job_id,
            batch_id=document.batch_id,
            total_items=1,
            status=JobStatus.queued,
            current_stage="parsing"
        )

        step_id = uuid.uuid4()
        step = ProcessingStep(
            id=step_id,
            job_id=job_id,
            document_id=document.id,
            stage=ProcessingStage.parsing,
            status=StepStatus.queued
        )

        # Reset document status
        document.status = DocumentStatus.uploaded
        document.updated_at = datetime.now(timezone.utc)
        self.session.add(document)
        self.session.add(job)
        self.session.add(step)
        self.session.flush()

        if document.batch_id:
            from app.models import IngestionBatchItem, BatchItemStatus
            batch_item = IngestionBatchItem(
                id=uuid.uuid4(),
                batch_id=document.batch_id,
                document_id=document.id,
                job_id=job_id,
                status=BatchItemStatus.queued,
                cached=True
            )
            self.session.add(batch_item)

        self.session.commit()

        # Trigger background execution with inline fallback
        from app.workers.tasks.document_processing import process_document_task
        try:
            process_document_task.delay(str(document_id), str(job_id), str(step_id))
        except Exception as err:
            logger.info(f"Worker queue dispatch bypassed ({err}), executing process_document_task directly.")
            process_document_task(str(document_id), str(job_id), str(step_id))

        return {
            "document_id": document.id,
            "job_id": job.id,
            "status": "queued",
            "reprocessed": True
        }

    def _handle_existing_document(self, doc: Document, batch_id: uuid.UUID) -> Dict[str, Any]:
        """
        Resolves duplicate uploads: returns already completed details, or active job pointer,
        and links an IngestionBatchItem to the batch.
        """
        from app.models import IngestionBatchItem, BatchItemStatus, ProcessingStep

        # Find the latest step for this document
        stmt = select(ProcessingStep).where(ProcessingStep.document_id == doc.id).order_by(ProcessingStep.created_at.desc())
        latest_step = self.session.exec(stmt).first()
        job_id = latest_step.job_id if latest_step else None

        if doc.status == DocumentStatus.processed:
            batch_item = IngestionBatchItem(
                id=uuid.uuid4(),
                batch_id=batch_id,
                document_id=doc.id,
                job_id=job_id,
                status=BatchItemStatus.completed,
                cached=True,
                completed_at=datetime.now(timezone.utc)
            )
            self.session.add(batch_item)
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()

            from app.services.batch import BatchService
            BatchService(self.session).update_batch_progress(batch_id)

            return {
                "document_id": doc.id,
                "job_id": job_id,
                "batch_id": batch_id,
                "status": "already_processed",
                "cached": True
            }
        
        if doc.status in [DocumentStatus.uploaded, DocumentStatus.parsing]:
            batch_item = IngestionBatchItem(
                id=uuid.uuid4(),
                batch_id=batch_id,
                document_id=doc.id,
                job_id=job_id,
                status=BatchItemStatus.processing,
                cached=True
            )
            self.session.add(batch_item)
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()

            from app.services.batch import BatchService
            BatchService(self.session).update_batch_progress(batch_id)

            return {
                "document_id": doc.id,
                "job_id": job_id,
                "batch_id": batch_id,
                "status": "processing",
                "cached": True
            }

        # If previous attempt failed, schedule a new job for retry
        job_id = uuid.uuid4()
        job = ProcessingJob(
            id=job_id,
            batch_id=batch_id,
            total_items=1,
            status=JobStatus.queued,
            current_stage="parsing"
        )
        step_id = uuid.uuid4()
        step = ProcessingStep(
            id=step_id,
            job_id=job_id,
            document_id=doc.id,
            stage=ProcessingStage.parsing,
            status=StepStatus.queued
        )

        batch_item = IngestionBatchItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            document_id=doc.id,
            job_id=job_id,
            status=BatchItemStatus.queued,
            cached=True
        )

        # Reset document status to prepare
        doc.status = DocumentStatus.uploaded
        self.session.add(doc)
        self.session.add(job)
        self.session.add(step)
        self.session.flush()

        self.session.add(batch_item)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()

        from app.services.batch import BatchService
        BatchService(self.session).update_batch_progress(batch_id)

        from app.workers.tasks.document_processing import process_document_task
        process_document_task.delay(str(doc.id), str(job_id), str(step_id))

        return {
            "document_id": doc.id,
            "job_id": job.id,
            "batch_id": batch_id,
            "status": "queued",
            "cached": True
        }
