"""Télécharge le corpus public de mesure et vérifie les empreintes.

    python eval/download_corpus.py --dest ~/urag-corpus/files

- La liste des documents est dans eval/corpus/sources.json.
- Les empreintes SHA-256 sont enregistrées dans eval/corpus/manifest.lock.json au premier
  téléchargement ; ensuite, tout fichier différent est signalé (le document a changé en ligne).
- Les fichiers ne sont jamais versionnés dans Git. Seuls les PDF sont acceptés.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "corpus" / "sources.json"
LOCK = HERE / "corpus" / "manifest.lock.json"
USER_AGENT = "Mozilla/5.0 (compatible; urag-corpus/1.0)"
MAX_BYTES = 40 * 1024 * 1024


def fetch(url: str, attempts: int = 3) -> bytes:
    last: Exception | None = None
    for i in range(attempts):
        try:
            if not url.startswith("https://"):
                raise ValueError("seules les adresses https sont acceptées")
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - https vérifié
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
                data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("fichier trop volumineux")
            return data
        except Exception as e:  # noqa: BLE001 - nouvelle tentative
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url} : {last}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dest", required=True, type=Path)
    p.add_argument("--update-lock", action="store_true", help="accepter les nouvelles empreintes")
    args = p.parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]
    lock = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}
    changed, failed = [], []
    for doc in sources:
        target = args.dest / f"{doc['id']}.pdf"
        known_hash = lock.get(doc["id"], {}).get("sha256")
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == known_hash:
            continue
        try:
            data = fetch(doc["url"])
        except RuntimeError as e:
            failed.append(str(e))
            continue
        if not data.startswith(b"%PDF"):
            failed.append(f"{doc['id']} : pas un PDF")
            continue
        digest = hashlib.sha256(data).hexdigest()
        known = lock.get(doc["id"])
        if known and known["sha256"] != digest and not args.update_lock:
            changed.append(doc["id"])
        target.write_bytes(data)
        if not known or args.update_lock:
            lock[doc["id"]] = {"sha256": digest, "bytes": len(data)}
        time.sleep(0.5)  # politesse envers les serveurs
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(sources) - len(failed)} documents présents dans {args.dest}")
    for f in failed:
        print("ÉCHEC", f)
    for c in changed:
        print("MODIFIÉ EN LIGNE (empreinte différente)", c)
    return 1 if failed or changed else 0


if __name__ == "__main__":
    sys.exit(main())
