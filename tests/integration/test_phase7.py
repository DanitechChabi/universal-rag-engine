# ruff: noqa: F811 - fixture « env » réutilisée depuis le module de la phase 1
"""Phase 7 : supervision — métriques Prometheus et journaux JSON sans contenu ni identifiant."""

from __future__ import annotations

import json
import logging
import uuid

import pytest

from tests.integration.test_phase1 import env, sync  # noqa: F401

pytestmark = pytest.mark.integration
SECRET_QUERY = "texte-de-recherche-confidentiel"


def test_01_metriques_internes_agregees(env, caplog):
    sync(env)
    c = env["client"]
    doc = str(uuid.uuid4())
    with caplog.at_level(logging.INFO, logger="urag.api.requests"):
        c.get(f"/api/v1/documents/{doc}", headers=env["admin_a"])
        c.get("/api/v1/documents", headers=env["admin_a"], params={"q": SECRET_QUERY})
    r = c.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    body = r.text
    # Compteurs par modèle de route : ni identifiant, ni paramètre de recherche.
    assert 'route="/documents/{document_id}"' in body  # modèle de route (sans le préfixe /api/v1)
    assert doc not in body and SECRET_QUERY not in body
    # Agrégats lus en base (fonction urag_metrics), toutes organisations confondues.
    assert "urag_database_up 1.0" in body
    assert 'urag_documents{state="indexed"}' in body and "urag_organizations" in body
    # Journal des requêtes : JSON, route modèle, sans le chemin réel ni les paramètres.
    lines = [rec for rec in caplog.records if rec.name == "urag.api.requests"]
    assert lines and all(doc not in rec.getMessage() and SECRET_QUERY not in str(vars(rec)) for rec in lines)
    assert {rec.route for rec in lines} >= {"/documents/{document_id}", "/documents"}


def test_02_metriques_jamais_sous_le_prefixe_publie(env):
    # Le relais HTTPS ne publie que /api/* : /metrics reste sur le réseau interne.
    assert env["client"].get("/api/v1/metrics").status_code == 404


def test_03_format_json_des_journaux():
    from urag_core.logs import JsonFormatter

    record = logging.makeLogRecord({"name": "urag.worker", "levelname": "INFO", "msg": "document %s : %s"})
    record.args = ("d1", "indexed")
    record.ms = 12
    entry = json.loads(JsonFormatter().format(record))
    assert entry["msg"] == "document d1 : indexed" and entry["ms"] == 12 and entry["lvl"] == "INFO"
