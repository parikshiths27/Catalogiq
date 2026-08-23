"""
Tests for Gemini extraction response resilience and tabular catalog spreadsheet ingestion.
"""
import json
import uuid
from unittest.mock import MagicMock, patch
import pytest
from sqlmodel import Session, select

from app.db.session import engine
from app.models import (
    Document, DocumentStatus, ProcessingJob, ProcessingStep,
    JobStatus, ProcessingStage, StepStatus, Product, ProductAttribute,
    ProductDocumentAssociation, EnrichmentResult
)
from app.services.llm.gemini_provider import GeminiProvider
from app.services.pipeline import ExtractionStage


def test_gemini_extract_resilience_to_list_response():
    """Test that GeminiProvider.extract() handles JSON lists without crashing."""
    provider = GeminiProvider()

    # Mock _call_gemini to return a JSON list of products
    list_json = json.dumps([
        {
            "sku": "P-1001",
            "brand": "Siemens",
            "product_name": "SIMOTICS GP Motor",
            "category": "Motors",
            "attributes": [
                {
                    "name": "rated_voltage",
                    "display_name": "Rated Voltage",
                    "raw_value": "400 V",
                    "unit": "V",
                    "data_type": "numeric",
                    "extraction_method": "llm",
                    "llm_confidence": 0.95
                }
            ]
        }
    ])

    with patch.object(provider, "_call_gemini", return_value=list_json):
        result = provider.extract({"pages": [{"text": "Sample text", "page_number": 1}]})
        assert result.sku == "P-1001"
        assert result.brand == "Siemens"
        assert result.product_name == "SIMOTICS GP Motor"
        assert len(result.attributes) == 1
        assert result.attributes[0].name == "rated_voltage"


def test_gemini_extract_resilience_to_wrapped_products_dict():
    """Test that GeminiProvider.extract() handles wrapped {'products': [...]} dict."""
    provider = GeminiProvider()

    wrapped_json = json.dumps({
        "products": [
            {
                "sku": "P-2002",
                "brand": "ABB",
                "product_name": "M2AA Motor",
                "attributes": []
            }
        ]
    })

    with patch.object(provider, "_call_gemini", return_value=wrapped_json):
        result = provider.extract({"pages": [{"text": "Sample text", "page_number": 1}]})
        assert result.sku == "P-2002"
        assert result.brand == "ABB"


def test_gemini_extract_resilience_to_markdown_codeblock():
    """Test that GeminiProvider.extract() handles ```json ... ``` markdown wraps."""
    provider = GeminiProvider()

    markdown_json = "```json\n" + json.dumps({
        "sku": "P-3003",
        "brand": "Schneider",
        "product_name": "Altivar Inverter",
        "attributes": []
    }) + "\n```"

    with patch.object(provider, "_call_gemini", return_value=markdown_json):
        result = provider.extract({"pages": [{"text": "Sample text", "page_number": 1}]})
        assert result.sku == "P-3003"
        assert result.brand == "Schneider"


def test_tabular_catalog_spreadsheet_ingestion(session: Session):
    """
    Test that ExtractionStage detects a multi-row Excel/CSV catalog spreadsheet,
    processes rows through EnrichmentPipeline, and persists all products with 5-channel descriptions.
    """
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    step_id = uuid.uuid4()

    mock_ir = {
        "metadata": {"title": "Sample Catalog Spreadsheet"},
        "pages": [
            {
                "page_number": 1,
                "text": "Catalog Sheet 1",
                "tables": [
                    {
                        "headers": ["Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"],
                        "rows": [
                            ["PDSH4816AF", "PDSH4816AF Dishwasher SS - Display Only", "Frigidaire", "Frigidaire", "Frigidaire", "Electrolux Major Appliances"],
                            ["3/8 CPLG BRS", "3/8 IN Brass Coupling 150# Threaded", "Anvil", "Anvil", "Anvil", "Anvil International"]
                        ]
                    }
                ]
            }
        ]
    }

    doc = Document(
        id=doc_id,
        filename="catalog_upload.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        storage_key="test/catalog_upload.xlsx",
        parsed_storage_key="test/catalog_upload_parsed.json",
        file_hash="test-hash-catalog",
        content_hash="test-hash-catalog",
        file_size=1024,
        status=DocumentStatus.parsing,
    )
    job = ProcessingJob(
        id=job_id,
        document_id=doc_id,
        status=JobStatus.processing,
        current_stage=ProcessingStage.extracting,
    )
    step = ProcessingStep(
        id=step_id,
        job_id=job_id,
        document_id=doc_id,
        stage=ProcessingStage.extracting,
        status=StepStatus.queued,
    )
    session.add(doc)
    session.add(job)
    session.add(step)
    session.commit()

    with patch("app.services.pipeline.get_storage_service") as mock_storage_factory:
        mock_storage = MagicMock()
        mock_storage.download_file.return_value = json.dumps(mock_ir).encode("utf-8")
        mock_storage_factory.return_value = mock_storage

        stage = ExtractionStage(llm_provider=MagicMock())
        stage.execute(session, doc_id, job_id, step_id)

    # Verify both products were created in the database and linked to the document
    assocs = session.exec(select(ProductDocumentAssociation).where(ProductDocumentAssociation.document_id == doc_id)).all()
    assert len(assocs) == 2, f"Expected 2 product associations, got {len(assocs)}"

    p1 = session.get(Product, assocs[0].product_id)
    p2 = session.get(Product, assocs[1].product_id)

    skus = {p1.sku, p2.sku}
    assert "PDSH4816AF" in skus or "3/8 CPLG BRS" in skus

    # Check enrichment result exists for p1
    enrich1 = session.exec(select(EnrichmentResult).where(EnrichmentResult.product_id == p1.id)).first()
    assert enrich1 is not None
    assert enrich1.generated_value is not None
    enrich_data = json.loads(enrich1.generated_value)
    assert "invoice_desc" in enrich_data
    assert "mobile_desc" in enrich_data
    assert "short_desc" in enrich_data
    assert "long_desc" in enrich_data
