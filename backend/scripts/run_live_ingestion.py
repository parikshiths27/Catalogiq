"""
Live Ingestion Runner for CatalogIQ Production Pipeline.
Runs the live 2-row test and 200-row dataset against the database and reports exact entity counts.
"""
import os
import sys
import uuid
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select, func
from app.db.session import engine
from app.models import (
    Document,
    DocumentStatus,
    ProcessingJob,
    ProcessingStep,
    ProcessingStage,
    JobStatus,
    StepStatus,
    Product,
    ProductAttribute,
    AttributeEvidence,
    EnrichmentResult,
    ValidationResult,
    IngestionBatch,
    IngestionBatchItem,
    BatchStatus,
)
from app.services.pipeline import DocumentProcessingService
from app.services.storage import get_storage_service


def run_live_test(csv_path: str, limit_rows: int = 200) -> None:
    storage = get_storage_service()

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    header = lines[0]
    data_lines = lines[1:limit_rows + 1]
    test_csv_content = header + "".join(data_lines)
    test_csv_bytes = test_csv_content.encode("utf-8")

    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    step_id = uuid.uuid4()
    batch_id = uuid.uuid4()

    storage_key = f"documents/raw/{doc_id}.csv"
    storage.upload_file(test_csv_bytes, storage_key)

    with Session(engine) as session:
        doc = Document(
            id=doc_id,
            filename=f"Live_Catalog_Ingest_{limit_rows}_Rows.csv",
            storage_backend="local",
            storage_key=storage_key,
            file_hash=f"live_hash_{limit_rows}_{uuid.uuid4().hex[:6]}",
            content_hash=f"live_hash_{limit_rows}_{uuid.uuid4().hex[:6]}",
            mime_type="text/csv",
            file_size=len(test_csv_bytes),
            batch_id=batch_id,
            status=DocumentStatus.uploaded,
        )
        batch = IngestionBatch(
            id=batch_id,
            name=f"Live Ingest Batch ({limit_rows} rows)",
            status=BatchStatus.processing,
            total_files=1,
            processed_files=0,
            failed_files=0,
        )
        batch_item = IngestionBatchItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            document_id=doc_id,
            job_id=job_id,
            status=BatchStatus.processing,
        )
        job = ProcessingJob(
            id=job_id,
            batch_id=batch_id,
            total_items=1,
            status=JobStatus.queued,
            current_stage="parsing",
        )
        step = ProcessingStep(
            id=step_id,
            job_id=job_id,
            document_id=doc_id,
            stage=ProcessingStage.parsing,
            status=StepStatus.queued,
        )
        session.add(batch)
        session.add(doc)
        session.flush()
        session.add(job)
        session.flush()
        session.add(batch_item)
        session.add(step)
        session.commit()

        print(f"[*] Starting live pipeline for {limit_rows} rows (Doc: {doc_id})...")
        
        # Stage 1: Parsing
        service = DocumentProcessingService(session)
        service.process_document(doc_id, job_id, step_id)

        # Stage 2: Tabular Extraction + Enrichment
        extract_step = ProcessingStep(
            id=uuid.uuid4(),
            job_id=job_id,
            document_id=doc_id,
            stage=ProcessingStage.extracting,
            status=StepStatus.queued,
        )
        session.add(extract_step)
        session.commit()

        service.extract_document(doc_id, job_id, extract_step.id)

        # Query and display counts
        product_count = session.exec(select(func.count()).select_from(Product)).one()
        attr_count = session.exec(select(func.count()).select_from(ProductAttribute)).one()
        enrich_count = session.exec(select(func.count()).select_from(EnrichmentResult)).one()
        val_count = session.exec(select(func.count()).select_from(ValidationResult)).one()
        ev_count = session.exec(select(func.count()).select_from(AttributeEvidence)).one()

        verified_count = session.exec(
            select(func.count()).select_from(Product).where(Product.status == "verified")
        ).one()
        review_count = session.exec(
            select(func.count()).select_from(Product).where(Product.status == "needs_review")
        ).one()

        print(f"\n[+] LIVE DATABASE COUNTS AFTER {limit_rows}-ROW RUN:")
        print(f"    - Products:           {product_count} (Verified: {verified_count}, Needs Review: {review_count})")
        print(f"    - Product Attributes: {attr_count}")
        print(f"    - Enrichment Results: {enrich_count}")
        print(f"    - Validation Results: {val_count}")
        print(f"    - Evidence Records:   {ev_count}")


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "Unihack_ Sample Dataset - Input (1).csv"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    run_live_test(csv_file, limit)
