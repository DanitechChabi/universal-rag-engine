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


def test_04_surcharge_refus_propre_sans_connexion_retenue(env):
    """Recherches au-delà de la limite : attente sans connexion à la base, puis 503 / « search.busy »."""
    sync(env)
    c = env["client"]
    retriever = c.app.state.urag.retriever
    slots, timeout = retriever._slots, retriever.queue_timeout
    import threading

    retriever._slots, retriever.queue_timeout = threading.BoundedSemaphore(1), 0.2
    try:
        with retriever.admit():  # la seule place est prise
            pool = c.app.state.urag.db.engine.pool
            before = pool.checkedout()
            r = c.post("/api/v1/search", headers=env["admin_a"], json={"query": "rapport"})
            assert r.status_code == 503 and r.json()["code"] == "search.busy"
            assert pool.checkedout() == before  # aucune connexion prise pendant l'attente
            with c.stream("POST", "/api/v1/chat", headers=env["admin_a"], json={"question": "rapport ?"}) as s:
                body = "".join(s.iter_text())
            assert "event: error" in body and "search.busy" in body
        assert c.post("/api/v1/search", headers=env["admin_a"], json={"query": "rapport"}).status_code == 200
    finally:
        retriever._slots, retriever.queue_timeout = slots, timeout


def test_05_tache_abandonnee_reprise_meme_sans_autre_tache(env):
    """Worker arrêté en pleine tâche, plus aucune autre tâche prête : la boucle du worker la reprend."""
    from sqlalchemy import text as sql
    from urag_core.jobs import take

    sync(env)
    (env["corpus"] / "note_abandon.txt").write_text("Note : l'inventaire a lieu en mars.", encoding="utf-8")
    env["client"].post(f"/api/v1/sources/{env['source']}/sync", headers=env["admin_a"])
    st, worker = env["state"], env["worker"]
    with st.db.anonymous() as conn:
        org_id = conn.execute(sql("SELECT * FROM urag_orgs_with_ready_jobs()")).scalars().one()
    with st.db.org(org_id) as conn:
        job = take(conn, "worker-mort")
        conn.execute(sql("UPDATE jobs SET heartbeat_at = now() - interval '1 hour' WHERE id = :i"), {"i": job.id})
    with st.db.anonymous() as conn:  # plus aucune tâche prête : l'organisation n'est plus listée ici
        assert conn.execute(sql("SELECT count(*) FROM urag_orgs_with_ready_jobs()")).scalar_one() == 0
    assert worker._requeue_stale() == 1  # chemin réel de la boucle du worker
    worker.run_until_idle()
    with st.db.org(org_id) as conn:
        assert (
            conn.execute(sql("SELECT status::text FROM jobs WHERE id = :i"), {"i": job.id}).scalar_one() == "succeeded"
        )
