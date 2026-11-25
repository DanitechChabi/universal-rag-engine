# ruff: noqa: F811 - fixture « env » réutilisée depuis le module de la phase 1
"""Routes d'administration des sources et des documents utilisées par l'interface (phase 4)."""

from __future__ import annotations

import uuid

import pytest

from tests.integration.test_phase1 import env, search, sync  # noqa: F401 - fixture du module phase 1

pytestmark = pytest.mark.integration


def documents(env, **params) -> dict:
    r = env["client"].get("/api/v1/documents", headers=env["admin_a"], params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_01_liste_filtree_et_paginee(env):
    sync(env)
    all_docs = documents(env)
    assert all_docs["total"] == len(all_docs["items"]) >= 4
    assert all_docs["by_status"].get("indexed", 0) >= 3
    found = documents(env, q="bail")
    assert [d["title"] for d in found["items"]] == ["contrat_bail_alpha"] and found["total"] == 1
    page = documents(env, limit=2, offset=1)
    assert len(page["items"]) == 2 and page["items"][0]["id"] == all_docs["items"][1]["id"]
    assert documents(env, q="%")["total"] == 0  # pas de joker SQL depuis l'interface
    assert env["client"].get("/api/v1/documents", headers=env["bob"]).status_code == 403  # rôle utilisateur


def test_02_fiche_sans_contenu(env):
    doc = documents(env, q="bail")["items"][0]
    r = env["client"].get(f"/api/v1/documents/{doc['id']}", headers=env["admin_a"])
    assert r.status_code == 200
    detail = r.json()
    assert detail["access"]["status"] == "complete" and detail["access"]["keys"] >= 1
    current = [v for v in detail["versions"] if v["current"]]
    assert len(current) == 1 and current[0]["chunk_count"] >= 1 and current[0]["status"] == "indexed"
    assert "450 000" not in r.text  # métadonnées seulement, jamais le texte
    assert env["client"].get(f"/api/v1/documents/{uuid.uuid4()}", headers=env["admin_a"]).status_code == 404


def test_03_exclure_puis_reintegrer(env):
    doc = documents(env, q="bail")["items"][0]
    client, h = env["client"], env["admin_a"]
    assert client.post(f"/api/v1/documents/{doc['id']}/exclude", headers=h).status_code == 204
    assert all(x["title"] != "contrat_bail_alpha" for x in search(env, "bob", "loyer mensuel du bail"))
    assert client.post(f"/api/v1/documents/{doc['id']}/include", headers=h).status_code == 204
    assert search(env, "bob", "loyer mensuel du bail")[0]["title"] == "contrat_bail_alpha"


def test_04_retirer_de_l_index_puis_reintegrer(env):
    doc = documents(env, q="procedure")["items"][0]
    client, h = env["client"], env["admin_a"]
    assert client.delete(f"/api/v1/documents/{doc['id']}/index", headers=h).status_code == 204
    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=h).json()
    assert detail["status"] == "excluded" and detail["versions"] == [] and detail["excluded"]
    assert all(x["title"] != "procedure_archivage" for x in search(env, "bob", "conservation des dossiers de crédit"))
    assert (env["corpus"] / "procedure_archivage.txt").is_file()  # le fichier d'origine est intact
    sync(env)  # une synchronisation ne le réindexe pas
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).json()["status"] == "excluded"
    assert client.post(f"/api/v1/documents/{doc['id']}/include", headers=h).status_code == 204
    env["worker"].run_until_idle()
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).json()["status"] == "indexed"
    assert any(x["title"] == "procedure_archivage" for x in search(env, "bob", "conservation des dossiers de crédit"))


def test_05_reindexer(env):
    doc = documents(env, q="bail")["items"][0]
    r = env["client"].post(f"/api/v1/documents/{doc['id']}/reindex", headers=env["admin_a"])
    assert r.status_code == 202 and r.json()["job_id"] is not None
    env["worker"].run_until_idle()
    assert documents(env, q="bail")["items"][0]["status"] == "indexed"  # contenu identique : inchangé


