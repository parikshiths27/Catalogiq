"""
Celery document processing task.

Implements the two-stage asynchronous pipeline:
  Stage 1 — ParsingStage    (process_document_task)
  Stage 2 — ExtractionStage (triggered automatically after parsing succeeds)

Each stage creates its own ProcessingStep record for independent tracking.
Parsing failures do not prevent the extraction step from being attempted on retry.
Extraction failures do not roll back parsing results.
"""
import uuid
import logging
import os
from typing import Optional
from datetime import datetime, timezone
from celery.exceptions import Retry
from sqlmodel import Session

from app.workers.celery_app import celery_app
from app.db.session import engine
from app.models import (
    Document, DocumentStatus, ProcessingJob, ProcessingStep,
    JobStatus, ProcessingStage, StepStatus,
)
from app.services.pipeline import (
    DocumentProcessingService,
    TransientProcessingError,
    NonRetryableProcessingError,
    ExtractionConfigurationError,
)
from app.services.parser import DoclingParser, MultiFormatParser, MockParser

logger = logging.getLogger(__name__)


def get_parser():
    """
    Dynamically loads the appropriate document parser.
    MockParser is used in tests (TEST_MOCK_PARSER=true env var).
    MultiFormatParser is used at runtime.
    """
    if os.getenv("TEST_MOCK_PARSER") == "true":
        return MockParser()
    return MultiFormatParser()


def _update_batch_progress_if_needed(session: Session, document: Optional[Document], error_message: Optional[str] = None) -> None:
    """Updates all parent IngestionBatchItem records and recalculates parent IngestionBatch progress."""
    if not document:
        return

    from app.models import IngestionBatchItem, BatchItemStatus, ProcessingJob, JobStatus
    from app.services.batch import BatchService
    from sqlmodel import select, or_

    conditions = [IngestionBatchItem.document_id == document.id]
    if document.batch_id:
        conditions.append(IngestionBatchItem.batch_id == document.batch_id)

    stmt = select(IngestionBatchItem).where(or_(*conditions))
    items = session.exec(stmt).all()

    affected_batch_ids = set()
    if document.batch_id:
        affected_batch_ids.add(document.batch_id)

    now = datetime.now(timezone.utc)
    for item in items:
        affected_batch_ids.add(item.batch_id)
        linked_job = session.get(ProcessingJob, item.job_id) if item.job_id else None

        if document.status == DocumentStatus.failed or (linked_job and linked_job.status == JobStatus.failed):
            item.status = BatchItemStatus.failed
            item.error_message = error_message or (linked_job.error_message if linked_job else "Document processing failed")
        elif document.status == DocumentStatus.processed and (not linked_job or linked_job.status == JobStatus.completed):
            item.status = BatchItemStatus.completed
            item.error_message = None
            if not item.completed_at:
                item.completed_at = now
        else:
            item.status = BatchItemStatus.processing

        item.updated_at = now
        session.add(item)

    session.commit()

    batch_service = BatchService(session)
    for b_id in affected_batch_ids:
        try:
            batch_service.update_batch_progress(b_id)
        except Exception as e:
            logger.warning(f"Failed to update batch progress for batch {b_id}: {e}")


def get_llm_provider():
    """
    Returns the configured LLM provider from settings.
    Fails clearly if misconfigured — never falls back silently.
    """
    from app.services.llm.factory import get_llm_provider as _factory
    return _factory()


def _create_extraction_step(session: Session, job_id: uuid.UUID, document_id: uuid.UUID) -> ProcessingStep:
    """Creates and persists a new ProcessingStep for the extraction stage."""
    step = ProcessingStep(
        id=uuid.uuid4(),
        job_id=job_id,
        document_id=document_id,
        stage=ProcessingStage.extracting,
        status=StepStatus.queued,
    )
    session.add(step)
    session.commit()
    session.refresh(step)
    return step


def _dispatch_next_task(task_func, *args):
    """Dispatches task via Celery worker queue with seamless inline fallback."""
    try:
        task_func.delay(*args)
    except Exception as err:
        logger.info(f"Worker queue dispatch bypassed ({err}), executing {task_func.__name__} directly.")
        task_func(*args)


