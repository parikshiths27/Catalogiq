import uuid
import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlmodel import Session
from pydantic import BaseModel

from app.db.session import get_session
from app.models import Document, DocumentStatus
from app.repositories import DocumentRepository
from app.services.document import DocumentService
from app.services.storage import get_storage_service

router = APIRouter(prefix="/documents")

# Typed upload response
class UploadResponse(BaseModel):
    document_id: uuid.UUID
    job_id: Optional[uuid.UUID]
    batch_id: Optional[uuid.UUID] = None
    status: str
    cached: bool

class ReprocessResponse(BaseModel):
    document_id: uuid.UUID
    job_id: uuid.UUID
    status: str
    reprocessed: bool

class BatchDocumentResult(BaseModel):
    filename: str
    document_id: uuid.UUID
    job_id: Optional[uuid.UUID]
    status: str
    cached: bool

class BatchRejectedResult(BaseModel):
    filename: str
    error: str

class BatchUploadResponse(BaseModel):
    batch_id: uuid.UUID
    batch_name: Optional[str]
    status: str
    total_files: int
    accepted_count: int
    rejected_count: int
    documents: List[BatchDocumentResult]
    rejected: List[BatchRejectedResult]

class BatchDocumentStatusResponse(BaseModel):
    document_id: Optional[uuid.UUID] = None
    filename: str
    status: str
    job_id: Optional[uuid.UUID] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    cached: Optional[bool] = False
    error_message: Optional[str] = None
    updated_at: Optional[Any] = None

class BatchDetailResponse(BaseModel):
    batch_id: uuid.UUID
    name: Optional[str]
    status: str
    total_files: int
    processed_files: int
    completed_files: int
    failed_files: int
    processing_files: int
    progress_percentage: float
    created_at: Any
    updated_at: Any
    completed_at: Optional[Any]
    documents: List[BatchDocumentStatusResponse]

@router.get("/", response_model=List[Document])
def list_documents(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    repo = DocumentRepository(session)
    return repo.list_documents(limit=limit, offset=offset, status=status)

@router.delete("/clear-all")
def clear_all_documents(session: Session = Depends(get_session)):
    """
    Clears all documents and their associated processing jobs/steps from the database.
    Does NOT delete the products that were created from those documents.
    """
    from sqlmodel import select as sel
    from app.models import ProcessingStep, ProcessingJob, IngestionBatch

    # Delete processing steps first (FK dependency)
    steps = session.exec(sel(ProcessingStep)).all()
    for s in steps:
        session.delete(s)

    # Delete processing jobs
    jobs = session.exec(sel(ProcessingJob)).all()
    for j in jobs:
        session.delete(j)

    # Delete documents
    docs = session.exec(sel(Document)).all()
    doc_count = len(docs)
    for d in docs:
        session.delete(d)

    # Delete ingestion batches
    batches = session.exec(sel(IngestionBatch)).all()
    for b in batches:
        session.delete(b)

    session.commit()

    return {
        "status": "cleared",
        "documents_removed": doc_count,
        "message": f"Successfully cleared {doc_count} documents and all associated processing records.",
    }

@router.get("/{document_id}", response_model=Document)
def get_document(document_id: uuid.UUID, session: Session = Depends(get_session)):
    repo = DocumentRepository(session)
    doc = repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found"
        )
    return doc

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    service = DocumentService(session)
    try:
        file_content = file.file.read()
        res = service.upload_document(
            file_content=file_content,
            filename=file.filename,
            mime_type=file.content_type or "application/octet-stream"
        )
        return UploadResponse(
            document_id=res["document_id"],
            job_id=res.get("job_id"),
            batch_id=res.get("batch_id"),
            status=res["status"],
            cached=res.get("cached", False)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File ingestion failed: {str(e)}"
        )

