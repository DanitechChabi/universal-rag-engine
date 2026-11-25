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
