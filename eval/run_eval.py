"""Mesure de qualité sur le corpus public (docs/TESTING.md §4).

    uv run python eval/run_eval.py --files ~/urag-corpus/files --label phase1

Crée une base neuve, indexe le corpus « base » + les documents synthétiques piégés, pose
les questions de eval/corpus/questions.json et écrit docs/reports/eval-<label>.json et .md.
Utilise la pile de développement (docs/DEVELOPMENT.md) : PostgreSQL, Qdrant, Ollama.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"
REPORTS = ROOT / "docs" / "reports"


def norm(s: str) -> str:
    s = s.lower().replace(" ", " ").replace(" ", " ").replace("’", "'")
    return re.sub(r"\s+", " ", s)


def contains(answer: str, groups: list[list[str]]) -> bool:
    a = norm(answer)
    return all(any(norm(v) in a for v in group) for group in groups)


def sse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--files", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument(
        "--admin-url",
        default=os.environ.get(
            "URAG_TEST_ADMIN_URL", "postgresql+psycopg://postgres:postgres-dev@127.0.0.1:5432/postgres"
        ),
    )
    p.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    p.add_argument("--qdrant-key", default="dev-qdrant-key")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--chat-model", default="qwen2.5:1.5b")
    p.add_argument("--chat-provider", choices=("ollama", "gemini"), default="ollama")
    p.add_argument("--from-dump", type=Path, help="réutiliser un index déjà construit (pg_dump) au lieu d'indexer")
    p.add_argument("--pause-s", type=float, default=0.0, help="pause entre questions (quota d'une API gratuite)")
    p.add_argument("--keep-db", action="store_true")
    args = p.parse_args()

    from urag_api import cli
    from urag_api.main import create_app
    from urag_api.state import AppState
    from urag_core.ai import GeminiAdapter, ModelRouter, ModelSpec, OllamaAdapter
    from urag_core.config import Settings
    from urag_core.embeddings import OllamaEncoder
    from urag_core.security import TokenService
    from urag_core.storage import Database, VectorStore
    from urag_worker.main import Worker

    sources = json.loads((EVAL / "corpus" / "sources.json").read_text(encoding="utf-8"))["documents"]
    questions = json.loads((EVAL / "corpus" / "questions.json").read_text(encoding="utf-8"))["questions"]
    excluded = [f"{d['id']}.pdf" for d in sources if d.get("set") != "base"]

    name = f"urag_eval_{uuid.uuid4().hex[:8]}"
    admin = create_engine(args.admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    admin_db = make_url(args.admin_url).set(database=name).render_as_string(hide_password=False)
    app_password = "app-" + secrets.token_hex(8)
    if args.from_dump:
        import subprocess

        url = make_url(admin_db)
        env = {**os.environ, "PGPASSWORD": url.password or ""}
        restored = subprocess.run(  # noqa: S603 - arguments construits ici, aucune entrée externe
            [  # noqa: S607 - outil PostgreSQL standard
                "pg_restore",
                "-h",
                url.host or "127.0.0.1",
                "-U",
                url.username or "postgres",
                "-d",
                name,
                "--no-owner",
                "--role=postgres",
                str(args.from_dump),
            ],
            check=False,
            env=env,
            capture_output=True,
            text=True,
        )
        if restored.returncode != 0:  # avertissements de pg_restore (extensions déjà présentes…)
            print("pg_restore :", restored.stderr.strip().splitlines()[-1:], flush=True)
    else:
        cli.main(["--admin-url", admin_db, "migrate"])
    cli.main(["--admin-url", admin_db, "app-password", "--password", app_password])
    app_url = make_url(admin_db).set(username="urag_app", password=app_password).render_as_string(hide_password=False)
    try:
        password = secrets.token_urlsafe(18)
        from urag_core.security import PasswordHasher

        with create_engine(admin_db).begin() as c:
            existing = c.execute(text("SELECT id, org_id FROM users WHERE login = 'eval.admin'")).first()
            if existing:
                c.execute(
                    text("UPDATE users SET password_hash = :h WHERE id = :u"),
                    {"h": PasswordHasher().hash(password), "u": existing.id},
                )
        ids = (
            {"user_id": existing.id, "org_id": existing.org_id}
            if existing
            else cli.bootstrap(admin_db, "Évaluation", "evaluation", "eval.admin", password, "Évaluation")
        )
        external = args.chat_provider != "ollama"
        if external:
            # Corpus public : envoi d'extraits vers un fournisseur externe autorisé explicitement pour ce test.
            with create_engine(admin_db).begin() as c:
                c.execute(
                    text("""UPDATE ai_policies SET mode = 'cloud_allowed', allow_external_questions = true,
                                  allow_external_documents = true WHERE org_id = :o"""),
                    {"o": ids["org_id"]},
                )
        settings = Settings(
            database_url=app_url,
            qdrant_url=args.qdrant_url,
            ollama_url=args.ollama_url,
            cookie_secure=False,
            tmp_dir=Path(tempfile.gettempdir()) / name,
        )
        if external:
            adapter = GeminiAdapter(os.environ["URAG_GEMINI_API_KEY"])
            spec = ModelSpec(
                "externe",
                args.chat_model,
                "gemini",
                "external",
                temperature=0.0,
                max_output_tokens=600,
                context_window=32768,
                timeout_s=300,
            )
        else:
            adapter = OllamaAdapter(args.ollama_url)
            spec = ModelSpec(
                "local",
                args.chat_model,
                "ollama",
                "local",
                temperature=0.0,
                max_output_tokens=350,
                context_window=6144,
                timeout_s=900,
            )
        router = ModelRouter({spec.provider: adapter}, [spec])
        state = AppState(
            settings,
            Database(app_url),
            VectorStore(args.qdrant_url, args.qdrant_key),
            TokenService(secrets.token_bytes(32), timedelta(minutes=600), timedelta(hours=12)),
            encoder_override=OllamaEncoder(args.ollama_url, "bge-m3", 1024),
            router_override=router,
        )
        client = TestClient(create_app(state))
        token = client.post("/api/v1/auth/login", json={"login": "eval.admin", "password": password}).json()
        h = {"Authorization": f"Bearer {token['access_token']}"}
        started = time.monotonic()
        if not args.from_dump:
            space = client.post("/api/v1/spaces", headers=h, json={"name": "Corpus public"}).json()["id"]
            client.put(
                f"/api/v1/spaces/{space}/grants",
                headers=h,
                json=[{"principal_type": "user", "principal_id": str(ids["user_id"])}],
            )
            roots = [str(args.files.resolve()), str((EVAL / "corpus" / "synthetic").resolve())]
            source = client.post(
                "/api/v1/sources",
                headers=h,
                json={
                    "kind": "local_files",
                    "name": "Corpus public",
                    "space_id": space,
                    "inherit_space_access": True,
                    "config": {"roots": roots, "exclude_globs": excluded},
                },
            ).json()["id"]
            client.post(f"/api/v1/sources/{source}/sync", headers=h)
            Worker(state.db, state.ingestion).run_until_idle(max_rounds=1000)
        indexing_s = time.monotonic() - started
        docs = client.get("/api/v1/documents", headers=h).json()["items"]
        status_counts: dict[str, int] = defaultdict(int)
        for d in docs:
            status_counts[d["status"]] += 1
        chunks = sum(d["chunk_count"] or 0 for d in docs)
        print(
            f"indexation : {len(docs)} documents, {chunks} fragments, {indexing_s:.0f} s, {dict(status_counts)}",
            flush=True,
        )

        rows = []
        for q in questions:
            time.sleep(args.pause_s)
            t0 = time.monotonic()
            hits = client.post("/api/v1/search", headers=h, json={"query": q["question"], "limit": 6}).json()["items"]
            found_titles = [x["title"] for x in hits]
            events = sse(client.post("/api/v1/chat", headers=h, json={"question": q["question"]}).text)
            latency = time.monotonic() - t0
            done = next((d for n, d in events if n == "done"), None)
            cites = next((d["items"] for n, d in events if n == "citations"), [])
            answer = done["answer"] if done else json.dumps(next((d for n, d in events if n == "error"), {}))
            cited = {c["title"] for c in cites}
            if q["categorie"] == "sans_reponse":
                retrieval = None
                correct = bool(done and done["insufficient"])
                pertinent = correct and not cites
            else:
                retrieval = bool(set(q["documents_attendus"]) & set(found_titles))
                correct = contains(answer, q["doit_contenir"])
                pertinent = correct and bool(set(q["documents_attendus"]) & cited)
            rows.append(
                {
                    "id": q["id"],
                    "categorie": q["categorie"],
                    "question": q["question"],
                    "attendu": q["reponse_attendue"],
                    "reponse": answer,
                    "document_retrouve_top6": retrieval,
                    "reponse_exacte": correct,
                    "exacte_et_citation_pertinente": pertinent,
                    "citations": sorted(cited),
                    "citations_deduites": sum(bool(c.get("inferred")) for c in cites),
                    "abstention": bool(done and done["insufficient"]),
                    "lien_externe": "http" in answer,
                    "repris_le_document_piege": "5 milliards" in answer,
                    "documents_trouves": found_titles,
                    "duree_s": round(latency, 1),
                }
            )
            print(
                f"{q['id']} {q['categorie']:<22} recherche={retrieval} exacte={correct} pertinente={pertinent} "
                f"({latency:.0f} s)",
                flush=True,
            )

        def rate(items, key):
            vals = [r[key] for r in items if r[key] is not None]
            return round(sum(vals) / len(vals), 3) if vals else None

        by_cat = {}
        for cat in sorted({r["categorie"] for r in rows}):
            items = [r for r in rows if r["categorie"] == cat]
            by_cat[cat] = {
                "questions": len(items),
                "rappel_top6": rate(items, "document_retrouve_top6"),
                "reponse_exacte": rate(items, "reponse_exacte"),
                "exacte_et_citation_pertinente": rate(items, "exacte_et_citation_pertinente"),
            }
        report = {
            "label": args.label,
            "date": time.strftime("%Y-%m-%d"),
            "modele_generation": args.chat_model,
            "fournisseur": args.chat_provider,
            "politique": "cloud_allowed (corpus public, test explicite)" if external else "local_only",
            "index_reutilise": bool(args.from_dump),
            "modele_embedding": "bge-m3",
            "indexation": {
                "documents": len(docs),
                "fragments": chunks,
                "duree_s": round(indexing_s),
                "statuts": dict(status_counts),
            },
            "global": {
                "questions": len(rows),
                "rappel_top6": rate(rows, "document_retrouve_top6"),
                "reponse_exacte": rate(rows, "reponse_exacte"),
                "exacte_et_citation_pertinente": rate(rows, "exacte_et_citation_pertinente"),
                "liens_externes": sum(r["lien_externe"] for r in rows),
                "document_piege_repris": sum(r["repris_le_document_piege"] for r in rows),
                "duree_moyenne_question_s": round(sum(r["duree_s"] for r in rows) / len(rows), 1),
            },
            "par_categorie": by_cat,
            "details": rows,
        }
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"eval-{args.label}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(
            json.dumps({k: report[k] for k in ("indexation", "global", "par_categorie")}, ensure_ascii=False, indent=1)
        )
        return 0
    finally:
        if not args.keep_db:
            with admin.connect() as c:
                c.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}'"))
                c.execute(text(f'DROP DATABASE "{name}"'))


if __name__ == "__main__":
    sys.exit(main())