@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, document_id_str: str, job_id_str: str, step_id_str: str) -> None:
    """
    Stage 1: Document parsing Celery task.

    On success: automatically triggers the extraction task for Stage 2.
    On transient failure: retries up to 3 times with 10s delay.
    On non-retryable failure: marks document, step, and job as failed.
    """
    doc_id = uuid.UUID(document_id_str)
    job_id = uuid.UUID(job_id_str)
    step_id = uuid.UUID(step_id_str)

    logger.info(f"[Stage 1: Parsing] Starting for Doc: {doc_id}, Job: {job_id}")

    with Session(engine) as session:
        document = session.get(Document, doc_id)
        job = session.get(ProcessingJob, job_id)
        step = session.get(ProcessingStep, step_id)

        if not document or not job or not step:
            logger.error(
                f"Task entities not found. "
                f"doc={document is not None}, job={job is not None}, step={step is not None}"
            )
            return

        # Idempotency: if already processed, create extraction step and trigger it
        if document.status == DocumentStatus.processed and document.parsed_storage_key:
            logger.info(f"Document {doc_id} is already parsed. Skipping to extraction.")
            now = datetime.now(timezone.utc)
            step.status = StepStatus.completed
            step.completed_at = now
            step.updated_at = now
            session.add(step)
            session.commit()

            extraction_step = _create_extraction_step(session, job_id, doc_id)
            _dispatch_next_task(
                extract_document_task,
                document_id_str, job_id_str, str(extraction_step.id)
            )
            return

        try:
            parser = get_parser()
            processor = DocumentProcessingService(session, parser=parser)
            processor.process_document(doc_id, job_id, step_id)
            logger.info(f"[Stage 1: Parsing] Completed for Doc: {doc_id}")

            # Trigger Stage 2: Extraction
            session.refresh(document)
            if document.status == DocumentStatus.processed:
                extraction_step = _create_extraction_step(session, job_id, doc_id)
                _dispatch_next_task(
                    extract_document_task,
                    document_id_str, job_id_str, str(extraction_step.id)
                )
                logger.info(
                    f"[Stage 2: Extraction] Queued for Doc: {doc_id}, "
                    f"ExtractionStep: {extraction_step.id}"
                )

        except TransientProcessingError as e:
            logger.warning(f"[Stage 1: Parsing] Transient error (attempt {self.request.retries + 1}): {e}")
            now = datetime.now(timezone.utc)
            step.attempt_count = self.request.retries + 2
            step.updated_at = now
            session.add(step)
            session.commit()
            try:
                self.retry(exc=e, countdown=10)
            except Retry:
                raise

        except Exception as e:
            logger.error(f"[Stage 1: Parsing] Fatal error for Doc: {doc_id}: {e}")
            now = datetime.now(timezone.utc)

            document.status = DocumentStatus.failed
            document.updated_at = now

            step.status = StepStatus.failed
            step.error_message = str(e)[:500]
            step.completed_at = now
            step.updated_at = now

            job.status = JobStatus.failed
            job.failed_items = 1
            job.error_message = str(e)[:500]
            job.completed_at = now
            job.updated_at = now

            session.add(document)
            session.add(step)
            session.add(job)
            session.commit()

            _update_batch_progress_if_needed(session, document)


def _create_validation_step(session: Session, job_id: uuid.UUID, document_id: uuid.UUID) -> ProcessingStep:
    """Creates and persists a new ProcessingStep for the validation stage."""
    step = ProcessingStep(
        id=uuid.uuid4(),
        job_id=job_id,
        document_id=document_id,
        stage=ProcessingStage.validating,
        status=StepStatus.queued,
    )
    session.add(step)
    session.commit()
    session.refresh(step)
    return step


def _create_enrichment_step(session: Session, job_id: uuid.UUID, document_id: uuid.UUID) -> ProcessingStep:
    """Creates and persists a new ProcessingStep for the enrichment stage."""
    step = ProcessingStep(
        id=uuid.uuid4(),
        job_id=job_id,
        document_id=document_id,
        stage=ProcessingStage.enriching,
        status=StepStatus.queued,
    )
    session.add(step)
    session.commit()
    session.refresh(step)
    return step