def test_06_source_fiche_desactivation(env):
    client, h, sid = env["client"], env["admin_a"], env["source"]
    detail = client.get(f"/api/v1/sources/{sid}", headers=h).json()
    assert detail["kind"] == "local_files" and detail["enabled"] and detail["last_sync"]["seen"] >= 4
    assert detail["credentials_configured"] is False and "roots" in detail["config"]
    assert client.post(f"/api/v1/sources/{sid}/disable", headers=h).status_code == 204
    assert client.post(f"/api/v1/sources/{sid}/sync", headers=h).status_code == 409
    assert search(env, "bob", "loyer mensuel du bail")  # documents toujours consultables
    assert client.post(f"/api/v1/sources/{sid}/enable", headers=h).status_code == 204
    assert client.post(f"/api/v1/sources/{sid}/sync", headers=h).status_code == 202
    env["worker"].run_until_idle()


def test_07_supprimer_une_source(env):
    client, h = env["client"], env["admin_a"]
    folder = env["tmp"] / "archives"
    folder.mkdir()
    (folder / "circulaire_tarifs.txt").write_text("Circulaire : frais de tenue de compte de 2 500 FCFA.", "utf-8")
    sid = client.post(
        "/api/v1/sources",
        headers=h,
        json={
            "kind": "local_files",
            "name": "Archives",
            "space_id": env["space"],
            "config": {"roots": [str(folder)]},
            "inherit_space_access": True,
        },
    ).json()["id"]
    client.post(f"/api/v1/sources/{sid}/sync", headers=h)
    env["worker"].run_until_idle()
    assert search(env, "bob", "frais de tenue de compte")[0]["title"] == "circulaire_tarifs"
    assert client.delete(f"/api/v1/sources/{sid}", headers=h).status_code == 204
    assert all(x["title"] != "circulaire_tarifs" for x in search(env, "bob", "frais de tenue de compte"))
    assert (folder / "circulaire_tarifs.txt").is_file()  # jamais supprimé de la source d'origine
    assert client.get(f"/api/v1/sources/{sid}", headers=h).status_code == 404


def test_08_tableau_de_bord_sans_contenu(env):
    env["client"].post("/api/v1/chat", headers=env["bob"], json={"question": "Quel est le loyer mensuel ?"})
    r = env["client"].get("/api/v1/admin/dashboard", headers=env["admin_a"])
    assert r.status_code == 200
    data = r.json()
    assert data["documents"]["total"] >= 4 and data["fragments"] >= 4 and data["sources"]["active"] >= 1
    assert data["services"] == {"postgres": "ok", "qdrant": "ok"} and data["policy"] == "local_only"
    assert data["usage_30d"]["answers"] >= 1 and data["usage_30d"]["external"] == 0
    assert {"action", "actor", "at"} <= set(data["activity"][0])
    assert "loyer" not in r.text and "450 000" not in r.text  # ni questions ni contenu
    assert env["client"].get("/api/v1/admin/dashboard", headers=env["bob"]).status_code == 403


def test_09_modifier_un_compte(env, database):
    client, h = env["client"], env["admin_a"]
    users = {u["login"].split(".")[0]: u for u in client.get("/api/v1/users", headers=h).json()["items"]}
    carol = users["carol"]
    r = client.patch(f"/api/v1/users/{carol['id']}", headers=h, json={"roles": ["user", "doc_admin"]})
    assert r.status_code == 204
    assert client.get("/api/v1/documents", headers=env["carol"]).status_code == 200  # nouveau rôle pris en compte
    assert client.patch(f"/api/v1/users/{carol['id']}", headers=h, json={"status": "disabled"}).status_code == 204
    assert client.get("/api/v1/auth/me", headers=env["carol"]).status_code == 401  # sessions révoquées
    me = client.get("/api/v1/auth/me", headers=h).json()["user_id"]
    assert client.patch(f"/api/v1/users/{me}", headers=h, json={"roles": ["user"]}).status_code == 422
    assert client.patch(f"/api/v1/users/{me}", headers=h, json={"status": "disabled"}).status_code == 422


def test_10_espaces_et_autorisations(env):
    spaces = env["client"].get("/api/v1/spaces", headers=env["admin_a"]).json()["items"]
    juridique = next(s for s in spaces if s["id"] == env["space"])
    assert juridique["sources"] >= 1 and [g["principal_id"] for g in juridique["grants"]] == [env["bob_id"]]


