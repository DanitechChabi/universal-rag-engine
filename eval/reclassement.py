"""Qualité et durée du reclassement selon son réglage (phase 7, suite des tests de charge).

Mesure, sur l'index réel d'un serveur et pour chaque question du corpus d'évaluation, si la
réponse attendue figure dans les passages réellement transmis au modèle (les 6 premiers,
passages suspects écartés), avec ou sans reclassement et pour plusieurs réglages. Le modèle de
génération n'intervient pas : on mesure la recherche seule, cause des écarts de capacité.

À lancer dans le conteneur de l'API (mêmes réglages, mêmes droits que le service) :

    docker compose cp eval/reclassement.py api:/tmp/ && docker compose cp eval/corpus/questions.json api:/tmp/
    docker compose exec -T api python /tmp/reclassement.py --questions /tmp/questions.json \
        --org-id ORG --user-id UTILISATEUR > rapport.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import uuid

from urag_api.state import AppState
from urag_core.config import Settings
from urag_core.permissions import AccessScope
from urag_core.rerank import OnnxReranker
from urag_core.retrieval import Retriever

CONTEXT_PASSAGES = 6  # passages transmis au modèle (réglage context_passages)


def norm(s: str) -> str:  # même normalisation que eval/run_eval.py
    s = s.lower().replace(" ", " ").replace(" ", " ").replace("’", "'")
    s = re.sub(r"\s*[-–—]\s*", "-", s)
    s = re.sub(r"\s*\(\d+\)", "", s)
    return re.sub(r"\s+", " ", s)


def contains(answer: str, groups: list[list[str]]) -> bool:
    a = norm(answer)
    return all(any(norm(v) in a for v in group) for group in groups)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--questions", required=True)
    p.add_argument("--org-id", required=True, type=uuid.UUID)
    p.add_argument("--user-id", required=True, type=uuid.UUID, help="utilisateur dont les droits s'appliquent")
    p.add_argument("--threads", type=int, default=0, help="fils ONNX (0 : tous les cœurs)")
    args = p.parse_args()

    settings = Settings()
    state = AppState.from_settings(settings)
    with open(args.questions, encoding="utf-8") as f:
        questions = [q for q in json.load(f)["questions"] if q["categorie"] != "sans_reponse"]
    org_id, user_id = args.org_id, args.user_id
    base = state.retriever  # collection et encodeur du service
    threads = args.threads or None
    variants = {
        "sans reclassement": None,
        "20 passages, 512 jetons (actuel)": (20, 512),
        "10 passages, 512 jetons": (10, 512),
        "20 passages, 256 jetons": (20, 256),
        "10 passages, 256 jetons": (10, 256),
    }
    rerankers = {}
    report = {"questions": len(questions), "passages_transmis": CONTEXT_PASSAGES, "variantes": []}
    for name, cfg in variants.items():
        reranker = None
        if cfg:
            n, tokens = cfg
            reranker = rerankers.get(tokens) or OnnxReranker(
                settings.rerank_model_dir, max_tokens=tokens, threads=threads
            )
            rerankers[tokens] = reranker
        retriever = Retriever(
            base.vectors, base.encoder, base.collection, settings.late_access_check, reranker, cfg[0] if cfg else 20
        )
        rows, durations = [], []
        for q in questions:
            with state.db.org(org_id) as conn:
                scope = AccessScope.for_user(conn, org_id, user_id)
                t = time.perf_counter()
                found = retriever.search(
                    conn, scope, q["question"], limit=CONTEXT_PASSAGES * 2, candidates=settings.retrieval_candidates
                )
                durations.append(time.perf_counter() - t)
            passages = [x for x in found if not x.suspicious][:CONTEXT_PASSAGES]
            texts = [f"{x.context or ''} {x.text}" for x in found if not x.suspicious]
            joined = " ".join(texts[:CONTEXT_PASSAGES])
            # Rang du premier passage contenant à lui seul la réponse (None : réponse répartie ou absente).
            rank = next((i + 1 for i, t in enumerate(texts) if contains(t, q["doit_contenir"])), None)
            rows.append(
                {
                    "id": q["id"],
                    "categorie": q["categorie"],
                    "reponse_dans_les_passages": contains(joined, q["doit_contenir"]),
                    "rang": rank,
                    "document_attendu_transmis": bool(set(q["documents_attendus"]) & {x.title for x in passages}),
                }
            )
        ok = sum(r["reponse_dans_les_passages"] for r in rows)
        doc = sum(r["document_attendu_transmis"] for r in rows)
        out = {
            "variante": name,
            "reponse_dans_les_passages": ok,
            "taux": round(100 * ok / len(rows), 1),
            "document_attendu_transmis": doc,
            "rang_reciproque_moyen": round(statistics.mean(1 / r["rang"] if r["rang"] else 0 for r in rows), 3),
            "reponse_en_tete": sum(r["rang"] == 1 for r in rows),
            "duree_recherche_mediane_s": round(statistics.median(durations), 2),
            "duree_recherche_p95_s": round(sorted(durations)[int(0.95 * len(durations)) - 1], 2),
            "questions": rows,
        }
        print(
            f"{name:<34} réponse transmise {ok}/{len(rows)} ({out['taux']} %), document {doc}/{len(rows)}, "
            f"en tête {out['reponse_en_tete']}, rang réciproque {out['rang_reciproque_moyen']}, "
            f"médiane {out['duree_recherche_mediane_s']} s",
            file=sys.stderr,
            flush=True,
        )
        report["variantes"].append(out)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