@celery_app.task(bind=True, max_retries=2)
def extract_document_task(
    self, document_id_str: str, job_id_str: str, step_id_str: str
) -> None:
    """
    Stage 2: AI product extraction Celery task.

    On success: triggers validate_document_task for Stage 3.
    """
    doc_id = uuid.UUID(document_id_str)
    job_id = uuid.UUID(job_id_str)
    step_id = uuid.UUID(step_id_str)

    logger.info(f"[Stage 2: Extraction] Starting for Doc: {doc_id}, Job: {job_id}")

    with Session(engine) as session:
        document = session.get(Document, doc_id)
        job = session.get(ProcessingJob, job_id)
        step = session.get(ProcessingStep, step_id)

        if not document or not job or not step:
            logger.error(
                f"[Stage 2] Extraction task entities not found. "
                f"doc={document is not None}, job={job is not None}, step={step is not None}"
            )
            return

        try:
            provider = get_llm_provider()
            processor = DocumentProcessingService(session, llm_provider=provider)
            processor.extract_document(doc_id, job_id, step_id)
            logger.info(f"[Stage 2: Extraction] Completed successfully for Doc: {doc_id}")

            session.refresh(job)
            session.refresh(document)
            if job.status == JobStatus.completed or document.status == DocumentStatus.processed:
                logger.info(f"[Stage 2: Extraction] Tabular catalog fully processed and enriched for Doc: {doc_id}.")
                return

            # Trigger Stage 3: Validation (for prose / PDF documents)
            val_step = _create_validation_step(session, job_id, doc_id)
            _dispatch_next_task(validate_document_task, document_id_str, job_id_str, str(val_step.id))
            logger.info(f"[Stage 3: Validation] Queued for Doc: {doc_id}, Step: {val_step.id}")

        except ExtractionConfigurationError as e:
            logger.error(f"[Stage 2: Extraction] Configuration error (non-retryable): {e}")
            now = datetime.now(timezone.utc)
            step.status = StepStatus.failed
            step.error_message = f"[ConfigurationError] {str(e)[:400]}"
            step.completed_at = now
            step.updated_at = now
            job.status = JobStatus.failed
            job.error_message = f"LLM configuration error: {str(e)[:400]}"
            job.failed_items = 1
            job.completed_at = now
            job.updated_at = now
            document.status = DocumentStatus.failed
            document.updated_at = now
            session.add(document)
            session.add(step)
            session.add(job)
            session.commit()
            _update_batch_progress_if_needed(session, document, error_message=str(e)[:400])

        except TransientProcessingError as e:
            logger.warning(f"[Stage 2: Extraction] Transient error (attempt {self.request.retries + 1}): {e}")
            now = datetime.now(timezone.utc)
            step.attempt_count = self.request.retries + 2
            step.updated_at = now
            session.add(step)
            session.commit()
            try:
                self.retry(exc=e, countdown=15)
            except Retry:
                raise

        except Exception as e:
            logger.error(f"[Stage 2: Extraction] Fatal error for Doc: {doc_id}: {e}", exc_info=True)
            now = datetime.now(timezone.utc)
            step.status = StepStatus.failed
            step.error_message = str(e)[:500]
            step.completed_at = now
            step.updated_at = now
            job.status = JobStatus.failed
            job.failed_items = 1
            job.error_message = str(e)[:500]
            job.completed_at = now
            job.updated_at = now
            document.status = DocumentStatus.failed
            document.updated_at = now
            session.add(document)
            session.add(step)
            session.add(job)
            session.commit()

            _update_batch_progress_if_needed(session, document, error_message=str(e)[:500])


