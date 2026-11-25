"""Phase 3 sur la pile réelle avec une source simulée (droits par document, groupes, refus).

Couvre les scénarios de recette 12 (changer les permissions) et 13 (accès révoqué) au
niveau du document, et la correspondance des comptes (ADR-0016)."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from urag_api.cli import bootstrap
from urag_api.main import create_app
from urag_core.ai import ModelRouter, ModelSpec
from urag_core.embeddings import HashingEncoder
from urag_worker.main import Worker

from tests.integration.conftest import login, make_state
from tests.integration.test_phase1 import ScriptedAdapter

pytestmark = pytest.mark.integration
PASSWORD = "mot de passe de test 2026"


@pytest.fixture(scope="module")
def env(database, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("phase3")
    adapter = ScriptedAdapter()
    router = ModelRouter({"fake": adapter}, [ModelSpec("local-fake", "modele-test", "fake", "local")])
    state = make_state(database, tmp, HashingEncoder(256), router)
    client = TestClient(create_app(state))
    sfx = uuid.uuid4().hex[:6]
    org = bootstrap(database["admin_url"], "Cabinet C", f"cabinet-c-{sfx}", f"admin.c.{sfx}", PASSWORD, "Admin C")
    admin = login(client, f"admin.c.{sfx}", PASSWORD)
    users = {}
    for name, email in (("alice", None), ("bruno", f"bruno.{sfx}@exemple.test"), ("chloe", None)):
        r = client.post(
            "/api/v1/users",
            headers=admin,
            json={"login": f"{name}.{sfx}", "display_name": name, "email": email, "password": PASSWORD},
        )
        assert r.status_code == 201, r.text
        users[name] = (r.json()["id"], login(client, f"{name}.{sfx}", PASSWORD))
    vault = {
        "users": [
            {"id": "42", "name": "Alice Martin", "login": f"ALICE.{sfx}"},  # même identifiant (casse différente)
            {"id": "43", "name": "Bruno Kossi", "login": "bkossi", "email": f"bruno.{sfx}@exemple.test"},
            {"id": "44", "name": "Dora Inconnue", "login": "dora"},  # aucun compte local
        ],
        "groups": [{"id": "7", "name": "Juridique", "members": ["42", "43"]}],
        "documents": [
            {
                "id": "101",
                "title": "bail_pins",
                "filename": "bail_pins.txt",
                "class": "Contrat",
                "text": "Le bail des Pins fixe un loyer trimestriel de 900 000 FCFA.",
                "acl": [{"group": "7"}],
            },
            {
                "id": "102",
                "title": "dossier_rh_alice",
                "filename": "dossier_rh_alice.txt",
                "class": "RH",
                "text": "Dossier RH : prime annuelle exceptionnelle accordée.",
                "acl": [{"user": "42"}],
            },
            {
                "id": "103",
                "title": "audit_interne",
                "filename": "audit_interne.txt",
                "class": "Audit",
                "text": "Audit interne : écarts de caisse relevés à l'agence nord.",
                "acl": [{"group": "7"}, {"user": "43", "deny": True}],
            },
            {
                "id": "104",
                "title": "projet_fusion",
                "filename": "projet_fusion.txt",
                "class": "Stratégie",
                "text": "Projet de fusion avec la banque partenaire.",
                "acl": [{"group": "7"}],
                "acl_complete": False,
            },
        ],
    }
    path = tmp / "coffre.json"
    path.write_text(json.dumps(vault), encoding="utf-8")
    space = client.post("/api/v1/spaces", headers=admin, json={"name": "GED"}).json()["id"]
    r = client.post(
        "/api/v1/sources",
        headers=admin,
        json={
            "kind": "simulator",
            "name": "GED simulée",
            "space_id": space,
            "config": {"path": str(path), "batch_size": 2},
        },
    )
    assert r.status_code == 201, r.text
    return {
        "client": client,
        "adapter": adapter,
        "worker": Worker(state.db, state.ingestion),
        "admin": admin,
        "users": users,
        "vault": vault,
        "path": path,
        "source": r.json()["id"],
        "org": org,
        "sfx": sfx,
    }


def log(env, kind: str, doc_id: str) -> None:
    """Journal de changements de la GED simulée (ce que la source enregistre à chaque modification)."""
    journal = env["vault"].setdefault("journal", [])
    journal.append({"seq": len(journal) + 1, "kind": kind, "id": doc_id})


def sync(env) -> None:
    env["path"].write_text(json.dumps(env["vault"]), encoding="utf-8")
    r = env["client"].post(f"/api/v1/sources/{env['source']}/sync", headers=env["admin"])
    assert r.status_code == 202, r.text
    env["worker"].run_until_idle()


def visible(env, who: str) -> set[str]:
    """Titres des documents que ``who`` retrouve, sur une requête couvrant tout le coffre."""
    titles = set()
    for q in (
        "loyer trimestriel bail des Pins",
        "prime annuelle exceptionnelle",
        "écarts de caisse agence nord",
        "projet de fusion banque partenaire",
    ):
        r = env["client"].post("/api/v1/search", headers=env["users"][who][1], json={"query": q})
        assert r.status_code == 200, r.text
        titles |= {h["title"] for h in r.json()["items"]}
    return titles


def identities(env) -> dict[str, dict]:
    r = env["client"].get(f"/api/v1/sources/{env['source']}/identities", headers=env["admin"])
    assert r.status_code == 200, r.text
    return {i["external_id"]: i for i in r.json()["items"]}


def test_01_identites_synchronisees_et_correspondances_proposees(env):
    sync(env)
    ids = identities(env)
    assert set(ids) == {"42", "43", "44", "7"}
    assert ids["7"]["kind"] == "group" and ids["7"]["memberships"] == 2
    assert ids["42"]["link"] == {"user_id": env["users"]["alice"][0], "login": f"alice.{env['sfx']}", "verified": False}
    assert ids["43"]["link"]["user_id"] == env["users"]["bruno"][0]  # proposé par le courriel
    assert ids["43"]["link"]["verified"] is False
    assert ids["44"]["link"] is None


def test_02_proposition_non_confirmee_ne_donne_aucun_droit(env):
    assert visible(env, "alice") == set()
    assert visible(env, "bruno") == set()


def test_03_confirmation_droits_par_document(env):
    ids = identities(env)
    r = env["client"].post(f"/api/v1/principal-links/{ids['42']['id']}/confirm", headers=env["admin"])
    assert r.status_code == 204, r.text
    # Alice : via le groupe 7 (bail) et en personne (dossier RH).
    assert visible(env, "alice") == {"bail_pins", "dossier_rh_alice"}


def test_03b_droit_retire_dans_la_source_effet_immediat(env):
    """Sans attendre la synchronisation : revérification auprès de la source à chaque requête."""
    client, alice = env["client"], env["users"]["alice"][1]
    hit = next(
        h
        for h in client.post("/api/v1/search", headers=alice, json={"query": "prime annuelle exceptionnelle"}).json()[
            "items"
        ]
        if h["title"] == "dossier_rh_alice"
    )
    assert client.get(f"/api/v1/documents/{hit['document_id']}/open", headers=alice).status_code == 200
    changed = json.loads(json.dumps(env["vault"]))
    next(d for d in changed["documents"] if d["id"] == "102")["acl"] = []  # retiré dans la GED, pas encore synchronisé
    env["path"].write_text(json.dumps(changed), encoding="utf-8")
    try:
        assert visible(env, "alice") == {"bail_pins"}
        assert client.get(f"/api/v1/documents/{hit['document_id']}/open", headers=alice).status_code == 404
        env["adapter"].last_messages = None
        r = client.post("/api/v1/chat", headers=alice, json={"question": "Quelle prime annuelle exceptionnelle ?"})
        assert env["adapter"].last_messages is not None  # le modèle a bien été appelé (avec le bail seulement)
        assert r.status_code == 200
        sent = " ".join(m.content for m in env["adapter"].last_messages or [])
        assert "Dossier RH" not in sent and "dossier_rh_alice" not in r.text  # ni transmis au modèle, ni cité
    finally:
        env["path"].write_text(json.dumps(env["vault"]), encoding="utf-8")
    assert visible(env, "alice") == {"bail_pins", "dossier_rh_alice"}


def test_03c_source_injoignable_ferme_par_defaut(env):
    hidden = env["path"].with_suffix(".absent")
    env["path"].rename(hidden)
    try:
        assert visible(env, "alice") == set()
    finally:
        hidden.rename(env["path"])
    assert visible(env, "alice") == {"bail_pins", "dossier_rh_alice"}


def test_04_refus_explicite_et_droits_incomplets_invisibles_pour_tous(env):
    docs = {d["title"]: d for d in env["client"].get("/api/v1/documents", headers=env["admin"]).json()["items"]}
    assert docs["audit_interne"]["acl_status"] == "uncertain"  # refus explicite non représentable
    assert docs["projet_fusion"]["acl_status"] == "uncertain"  # droits non résolus par la source
    assert docs["audit_interne"]["access_key_count"] == 0 and docs["projet_fusion"]["access_key_count"] == 0
    assert not {"audit_interne", "projet_fusion"} & visible(env, "alice")


def test_05_import_csv(env):
    sfx = env["sfx"]
    bad = f"login_local;identifiant_externe\nbruno.{sfx};43\ninconnu;44\n"
    r = env["client"].post(
        f"/api/v1/sources/{env['source']}/principal-links/import", headers=env["admin"], json={"csv": bad}
    )
    assert r.status_code == 422 and "compte local inconnu" in r.text
    assert identities(env)["43"]["link"]["verified"] is False  # rien n'a été importé
    r = env["client"].post(
        f"/api/v1/sources/{env['source']}/principal-links/import",
        headers=env["admin"],
        json={"csv": f"login_local;identifiant_externe\nbruno.{sfx};43\n"},
    )
    assert r.status_code == 200 and r.json() == {"imported": 1}
    assert visible(env, "bruno") == {"bail_pins"}  # pas le dossier RH d'Alice
    assert visible(env, "chloe") == set()  # aucun lien : aucun document de la source


def test_06_scenario_12_permissions_modifiees(env):
    doc = next(d for d in env["vault"]["documents"] if d["id"] == "102")
    doc["acl"] = [{"user": "43"}]  # le dossier passe d'Alice à Bruno
    log(env, "access_changed", "102")
    sync(env)  # incrémentale : seul le dossier 102 est relu
    assert "dossier_rh_alice" not in visible(env, "alice")
    assert "dossier_rh_alice" in visible(env, "bruno")


def test_07_scenario_13_revocation(env):
    env["vault"]["groups"][0]["members"] = ["43"]  # Alice quitte le groupe Juridique
    sync(env)
    assert visible(env, "alice") == set()
    assert "bail_pins" in visible(env, "bruno")
    # Lien supprimé par l'administrateur : effet immédiat, sans synchronisation.
    ids = identities(env)
    r = env["client"].delete(f"/api/v1/principal-links/{ids['43']['id']}", headers=env["admin"])
    assert r.status_code == 204
    assert visible(env, "bruno") == set()


def test_08_identite_disparue_de_la_source(env):
    ids = identities(env)
    env["client"].put(
        "/api/v1/principal-links",
        headers=env["admin"],
        json={"user_id": env["users"]["bruno"][0], "external_principal_id": ids["43"]["id"]},
    )
    assert "bail_pins" in visible(env, "bruno")
    env["vault"]["users"] = [u for u in env["vault"]["users"] if u["id"] != "43"]
    env["vault"]["groups"][0]["members"] = []
    sync(env)
    assert "43" not in identities(env)
    assert visible(env, "bruno") == set()


def test_09_garde_fous(env):
    ids = identities(env)
    alice = env["users"]["alice"][1]
    assert env["client"].get(f"/api/v1/sources/{env['source']}/identities", headers=alice).status_code == 403
    r = env["client"].put(
        "/api/v1/principal-links",
        headers=env["admin"],
        json={"user_id": env["users"]["chloe"][0], "external_principal_id": ids["7"]["id"]},
    )
    assert r.status_code == 422  # un groupe ne se lie pas à un compte
    r = env["client"].put(
        "/api/v1/principal-links",
        headers=env["admin"],
        json={"user_id": env["users"]["chloe"][0], "external_principal_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


def test_10_synchronisation_incrementale_reprise_apres_coupure(env, database):
    """Scénario 16 : coupure de la source au milieu d'une synchronisation, reprise sans perte ni doublon."""
    from sqlalchemy import create_engine, text

    for i in range(5):
        env["vault"]["documents"].append(
            {
                "id": f"2{i:02d}",
                "title": f"circulaire_{i}",
                "filename": f"circulaire_{i}.txt",
                "class": "Circulaire",
                "text": f"Circulaire numéro {i} relative aux horaires du guichet.",
                "acl": [{"group": "7"}],
            }
        )
        log(env, "upsert", f"2{i:02d}")
    first_new = env["vault"]["journal"][-5]["seq"]
    env["vault"]["fail_from_seq"] = first_new + 2  # lots de 2 : le premier passe, le deuxième coupe
    sync(env)
    admin = create_engine(database["admin_url"])
    with admin.connect() as c:
        cursor = c.execute(text("SELECT sync_cursor FROM sources WHERE id = :s"), {"s": env["source"]}).scalar()
        job = c.execute(
            text("SELECT status::text, last_error FROM jobs WHERE kind = 'sync_source' ORDER BY id DESC LIMIT 1")
        ).first()
    assert cursor == {"seq": first_new + 1}  # le lot terminé est acquis
    assert job.status == "queued" and "coupure simulée" in job.last_error  # nouvel essai prévu
    del env["vault"]["fail_from_seq"]
    env["path"].write_text(json.dumps(env["vault"]), encoding="utf-8")
    with admin.begin() as c:  # on n'attend pas le délai du nouvel essai
        c.execute(text("UPDATE jobs SET run_after = now() WHERE kind = 'sync_source' AND status = 'queued'"))
    env["worker"].run_until_idle()
    with admin.connect() as c:
        rows = c.execute(
            text("SELECT title, status::text FROM documents WHERE source_id = :s AND title LIKE 'circulaire_%'"),
            {"s": env["source"]},
        ).all()
        cursor = c.execute(text("SELECT sync_cursor FROM sources WHERE id = :s"), {"s": env["source"]}).scalar()
    assert sorted(r.title for r in rows) == [f"circulaire_{i}" for i in range(5)]  # aucun doublon, aucune perte
    assert {r.status for r in rows} == {"indexed"}
    assert cursor == {"seq": env["vault"]["journal"][-1]["seq"]}
    # Suppression journalisée : retirée de l'index à la synchronisation incrémentale suivante.
    next(d for d in env["vault"]["documents"] if d["id"] == "200")["deleted"] = True
    log(env, "delete", "200")
    sync(env)
    with admin.connect() as c:
        status = c.execute(
            text("SELECT status::text FROM documents WHERE source_id = :s AND external_id = '200'"),
            {"s": env["source"]},
        ).scalar()
    assert status == "deleted"