@router.post("/{document_id}/reprocess", response_model=ReprocessResponse)
def reprocess_document(
    document_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    service = DocumentService(session)
    try:
        res = service.force_reprocess(document_id)
        return ReprocessResponse(
            document_id=res["document_id"],
            job_id=res["job_id"],
            status=res["status"],
            reprocessed=res.get("reprocessed", True)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reprocessing failed: {str(e)}"
        )

@router.get("/{document_id}/parsed")
def get_parsed_document(
    document_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    repo = DocumentRepository(session)
    doc = repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found"
        )
    
    # 1. Check if parsed intermediate JSON is already stored durably in PostgreSQL metadata
    if doc.metadata_json:
        if isinstance(doc.metadata_json.get("intermediate_json"), dict):
            return doc.metadata_json["intermediate_json"]
        if isinstance(doc.metadata_json.get("parsed_content"), dict):
            return doc.metadata_json["parsed_content"]

    # 2. Check if the document was never parsed
    if not doc.parsed_storage_key and doc.status != DocumentStatus.processed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document status is '{doc.status}'. It has not been successfully parsed yet."
        )

    # 3. Download the structured intermediate representation from storage
    storage = get_storage_service()
    if doc.parsed_storage_key:
        try:
            file_bytes = storage.download_file(doc.parsed_storage_key)
            parsed_data = json.loads(file_bytes.decode("utf-8"))
            # Backfill durable database metadata for future queries
            meta = dict(doc.metadata_json or {})
            meta["intermediate_json"] = parsed_data
            doc.metadata_json = meta
            session.add(doc)
            session.commit()
            return parsed_data
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Error reading parsed storage file for document {document_id}: {e}")

    # 4. Check if raw source file is available to re-parse on-demand
    if doc.storage_key:
        try:
            raw_bytes = storage.download_file(doc.storage_key)
            import os
            from app.services.parser import DoclingParser, ExcelParser, CSVParser, JSONParser, XMLParser, TextParser, HTMLParser
            ext = os.path.splitext(doc.filename.lower())[1] if doc.filename else ".pdf"
            
            if ext in (".xlsx", ".xls"):
                parser = ExcelParser()
            elif ext in (".csv", ".tsv"):
                parser = CSVParser()
            elif ext == ".json":
                parser = JSONParser()
            elif ext in (".xml", ".xaml"):
                parser = XMLParser()
            elif ext in (".html", ".htm"):
                parser = HTMLParser()
            elif ext in (".txt", ".text", ".md", ".log"):
                parser = TextParser()
            else:
                parser = DoclingParser()

            parsed_data = parser.parse(raw_bytes, filename=doc.filename)
            parsed_data["document_id"] = str(document_id)
            parsed_data["parser"] = {"name": parser.__class__.__name__, "version": getattr(parser, "version", "1.0.0")}
            
            # Save durably to DB
            meta = dict(doc.metadata_json or {})
            meta["intermediate_json"] = parsed_data
            doc.metadata_json = meta
            session.add(doc)
            session.commit()
            return parsed_data
        except Exception as e:
            logger.warning(f"Failed to re-parse document on demand: {e}")

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Intermediate representation artifact not found for document {document_id}. The document may need to be reprocessed."
    )
@router.get("/{document_id}/extracted")
def get_extracted_document(
    document_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """
    Returns the extraction summary for a document (product + attributes count).
    The full product data is available via GET /api/v1/products/{product_id}.
    """
    repo = DocumentRepository(session)
    doc = repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found"
        )

    extraction_key = f"documents/extracted/{document_id}.json"
    storage = get_storage_service()
    try:
        file_bytes = storage.download_file(extraction_key)
        return json.loads(file_bytes.decode("utf-8"))
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Extraction results not yet available for this document. "
                   "Ensure the document has been processed through the extraction stage."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load extraction results: {str(e)}"
        )

@router.post("/upload-batch", response_model=BatchUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_batch(
    files: Optional[List[UploadFile]] = File(None),
    zip_file: Optional[UploadFile] = File(None),
    batch_name: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    from app.services.batch import BatchService
    service = BatchService(session)
    try:
        if zip_file:
            zip_bytes = zip_file.file.read()
            res = service.create_batch_from_zip(zip_bytes, zip_file.filename)
        elif files:
            file_tuples = []
            for f in files:
                content = f.file.read()
                file_tuples.append((f.filename, content, f.content_type or "application/octet-stream"))
            res = service.create_batch_from_files(file_tuples, batch_name=batch_name)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'files' (multi-file) or 'zip_file' must be provided."
            )
        return BatchUploadResponse(**res)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch upload failed: {str(e)}"
        )

@router.get("/batches/list", response_model=List[BatchDetailResponse])
@router.get("/batches", response_model=List[BatchDetailResponse])
def list_batches(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    from app.services.batch import BatchService
    from app.models import IngestionBatch
    from sqlmodel import select

    stmt = select(IngestionBatch)
    if status:
        stmt = stmt.where(IngestionBatch.status == status)
    stmt = stmt.order_by(IngestionBatch.created_at.desc()).offset(offset).limit(limit)
    batches = session.exec(stmt).all()

    service = BatchService(session)
    return [BatchDetailResponse(**service.get_batch_status(b.id)) for b in batches]

@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
def get_batch(
    batch_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    from app.services.batch import BatchService
    service = BatchService(session)
    try:
        res = service.get_batch_status(batch_id)
        return BatchDetailResponse(**res)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve batch status: {str(e)}"
        )