@celery_app.task(bind=True, max_retries=2)
def validate_document_task(
    self, document_id_str: str, job_id_str: str, step_id_str: str
) -> None:
    """
    Stage 3: Validation Celery task.

    Runs independently. On success: triggers Stage 4 (Enrichment).
    """
    doc_id = uuid.UUID(document_id_str)
    job_id = uuid.UUID(job_id_str)
    step_id = uuid.UUID(step_id_str)

    logger.info(f"[Stage 3: Validation] Starting for Doc: {doc_id}, Job: {job_id}")

    with Session(engine) as session:
        document = session.get(Document, doc_id)
        job = session.get(ProcessingJob, job_id)
        step = session.get(ProcessingStep, step_id)

        if not document or not job or not step:
            logger.error("[Stage 3] Validation task entities not found.")
            return

        try:
            provider = get_llm_provider()
            processor = DocumentProcessingService(session, llm_provider=provider)
            processor.validate_document(doc_id, job_id, step_id)
            logger.info(f"[Stage 3: Validation] Completed successfully for Doc: {doc_id}")

            # Trigger Stage 4: Enrichment
            enrich_step = _create_enrichment_step(session, job_id, doc_id)
            _dispatch_next_task(enrich_document_task, document_id_str, job_id_str, str(enrich_step.id))
            logger.info(f"[Stage 4: Enrichment] Queued for Doc: {doc_id}, Step: {enrich_step.id}")

        except Exception as e:
            logger.error(f"[Stage 3: Validation] Error for Doc {doc_id}: {e}", exc_info=True)
            now = datetime.now(timezone.utc)
            step.status = StepStatus.failed
            step.error_message = str(e)[:500]
            step.completed_at = now
            step.updated_at = now
            job.status = JobStatus.failed
            job.error_message = str(e)[:500]
            job.completed_at = now
            job.updated_at = now
            document.status = DocumentStatus.failed
            document.updated_at = now
            session.add(document)
            session.add(step)
            session.add(job)
            session.commit()

            _update_batch_progress_if_needed(session, document, error_message=str(e)[:500])


@celery_app.task(bind=True, max_retries=2)
def enrich_document_task(
    self, document_id_str: str, job_id_str: str, step_id_str: str
) -> None:
    """
    Stage 4: AI Commerce Enrichment Celery task.

    Final stage. On success: marks processing job as completed.
    """
    doc_id = uuid.UUID(document_id_str)
    job_id = uuid.UUID(job_id_str)
    step_id = uuid.UUID(step_id_str)

    logger.info(f"[Stage 4: Enrichment] Starting for Doc: {doc_id}, Job: {job_id}")

    with Session(engine) as session:
        document = session.get(Document, doc_id)
        job = session.get(ProcessingJob, job_id)
        step = session.get(ProcessingStep, step_id)

        if not document or not job or not step:
            logger.error("[Stage 4] Enrichment task entities not found.")
            return

        try:
            provider = get_llm_provider()
            processor = DocumentProcessingService(session, llm_provider=provider)
            processor.enrich_document(doc_id, job_id, step_id)
            logger.info(f"[Stage 4: Enrichment] Completed successfully for Doc: {doc_id}")
            
            document.status = DocumentStatus.processed
            document.updated_at = datetime.now(timezone.utc)
            session.add(document)
            session.commit()

            _update_batch_progress_if_needed(session, document)

        except TransientProcessingError as e:
            logger.warning(f"[Stage 4: Enrichment] Transient error (attempt {self.request.retries + 1}): {e}")
            now = datetime.now(timezone.utc)
            step.attempt_count = self.request.retries + 2
            step.updated_at = now
            session.add(step)
            session.commit()
            try:
                self.retry(exc=e, countdown=15)
            except Retry:
                raise

        except Exception as e:
            logger.error(f"[Stage 4: Enrichment] Error for Doc {doc_id}: {e}", exc_info=True)
            now = datetime.now(timezone.utc)
            step.status = StepStatus.failed
            step.error_message = str(e)[:500]
            step.completed_at = now
            step.updated_at = now
            job.status = JobStatus.failed
            job.error_message = str(e)[:500]
            job.completed_at = now
            job.updated_at = now
            document.status = DocumentStatus.failed
            document.updated_at = now
            session.add(document)
            session.add(step)
            session.add(job)
            session.commit()

            _update_batch_progress_if_needed(session, document, error_message=str(e)[:500])

