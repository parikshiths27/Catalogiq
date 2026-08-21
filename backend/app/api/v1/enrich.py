"""
CatalogIQ Product Content Enrichment API Router.
Provides endpoints for single-row, batch, CSV/XLSX upload, and benchmark evaluation.
"""
import io
import csv
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.enrichment.pipeline import EnrichmentPipeline
from app.services.enrichment.benchmark import BenchmarkEvaluator

router = APIRouter(prefix="/enrich", tags=["Enrichment"])

_pipeline = EnrichmentPipeline()


class EnrichRowRequest(BaseModel):
    Mfg_Part_Num: Optional[str] = ""
    Part_Desc: Optional[str] = ""
    E1_Brand: Optional[str] = ""
    Unilog_Brand: Optional[str] = ""
    DIB_Brand: Optional[str] = ""
    Part_Manuf: Optional[str] = ""


class BatchEnrichRequest(BaseModel):
    rows: List[EnrichRowRequest]


@router.post("/row")
def enrich_single_row(payload: EnrichRowRequest) -> Dict[str, Any]:
    """
    Enriches a single raw catalog row into a standardized 252-column delivery record.
    """
    try:
        row_dict = payload.model_dump()
        result = _pipeline.process_row(row_dict)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Enrichment processing error: {str(e)}",
        )


@router.post("/batch")
def enrich_batch_rows(payload: BatchEnrichRequest) -> Dict[str, Any]:
    """
    Enriches a batch of raw catalog rows and returns enriched delivery records with KPI metrics.
    """
    start_time = time.time()
    results = []
    verified_count = 0
    needs_review_count = 0

    for item in payload.rows:
        row_dict = item.model_dump()
        res = _pipeline.process_row(row_dict)
        results.append(res)
        if res.get("validation", {}).get("is_verified"):
            verified_count += 1
        else:
            needs_review_count += 1

    elapsed = round(time.time() - start_time, 3)
    total = len(results)

    return {
        "summary": {
            "total_processed": total,
            "verified_count": verified_count,
            "needs_review_count": needs_review_count,
            "verification_rate": round((verified_count / total * 100) if total else 0, 1),
            "elapsed_seconds": elapsed,
            "throughput_rows_per_sec": round(total / elapsed, 1) if elapsed > 0 else total,
        },
        "items": results,
    }


@router.post("/upload")
async def enrich_file_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Accepts CSV or XLSX file upload of raw catalog rows, runs enrichment, and returns delivery records.
    """
    start_time = time.time()
    content = await file.read()
    filename = file.filename or "upload.csv"

    rows: List[Dict[str, Any]] = []

    try:
        if filename.endswith(".csv"):
            text_stream = io.StringIO(content.decode("utf-8-sig", errors="replace"))
            reader = csv.DictReader(text_stream)
            rows = list(reader)
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            sheet = wb.active
            headers = [str(cell.value or "").strip() for cell in sheet[1]]
            for row_cells in sheet.iter_rows(min_row=2, values_only=True):
                if any(row_cells):
                    row_dict = {headers[i]: (str(val).strip() if val is not None else "") for i, val in enumerate(row_cells) if i < len(headers)}
                    rows.append(row_dict)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file format. Please upload CSV or XLSX.",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse uploaded spreadsheet: {str(e)}",
        )

    enriched_items = []
    verified_count = 0
    needs_review_count = 0

    for r in rows:
        res = _pipeline.process_row(r)
        enriched_items.append(res)
        if res.get("validation", {}).get("is_verified"):
            verified_count += 1
        else:
            needs_review_count += 1

    elapsed = round(time.time() - start_time, 3)
    total = len(enriched_items)

    return {
        "filename": filename,
        "summary": {
            "total_processed": total,
            "verified_count": verified_count,
            "needs_review_count": needs_review_count,
            "verification_rate": round((verified_count / total * 100) if total else 0, 1),
            "elapsed_seconds": elapsed,
            "throughput_rows_per_sec": round(total / elapsed, 1) if elapsed > 0 else total,
        },
        "items": enriched_items,
    }


@router.get("/benchmark")
def run_enrichment_benchmark(limit: int = Query(default=100, ge=1, le=1000)) -> Dict[str, Any]:
    """
    Executes automated benchmark evaluation over the input dataset.
    """
    from pathlib import Path
    current = Path(__file__).resolve()
    # Check parent dirs
    input_path = None
    expected_path = None
    for p in [current.parent.parent.parent.parent.parent, current.parent.parent.parent.parent, Path.cwd()]:
        candidate_in = p / "Unihack_ Sample Dataset - Input (1).csv"
        candidate_exp = p / "Unihack_ Expected Output - Delivery Format.csv"
        if candidate_in.exists():
            input_path = str(candidate_in)
            expected_path = str(candidate_exp)
            break

    if not input_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unihack sample dataset files not found on disk.",
        )

    evaluator = BenchmarkEvaluator(input_csv_path=input_path, expected_csv_path=expected_path)
    try:
        report = evaluator.run_benchmark(limit=limit)
        return report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Benchmark execution failed: {str(e)}",
        )
