"""Adaptateur Anthropic (Claude) testé contre un faux serveur au format de l'API Messages.

Aucun appel réseau : le transport HTTP du SDK est remplacé par un gestionnaire local.
"""

from __future__ import annotations

import json

import httpx2
import pytest
from anthropic import DefaultHttpxClient
from urag_core.ai import AnthropicAdapter, ChatMessage, ChatResult, ModelSpec, ProviderError

KEY = "cle-de-test-anthropic"
SPEC = ModelSpec("c", "claude-test", "anthropic", "external", max_output_tokens=300)


def sse(*events: dict) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def answer(stop_reason: str = "end_turn") -> bytes:
    message = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 1, "cache_read_input_tokens": 100},
    }
    return sse(
        {"type": "message_start", "message": message},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Le loyer est "}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "de 450 000 FCFA [1]."}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 50},
        },
        {"type": "message_stop"},
    )


class Fake:
    def __init__(self, status: int = 200, stop_reason: str = "end_turn") -> None:
        self.requests: list[httpx2.Request] = []
        self.status, self.stop_reason = status, stop_reason

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.status != 200:
            err = {"type": "error", "error": {"type": "authentication_error", "message": "clé refusée"}}
            return httpx2.Response(self.status, json=err)
        if request.url.path == "/v1/models":
            return httpx2.Response(200, json={"data": [], "has_more": False, "first_id": None, "last_id": None})
        if request.url.path.startswith("/v1/models/"):
            name = request.url.path.rsplit("/", 1)[1]
            if name != "claude-test":
                return httpx2.Response(
                    404, json={"type": "error", "error": {"type": "not_found_error", "message": "?"}}
                )
            return httpx2.Response(
                200, json={"type": "model", "id": name, "display_name": name, "created_at": "2026-01-01T00:00:00Z"}
            )
        if request.url.path == "/v1/messages":
            return httpx2.Response(200, content=answer(self.stop_reason), headers={"content-type": "text/event-stream"})
        return httpx2.Response(404)


def adapter(fake: Fake, key: str | None = KEY) -> AnthropicAdapter:
    return AnthropicAdapter(
        key, "http://faux-anthropic", http_client=DefaultHttpxClient(transport=httpx2.MockTransport(fake))
    )


MESSAGES = [ChatMessage("system", "Réponds avec des citations."), ChatMessage("user", "Quel est le loyer ?")]


def test_reponse_progressive_jetons_et_requete_conforme():
    fake = Fake()
    result = ChatResult()
    text = "".join(adapter(fake).chat(SPEC, MESSAGES, result))
    assert text == "Le loyer est de 450 000 FCFA [1]."
    assert (result.tokens_in, result.tokens_out) == (1000, 50) and not result.incomplete
    req = fake.requests[-1]
    body = json.loads(req.content)
    assert req.headers["authorization"] == f"Bearer {KEY}"  # forme envoyée par le SDK officiel
    assert AnthropicAdapter.FALLBACK_BETA in req.headers["anthropic-beta"]
    assert body["system"] == "Réponds avec des citations." and body["fallbacks"] == "default"
    assert body["messages"] == [{"role": "user", "content": "Quel est le loyer ?"}]  # consigne hors des messages
    assert "temperature" not in body and body["max_tokens"] == 300 and body["stream"] is True


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refus_ou_coupure_jamais_presentes_comme_complets(stop):
    result = ChatResult()
    list(adapter(Fake(stop_reason=stop)).chat(SPEC, MESSAGES, result))
    assert result.incomplete and result.finish_reason == stop


def test_cle_refusee_et_sante():
    with pytest.raises(ProviderError, match="HTTP 401"):
        list(adapter(Fake(status=401)).chat(SPEC, MESSAGES, ChatResult()))
    assert adapter(Fake(status=401)).health() is False
    ok = adapter(Fake())
    assert ok.health() and ok.has_model("claude-test") and not ok.has_model("claude-inconnu")


def test_sans_cle_aucun_appel_et_aucun_identifiant_de_l_environnement(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "cle-du-serveur-a-ne-jamais-utiliser")
    fake = Fake()
    a = adapter(fake, key=None)
    assert a.health() is False and a.has_model("claude-test") is False
    with pytest.raises(ProviderError, match="clé"):
        list(a.chat(SPEC, MESSAGES, ChatResult()))
    assert fake.requests == []
    configured = adapter(fake)
    list(configured.chat(SPEC, MESSAGES, ChatResult()))
    sent = fake.requests[-1].headers
    assert sent["authorization"] == f"Bearer {KEY}" and "cle-du-serveur" not in str(sent)  # clé de l'organisation
