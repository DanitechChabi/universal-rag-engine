"""Faux modèle de génération « compatible OpenAI » pour les tests de charge (phase 7).

Il simule un GPU : délai avant le premier jeton, puis débit constant. On mesure ainsi le
**surcoût du moteur** (recherche, reclassement, contexte, validation des citations, base, flux)
indépendamment du matériel de génération, mesuré à part (docs/reports/COMPARAISON-MODELES-LOCAUX.md).

    python faux_modele.py --port 8080 --first-token 0.4 --tokens-per-s 40 --tokens 120
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

ANSWER = (
    "D'après les extraits fournis, la réponse figure dans le document cité [1]. "
    "Les montants et les dates sont repris tels qu'ils apparaissent dans la source [1]."
)


def build(first_token: float, tokens_per_s: float, tokens: int) -> FastAPI:
    app = FastAPI()
    state = {"active": 0, "peak": 0, "calls": 0}

    @app.get("/v1/models")
    def models():
        return {"data": [{"id": "faux-gpu"}]}

    @app.get("/stats")
    def stats():
        return state

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        words = ANSWER.split(" ")

        async def stream():
            state["active"] += 1
            state["calls"] += 1
            state["peak"] = max(state["peak"], state["active"])
            try:
                await asyncio.sleep(first_token)
                start = time.monotonic()
                for i in range(tokens):
                    piece = words[i % len(words)] + " "
                    delta = {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                    yield f"data: {json.dumps(delta)}\n\n"
                    await asyncio.sleep(max(0.0, start + (i + 1) / tokens_per_s - time.monotonic()))
                done = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {json.dumps(done)}\n\n"
                prompt = sum(len(m.get("content", "")) for m in body.get("messages", [])) // 4
                usage = {"choices": [], "usage": {"prompt_tokens": prompt, "completion_tokens": tokens}}
                yield f"data: {json.dumps(usage)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                state["active"] -= 1

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 - conteneur de test sur le réseau interne
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--first-token", type=float, default=0.4)
    p.add_argument("--tokens-per-s", type=float, default=40.0)
    p.add_argument("--tokens", type=int, default=120)
    a = p.parse_args()
    uvicorn.run(build(a.first_token, a.tokens_per_s, a.tokens), host=a.host, port=a.port, log_level="warning")
