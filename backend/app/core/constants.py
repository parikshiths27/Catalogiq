"""
CatalogIQ Multi-Format Document Ingestion Registry.
Defines authoritative supported document extensions, MIME types, and magic byte validators.
"""
from typing import Dict, Set

# Authoritative set of supported document extensions (lowercase with leading dot)
SUPPORTED_DOCUMENT_EXTENSIONS: Set[str] = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".txt",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".md",
}

# Authoritative mapping of supported extensions to canonical MIME types
EXTENSION_TO_MIME_TYPE: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
}

SUPPORTED_DOCUMENT_MIME_TYPES: Set[str] = set(EXTENSION_TO_MIME_TYPE.values()) | {
    "text/xml",
    "application/x-xml",
    "text/x-markdown",
    "application/x-zip-compressed",
}

FORMAT_DISPLAY_NAMES: Dict[str, str] = {
    ".pdf": "PDF",
    ".docx": "Word (DOCX)",
    ".xlsx": "Excel (XLSX)",
    ".csv": "CSV",
    ".txt": "Text (TXT)",
    ".json": "JSON",
    ".xml": "XML",
    ".html": "HTML",
    ".htm": "HTML",
    ".md": "Markdown",
}
