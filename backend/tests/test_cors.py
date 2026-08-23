from fastapi.testclient import TestClient
from app.main import app
from app.core.config import Settings

client = TestClient(app)


def test_cors_production_origin_allowed():
    """Verifies production Vercel origin is allowed and returns proper CORS headers."""
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "https://catalogiq-orcin.vercel.app"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://catalogiq-orcin.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_localhost_development_allowed():
    """Verifies local frontend development origins (Vite 5173, Next 3000) are allowed."""
    for origin in ["http://localhost:5173", "http://localhost:3000"]:
        response = client.get(
            "/api/v1/health",
            headers={"Origin": origin}
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
        assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_vercel_preview_origin_allowed():
    """Verifies dynamic Vercel preview deployment origins match regex."""
    preview_origin = "https://catalogiq-git-feature-parikshiths27.vercel.app"
    response = client.get(
        "/api/v1/health",
        headers={"Origin": preview_origin}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == preview_origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_unknown_origin_rejected():
    """Verifies unauthorized origins do not receive Access-Control-Allow-Origin header."""
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "https://unauthorized-attacker-site.com"}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_options_request():
    """Verifies preflight OPTIONS request returns valid CORS headers."""
    response = client.options(
        "/api/v1/overview/summary",
        headers={
            "Origin": "https://catalogiq-orcin.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type,authorization",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://catalogiq-orcin.vercel.app"
    assert "GET" in response.headers.get("access-control-allow-methods", "")
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_origin_parsing_and_trailing_slashes():
    """Verifies whitespace and trailing slashes are safely normalized."""
    cfg = Settings(
        CORS_ORIGINS=" https://catalogiq-orcin.vercel.app/ , http://localhost:5173/ , https://test.domain.com ",
        _env_file=None,
    )
    assert cfg.cors_origins_list == [
        "https://catalogiq-orcin.vercel.app",
        "http://localhost:5173",
        "https://test.domain.com",
    ]
    assert cfg.cors_allow_credentials is True


def test_cors_wildcard_credentials_incompatibility():
    """Verifies when CORS_ORIGINS is '*', allow_credentials evaluates to False per W3C specification."""
    cfg = Settings(
        CORS_ORIGINS="*",
        CORS_ALLOW_CREDENTIALS=True,
        _env_file=None,
    )
    assert cfg.cors_origins_list == ["*"]
    assert cfg.cors_allow_credentials is False
