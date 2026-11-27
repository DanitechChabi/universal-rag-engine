# ruff: noqa: F811 - fixture « env » réutilisée depuis le module de la phase 1
"""Phase 8 : correctifs de la revue de sécurité (docs/reports/SECURITE-PHASE8.md)."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from urag_api.main import create_app

from tests.integration.test_phase1 import PASSWORD, env, sync  # noqa: F401

pytestmark = pytest.mark.integration


def _new_user(env, roles=("user",)) -> tuple[str, str]:
    name = f"essai.{uuid.uuid4().hex[:6]}"
    r = env["client"].post(
        "/api/v1/users",
        headers=env["admin_a"],
        json={"login": name, "display_name": name, "password": PASSWORD, "roles": list(roles)},
    )
    assert r.status_code == 201, r.text
    return name, r.json()["id"]


def test_01_source_locale_hors_des_dossiers_autorises(env):
    """Même un administrateur ne peut pas faire indexer un dossier choisi librement sur le serveur."""
    c = env["client"]
    for root in ("/", "/etc", "/run/urag"):
        r = c.post(
            "/api/v1/sources",
            headers=env["admin_a"],
            json={"kind": "local_files", "name": f"x{root}", "space_id": env["space"], "config": {"roots": [root]}},
        )
        assert r.status_code == 422 and r.json()["code"] == "source.root_not_allowed", r.text


def test_02_essais_paralleles_bloques(env, database):
    """Le blocage après 5 échecs tient même quand les essais arrivent en même temps."""
    name, _ = _new_user(env)
    app = create_app(env["state"])

    def attempt(_):
        return TestClient(app).post("/api/v1/auth/login", json={"login": name, "password": "mauvais-mot-de-passe"})

    with ThreadPoolExecutor(12) as ex:
        codes = [r.status_code for r in ex.map(attempt, range(12))]
    with create_engine(database["admin_url"]).connect() as conn:
        failures, locked = conn.execute(
            text("SELECT failed_logins, locked_until IS NOT NULL FROM users WHERE login = :l"), {"l": name}
        ).one()
    # Chaque essai vérifié a été compté ; au-delà de la limite, refus sans vérifier le mot de passe.
    assert locked and codes.count(401) == failures == 5 and codes.count(423) == 7
    # Le bon mot de passe reste refusé pendant le blocage.
    r = env["client"].post("/api/v1/auth/login", json={"login": name, "password": PASSWORD})
    assert r.status_code == 423


def test_03_deconnexion_efface_les_cookies(env):
    name, _ = _new_user(env)
    c = TestClient(create_app(env["state"]))
    r = c.post("/api/v1/auth/login", json={"login": name, "password": PASSWORD})
    csrf = r.json()["csrf_token"]
    r = c.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})
    assert r.status_code == 204
    cleared = {h.split("=", 1)[0]: h for h in r.headers.get_list("set-cookie")}
    assert "Path=/api;" in cleared["urag_access"] and "Max-Age=0" in cleared["urag_access"]
    assert "Path=/api/v1/auth" in cleared["urag_refresh"] and "Max-Age=0" in cleared["urag_refresh"]


def test_04_compte_super_administrateur_protege(env, database):
    name, uid = _new_user(env, roles=("user",))
    with create_engine(database["admin_url"]).begin() as conn:
        conn.execute(
            text("""INSERT INTO user_roles (org_id, user_id, role)
                    SELECT org_id, id, 'super_admin' FROM users WHERE id = :u"""),
            {"u": uid},
        )
    c = env["client"]
    for patch in ({"status": "disabled"}, {"roles": ["user"]}):
        r = c.patch(f"/api/v1/users/{uid}", headers=env["admin_a"], json=patch)
        assert r.status_code == 403 and r.json()["code"] == "user.protected"
    assert c.patch(f"/api/v1/users/{uid}", headers=env["admin_a"], json={"display_name": "Renommé"}).status_code == 204
    with create_engine(database["admin_url"]).connect() as conn:
        roles = conn.execute(text("SELECT role::text FROM user_roles WHERE user_id = :u"), {"u": uid}).scalars().all()
    assert "super_admin" in roles


def test_05_limite_des_echecs_par_adresse(env, database):
    """Même mot de passe essayé sur de nombreux comptes : au-delà de 20 échecs en 15 min, 429."""
    name, uid = _new_user(env)
    attacker, other = "203.0.113.9", "203.0.113.10"
    with create_engine(database["admin_url"]).begin() as conn:
        conn.execute(
            text("""INSERT INTO audit_log (org_id, actor_user_id, action, outcome, ip)
                    SELECT org_id, id, 'auth.login', 'failure', CAST(:ip AS inet)
                    FROM users, generate_series(1, 20) WHERE id = :u"""),
            {"ip": attacker, "u": uid},
        )
    app = create_app(env["state"])
    r = TestClient(app, client=(attacker, 50000)).post("/api/v1/auth/login", json={"login": name, "password": PASSWORD})
    assert r.status_code == 429 and r.json()["code"] == "auth.too_many_attempts"
    assert r.headers["retry-after"] == "900"
    r = TestClient(app, client=(other, 50000)).post("/api/v1/auth/login", json={"login": name, "password": PASSWORD})
    assert r.status_code == 200  # les autres adresses ne sont pas touchées


def _converse(env, who: str, message: str, reply: str):
    """Pose un message en remplaçant la réponse du modèle factice ; renvoie (évènements, messages envoyés)."""
    from tests.integration.conftest import sse_events

    adapter, sent = env["adapter"], {}

    def chat(model, messages, result):
        sent["messages"] = messages
        result.tokens_in, result.tokens_out = 50, 12
        yield reply

    original, adapter.chat = adapter.chat, chat
    try:
        r = env["client"].post("/api/v1/chat", headers=env[who], json={"question": message})
    finally:
        adapter.chat = original
    assert r.status_code == 200, r.text
    return sse_events(r.text), sent.get("messages")


def test_06_conversation_naturelle_sans_recherche(env):
    """« Bonjour » : réponse du modèle, naturelle, sans recherche ni extrait, avec les titres accessibles."""
    sync(env)
    events, messages = _converse(env, "bob", "Bonjour !", "Bonjour bob ! Que puis-je chercher pour vous ?")
    names = [n for n, _ in events]
    done = dict(events)["done"]
    assert dict(events)["meta"]["conversation"] is True and done["conversation"] is True
    assert done["answer"] == "Bonjour bob ! Que puis-je chercher pour vous ?" and not done["insufficient"]
    assert "sources" not in names and dict(events)["citations"]["items"] == []
    system = messages[0].content
    assert "bob" in system and "titres seulement" in system  # prénom et documents accessibles
    assert "EXTRAITS" not in "".join(m.content for m in messages)  # aucun contenu de document
    # Suite de la conversation : l'échange précédent est transmis au modèle.
    conv = dict(events)["meta"]["conversation_id"]
    from tests.integration.conftest import sse_events

    adapter, sent = env["adapter"], {}

    def chat(model, msgs, result):
        sent["m"] = msgs
        yield "Avec plaisir !"

    original, adapter.chat = adapter.chat, chat
    try:
        r = env["client"].post(
            "/api/v1/chat", headers=env["bob"], json={"question": "Merci beaucoup", "conversation_id": conv}
        )
    finally:
        adapter.chat = original
    assert dict(sse_events(r.text))["done"]["answer"] == "Avec plaisir !"
    assert any(m.role == "assistant" and "Bonjour bob" in m.content for m in sent["m"])


def test_07_conversation_sans_fait_non_source(env):
    """Si le modèle avance un chiffre en simple conversation, la réponse est remplacée."""
    events, _ = _converse(env, "bob", "Salut", "Salut ! Le taux directeur est de 3,5 % en ce moment.")
    done = dict(events)["done"]
    assert "3,5" not in done["answer"] and "documentaire" in done["answer"]


def test_08_question_documentaire_inchangee(env):
    """Une question précédée d'une salutation reste une question documentaire, avec ses sources."""
    from tests.integration.conftest import sse_events

    sync(env)
    r = env["client"].post("/api/v1/chat", headers=env["bob"], json={"question": "Bonjour, quel est le loyer ?"})
    events = dict(sse_events(r.text))
    assert not events["done"].get("conversation") and events["citations"]["items"]
