"""Serveur de démonstration et de test de l'interface web (phase 4).

Lance la **vraie API** sur une base PostgreSQL neuve, avec un petit corpus indexé, un worker en
tâche de fond et un modèle de réponse **déterministe** (cite le premier extrait, mot à mot, pour
tester l'affichage progressif et l'annulation). Jamais utilisé en production.

Les identifiants générés sont écrits dans le fichier ``--info`` (hors du dépôt), lu par les tests
Playwright ; la base est supprimée à l'arrêt.

    uv run python tests/e2e/serveur_de_test.py --port 8000 --info /tmp/urag-e2e.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import signal
import sys
import tempfile
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class DemoAdapter:
    """Répond à partir du premier extrait fourni, en le citant, mot à mot."""

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def health(self) -> bool:
        return True

    def chat(self, model, messages, result):
        from urag_core.rag import REWRITE_PROMPT

        content = messages[-1].content
        if messages[0].content == REWRITE_PROMPT:  # reformulation : la question, plus le sujet précédent
            previous = re.findall(r"Utilisateur : (.*)", content)
            last = re.search(r"DERNIÈRE QUESTION : (.*)", content)
            result.finish_reason = "STOP"
            # « Et sa durée ? » après « … du bail ? » → « Quelle est la durée du bail ? »
            noun = re.findall(r"\w+", last.group(1))[-1]
            subject = re.findall(r"\w+", previous[-1])[-1]
            yield f"Quelle est la {noun} du {subject} ?"
            return
        blocks = re.findall(r"<<<EXTRAIT\n(.*?)\nEXTRAIT>>>", content, flags=re.S)
        if not blocks:
            from urag_core.citations import INSUFFICIENT

            words = INSUFFICIENT.split(" ")
        else:
            # Phrase la plus proche de la question, parmi tous les extraits (citée avec son numéro) ;
            # un intertitre court (« Article 3 - Durée. ») est rattaché à la phrase qui le suit.
            asked = re.search(r"QUESTION : (.*)", content)
            wanted = set(re.findall(r"\w{4,}", (asked.group(1) if asked else "").lower()))
            best, rank, score = "", 1, -1
            for n, block in enumerate(blocks, start=1):
                parts, merged = re.split(r"(?<=[.!?])\s", " ".join(block.split())), []
                for part in parts:
                    if merged and len(merged[-1]) < 25:
                        merged[-1] = f"{merged[-1]} {part}"
                    else:
                        merged.append(part)
                for sentence in (x.strip(" .…") for x in merged):
                    hits = len(wanted & set(re.findall(r"\w{4,}", sentence.lower())))
                    if sentence and hits > score:
                        best, rank, score = sentence, n, hits
            words = f"D'après les documents : {best} [{rank}].".split()
        result.tokens_in, result.tokens_out, result.finish_reason = len(content) // 4, len(words), "STOP"
        for i, word in enumerate(words):
            time.sleep(self.delay)
            yield word if i == 0 else f" {word}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--info", type=Path, required=True)
    p.add_argument("--delay", type=float, default=0.04, help="délai entre deux mots de la réponse (s)")
    p.add_argument(
        "--admin-url",
        default=os.environ.get(
            "URAG_TEST_ADMIN_URL", "postgresql+psycopg://postgres:postgres-dev@127.0.0.1:5432/postgres"
        ),
    )
    p.add_argument("--qdrant-url", default=os.environ.get("URAG_TEST_QDRANT_URL", "http://127.0.0.1:6333"))
    p.add_argument("--qdrant-key", default=os.environ.get("URAG_TEST_QDRANT_KEY", "dev-qdrant-key"))
    args = p.parse_args()

    import uvicorn
    from urag_api import cli
    from urag_api.main import create_app
    from urag_api.state import AppState
    from urag_core.ai import ModelRouter, ModelSpec
    from urag_core.config import Settings
    from urag_core.embeddings import HashingEncoder
    from urag_core.security import TokenService
    from urag_core.storage import Database, VectorStore
    from urag_worker.main import Worker

    from tests.fixtures.documents import build_corpus

    name = f"urag_e2e_{uuid.uuid4().hex[:8]}"
    admin = create_engine(args.admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    admin_db = make_url(args.admin_url).set(database=name).render_as_string(hide_password=False)
    cli.main(["--admin-url", admin_db, "migrate"])
    role, role_password = f"urag_run_{secrets.token_hex(6)}", secrets.token_urlsafe(18)
    cli.create_run_role(admin_db, role, role_password)
    app_url = make_url(admin_db).set(username=role, password=role_password).render_as_string(hide_password=False)

    work = Path(tempfile.mkdtemp(prefix="urag-e2e-"))
    corpus = build_corpus(work / "corpus")
    for junk in ("~$brouillon.docx", "Thumbs.db"):
        (corpus / junk).unlink(missing_ok=True)
    password = secrets.token_urlsafe(14)
    sfx = uuid.uuid4().hex[:4]
    org = cli.bootstrap(admin_db, "Cabinet Démo", f"cabinet-demo-{sfx}", f"admin.{sfx}", password, "Awa Diallo")

    settings = Settings(
        database_url=app_url,
        qdrant_url=args.qdrant_url,
        cookie_secure=False,
        tmp_dir=work / "tmp",
        context_passages=4,
    )
    tokens = TokenService(secrets.token_bytes(32), timedelta(minutes=15), timedelta(hours=12))
    model = ModelSpec("local-demo", "modèle de démonstration", "demo", "local")
    state = AppState(
        settings,
        Database(app_url),
        VectorStore(args.qdrant_url, args.qdrant_key),
        tokens,
        encoder_override=HashingEncoder(256),
        router_override=ModelRouter({"demo": DemoAdapter(args.delay)}, [model]),
    )
    app = create_app(state)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"login": f"admin.{sfx}", "password": password})
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    users = {}
    for login, display, roles in (
        (f"alice.{sfx}", "Alice Mensah", ["user"]),
        (f"chloe.{sfx}", "Chloé Adjovi", ["user"]),
        (f"doc.{sfx}", "Koffi Agbo", ["doc_admin"]),
    ):
        r = client.post(
            "/api/v1/users",
            headers=h,
            json={"login": login, "display_name": display, "password": password, "roles": roles},
        )
        r.raise_for_status()
        users[login.split(".")[0]] = {"id": r.json()["id"], "login": login}
    space = client.post("/api/v1/spaces", headers=h, json={"name": "Juridique"}).json()["id"]
    client.put(
        f"/api/v1/spaces/{space}/grants",
        headers=h,
        json=[
            {"principal_type": "user", "principal_id": users["alice"]["id"]},
            {"principal_type": "user", "principal_id": str(org["user_id"])},
        ],
    ).raise_for_status()
    source = client.post(
        "/api/v1/sources",
        headers=h,
        json={
            "kind": "local_files",
            "name": "Partage juridique",
            "space_id": space,
            "config": {"roots": [str(corpus)]},
            "inherit_space_access": True,
        },
    ).json()["id"]
    client.post(f"/api/v1/sources/{source}/sync", headers=h).raise_for_status()
    # Source simulée (GED avec identités) : montre la correspondance des comptes.
    vault = work / "ged.json"
    vault.write_text(
        json.dumps(
            {
                "users": [
                    {"id": "42", "name": "Alice Mensah", "login": users["alice"]["login"]},
                    {"id": "57", "name": "Yao Kouassi", "login": "ykouassi", "email": "y.kouassi@exemple.test"},
                ],
                "groups": [{"id": "7", "name": "Direction juridique", "members": ["42", "57"]}],
                "documents": [
                    {
                        "id": "901",
                        "title": "politique_credit_2026",
                        "filename": "politique_credit_2026.txt",
                        "class": "Politique",
                        "text": "Politique de crédit 2026. Le taux d'endettement maximal est fixé à 33 % des revenus.",
                        "acl": [{"group": "7"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ged_space = client.post("/api/v1/spaces", headers=h, json={"name": "GED"}).json()["id"]
    ged = client.post(
        "/api/v1/sources",
        headers=h,
        json={"kind": "simulator", "name": "GED (simulée)", "space_id": ged_space, "config": {"path": str(vault)}},
    ).json()["id"]
    client.post(f"/api/v1/sources/{ged}/sync", headers=h).raise_for_status()
    worker = Worker(state.db, state.ingestion)
    worker.run_until_idle()

    stop = threading.Event()

    def background() -> None:  # le worker traite aussi les synchronisations lancées depuis l'interface
        while not stop.is_set():
            worker.run_until_idle()
            stop.wait(1.0)

    threading.Thread(target=background, daemon=True).start()
    args.info.write_text(
        json.dumps(
            {
                "base_url": f"http://127.0.0.1:{args.port}",
                "password": password,
                "admin": f"admin.{sfx}",
                "alice": users["alice"]["login"],
                "chloe": users["chloe"]["login"],
                "doc_admin": users["doc"]["login"],
                "organization": "Cabinet Démo",
                "corpus": str(corpus),
            }
        ),
        encoding="utf-8",
    )
    args.info.chmod(0o600)
    print(f"API prête sur http://127.0.0.1:{args.port} (identifiants dans {args.info})", flush=True)

    def cleanup(*_):
        stop.set()
        state.db.dispose()
        with admin.connect() as c:
            c.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}'"))
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        cli.drop_run_role(args.admin_url, role)
        args.info.unlink(missing_ok=True)

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
