"""Construction du contexte numéroté et validation des citations (section 8.3, docs/SECURITY.md §6).

Les extraits sont des **données** : ils sont encadrés, et tout délimiteur présent
dans le texte d'un document est neutralisé. Seules les références ``[n]`` qui
correspondent à un extrait réellement fourni sont conservées ; titres, pages et
versions viennent de la base, jamais du texte généré.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..retrieval import Passage

OPEN, CLOSE = "<<<EXTRAIT", "EXTRAIT>>>"
_CITE = re.compile(r"\[(\d{1,3}(?:\s*[,;]\s*\d{1,3})*)\]")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\((?:https?|ftp|data|javascript):[^)]*\)", re.IGNORECASE)
_HTML = re.compile(r"<\s*/?\s*(?:img|a|script|iframe|style|svg|object|embed)[^>]*>", re.IGNORECASE)
_RAW_URL = re.compile(r"\b(?:https?|ftp)://\S+", re.IGNORECASE)

INSUFFICIENT = "Les documents disponibles ne permettent pas de répondre avec suffisamment de certitude."


def neutralize(text: str) -> str:
    """Empêche un document de fermer son bloc ou d'imiter un autre extrait."""
    text = text.replace("<<<", "‹‹‹").replace(">>>", "›››")
    return re.sub(r"^\s*\[(\d+)\]", r"(\1)", text, flags=re.MULTILINE)


def pages_label(p: Passage) -> str:
    if p.page_start is None:
        return ""
    return f"page {p.page_start}" if p.page_end in (None, p.page_start) else f"pages {p.page_start}-{p.page_end}"


def build_context(passages: list[Passage]) -> str:
    parts = []
    for n, p in enumerate(passages, start=1):
        head = " — ".join(x for x in (p.title, p.source_name, pages_label(p), " > ".join(p.section_path)) if x)
        parts.append(f"[{n}] {neutralize(head)}\n{OPEN}\n{neutralize(p.text)}\n{CLOSE}")
    return "\n\n".join(parts)


@dataclass(frozen=True)
class Citation:
    rank: int
    passage: Passage


@dataclass(frozen=True)
class ValidatedAnswer:
    text: str
    citations: list[Citation]
    removed: int
    insufficient: bool


def sanitize(answer: str) -> str:
    """Rendu sûr : pas d'image, pas de lien externe, pas de HTML actif dans la réponse générée."""
    answer = _IMAGE.sub("", answer)
    answer = _LINK.sub(r"\1", answer)
    answer = _HTML.sub("", answer)
    return _RAW_URL.sub("[lien retiré]", answer)


def validate(answer: str, passages: list[Passage]) -> ValidatedAnswer:
    """Garde les citations valides, dans l'ordre de première apparition ; retire les autres."""
    used: list[int] = []
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        kept = []
        for raw in re.split(r"\s*[,;]\s*", match.group(1)):
            n = int(raw)
            if 1 <= n <= len(passages):
                kept.append(n)
                if n not in used:
                    used.append(n)
            else:
                removed += 1
        return "".join(f"[{n}]" for n in kept)

    cleaned = _CITE.sub(replace, sanitize(answer))
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned).strip()
    insufficient = "ne permettent pas de répondre" in cleaned.lower()
    return ValidatedAnswer(cleaned, [Citation(n, passages[n - 1]) for n in used], removed, insufficient)
