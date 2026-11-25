# ruff: noqa: S310, S602, S603, S607 - notebook Kaggle isolé : commandes fixes, seule adresse appelée = Ollama local
"""Notebook Kaggle (GPU) : fait répondre des modèles locaux candidats aux questions exportées.

Entrée : le fichier ``prompts*.json`` produit par ``run_eval.py --chat-provider export`` (jeu de
données Kaggle privé). Sortie : ``/kaggle/working/answers.json``, noté ensuite par
``eval/score_answers.py``. Corpus public uniquement : aucun document d'un client ne passe par Kaggle.

Les modèles sont servis par Ollama, comme dans le produit (adaptateur ``ollama``), avec les mêmes
réglages que la mesure locale : température 0, contexte 8 192 jetons, 400 jetons de réponse au plus.
"""

import glob
import json
import os
import subprocess
import time
import urllib.request

MODELS = os.environ.get("URAG_MODELS", "qwen2.5:7b,qwen2.5:14b,qwen3:8b,llama3.1:8b,gemma3:12b,mistral-nemo:12b").split(
    ","
)
OLLAMA = "http://127.0.0.1:11434"
OUT = "/kaggle/working/answers.json"


def call(path, body=None, timeout=900):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{OLLAMA}{path}", data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def save(answers):
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False)


def main():
    subprocess.run("nvidia-smi --query-gpu=name,memory.total --format=csv", shell=True, check=False)
    subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            print("ollama", call("/api/version")["version"], flush=True)
            break
        except OSError:
            time.sleep(2)
    path = sorted(glob.glob("/kaggle/input/**/prompts*.json", recursive=True))[0]
    with open(path, encoding="utf-8") as f:
        prompts = json.load(f)
    answers = []
    for model in MODELS:
        started = time.time()
        pulled = subprocess.run(["ollama", "pull", model], capture_output=True, text=True)
        if pulled.returncode != 0:
            print(f"{model} : téléchargement impossible ({pulled.stderr[-200:]})", flush=True)
            continue
        print(f"{model} : téléchargé en {time.time() - started:.0f} s", flush=True)
        for p in prompts:
            body = {
                "model": model,
                "messages": p["messages"],
                "stream": False,
                "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 400},
            }
            if model.startswith("qwen3"):
                body["think"] = False  # réponse directe, sans raisonnement affiché
            t0 = time.time()
            try:
                r = call("/api/chat", body)
                answers.append(
                    {
                        "id": p["id"],
                        "model": model,
                        "answer": r["message"]["content"],
                        "seconds": round(time.time() - t0, 2),
                        "tokens_in": r.get("prompt_eval_count"),
                        "tokens_out": r.get("eval_count"),
                    }
                )
            except Exception as e:  # noqa: BLE001 - une question en échec n'arrête pas la mesure
                answers.append({"id": p["id"], "model": model, "answer": "", "error": f"{type(e).__name__}: {e}"})
        done = [a for a in answers if a["model"] == model and not a.get("error")]
        mean = sum(a["seconds"] for a in done) / max(len(done), 1)
        print(f"{model} : {len(done)}/{len(prompts)} réponses, {mean:.1f} s par question", flush=True)
        save(answers)
        subprocess.run(["ollama", "rm", model], capture_output=True)  # libère le disque
    save(answers)
    print("terminé :", len(answers), "réponses", flush=True)


main()
