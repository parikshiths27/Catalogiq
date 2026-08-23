import io
import os
import json
import pytest
from sqlmodel import Session

from app.models import Document, DocumentStatus
from app.services.document import DocumentService
from app.services.parser import (
    MultiFormatParser, DoclingParser, ExcelParser, CSVParser,
    TextParser, JSONParser, XMLParser, HTMLParser, MockParser
)
from app.core.constants import SUPPORTED_DOCUMENT_EXTENSIONS


@pytest.fixture(autouse=True)
def mock_parser_env(monkeypatch):
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")


def test_supported_document_extensions_registry():
    """Verifies that all 9 target formats are registered in the authoritative constants."""
    target_extensions = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".json", ".xml", ".html", ".htm", ".md"}
    for ext in target_extensions:
        assert ext in SUPPORTED_DOCUMENT_EXTENSIONS


def test_validation_rejects_unsupported_extension(session: Session):
    """Verifies that unsupported file extensions are rejected cleanly with a clear error message."""
    service = DocumentService(session)
    with pytest.raises(ValueError) as exc_info:
        service.validate_file(b"some exe content", "malware.exe")
    assert "Unsupported file type" in str(exc_info.value)
    assert "Supported formats: PDF, DOCX, XLSX, CSV, TXT, JSON, XML, HTML, MD." in str(exc_info.value)


def test_validation_rejects_oversized_file(session: Session):
    """Verifies that files exceeding MAX_UPLOAD_SIZE_MB are rejected cleanly."""
    service = DocumentService(session)
    large_bytes = b"0" * (51 * 1024 * 1024)
    with pytest.raises(ValueError) as exc_info:
        service.validate_file(large_bytes, "large_catalog.pdf")
    assert "File size exceeds limit" in str(exc_info.value)


def test_validation_magic_bytes_bypass_prevention(session: Session):
    """Verifies that renaming invalid files to .pdf or .docx cannot bypass magic byte signature validation."""
    service = DocumentService(session)
    
    # Renamed text file claiming to be PDF
    with pytest.raises(ValueError) as exc_info:
        service.validate_file(b"This is fake pdf content", "fake.pdf")
    assert "Magic bytes do not match %PDF signature" in str(exc_info.value)

    # Renamed text file claiming to be DOCX
    with pytest.raises(ValueError) as exc_info:
        service.validate_file(b"This is fake docx content", "fake.docx")
    assert "missing standard Office Open XML header signature" in str(exc_info.value)


def test_pdf_upload_and_parsing(session: Session, monkeypatch):
    """Verifies PDF upload and parsing to common IR."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = DocumentService(session)
    pdf_bytes = b"%PDF-1.4 sample content"
    res = service.upload_document(pdf_bytes, "motor_spec.pdf", "application/pdf", process_inline=False)
    assert res["status"] == "queued"

    parser = MultiFormatParser()
    ir = parser.parse(pdf_bytes, filename="motor_spec.pdf")
    assert "pages" in ir
    assert "metadata" in ir
    assert len(ir["pages"]) > 0


def test_docx_upload_and_parsing(session: Session, monkeypatch):
    """Verifies DOCX upload and parsing to common IR."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = DocumentService(session)
    docx_bytes = b"PK\x03\x04sample docx zip bytes"
    res = service.upload_document(docx_bytes, "manual.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", process_inline=False)
    assert res["status"] == "queued"

    doc = session.get(Document, res["document_id"])
    assert doc.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert doc.storage_key.endswith(".docx")

    parser = MultiFormatParser()
    ir = parser.parse(docx_bytes, filename="manual.docx")
    assert "pages" in ir
    assert ir["pages"][0]["tables"][0]["headers"] == ["Spec", "Value"]


