"""Détection des consignes adressées à une IA dans le contenu des documents (docs/SECURITY.md §6).

Un document est une donnée, jamais une instruction. Les passages qui contiennent des consignes
visant un assistant (« ignore les instructions précédentes », faux délimiteurs, liens d'images
externes…) sont marqués à l'indexation et écartés du contexte envoyé au modèle. Ils restent
visibles dans la recherche, signalés, pour que l'administrateur puisse les examiner.

Détection par règles : simple, explicable, sans dépendance. Elle ne prétend pas tout attraper ;
c'est une couche de plus, après le cloisonnement du contexte et la validation des citations.
"""

from __future__ import annotations

import re
import unicodedata

_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "consigne d'ignorer les instructions",
        re.compile(
            r"\b(ignore[rz]?|oublie[rz]?|ne tiens? pas compte)\b.{0,40}\b(instructions?|consignes?|regles?)\b"
            r"|\bignore\b.{0,20}\b(previous|prior|above|all)\b.{0,20}\binstructions?\b|\bdisregard\b.{0,30}\binstructions?\b"
        ),
    ),
    (
        "consigne adressée au système",
        re.compile(
            r"\b(instructions?|consignes?|message)\s+(au|pour l[ea']?|a l')\s*(systeme|assistant|ia|modele|chatbot)\b"
            r"|\bsystem\s+prompt\b|\bnote\s+to\s+(the\s+)?(ai|assistant|model)\b|\b(tu es|you are)\s+(maintenant|now)\b"
        ),
    ),
    (
        "réponse imposée",
        re.compile(
            r"\b(quand|si|lorsqu)\s*(on|l'on)?\s*te\s+demande\b|\bwhen\s+(you\s+are\s+)?asked\b.{0,40}\b(answer|reply|say)\b"
            r"|\breponds?\s+(uniquement\s+)?que\b"
        ),
    ),
    ("faux délimiteur", re.compile(r"<<<\s*extrait|extrait\s*>>>|\[/?inst\]|<\|im_(start|end)\|>|</?s>", re.I)),
    ("image ou lien externe", re.compile(r"!\[[^\]]*\]\(\s*(https?|data):", re.I)),
]


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("’", "'")


def suspicious_reason(text: str) -> str | None:
    """Raisons détectées (séparées par « ; »), ou None si le passage paraît sain."""
    folded = _fold(text)
    reasons = [name for name, rule in _RULES if rule.search(folded) or rule.search(text)]
    return "; ".join(reasons) if reasons else None
