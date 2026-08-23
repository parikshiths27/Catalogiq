import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db.session import get_session
from app.models import ProcessingJob, ProcessingStep, JobStatus, StepStatus

router = APIRouter(prefix="/jobs")

# Strongly typed API schemas for job monitoring
class ProcessingStepResponse(BaseModel):
    id: uuid.UUID
    stage: str
    status: str
    attempt_count: int
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class ProcessingJobDetail(BaseModel):
    job_id: uuid.UUID
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    current_stage: str
    error_message: Optional[str]
    steps: List[ProcessingStepResponse]

    class Config:
        from_attributes = True

@router.get("/", response_model=List[ProcessingJob])
def list_jobs(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    session: Session = Depends(get_session)
):
    statement = select(ProcessingJob)
    if status:
        statement = statement.where(ProcessingJob.status == status)
    statement = statement.offset(offset).limit(limit)
    return list(session.exec(statement).all())

@router.get("/{job_id}", response_model=ProcessingJobDetail)
def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found"
        )
    
    # Retrieve steps associated with this job
    stmt = select(ProcessingStep).where(ProcessingStep.job_id == job_id).order_by(ProcessingStep.created_at.asc())
    steps = session.exec(stmt).all()
    
    return ProcessingJobDetail(
        job_id=job.id,
        status=job.status,
        total_items=job.total_items,
        completed_items=job.completed_items,
        failed_items=job.failed_items,
        current_stage=job.current_stage,
        error_message=job.error_message,
        steps=[ProcessingStepResponse.model_validate(s) for s in steps]
    )

@router.post("/{job_id}/retry")
def retry_job(job_id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found"
        )
    
    if job.status != JobStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only failed jobs can be retried. Current status is '{job.status}'"
        )

    # Find the latest step associated with this job
    stmt = select(ProcessingStep).where(ProcessingStep.job_id == job_id).order_by(ProcessingStep.created_at.desc())
    step = session.exec(stmt).first()
    if not step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No steps found for this job to retry"
        )

    # Reset job and step statuses back to queued
    job.status = JobStatus.queued
    job.error_message = None
    job.completed_items = 0
    job.failed_items = 0
    
    step.status = StepStatus.queued
    step.error_message = None
    step.attempt_count += 1
    
    session.add(job)
    session.add(step)
    session.commit()

    # Re-trigger processing according to PROCESSING_MODE
    from app.core.config import settings
    if settings.PROCESSING_MODE.lower() == "inline":
        from app.services.document import DocumentService
        doc_service = DocumentService(session)
        doc_service.process_document_inline(step.document_id, job_id, step.id)
        return {"message": "Job retry executed successfully", "job_id": job_id}
    else:
        from app.workers.tasks.document_processing import process_document_task
        process_document_task.delay(str(step.document_id), str(job_id), str(step.id))
        return {"message": "Job retry scheduled successfully", "job_id": job_id}