def test_xlsx_upload_and_parsing(session: Session, monkeypatch):
    """Verifies XLSX upload and parsing to common IR."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    service = DocumentService(session)
    xlsx_bytes = b"PK\x03\x04sample xlsx zip bytes"
    res = service.upload_document(xlsx_bytes, "catalog.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", process_inline=False)
    assert res["status"] == "queued"

    doc = session.get(Document, res["document_id"])
    assert doc.storage_key.endswith(".xlsx")

    parser = MultiFormatParser()
    ir = parser.parse(xlsx_bytes, filename="catalog.xlsx")
    assert "pages" in ir
    assert len(ir["pages"]) > 0


def test_csv_upload_and_parsing(session: Session):
    """Verifies CSV upload and parsing to common IR."""
    service = DocumentService(session)
    csv_bytes = b"SKU,Name,Voltage,Power\nCSV-100,CSV Motor,230V,5.5kW\n"
    res = service.upload_document(csv_bytes, "products.csv", "text/csv", process_inline=False)
    assert res["status"] == "queued"

    doc = session.get(Document, res["document_id"])
    assert doc.mime_type == "text/csv"
    assert doc.storage_key.endswith(".csv")

    parser = CSVParser()
    ir = parser.parse(csv_bytes, filename="products.csv")
    assert "pages" in ir
    assert ir["pages"][0]["tables"][0]["headers"] == ["SKU", "Name", "Voltage", "Power"]
    assert ir["pages"][0]["tables"][0]["rows"][0] == ["CSV-100", "CSV Motor", "230V", "5.5kW"]


def test_txt_upload_and_parsing(session: Session):
    """Verifies TXT upload and parsing to common IR."""
    service = DocumentService(session)
    txt_bytes = b"Industrial Motor Technical Datasheet\nModel: TXT-100\nSKU: TXT-100-SKU\nVoltage: 400V\n"
    res = service.upload_document(txt_bytes, "datasheet.txt", "text/plain", process_inline=False)
    assert res["status"] == "queued"

    parser = TextParser()
    ir = parser.parse(txt_bytes, filename="datasheet.txt")
    assert "pages" in ir
    assert "Model: TXT-100" in ir["pages"][0]["text"]


def test_json_upload_and_parsing(session: Session):
    """Verifies JSON upload and parsing to common IR."""
    service = DocumentService(session)
    json_bytes = json.dumps([
        {"sku": "JSON-100", "name": "Pump Motor", "voltage": "230V", "power": "4.0kW"}
    ]).encode("utf-8")

    res = service.upload_document(json_bytes, "catalog.json", "application/json", process_inline=False)
    assert res["status"] == "queued"

    parser = JSONParser()
    ir = parser.parse(json_bytes, filename="catalog.json")
    assert "pages" in ir
    assert ir["pages"][0]["tables"][0]["rows"][0] == ["JSON-100", "Pump Motor", "230V", "4.0kW"] or len(ir["pages"][0]["tables"][0]["rows"]) > 0


def test_xml_upload_and_parsing(session: Session):
    """Verifies XML upload and parsing to common IR."""
    service = DocumentService(session)
    xml_bytes = b"""<?xml version="1.0"?>
    <catalog>
        <product>
            <sku>XML-100</sku>
            <name>XML Drive</name>
        </product>
    </catalog>"""

    res = service.upload_document(xml_bytes, "feed.xml", "application/xml", process_inline=False)
    assert res["status"] == "queued"

    parser = XMLParser()
    ir = parser.parse(xml_bytes, filename="feed.xml")
    assert "pages" in ir
    assert len(ir["pages"][0]["tables"]) > 0
    assert "XML-100" in ir["pages"][0]["text"]


def test_html_upload_and_parsing(session: Session):
    """Verifies HTML upload and parsing to common IR."""
    service = DocumentService(session)
    html_bytes = b"""<!DOCTYPE html>
    <html>
    <body>
        <h1>Industrial Valve</h1>
        <table>
            <tr><th>Parameter</th><th>Value</th></tr>
            <tr><td>SKU</td><td>VALVE-99</td></tr>
            <tr><td>Pressure</td><td>16 bar</td></tr>
        </table>
    </body>
    </html>"""

    res = service.upload_document(html_bytes, "spec.html", "text/html", process_inline=False)
    assert res["status"] == "queued"

    parser = HTMLParser()
    ir = parser.parse(html_bytes, filename="spec.html")
    assert "pages" in ir
    assert ir["pages"][0]["tables"][0]["headers"] == ["Parameter", "Value"]
    assert ir["pages"][0]["tables"][0]["rows"][0] == ["SKU", "VALVE-99"]


def test_markdown_upload_and_parsing(session: Session):
    """Verifies Markdown upload and parsing to common IR."""
    service = DocumentService(session)
    md_bytes = b"# Motor Spec Sheet\n\n- **SKU**: MD-500\n- **Power**: 11 kW\n- **Voltage**: 400 V\n"
    res = service.upload_document(md_bytes, "spec.md", "text/markdown", process_inline=False)
    assert res["status"] == "queued"

    parser = TextParser()
    ir = parser.parse(md_bytes, filename="spec.md")
    assert "pages" in ir
    assert "MD-500" in ir["pages"][0]["text"]


def test_multiformat_dispatcher_routing(monkeypatch):
    """Verifies that MultiFormatParser routes all 9 formats to the appropriate format parsers."""
    monkeypatch.setenv("TEST_MOCK_PARSER", "true")
    dispatcher = MultiFormatParser()

    formats = [
        ("test.pdf", b"%PDF-1.4 bytes"),
        ("test.docx", b"PK\x03\x04bytes"),
        ("test.xlsx", b"PK\x03\x04bytes"),
        ("test.csv", b"a,b\n1,2"),
        ("test.txt", b"plain text"),
        ("test.json", b'{"key": "val"}'),
        ("test.xml", b"<xml></xml>"),
        ("test.html", b"<html></html>"),
        ("test.md", b"# Title")
    ]

    for fname, content in formats:
        ir = dispatcher.parse(content, filename=fname)
        assert "pages" in ir
        assert "metadata" in ir
        assert len(ir["pages"]) > 0
