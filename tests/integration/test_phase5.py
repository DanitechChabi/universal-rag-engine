# ruff: noqa: F811 - fixture « env » réutilisée depuis le module de la phase 1
"""Phase 5 : IA hybride — modèles configurés par l'organisation, politique, plafonds, consommation.

Un faux fournisseur « compatible OpenAI » (vrai serveur HTTP local) joue le modèle local et le modèle
externe : les adaptateurs sont testés de bout en bout sans clé réelle ni accès à Internet.
Le même serveur imite aussi l'API Messages d'Anthropic (Claude) pour l'adaptateur Anthropic.
Scénarios de recette 14 (basculer entre deux modèles) et 15 (désactiver l'accès aux API externes).
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import create_engine, text

from tests.integration.conftest import sse_events
from tests.integration.test_phase1 import env, sync  # noqa: F401

pytestmark = pytest.mark.integration
SECRET_KEY = "cle-de-test-externe-123"
CLAUDE_KEY = "cle-de-test-anthropic-456"


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.app = FastAPI()

        @self.app.get("/v1/models")
        def models(request: Request):
            return {"data": [{"id": "local-7b"}, {"id": "cloud-large"}]}

        @self.app.post("/v1/chat/completions")
        async def chat(request: Request):
            body = await request.json()
            self.calls.append({"auth": request.headers.get("authorization"), "body": body})

            def stream():
                for piece in ["Le loyer mensuel est ", "de 450 000 FCFA [1]."]:
                    delta = {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                    yield f"data: {json.dumps(delta)}\n\n"
                yield f"data: {json.dumps({'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                usage = {"choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 50}}
                yield f"data: {json.dumps(usage)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(stream(), media_type="text/event-stream")

        @self.app.get("/v1/models/{name}")
        def anthropic_model(name: str):
            if name != "claude-test":
                return JSONResponse({"type": "error", "error": {"type": "not_found_error", "message": "?"}}, 404)
            return {"type": "model", "id": name, "display_name": name, "created_at": "2026-01-01T00:00:00Z"}

        @self.app.post("/v1/messages")
        async def anthropic_messages(request: Request):
            body = await request.json()
            self.calls.append({"auth": request.headers.get("authorization"), "body": body})
            message = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 700, "output_tokens": 1},
            }
            events = [
                {"type": "message_start", "message": message},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Le loyer mensuel est de 450 000 FCFA [1]."},
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 30},
                },
                {"type": "message_stop"},
            ]
            data = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
            return StreamingResponse(iter([data]), media_type="text/event-stream")


@pytest.fixture(scope="module")
def provider():
    fake = FakeProvider()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    fake.url = f"http://127.0.0.1:{port}/v1"
    yield fake
    server.should_exit = True


def chat(env, question: str, model_id: str | None = None) -> list[tuple[str, dict]]:
    body = {"question": question} | ({"model_id": model_id} if model_id else {})
    r = env["client"].post("/api/v1/chat", headers=env["bob"], json=body)
    assert r.status_code == 200, r.text
    return sse_events(r.text)


def meta(events):
    return next(d for n, d in events if n == "meta")


def test_01_configuration_et_cle_chiffree(env, provider, database):
    sync(env)
    c, h = env["client"], env["admin_a"]
    r = c.post(
        "/api/v1/admin/ai/providers",
        headers=h,
        json={"kind": "openai_compatible", "name": "Serveur local", "endpoint": provider.url, "locality": "local"},
    )
    assert r.status_code == 201 and r.json()["locality"] == "local"
    local_provider = r.json()["id"]
    r = c.post(
        "/api/v1/admin/ai/providers",
        headers=h,
        json={"kind": "openai", "name": "OpenAI", "endpoint": provider.url, "api_key": SECRET_KEY},
    )
    assert r.status_code == 201 and r.json()["locality"] == "external"  # imposé pour OpenAI
    external_provider = r.json()["id"]
    overview = c.get("/api/v1/admin/ai", headers=h)
    assert SECRET_KEY not in overview.text  # jamais renvoyée
    keys = {p["name"]: p["key_configured"] for p in overview.json()["providers"]}
    assert keys == {"Serveur local": False, "OpenAI": True}
    with create_engine(database["admin_url"]).connect() as conn:
        stored = conn.execute(text("SELECT ciphertext FROM secrets WHERE purpose LIKE 'provider:%'")).scalars().all()
    assert stored and all(SECRET_KEY.encode() not in bytes(x) for x in stored)  # chiffrée en base
    local = c.post(
        "/api/v1/admin/ai/models",
        headers=h,
        json={"provider_id": local_provider, "name": "local-7b", "priority": 10},
    ).json()["id"]
    external = c.post(
        "/api/v1/admin/ai/models",
        headers=h,
        json={
            "provider_id": external_provider,
            "name": "cloud-large",
            "priority": 20,
            "input_cost_per_mtok": 2.0,
            "output_cost_per_mtok": 8.0,
        },
    ).json()["id"]
    env["models"] = {"local": local, "external": external}
    # Pas encore testés : jamais proposés (le modèle de l'installation reste utilisé).
    assert [m["name"] for m in c.get("/api/v1/models", headers=env["bob"]).json()["items"]] == ["modele-test"]
    for mid in (local, external):
        r = c.post(f"/api/v1/admin/ai/models/{mid}/test", headers=h)
        assert r.json()["available"] is True, r.text


def test_02_politique_locale_par_defaut(env, provider):
    names = [m["name"] for m in env["client"].get("/api/v1/models", headers=env["bob"]).json()["items"]]
    assert names == ["local-7b"]  # l'externe n'est pas proposé en « local uniquement »
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=env["models"]["external"])
    assert meta(events)["model"]["name"] == "local-7b"  # demandé, mais interdit : modèle local
    assert provider.calls[-1]["auth"] is None  # aucune clé envoyée au serveur local


def test_03_scenario_14_basculer_vers_le_modele_externe(env, provider, database):
    c, h = env["client"], env["admin_a"]
    r = c.put("/api/v1/admin/ai/policy", headers=h, json={"mode": "cloud_allowed", "allow_external_documents": True})
    assert r.status_code == 204, r.text
    names = [m["name"] for m in c.get("/api/v1/models", headers=env["bob"]).json()["items"]]
    assert names == ["local-7b", "cloud-large"]
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=env["models"]["external"])
    assert meta(events)["model"] == {"id": env["models"]["external"], "name": "cloud-large", "locality": "external"}
    assert provider.calls[-1]["auth"] == f"Bearer {SECRET_KEY}"  # clé déchiffrée seulement pour l'appel
    assert "450 000" in next(d for n, d in events if n == "done")["answer"]
    with create_engine(database["admin_url"]).connect() as conn:
        usage = conn.execute(
            text("SELECT tokens_in, tokens_out, cost_estimate FROM usage_records ORDER BY id DESC LIMIT 1")
        ).one()
        audit = conn.execute(
            text("SELECT details::text FROM audit_log WHERE action = 'ai.external_call' ORDER BY id DESC LIMIT 1")
        ).scalar()
    assert (usage.tokens_in, usage.tokens_out) == (1000, 50)
    assert float(usage.cost_estimate) == pytest.approx((1000 * 2.0 + 50 * 8.0) / 1e6)
    assert "cloud-large" in audit and "loyer" not in audit and "450 000" not in audit  # sans contenu


def test_04_scenario_15_couper_l_externe(env, provider):
    c = env["client"]
    assert c.put("/api/v1/admin/ai/policy", headers=env["admin_a"], json={"mode": "local_only"}).status_code == 204
    assert [m["name"] for m in c.get("/api/v1/models", headers=env["bob"]).json()["items"]] == ["local-7b"]
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=env["models"]["external"])
    assert meta(events)["model"]["locality"] == "local"  # effet immédiat
    r = c.put(
        "/api/v1/admin/ai/policy",
        headers=env["admin_a"],
        json={"mode": "local_only", "allow_external_questions": True},
    )
    assert r.status_code == 422  # politique incohérente refusée (contrainte de la base)


def test_05_plafond_depasse_coupe_l_externe(env, provider):
    c, h = env["client"], env["admin_a"]
    c.put("/api/v1/admin/ai/policy", headers=h, json={"mode": "cloud_allowed", "allow_external_documents": True})
    assert c.put("/api/v1/admin/ai/limits", headers=h, json=[{"period": "day", "max_tokens": 1500}]).status_code == 204
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=env["models"]["external"])
    assert meta(events)["model"]["locality"] == "external"  # 1 050 jetons externes au total : sous le plafond
    status = c.get("/api/v1/admin/ai", headers=h).json()["limits_status"]
    assert status[0]["exceeded"] is True  # 2 100 jetons externes aujourd'hui > 1 500
    models = c.get("/api/v1/models", headers=env["bob"]).json()
    assert models["external_blocked_by_limit"] is True and [m["name"] for m in models["items"]] == ["local-7b"]
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=env["models"]["external"])
    assert meta(events)["model"]["locality"] == "local"


def test_06_reserve_a_l_administrateur(env):
    assert env["client"].get("/api/v1/admin/ai", headers=env["bob"]).status_code == 403
    r = env["client"].put("/api/v1/admin/ai/policy", headers=env["bob"], json={"mode": "cloud_allowed"})
    assert r.status_code == 403


def test_07_claude_par_l_adaptateur_anthropic(env, provider, database):
    c, h = env["client"], env["admin_a"]
    assert c.put("/api/v1/admin/ai/limits", headers=h, json=[]).status_code == 204  # plafond du test 05 retiré
    r = c.post(
        "/api/v1/admin/ai/providers",
        headers=h,
        json={
            "kind": "anthropic",
            "name": "Anthropic",
            "endpoint": provider.url.removesuffix("/v1"),
            "api_key": CLAUDE_KEY,
            "locality": "local",
        },
    )
    assert r.status_code == 201 and r.json()["locality"] == "external"  # toujours externe, même si « local » demandé
    pid = r.json()["id"]
    inconnu = c.post("/api/v1/admin/ai/models", headers=h, json={"provider_id": pid, "name": "claude-inconnu"}).json()[
        "id"
    ]
    assert c.post(f"/api/v1/admin/ai/models/{inconnu}/test", headers=h).json()["available"] is False
    claude = c.post(
        "/api/v1/admin/ai/models",
        headers=h,
        json={
            "provider_id": pid,
            "name": "claude-test",
            "priority": 30,
            "input_cost_per_mtok": 4.0,
            "output_cost_per_mtok": 20.0,
        },
    ).json()["id"]
    assert c.post(f"/api/v1/admin/ai/models/{claude}/test", headers=h).json()["available"] is True
    assert CLAUDE_KEY not in c.get("/api/v1/admin/ai", headers=h).text
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=claude)
    assert meta(events)["model"] == {"id": claude, "name": "claude-test", "locality": "external"}
    done = next(d for n, d in events if n == "done")
    assert "450 000" in done["answer"] and "[1]" in done["answer"] and not done["insufficient"]
    call = provider.calls[-1]
    assert call["auth"] == f"Bearer {CLAUDE_KEY}" and "temperature" not in call["body"]
    assert call["body"]["system"] and all(m["role"] != "system" for m in call["body"]["messages"])
    with create_engine(database["admin_url"]).connect() as conn:
        usage = conn.execute(
            text("SELECT tokens_in, tokens_out, cost_estimate FROM usage_records ORDER BY id DESC LIMIT 1")
        ).one()
    assert (usage.tokens_in, usage.tokens_out) == (700, 30)
    assert float(usage.cost_estimate) == pytest.approx((700 * 4.0 + 30 * 20.0) / 1e6)
    c.put("/api/v1/admin/ai/policy", headers=h, json={"mode": "local_only"})
    events = chat(env, "Quel est le loyer mensuel du bail ?", model_id=claude)
    assert meta(events)["model"]["locality"] == "local"  # scénario 15 : Claude coupé immédiatement
