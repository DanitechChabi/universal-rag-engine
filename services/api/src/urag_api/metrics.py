"""Métriques Prometheus et journal des requêtes (docs/DEPLOYMENT.md §5).

- ``/metrics`` est servi **hors** du préfixe ``/api`` : le relais HTTPS (Caddy) ne le publie pas ;
  seul le réseau interne (Prometheus, supervision) y accède.
- Les requêtes sont comptées par **modèle de route** (``/api/v1/documents/{document_id}``), jamais
  par chemin réel ni paramètres : ni identifiant, ni texte de recherche dans les métriques ou les
  journaux.
- Plusieurs processus uvicorn : mode multiprocessus de prometheus_client
  (``PROMETHEUS_MULTIPROC_DIR``), agrégé à la lecture.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import text

log = logging.getLogger("urag.api.requests")

REQUESTS = Counter("urag_http_requests_total", "Requêtes HTTP", ["method", "route", "status"])
LATENCY = Histogram(
    "urag_http_request_seconds",
    "Durée des requêtes HTTP (jusqu'au premier octet pour les réponses diffusées)",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
CHAT_FIRST_TOKEN = Histogram(
    "urag_chat_first_token_seconds",
    "Délai entre la question et le premier morceau de réponse",
    buckets=(0.25, 0.5, 1, 2, 4, 8, 15, 30, 60),
)


class DatabaseCollector:
    """Agrégats lus en base à chaque collecte (fonction urag_metrics, migration 0008)."""

    def __init__(self, db) -> None:
        self.db = db

    def collect(self):
        families: dict[str, GaugeMetricFamily] = {}
        try:
            with self.db.anonymous() as conn:
                rows = conn.execute(text("SELECT metric, label, value FROM urag_metrics()")).all()
        except Exception:  # noqa: BLE001 - base indisponible : signalée par urag_up
            rows = []
        up = GaugeMetricFamily("urag_database_up", "Base PostgreSQL joignable")
        up.add_metric([], 1 if rows else 0)
        yield up
        for metric, label, value in rows:
            name = f"urag_{metric}"
            if name not in families:
                families[name] = GaugeMetricFamily(name, f"Agrégat {metric} (toutes organisations)", labels=["state"])
            families[name].add_metric([label or "all"], float(value or 0))
        yield from families.values()


def _route(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "inconnue"


def install(app: FastAPI, state) -> None:
    @app.middleware("http")
    async def measure(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = _route(request)
            if route != "/metrics":
                elapsed = time.perf_counter() - start
                REQUESTS.labels(request.method, route, str(status)).inc()
                LATENCY.labels(request.method, route).observe(elapsed)
                log.info(
                    "requête",
                    extra={"method": request.method, "route": route, "status": status, "ms": round(elapsed * 1000)},
                )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        registry = CollectorRegistry()
        if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
            from prometheus_client import multiprocess

            multiprocess.MultiProcessCollector(registry)
        else:
            from prometheus_client import REGISTRY

            registry = REGISTRY
        data = generate_latest(registry) + generate_latest(_db_registry(state))
        return Response(data, media_type=CONTENT_TYPE_LATEST)


def _db_registry(state) -> CollectorRegistry:
    registry = CollectorRegistry()
    registry.register(DatabaseCollector(state.db))
    return registry
