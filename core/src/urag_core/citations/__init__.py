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
        head = " — ".join(
            x for x in (p.title, p.context, p.source_name, pages_label(p), " > ".join(p.section_path)) if x
        )
        parts.append(f"[{n}] {neutralize(head)}\n{OPEN}\n{neutralize(p.text)}\n{CLOSE}")
    return "\n\n".join(parts)


@dataclass(frozen=True)
class Citation:
    rank: int
    passage: Passage
    inferred: bool = False  # ajoutée par l'attribution automatique, pas par le modèle


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


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀÂÉÈÊÎÔÛÇ0-9«\"])")
_NUMERIC = re.compile(r"\b[\w/.-]*\d[\w/.-]*\b")
_WORD = re.compile(r"[a-zàâäéèêëîïôöùûüç]{6,}")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("\u202f", " ").replace("\u00a0", " "))


def attribute(answer: str, passages: list[Passage]) -> tuple[str, list[int]]:
    """Attribution vérifiable quand le modèle n'a rien cité.

    Une phrase est rattachée à un extrait seulement si **tous** ses chiffres et références
    (montants, dates, numéros) figurent à l'identique dans l'extrait, et si au moins la
    moitié de ses mots significatifs s'y trouvent. Sinon, la phrase reste sans citation.
    """
    texts = [_norm(p.text) for p in passages]
    tokens = [_number_tokens(t) for t in texts]
    out, used = [], []
    for sentence in _SENTENCE.split(answer):
        low = _norm(sentence)
        numbers = _numbers(sentence)
        words = set(_WORD.findall(low))
        best, best_score = None, 0.0
        for i, t in enumerate(texts):
            if not numbers or not set(numbers) <= tokens[i]:
                continue
            score = len([w for w in words if w in t]) / max(1, len(words))
            if score >= 0.5 and score > best_score:
                best, best_score = i + 1, score
        if best is not None:
            sentence = re.sub(r"([.!?]?)\s*$", lambda m, b=best: f" [{b}]{m.group(1)}", sentence, count=1)
            if best not in used:
                used.append(best)
        out.append(sentence)
    return " ".join(out), used


def _number_tokens(text: str) -> set[str]:
    """Chiffres et références comparés en entier : « 45 » ne correspond pas à « 450 »."""
    return {n.strip(".-/") for n in _NUMERIC.findall(text)}


def _numbers(sentence: str) -> list[str]:
    return [n for n in _number_tokens(_norm(_CITE.sub("", sentence))) if len(n) >= 2]


def verify_support(answer: str, passages: list[Passage]) -> tuple[str, int, set[int]]:
    """Vérifie qu'un extrait cité contient bien les chiffres et références de la phrase.

    Sinon la citation est remplacée par l'extrait qui les contient (citation déduite),
    ou retirée si aucun extrait ne les contient. Renvoie (texte, citations corrigées, rangs déduits).
    """
    tokens = [_number_tokens(_norm(p.text)) for p in passages]
    fixed, inferred, out = 0, set(), []
    for sentence in _SENTENCE.split(answer):
        cited = [int(n) for group in _CITE.findall(sentence) for n in re.split(r"\s*[,;]\s*", group)]
        numbers = _numbers(sentence)
        if cited and numbers and not any(set(numbers) <= tokens[n - 1] for n in cited):
            fixed += 1
            bare = _CITE.sub("", sentence)
            replacement, used = attribute(bare, passages)
            out.append(replacement)
            inferred.update(used)
            continue
        out.append(sentence)
    return " ".join(out), fixed, inferred


def validate(answer: str, passages: list[Passage]) -> ValidatedAnswer:
    """Garde les citations valides et justifiées, dans l'ordre de première apparition ; retire les autres."""
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
    cleaned, fixed, corrected = verify_support(cleaned, passages)
    removed += fixed
    used = [
        n
        for n in dict.fromkeys(int(x) for g in _CITE.findall(cleaned) for x in re.split(r"\s*[,;]\s*", g))
        if n not in corrected
    ]
    inferred: list[int] = sorted(corrected - set(used))
    insufficient = "ne permettent pas de répondre" in cleaned.lower()
    if not used and not inferred and not insufficient:
        cleaned, inferred = attribute(cleaned, passages)
    citations = [Citation(n, passages[n - 1]) for n in used] + [Citation(n, passages[n - 1], True) for n in inferred]
    return ValidatedAnswer(cleaned, citations, removed, insufficient)
