import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine base project directories relative to config.py location
_CONFIG_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CONFIG_DIR.parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

# Default .env search locations resolved relative to project structure, not CWD
_DEFAULT_ENV_FILES = (_ROOT_DIR / ".env", _BACKEND_DIR / ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE_PATH") or _DEFAULT_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def __init__(self, *args, **kwargs):
        if "ENV_FILE_PATH" in os.environ and "_env_file" not in kwargs:
            kwargs["_env_file"] = os.environ["ENV_FILE_PATH"]
        super().__init__(*args, **kwargs)

    APP_NAME: str = "CatalogIQ"
    ENV: str = "development"
    PORT: int = 8000

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/catalogiq"
    REDIS_URL: str = "redis://localhost:6379/0"
    QDRANT_URL: str = "http://localhost:6333"

    STORAGE_PROVIDER: str = "local"
    LOCAL_STORAGE_DIR: str = "./storage"

    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    S3_REGION: Optional[str] = "us-east-1"

    # --- LLM Provider ---
    # Options: ollama | gemini | mock (mock only valid when ENV=test)
    LLM_PROVIDER: str = "ollama"

    # --- Ollama (local development) ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:8b"
    OLLAMA_TIMEOUT_SECONDS: int = 180
    OLLAMA_MAX_RETRIES: int = 1
    OLLAMA_KEEP_ALIVE: str = "30m"

    # --- Gemini (production) ---
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"

    # --- Embedding ---
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    QDRANT_COLLECTION_NAME: str = "catalogiq_products"

    # --- Extraction Versioning ---
    # Changing any of these will invalidate the extraction cache for all documents.
    EXTRACTION_PROMPT_VERSION: str = "v1.0"
    EXTRACTION_SCHEMA_VERSION: str = "v1"
    PIPELINE_VERSION: str = "v1"

    WORKER_CONCURRENCY: int = 4
    MAX_UPLOAD_SIZE_MB: int = 50
    CONFIDENCE_THRESHOLD_HIGH: float = 0.85  # 85/100 — verified
    CONFIDENCE_THRESHOLD_MEDIUM: float = 0.60  # 60/100 — needs review below

# Load settings instance
settings = Settings()
