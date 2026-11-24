"""La page de test /api/v1/docs fonctionne hors ligne et sous une politique CSP compatible."""

from datetime import timedelta

from fastapi.testclient import TestClient
from urag_api.main import create_app
from urag_api.state import AppState
from urag_core.config import Settings
from urag_core.security import TokenService


def _client() -> TestClient:
    state = AppState(Settings(), None, None, TokenService(b"k" * 32, timedelta(minutes=5), timedelta(hours=1)))
    return TestClient(create_app(state))


def test_page_de_test_sans_ressource_externe():
    c = _client()
    page = c.get("/api/v1/docs")
    assert page.status_code == 200
    assert "http://" not in page.text.replace("http://127", "") and "https://" not in page.text
    assert "'unsafe-inline'" in page.headers["content-security-policy"]
    for asset in ("swagger-ui-bundle.js", "swagger-ui.css"):
        assert c.get(f"/api/v1/static/swagger/{asset}").status_code == 200


def test_csp_stricte_ailleurs_et_jeton_porteur_documente():
    c = _client()
    r = c.get("/api/v1/openapi.json")
    assert "unsafe-inline" not in r.headers["content-security-policy"]
    assert "HTTPBearer" in r.json()["components"]["securitySchemes"]
