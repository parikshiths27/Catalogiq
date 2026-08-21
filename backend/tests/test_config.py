import os
import tempfile
from pathlib import Path
import pytest

from app.core.config import Settings
from app.services.llm.factory import get_llm_provider
from app.services.llm.gemini_provider import GeminiProvider


def test_env_resolution_from_root_directory(monkeypatch):
    """Proves project .env is loaded when CWD is repository root."""
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    root_dir = Path(__file__).resolve().parent.parent.parent
    old_cwd = os.getcwd()
    try:
        os.chdir(root_dir)
        settings = Settings()
        assert settings.LLM_PROVIDER == "gemini"
        assert "gemini" in settings.GEMINI_MODEL
        assert settings.GEMINI_API_KEY is not None
        assert len(settings.GEMINI_API_KEY) > 0
    finally:
        os.chdir(old_cwd)


def test_env_resolution_from_backend_directory(monkeypatch):
    """Proves project .env is loaded when CWD is backend/ directory."""
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    backend_dir = Path(__file__).resolve().parent.parent
    old_cwd = os.getcwd()
    try:
        os.chdir(backend_dir)
        settings = Settings()
        assert settings.LLM_PROVIDER == "gemini"
        assert "gemini" in settings.GEMINI_MODEL
        assert settings.GEMINI_API_KEY is not None
        assert len(settings.GEMINI_API_KEY) > 0
    finally:
        os.chdir(old_cwd)


def test_env_resolution_from_arbitrary_directory(monkeypatch):
    """Proves project .env is loaded when CWD is an arbitrary non-project directory."""
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with tempfile.TemporaryDirectory() as temp_dir:
        old_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            settings = Settings()
            assert settings.LLM_PROVIDER == "gemini"
            assert "gemini" in settings.GEMINI_MODEL
            assert settings.GEMINI_API_KEY is not None
        finally:
            os.chdir(old_cwd)


def test_explicit_env_file_path_override(monkeypatch):
    """Proves ENV_FILE_PATH explicit override takes precedence when provided."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env") as f:
        f.write("LLM_PROVIDER=ollama\nOLLAMA_MODEL=custom-test-model\n")
        temp_env_path = f.name

    try:
        monkeypatch.setenv("ENV_FILE_PATH", temp_env_path)
        settings = Settings()
        assert settings.LLM_PROVIDER == "ollama"
        assert settings.OLLAMA_MODEL == "custom-test-model"
    finally:
        os.unlink(temp_env_path)


def test_system_environment_variable_precedence(monkeypatch):
    """Proves OS environment variables override .env settings."""
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ENV", "test")

    settings = Settings()
    assert settings.LLM_PROVIDER == "mock"
    assert settings.ENV == "test"


def test_llm_factory_resolves_gemini_provider(monkeypatch):
    """
    Proves get_llm_provider() factory returns a GeminiProvider instance
    targeting configured gemini model when Gemini config is present in project .env.
    """
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    from app.core import config
    import app.services.llm.factory as factory_mod

    new_settings = Settings()
    monkeypatch.setattr(config, "settings", new_settings)
    monkeypatch.setattr(factory_mod, "settings", new_settings)

    provider = get_llm_provider()

    assert isinstance(provider, GeminiProvider)
    assert provider.provider_name == "gemini"
    assert "gemini" in provider.model_name
