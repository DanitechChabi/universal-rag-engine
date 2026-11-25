"""Application FastAPI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from urag_core.config import get_settings

from .routes import admin, auth, chat, documents
from .state import AppState

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).resolve().parent / "static"
STRICT_CSP = "default-src 'self'; img-src 'self'; frame-ancestors 'none'"
# Page de test : la bibliothèque Swagger UI est servie localement (fonctionnement hors ligne) ;
# son script d'initialisation est en ligne, d'où 'unsafe-inline' sur cette seule page.
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; frame-ancestors 'none'"
)


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(
        title="Universal RAG Engine",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.state.urag = state

    @app.exception_handler(HTTPException)
    async def problem_handler(request: Request, exc: HTTPException):  # RFC 9457
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "title": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={"type": "about:blank", "status": exc.status_code, **detail},
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        csp = DOCS_CSP if request.url.path == f"{API_PREFIX}/docs" else STRICT_CSP
        response.headers.setdefault("Content-Security-Policy", csp)
        return response

    app.mount(f"{API_PREFIX}/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get(f"{API_PREFIX}/docs", include_in_schema=False)
    async def docs() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=f"{API_PREFIX}/openapi.json",
            title="Universal RAG Engine — page de test",
            swagger_js_url=f"{API_PREFIX}/static/swagger/swagger-ui-bundle.js",
            swagger_css_url=f"{API_PREFIX}/static/swagger/swagger-ui.css",
            swagger_favicon_url=f"{API_PREFIX}/static/swagger/favicon.png",
        )

    for router in (auth.router, admin.router, chat.router, documents.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(AppState.from_settings(settings)), host="127.0.0.1", port=8000)
