"""Note les réponses de modèles produites ailleurs (ex. GPU Kaggle) avec la grille de run_eval.py.

Entrées :
- ``--prompts`` : export de ``run_eval.py --chat-provider export`` (messages et extraits par question) ;
- ``--answers`` : liste ``[{id, model, answer, seconds?, tokens_in?, tokens_out?, error?}]``.

Chaque réponse passe par la **même validation des citations** que le moteur (``citations.validate``),
puis par les mêmes critères : réponse exacte, citation d'un document attendu, abstention correcte.
Un rapport par modèle est écrit dans ``docs/reports/eval-<label>-<modèle>.json``.

    uv run python eval/score_answers.py --prompts prompts.json --answers answers.json --label phase5-kaggle
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL))

from run_eval import contains  # noqa: E402 - même normalisation que la mesure principale


def passages_from(export: dict):
    from urag_core.retrieval import Passage

    return [
        Passage(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            p["title"],
            uuid.uuid4(),
            p["source_name"],
            p["text"],
            p["page_start"],
            p["page_end"],
            tuple(p["section_path"]),
            None,
            0.0,
            (),
            None,
            p["context"],
        )
        for p in export["passages"]
    ]


def score(prompts: list[dict], answers: list[dict], questions: dict[str, dict], label: str) -> dict[str, dict]:
    from urag_core.citations import validate

    by_id = {p["id"]: p for p in prompts}
    reports: dict[str, dict] = {}
    for model in sorted({a["model"] for a in answers}):
        rows = []
        for a in (x for x in answers if x["model"] == model):
            q, export = questions[a["id"]], by_id[a["id"]]
            passages = passages_from(export)
            if a.get("error"):
                text, cited, insufficient = json.dumps({"error": a["error"]}), set(), False
            else:
                v = validate(a["answer"], passages)
                text, insufficient = v.text, v.insufficient
                cited = {c.passage.title for c in v.citations}
            if q["categorie"] == "sans_reponse":
                correct = insufficient
                pertinent = correct and not cited
            else:
                correct = contains(text, q["doit_contenir"])
                pertinent = correct and bool(set(q["documents_attendus"]) & cited)
            rows.append(
                {
                    "id": q["id"],
                    "categorie": q["categorie"],
                    "question": q["question"],
                    "attendu": q["reponse_attendue"],
                    "reponse": text,
                    "reponse_exacte": correct,
                    "exacte_et_citation_pertinente": pertinent,
                    "abstention": insufficient,
                    "citations": sorted(cited),
                    "lien_externe": "http" in text,
                    "repris_le_document_piege": "5 milliards" in text,
                    "duree_s": a.get("seconds"),
                    "tokens_out": a.get("tokens_out"),
                }
            )

        def rate(items, key):
            return round(sum(bool(r[key]) for r in items) / len(items), 3) if items else None

        cats: dict[str, list] = defaultdict(list)
        for r in rows:
            cats[r["categorie"]].append(r)
        durations = [r["duree_s"] for r in rows if r["duree_s"]]
        reports[model] = {
            "label": f"{label}-{model}",
            "date": date.today().isoformat(),
            "modele_generation": model,
            "fournisseur": "ollama (GPU Kaggle)",
            "politique": "local (modèle ouvert, corpus public)",
            "extraits": "identiques pour tous les modèles (export de la phase 4, reclassement activé)",
            "global": {
                "questions": len(rows),
                "reponse_exacte": rate(rows, "reponse_exacte"),
                "exacte_et_citation_pertinente": rate(rows, "exacte_et_citation_pertinente"),
                "liens_externes": sum(r["lien_externe"] for r in rows),
                "document_piege_repris": sum(r["repris_le_document_piege"] for r in rows),
                "duree_moyenne_question_s": round(sum(durations) / len(durations), 1) if durations else None,
            },
            "par_categorie": {
                c: {
                    "questions": len(items),
                    "reponse_exacte": rate(items, "reponse_exacte"),
                    "exacte_et_citation_pertinente": rate(items, "exacte_et_citation_pertinente"),
                }
                for c, items in sorted(cats.items())
            },
            "details": rows,
        }
    return reports


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prompts", type=Path, required=True)
    p.add_argument("--answers", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--out", type=Path, default=EVAL.parent / "docs" / "reports")
    args = p.parse_args()
    questions = {
        q["id"]: q for q in json.loads((EVAL / "corpus" / "questions.json").read_text(encoding="utf-8"))["questions"]
    }
    reports = score(
        json.loads(args.prompts.read_text(encoding="utf-8")),
        json.loads(args.answers.read_text(encoding="utf-8")),
        questions,
        args.label,
    )
    for model, report in reports.items():
        name = re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")
        (args.out / f"eval-{args.label}-{name}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        g = report["global"]
        print(
            f"{model:<20} exact {g['reponse_exacte']:.1%}  exact et cité {g['exacte_et_citation_pertinente']:.1%}  "
            f"{g['duree_moyenne_question_s']} s/question"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
