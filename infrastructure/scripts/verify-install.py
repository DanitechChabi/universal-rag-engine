"""Essai de bout en bout d'une installation Server, par le relais HTTPS (comme un navigateur).

Connexion de l'administrateur, espace et source « fichiers locaux » sur un sous-dossier du dossier
des documents, synchronisation par le worker, recherche avec citations. Sans modèle de génération,
la recherche suffit à prouver la chaîne complète (extraction, OCR, encodage, index, droits).

    python verify-install.py --url https://rag.cabinet.local --login admin --password-file FICHIER \
        --folder essai [--insecure] [--question "…"]

Le mot de passe est lu dans un fichier (droits 600), jamais passé en argument.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--login", required=True)
    p.add_argument("--password-file", type=Path, required=True)
    p.add_argument("--folder", default="", help="sous-dossier du dossier des documents (vu en /documents)")
    p.add_argument("--question", default="Quel est le taux moyen pondéré de l'adjudication n°36/H/2026 ?")
    p.add_argument("--expect", default="3,2973")
    p.add_argument("--insecure", action="store_true", help="autorité interne non installée sur ce poste")
    p.add_argument("--timeout", type=int, default=900)
    args = p.parse_args()
    lines = args.password_file.read_text(encoding="utf-8").splitlines()
    password = next((x.split(":", 1)[1].strip() for x in lines if "mot de passe" in x), lines[0].strip())

    c = httpx.Client(base_url=f"{args.url.rstrip('/')}/api/v1", verify=not args.insecure, timeout=60, trust_env=False)
    h: dict[str, str] = {}

    def login() -> None:
        r = c.post("/auth/login", json={"login": args.login, "password": password})
        r.raise_for_status()
        # Jeton porteur plutôt que cookies : ceux-ci sont « Secure » et ne repartent pas en HTTP
        # simple (installation derrière un relais HTTPS, vérifiée en local).
        h["Authorization"] = f"Bearer {r.json()['access_token']}"

    def get(path: str, **kw) -> dict:
        """Lecture qui se reconnecte si la session a expiré (jeton d'accès de 15 min)."""
        r = c.get(path, headers=h, **kw)
        if r.status_code == 401:
            login()
            r = c.get(path, headers=h, **kw)
        r.raise_for_status()
        return r.json()

    login()
    me = get("/auth/me")
    print(f"connecté : {me.get('display_name') or args.login}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    space = c.post("/spaces", headers=h, json={"name": f"Essai d'installation {stamp}"})
    space.raise_for_status()
    space_id = space.json()["id"]
    c.put(f"/spaces/{space_id}/grants", headers=h, json=[{"principal_type": "user", "principal_id": me["user_id"]}])
    root = f"/documents/{args.folder}".rstrip("/")
    source = c.post(
        "/sources",
        headers=h,
        json={
            "kind": "local_files",
            "name": f"Essai {stamp}",
            "space_id": space_id,
            "config": {"roots": [root]},
            "inherit_space_access": True,
        },
    )
    source.raise_for_status()
    source_id = source.json()["id"]
    c.post(f"/sources/{source_id}/sync", headers=h, json={"mode": "full"}).raise_for_status()
    print(f"source créée sur {root}, synchronisation demandée")

    start = time.monotonic()
    while time.monotonic() - start < args.timeout:
        time.sleep(5)
        detail = get(f"/sources/{source_id}")
        busy = [j for j in get("/admin/jobs")["items"] if j["status"] in ("queued", "running")]
        if detail.get("last_sync_at") and not busy:
            break
    docs = get("/documents", params={"source_id": source_id})
    statuses: dict[str, int] = {}
    for d in docs.get("items", []):
        statuses[d.get("status", "?")] = statuses.get(d.get("status", "?"), 0) + 1
    print(f"indexation terminée en {time.monotonic() - start:.0f} s : {statuses}")

    login()
    res = c.post("/search", headers=h, json={"query": args.question})
    res.raise_for_status()
    items = res.json()["items"]
    found = any(args.expect in x["excerpt"] for x in items[:6])
    print(f"recherche : {len(items)} passages, réponse attendue {'trouvée' if found else 'ABSENTE'}")
    if items:
        top = items[0]
        print(f"  1er passage : {top['title']} ({top['pages']})")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