def test_11_question_de_suite_reformulee(env, database):
    """« Et sa durée ? » après une question sur le bail : recherche faite sur la question autonome."""
    from sqlalchemy import create_engine, text
    from urag_core.rag import REWRITE_PROMPT

    from tests.integration.conftest import sse_events

    client, adapter = env["client"], env["adapter"]
    first = sse_events(
        client.post("/api/v1/chat", headers=env["bob"], json={"question": "Quel est le loyer mensuel du bail ?"}).text
    )
    conversation = first[0][1]["conversation_id"]
    seen: list[list] = []
    original = adapter.chat

    def scripted(model, messages, result):
        seen.append(messages)
        result.finish_reason = "STOP"
        if messages[0].content == REWRITE_PROMPT:
            assert "loyer mensuel" in messages[1].content and "[1]" not in messages[1].content.split("QUESTION")[0]
            yield "Quelle est la durée du bail commercial ?"
        else:
            yield "Le bail arrive à échéance le 31/12/2026 [1]."

    adapter.chat = scripted
    try:
        events = sse_events(
            client.post(
                "/api/v1/chat", headers=env["bob"], json={"question": "Et sa durée ?", "conversation_id": conversation}
            ).text
        )
    finally:
        adapter.chat = original
    meta = events[0][1]
    assert meta["question_reformulee"] == "Quelle est la durée du bail commercial ?"
    answer_prompt = seen[-1][1].content
    assert "QUESTION : Quelle est la durée du bail commercial ?" in answer_prompt
    assert "31/12/2026" in answer_prompt  # le bon extrait a été retrouvé grâce à la reformulation
    done = next(d for n, d in events if n == "done")
    assert "31/12/2026" in done["answer"]
    with create_engine(database["admin_url"]).connect() as c:
        details = c.execute(
            text("SELECT details FROM audit_log WHERE action = 'ai.query' ORDER BY id DESC LIMIT 1")
        ).scalar()
    assert details == {"question": "Et sa durée ?", "reformulee": "Quelle est la durée du bail commercial ?"}


def test_12_sommaire_place_apres_le_contenu(env, database):
    """Une ligne de sommaire qui reprend les mots de la question ne passe jamais devant la clause."""
    from tests.fixtures.documents import write_pdf

    toc = (
        "SOMMAIRE\nArticle 1 - Objet du contrat de maintenance ........ 2\n"
        "Article 2 - Durée du contrat de maintenance ........ 3\n"
        "Article 3 - Pénalités de retard de maintenance ........ 4\n"
        "Article 4 - Résiliation du contrat de maintenance ........ 5"
    )
    clause = (
        "Article 3 - Pénalités de retard de maintenance.\n"
        "Tout retard d'intervention entraîne une pénalité de 25 000 FCFA par jour ouvré, plafonnée à 10 %."
    )
    write_pdf(env["corpus"] / "contrat_maintenance.pdf", [toc, clause])
    sync(env)
    docs = documents(env, q="maintenance")["items"]
    detail = env["client"].get(f"/api/v1/documents/{docs[0]['id']}", headers=env["admin_a"]).json()
    assert [v["pipeline_version"] for v in detail["versions"] if v["current"]] == [3]
    hits = [h for h in search(env, "bob", "pénalités de retard de maintenance") if h["title"] == "contrat_maintenance"]
    assert hits and hits[0]["pages"] == "page 2" and "25 000 FCFA" in hits[0]["excerpt"]
    from sqlalchemy import create_engine, text

    with create_engine(database["admin_url"]).connect() as c:
        kinds = dict(
            c.execute(
                text("""SELECT c.page_start, c.kind FROM chunks c
                        JOIN documents d ON d.current_version_id = c.version_id
                        WHERE d.title = 'contrat_maintenance'""")
            ).all()
        )
    assert kinds == {1: "navigation", 2: "text"}  # le sommaire est reconnu, la clause non
    pages = [h["pages"] for h in hits]
    if "page 1" in pages:  # le sommaire peut ressortir, mais toujours après la clause
        assert pages.index("page 2") < pages.index("page 1")
