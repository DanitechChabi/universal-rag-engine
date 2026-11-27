"""Contrôle des licences des dépendances livrées (cahier des charges, livrable 29 ; CLAUDE.md).

Dépendances **livrées** seulement : paquets Python de production de l'API et du worker (d'après
uv.lock, sans les outils de développement) et paquets JavaScript intégrés à l'interface
construite (`pnpm licenses list --prod`). Les licences sont lues dans les métadonnées des
paquets installés.

- permissives (MIT, BSD, Apache…) : acceptées ;
- copyleft faible (LGPL, MPL) : acceptées, listées à part (bibliothèques non modifiées,
  remplaçables ; obligations dans docs/LICENCES.md) ;
- AGPL, SSPL, GPL, BUSL, RSAL, Commons Clause, non commerciales : **refusées** ;
- licence inconnue : refusée, sauf exception justifiée dans ``EXCEPTIONS``.

    uv run python tools/verifier_licences.py [--markdown docs/reports/licences-dependances.md]

Code de sortie 1 si une dépendance est refusée.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("urag-api", "urag-worker")
OWN = {"urag-api", "urag-worker", "urag-core", "urag-connectors-base", "urag-connector-local-files"}

FORBIDDEN = re.compile(
    r"(?<![L])\bA?GPL|GNU (Affero )?General Public|SSPL|Server Side Public|BUSL|Business Source"
    r"|RSAL|Redis Source Available|Commons Clause|Elastic License|\bNC\b|NonCommercial|Non-Commercial",
    re.IGNORECASE,
)
WEAK = re.compile(r"LGPL|Lesser General Public|MPL|Mozilla Public", re.IGNORECASE)
PERMISSIVE = re.compile(
    r"MIT|BSD|Apache|ISC|PSF|Python Software Foundation|Zlib|0BSD|CC0|Unlicense|HPND|Public Domain",
    re.IGNORECASE,
)
# Métadonnées incomplètes : licence vérifiée à la main dans le dépôt du projet.
EXCEPTIONS: dict[str, str] = {}


def classify(text: str) -> str:
    # « GPL » d'une exception de liaison (ex. « GPL-2.0 WITH Classpath-exception ») non prévu ici :
    # tout GPL est refusé, à examiner au cas par cas.
    if FORBIDDEN.search(text.replace("LGPL", "").replace("Lesser General Public", "")):
        return "refusée"
    if WEAK.search(text):
        return "copyleft faible"
    if PERMISSIVE.search(text):
        return "permissive"
    return "inconnue"


def python_rows() -> list[dict]:
    args = [
        "uv",
        "export",
        "--frozen",
        "--no-dev",
        "--no-hashes",
        "--no-emit-workspace",
        "--format",
        "requirements-txt",
    ]
    for p in PACKAGES:
        args += ["--package", p]
    # Commandes fixes (uv, pnpm), sans entrée extérieure.
    out = subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout  # noqa: S603
    from packaging.markers import Marker

    rows = []
    for line in sorted(x for x in out.splitlines() if x and x[0].isalnum()):
        spec, _, marker = line.partition(";")
        name, version = re.split(r"[=<>\[ ]", spec, maxsplit=1)[0], spec.split("==")[-1].strip()
        if name in OWN:
            continue
        if marker.strip() and not Marker(marker.strip()).evaluate():
            # Autre système (Windows pour le mode Desktop) : contrôlé quand ce mode sera construit.
            rows.append(
                {
                    "ecosysteme": "Python",
                    "nom": name,
                    "version": version,
                    "licence": f"({marker.strip()})",
                    "classe": "autre plateforme",
                }
            )
            continue
        try:
            meta = md.metadata(name)
        except md.PackageNotFoundError:
            rows.append(
                {"ecosysteme": "Python", "nom": name, "version": "?", "licence": "non installé", "classe": "inconnue"}
            )
            continue
        classifiers = [
            c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")
        ]
        raw = (meta.get("License") or "").strip().splitlines()
        lic = meta.get("License-Expression") or ", ".join(classifiers) or (raw[0][:100] if raw else "")
        rows.append({"ecosysteme": "Python", "nom": meta["Name"], "version": meta["Version"], "licence": lic})
    return rows


def web_rows() -> list[dict]:
    out = subprocess.run(  # noqa: S603
        ["pnpm", "licenses", "list", "--prod", "--json"],  # noqa: S607
        cwd=ROOT / "apps" / "web",
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows = []
    for lic, packages in json.loads(out).items():
        for p in packages:
            for v in p["versions"]:
                rows.append({"ecosysteme": "JavaScript", "nom": p["name"], "version": v, "licence": lic})
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--markdown", type=Path, help="écrire l'inventaire en Markdown")
    p.add_argument("--sans-web", action="store_true", help="ne pas contrôler l'interface (pnpm absent)")
    args = p.parse_args()
    rows = python_rows() + ([] if args.sans_web else web_rows())
    for r in rows:
        r.setdefault("classe", classify(r["licence"]))
        if r["classe"] == "inconnue" and r["nom"] in EXCEPTIONS:
            r["classe"], r["licence"] = "permissive", EXCEPTIONS[r["nom"]]
    bad = [r for r in rows if r["classe"] in ("refusée", "inconnue")]
    weak = [r for r in rows if r["classe"] == "copyleft faible"]
    if args.markdown:
        lines = [
            "# Inventaire des licences des dépendances livrées",
            "",
            "Généré par `tools/verifier_licences.py` (ne pas modifier à la main). Explications et",
            "obligations : `docs/LICENCES.md`.",
            "",
            f"{len(rows)} dépendances ; {len(weak)} sous copyleft faible ; {len(bad)} refusées ou inconnues.",
            "",
            "| Écosystème | Paquet | Version | Licence | Classe |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {r['ecosysteme']} | {r['nom']} | {r['version']} | {r['licence'].replace('|', '/')} | {r['classe']} |"
            for r in sorted(rows, key=lambda r: (r["ecosysteme"], r["nom"].lower()))
        ]
        args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"{len(rows)} dépendances livrées contrôlées ; "
        f"copyleft faible : {', '.join(r['nom'] for r in weak) or 'aucune'}"
    )
    for r in bad:
        print(
            f"REFUSÉE : {r['ecosysteme']} {r['nom']} {r['version']} — "
            f"{r['licence'] or 'licence absente'} ({r['classe']})"
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
