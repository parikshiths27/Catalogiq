import uuid
import zipfile
import io
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlmodel import Session, select

from app.models import (
    IngestionBatch, BatchStatus, IngestionBatchItem, BatchItemStatus,
    Document, DocumentStatus, ProcessingJob, ProcessingStep, JobStatus, StepStatus
)
from app.services.document import DocumentService
from app.core.constants import SUPPORTED_DOCUMENT_EXTENSIONS, EXTENSION_TO_MIME_TYPE

logger = logging.getLogger(__name__)

class BatchService:
    def __init__(self, session: Session):
        self.session = session
        self.doc_service = DocumentService(session)

    def create_batch_from_files(
        self,
        files: List[Tuple[str, bytes, str]],  # List of (filename, file_content, mime_type)
        batch_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new IngestionBatch and registers multiple uploaded files under it.
        Processes each file independently; partial failures in individual files
        do not abort the rest of the batch.
        """
        if not files:
            raise ValueError("No files provided for batch processing")

        batch_id = uuid.uuid4()
        batch_name = batch_name or f"Batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        batch = IngestionBatch(
            id=batch_id,
            name=batch_name,
            status=BatchStatus.processing,
            total_files=len(files),
            processed_files=0,
            completed_files=0,
            failed_files=0,
            started_at=datetime.now(timezone.utc)
        )
        self.session.add(batch)
        self.session.commit()

        document_results = []
        rejected_files = []

        for filename, content, mime in files:
            try:
                # Use doc_service to upload document registered under batch_id
                res = self.doc_service.upload_document(
                    file_content=content,
                    filename=filename,
                    mime_type=mime,
                    batch_id=batch_id
                )
                document_results.append({
                    "filename": filename,
                    "document_id": res["document_id"],
                    "job_id": res.get("job_id"),
                    "status": res["status"],
                    "cached": res.get("cached", False)
                })
            except Exception as e:
                logger.warning(f"File '{filename}' in batch {batch_id} failed ingestion: {e}")
                rejected_files.append({
                    "filename": filename,
                    "error": str(e)
                })
                item = IngestionBatchItem(
                    id=uuid.uuid4(),
                    batch_id=batch_id,
                    document_id=None,
                    job_id=None,
                    status=BatchItemStatus.failed,
                    cached=False,
                    error_message=str(e)
                )
                self.session.add(item)
                self.session.commit()

        # Update batch aggregate statistics
        self.session.refresh(batch)
        batch.failed_files += len(rejected_files)
        batch.processed_files += len(rejected_files)
        if batch.processed_files >= batch.total_files:
            if batch.failed_files == batch.total_files:
                batch.status = BatchStatus.failed
            elif batch.failed_files > 0:
                batch.status = BatchStatus.partially_completed
            else:
                batch.status = BatchStatus.completed
            batch.completed_at = datetime.now(timezone.utc)

        self.session.add(batch)
        self.session.commit()

        return {
            "batch_id": batch.id,
            "batch_name": batch.name,
            "status": batch.status,
            "total_files": batch.total_files,
            "accepted_count": len(document_results),
            "rejected_count": len(rejected_files),
            "documents": document_results,
            "rejected": rejected_files
        }

    def create_batch_from_zip(self, zip_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Unpacks a ZIP archive safely with bounded memory consumption and security checks:
        - Archive size limit (MAX_ARCHIVE_SIZE_MB)
        - Extracted total size limit / Zip Bomb protection (MAX_ARCHIVE_EXTRACTED_SIZE_MB)
        - Maximum file count limit (MAX_ARCHIVE_FILES)
        - Single file size limit (MAX_ARCHIVE_FILE_SIZE_MB)
        - Path traversal & absolute path protection
        - Bounded streaming (processes member by member without holding all bytes in RAM)
        """
        from app.core.config import settings

        if not zip_content:
            raise ValueError("ZIP file is empty")

        # 1. Archive compressed size check
        max_zip_bytes = settings.MAX_ARCHIVE_SIZE_MB * 1024 * 1024
        if len(zip_content) > max_zip_bytes:
            raise ValueError(f"ZIP archive size exceeds limit of {settings.MAX_ARCHIVE_SIZE_MB}MB")

        max_extracted_bytes = settings.MAX_ARCHIVE_EXTRACTED_SIZE_MB * 1024 * 1024
        max_single_bytes = settings.MAX_ARCHIVE_FILE_SIZE_MB * 1024 * 1024

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_content))
        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file archive signature")

        infolist = zf.infolist()

        # 2. File count check
        if len(infolist) > settings.MAX_ARCHIVE_FILES:
            raise ValueError(f"ZIP archive contains {len(infolist)} files, exceeding limit of {settings.MAX_ARCHIVE_FILES}")

        # Filter valid target entries and check uncompressed size ceilings
        valid_members = []
        cumulative_extracted = 0

        for member in infolist:
            if member.is_dir() or member.filename.startswith("__MACOSX") or os.path.basename(member.filename).startswith("."):
                continue

            file_basename = os.path.basename(member.filename)
            _, ext = os.path.splitext(file_basename.lower())

            # Path traversal / absolute path check
            if ".." in member.filename or member.filename.startswith("/") or (len(member.filename) > 1 and member.filename[1] == ":"):
                logger.warning(f"Path traversal attempt blocked in ZIP member: {member.filename}")
                continue

            # Nested zip check
            if ext == ".zip":
                logger.warning(f"Nested ZIP member skipped: {member.filename}")
                continue

            if ext in SUPPORTED_DOCUMENT_EXTENSIONS:
                if member.file_size > max_single_bytes:
                    raise ValueError(f"File '{file_basename}' inside ZIP exceeds max file size of {settings.MAX_ARCHIVE_FILE_SIZE_MB}MB")

                cumulative_extracted += member.file_size
                if cumulative_extracted > max_extracted_bytes:
                    raise ValueError(f"ZIP cumulative extracted size exceeds limit of {settings.MAX_ARCHIVE_EXTRACTED_SIZE_MB}MB")

                valid_members.append((member, file_basename, ext))

        if not valid_members:
            raise ValueError("No supported document files found inside ZIP archive")

        batch_id = uuid.uuid4()
        batch_label = os.path.splitext(filename)[0]
        batch_name = f"ZIP_{batch_label}"

        batch = IngestionBatch(
            id=batch_id,
            name=batch_name,
            status=BatchStatus.processing,
            total_files=len(valid_members),
            processed_files=0,
            completed_files=0,
            failed_files=0,
            started_at=datetime.now(timezone.utc)
        )
        self.session.add(batch)
        self.session.commit()

        document_results = []
        rejected_files = []

        # 3. Stream and process members ONE BY ONE (Memory Bounded)
        for member, file_basename, ext in valid_members:
            try:
                content = zf.read(member.filename)
                mime = EXTENSION_TO_MIME_TYPE.get(ext, "application/octet-stream")
                res = self.doc_service.upload_document(
                    file_content=content,
                    filename=file_basename,
                    mime_type=mime,
                    batch_id=batch_id
                )
                document_results.append({
                    "filename": file_basename,
                    "document_id": res["document_id"],
                    "job_id": res.get("job_id"),
                    "status": res["status"],
                    "cached": res.get("cached", False)
                })
            except Exception as e:
                logger.warning(f"File '{file_basename}' in ZIP batch {batch_id} failed ingestion: {e}")
                rejected_files.append({
                    "filename": file_basename,
                    "error": str(e)
                })
                item = IngestionBatchItem(
                    id=uuid.uuid4(),
                    batch_id=batch_id,
                    document_id=None,
                    job_id=None,
                    status=BatchItemStatus.failed,
                    cached=False,
                    error_message=str(e)
                )
                self.session.add(item)
                self.session.commit()

        # Update batch aggregate statistics
        self.session.refresh(batch)
        batch.failed_files += len(rejected_files)
        batch.processed_files += len(rejected_files)
        if batch.processed_files >= batch.total_files:
            if batch.failed_files == batch.total_files:
                batch.status = BatchStatus.failed
            elif batch.failed_files > 0:
                batch.status = BatchStatus.partially_completed
            else:
                batch.status = BatchStatus.completed
            batch.completed_at = datetime.now(timezone.utc)

        self.session.add(batch)
        self.session.commit()

        return {
            "batch_id": batch.id,
            "batch_name": batch.name,
            "status": batch.status,
            "total_files": batch.total_files,
            "accepted_count": len(document_results),
            "rejected_count": len(rejected_files),
            "documents": document_results,
            "rejected": rejected_files
        }

    def get_batch_status(self, batch_id: uuid.UUID) -> Dict[str, Any]:
        """
        Retrieves batch aggregate state and progress metrics for all associated IngestionBatchItems.
        """
        batch = self.session.get(IngestionBatch, batch_id)
        if not batch:
            raise ValueError(f"Batch with ID {batch_id} not found")

        # Query all IngestionBatchItems belonging to this batch
        stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id)
        items = self.session.exec(stmt).all()

        completed_count = sum(1 for item in items if item.status == BatchItemStatus.completed)
        failed_count = sum(1 for item in items if item.status == BatchItemStatus.failed)
        processing_count = sum(1 for item in items if item.status in (BatchItemStatus.queued, BatchItemStatus.processing))

        total = batch.total_files or len(items)
        processed = completed_count + failed_count
        progress_percentage = (processed / total * 100.0) if total > 0 else 0.0

        doc_statuses = []
        for item in items:
            doc = self.session.get(Document, item.document_id) if item.document_id else None
            doc_statuses.append({
                "document_id": item.document_id,
                "filename": doc.filename if doc else "Document",
                "status": item.status,
                "job_id": item.job_id,
                "mime_type": doc.mime_type if doc else None,
                "file_size": doc.file_size if doc else None,
                "cached": item.cached,
                "error_message": item.error_message,
                "updated_at": item.updated_at
            })

        return {
            "batch_id": batch.id,
            "name": batch.name,
            "status": batch.status,
            "total_files": total,
            "processed_files": processed,
            "completed_files": completed_count,
            "failed_files": failed_count,
            "processing_files": processing_count,
            "progress_percentage": round(progress_percentage, 1),
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
            "completed_at": batch.completed_at,
            "documents": doc_statuses
        }

    def update_batch_progress(self, batch_id: uuid.UUID) -> None:
        """
        Recalculates aggregate statistics for a batch from its IngestionBatchItems.
        """
        batch = self.session.get(IngestionBatch, batch_id)
        if not batch:
            return

        stmt = select(IngestionBatchItem).where(IngestionBatchItem.batch_id == batch_id)
        items = self.session.exec(stmt).all()

        completed_count = sum(1 for item in items if item.status == BatchItemStatus.completed)
        failed_count = sum(1 for item in items if item.status == BatchItemStatus.failed)
        total = batch.total_files or len(items)
        processed = completed_count + failed_count

        batch.completed_files = completed_count
        batch.failed_files = failed_count
        batch.processed_files = processed

        if processed >= total and total > 0:
            if failed_count == total:
                batch.status = BatchStatus.failed
            elif failed_count > 0:
                batch.status = BatchStatus.partially_completed
            else:
                batch.status = BatchStatus.completed
            if not batch.completed_at:
                batch.completed_at = datetime.now(timezone.utc)

        batch.updated_at = datetime.now(timezone.utc)
        self.session.add(batch)
        self.session.commit()
