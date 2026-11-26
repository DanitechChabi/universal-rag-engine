"""Test de charge par le relais HTTPS (phase 7, ROADMAP : « rapport de charge »).

Des utilisateurs virtuels enchaînent des recherches ou des questions complètes (réponse diffusée)
pendant une durée fixe, à plusieurs niveaux de simultanéité. Mesures : débit, durées p50/p95/p99,
délai du premier morceau de réponse, erreurs. Les questions viennent du corpus public d'évaluation.

    python charge.py --url https://rag.local --login admin --password-file F --insecure \
        --scenario question --users 1,5,10,20 --duration 60 --out rapport.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import httpx

QUESTIONS = Path(__file__).resolve().parents[1] / "corpus" / "questions.json"


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 3)


async def login(client: httpx.AsyncClient, user: str, password: str) -> dict:
    r = await client.post("/auth/login", json={"login": user, "password": password})
    r.raise_for_status()
    return {"x-csrf-token": r.json()["csrf_token"]}


async def one_search(client, headers, question) -> dict:
    t = time.perf_counter()
    r = await client.post("/search", headers=headers, json={"query": question})
    return {"ok": r.status_code == 200, "total": time.perf_counter() - t, "status": r.status_code}


async def one_question(client, headers, question) -> dict:
    t = time.perf_counter()
    first = None
    ok, status = False, 0
    async with client.stream("POST", "/chat", headers=headers, json={"question": question}) as r:
        status = r.status_code
        event = None
        async for line in r.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                now = time.perf_counter() - t
                if event == "token" and first is None:
                    first = now
                elif event == "done":
                    ok = not json.loads(line[6:]).get("error")
                elif event == "error":
                    ok = False
    return {"ok": ok and status == 200, "total": time.perf_counter() - t, "first": first, "status": status}


async def level(args, password: str, users: int, questions: list[str]) -> dict:
    results: list[dict] = []
    stop = time.monotonic() + args.duration
    limits = httpx.Limits(max_connections=users + 5)

    async def virtual_user(n: int):
        async with httpx.AsyncClient(
            base_url=f"{args.url.rstrip('/')}/api/v1",
            verify=not args.insecure,
            timeout=300,
            trust_env=False,
            limits=limits,
        ) as client:
            headers = await login(client, args.login, password)
            rnd = random.Random(n)  # noqa: S311 - choix reproductible des questions, sans usage de sécurité
            while time.monotonic() < stop:
                q = rnd.choice(questions)
                try:
                    res = await (one_search if args.scenario == "recherche" else one_question)(client, headers, q)
                except httpx.HTTPError as e:
                    res = {"ok": False, "total": 0.0, "status": type(e).__name__}
                results.append(res)

    started = time.monotonic()
    await asyncio.gather(*(virtual_user(i) for i in range(users)))
    elapsed = time.monotonic() - started
    good = [r for r in results if r["ok"]]
    totals = [r["total"] for r in good]
    out = {
        "utilisateurs": users,
        "requetes": len(results),
        "erreurs": len(results) - len(good),
        "debit_par_minute": round(len(good) / elapsed * 60, 1),
        "duree_p50_s": pct(totals, 0.5),
        "duree_p95_s": pct(totals, 0.95),
        "duree_p99_s": pct(totals, 0.99),
        "duree_moyenne_s": round(statistics.mean(totals), 3) if totals else None,
    }
    if args.scenario == "question":
        firsts = [r["first"] for r in good if r.get("first") is not None]
        out |= {
            "premier_morceau_p50_s": pct(firsts, 0.5),
            "premier_morceau_p95_s": pct(firsts, 0.95),
        }
    errors = sorted({str(r["status"]) for r in results if not r["ok"]})
    if errors:
        out["erreurs_types"] = errors
    return out


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--login", required=True)
    p.add_argument("--password-file", type=Path, required=True)
    p.add_argument("--scenario", choices=["recherche", "question"], default="recherche")
    p.add_argument("--users", default="1,5,10,20")
    p.add_argument("--duration", type=int, default=60)
    p.add_argument("--insecure", action="store_true")
    p.add_argument("--out", type=Path)
    p.add_argument("--note", default="")
    args = p.parse_args()
    lines = args.password_file.read_text(encoding="utf-8").splitlines()
    password = next((x.split(":", 1)[1].strip() for x in lines if "mot de passe" in x), lines[0].strip())
    questions = [
        q["question"]
        for q in json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
        if q["categorie"] != "sans_reponse"
    ]
    report = {"scenario": args.scenario, "duree_par_niveau_s": args.duration, "note": args.note, "niveaux": []}
    for users in (int(x) for x in args.users.split(",")):
        res = await level(args, password, users, questions)
        print(json.dumps(res, ensure_ascii=False), flush=True)
        report["niveaux"].append(res)
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
