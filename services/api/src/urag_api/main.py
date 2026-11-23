"""Application FastAPI."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from urag_core.config import get_settings

from .routes import admin, auth, chat
from .state import AppState

API_PREFIX = "/api/v1"


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(title="Universal RAG Engine", version="0.1.0", openapi_url=f"{API_PREFIX}/openapi.json",
                  docs_url=f"{API_PREFIX}/docs", redoc_url=None)
    app.state.urag = state

    @app.exception_handler(HTTPException)
    async def problem_handler(request: Request, exc: HTTPException):  # RFC 9457
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "title": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, media_type="application/problem+json",
                            content={"type": "about:blank", "status": exc.status_code, **detail})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self'; frame-ancestors 'none'")
        return response

    for router in (auth.router, admin.router, chat.router):
        app.include_router(router, prefix=API_PREFIX)
    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(AppState.from_settings(settings)), host="127.0.0.1", port=8000)
