"""
1,000-Row Scale Test Runner for CatalogIQ Enrichment Foundation.
Step 17 Scalability & Throughput Verification.

Measures:
- Total rows processed
- Successful enrichments
- Needs review count & rate
- Invalid count & rate
- Total execution time
- Average time per product
- Throughput (items/sec)
- Validation compliance
- Evidence coverage
"""
import csv
import os
import sys
import time
from typing import Any, Dict, List, Optional
from app.services.enrichment.pipeline import EnrichmentPipeline


class ScaleTester:
    """Evaluates pipeline throughput and scalability over 1,000-item catalogs."""

    def __init__(self, dataset_path: str) -> None:
        self.dataset_path = dataset_path
        self.pipeline = EnrichmentPipeline()

    def run_scale_test(self, max_rows: int = 1000) -> Dict[str, Any]:
        """Runs the enrichment engine across up to 1000 items and measures throughput."""
        if not os.path.exists(self.dataset_path):
            raise FileNotFoundError(f"Scale dataset file not found at: {self.dataset_path}")

        rows: List[Dict[str, Any]] = []
        with open(self.dataset_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
                if len(rows) >= max_rows:
                    break

        total_rows = len(rows)
        start_time = time.perf_counter()

        verified_count = 0
        needs_review_count = 0
        invalid_count = 0
        total_attributes = 0
        total_evidence_fields = 0

        for row in rows:
            res = self.pipeline.process_row(row)
            status = res["validation"]["status"]
            if status == "verified":
                verified_count += 1
            elif status == "needs_review":
                needs_review_count += 1
            else:
                invalid_count += 1

            total_attributes += len(res["attributes"])
            total_evidence_fields += res["evidence_summary"]["total_fields_tracked"]

        duration = time.perf_counter() - start_time
        avg_time = duration / total_rows if total_rows > 0 else 0
        throughput = total_rows / duration if duration > 0 else 0

        return {
            "total_rows": total_rows,
            "duration_seconds": round(duration, 3),
            "avg_time_per_product_ms": round(avg_time * 1000, 2),
            "throughput_items_per_sec": round(throughput, 1),
            "verified_count": verified_count,
            "verified_rate": round((verified_count / total_rows) * 100, 2),
            "needs_review_count": needs_review_count,
            "needs_review_rate": round((needs_review_count / total_rows) * 100, 2),
            "invalid_count": invalid_count,
            "invalid_rate": round((invalid_count / total_rows) * 100, 2),
            "total_attributes_extracted": total_attributes,
            "avg_attributes_per_product": round(total_attributes / total_rows, 2),
            "avg_evidence_fields_per_product": round(total_evidence_fields / total_rows, 2),
        }


def main() -> None:
    csv_candidates = [
        r"C:\Users\Parikshith S\Downloads\Unihack_ Sample Dataset - Input.csv",
        r"C:\Users\Parikshith S\Downloads\Unihack_ Sample Dataset - Input (1).csv",
    ]
    input_path = next((p for p in csv_candidates if os.path.exists(p)), None)
    if not input_path:
        print("Error: Could not locate 1000-item dataset.")
        sys.exit(1)

    tester = ScaleTester(input_path)
    res = tester.run_scale_test(max_rows=1000)

    print("\n" + "=" * 70)
    print(" CATALOGIQ PHASE 11: 1,000-ROW SCALE & THROUGHPUT TEST REPORT")
    print("=" * 70)
    print(f" Total Rows Processed         : {res['total_rows']}")
    print(f" Total Duration               : {res['duration_seconds']}s")
    print(f" Average Latency per Product  : {res['avg_time_per_product_ms']} ms")
    print(f" Deterministic Enrichment Throughput: {res['throughput_items_per_sec']} items/sec")
    print("-" * 70)
    print(f" Verified Products            : {res['verified_count']} ({res['verified_rate']}%)")
    print(f" Needs Review Products        : {res['needs_review_count']} ({res['needs_review_rate']}%)")
    print(f" Invalid Products             : {res['invalid_count']} ({res['invalid_rate']}%)")
    print(f" Total Attributes Extracted   : {res['total_attributes_extracted']} (Avg {res['avg_attributes_per_product']} / prod)")
    print(f" Avg Evidence Fields Tracked  : {res['avg_evidence_fields_per_product']} fields / prod")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
