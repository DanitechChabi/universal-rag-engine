"""Découpage en fragments (section 6.4).

- les titres ouvrent une section ; leur chemin est conservé avec chaque fragment ;
- les paragraphes sont regroupés jusqu'à ``max_chars`` ;
- un tableau n'est jamais mélangé à du texte ; un très grand tableau est découpé
  par lignes en répétant la ligne d'en-tête ;
- un fragment ne chevauche jamais deux pages : la citation désigne une page précise ;
- un chevauchement (fin du fragment précédent) relie deux fragments d'une même section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..extraction import Block, ExtractedDocument


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    text: str
    kind: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None

    def embedding_text(self, title: str, context: str | None = None) -> str:
        """Texte encodé : titre et contexte du document (ADR-0021), section, puis le passage."""
        head = " > ".join((f"{title} — {context}" if context else title, *self.section_path))
        return f"{head}\n{self.text}"


_NAV_HEADING = re.compile(
    r"^\s*(s\s?o\s?m\s?m\s?a\s?i\s?r\s?e|table des mati[eè]res|table of contents|contents|index|"
    r"liste des (tableaux|graphiques|figures|encadr[ée]s|annexes))\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_LEADERS = re.compile(r"(\.\s?){4,}\s*(\d{1,4}|[ivxlcIVXLC]{1,6})\s*$|…{2,}\s*\d{1,4}\s*$")  # points de conduite → page
# Même sans retours à la ligne (texte recollé par l'extraction ou l'OCR) : pointillés puis numéro de page.
_LEADER_ANY = re.compile(
    r"(?:\.\s?){4,}\s*(?:\d{1,4}|[ivxlcIVXLC]{1,6})\b(?!\.\d|\s?-\s)|…{2,}\s*\d{1,4}\b(?!\.\d|\s?-\s)"
)  # pas « ……… 1.3 - Nom » (rubrique de formulaire)
_PAGE_AT_END = re.compile(r"\D\s*\b\d{1,3}\s*$")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")  # chaque groupe compte (« 476 420 » = 2)
_WORD = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def _toc_line(line: str) -> bool:
    """Ligne de sommaire : du texte puis *un* numéro de page (pas une ligne de tableau chiffré)."""
    if _LEADERS.search(line):
        return True
    if not _PAGE_AT_END.search(line):
        return False
    words, numbers = len(_WORD.findall(line)), len(_NUMBER.findall(line))
    return words >= 3 and numbers <= 3 and numbers <= words / 3


def is_navigational(text: str) -> bool:
    """Table des matières, sommaire, liste des tableaux ou index : utile pour s'orienter, pas pour
    répondre. Ces passages sont placés après les passages de contenu au classement (ADR-0021)."""
    if len(_LEADER_ANY.findall(text)) >= 3:
        return True
    lines = [x for x in text.splitlines() if x.strip()]
    if len(lines) < 4:
        return False
    toc = sum(_toc_line(x) for x in lines)
    leaders = sum(bool(_LEADERS.search(x)) for x in lines)
    if leaders >= 3:
        return True
    if _NAV_HEADING.search(text):
        return toc / len(lines) >= 0.3
    return toc / len(lines) >= 0.6


@dataclass(frozen=True)
class ChunkingProfile:
    max_chars: int = 1200
    overlap_chars: int = 150
    min_chars: int = 300  # un fragment plus court est complété par le paragraphe suivant


def _pages(blocks: list[Block]) -> tuple[int | None, int | None]:
    pages = [b.page for b in blocks if b.page is not None]
    return (min(pages), max(pages)) if pages else (None, None)


def _tail(text: str, size: int) -> str:
    """Fin du texte, coupée en début de phrase ou de mot."""
    if size <= 0 or len(text) <= size:
        return text if size > 0 else ""
    tail = text[-size:]
    m = re.search(r"(?<=[.!?;:])\s+", tail)
    if m and m.end() < len(tail) - 20:
        return tail[m.end() :]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def _split_long(text: str, max_chars: int) -> list[str]:
    """Coupe un paragraphe trop long : par lignes (listes), puis par phrases, sinon par mots."""
    if len(text) <= max_chars:
        return [text]
    if "\n" in text:
        parts: list[str] = []
        current = ""
        for line in text.split("\n"):
            for piece in _split_long(line, max_chars) if len(line) > max_chars else [line]:
                if current and len(current) + 1 + len(piece) > max_chars:
                    parts.append(current)
                    current = piece
                else:
                    current = f"{current}\n{piece}" if current else piece
        if current:
            parts.append(current)
        return parts
    parts: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def _split_table(block: Block, max_chars: int) -> list[str]:
    rows = block.text.split("\n")
    if len(block.text) <= max_chars or len(rows) < 3:
        return [block.text]
    header, body = rows[0], rows[1:]
    parts, current = [], [header]
    for row in body:
        if len("\n".join(current)) + len(row) + 1 > max_chars and len(current) > 1:
            parts.append("\n".join(current))
            current = [header]
        current.append(row)
    if len(current) > 1:
        parts.append("\n".join(current))
    return parts


def chunk_document(doc: ExtractedDocument, profile: ChunkingProfile = ChunkingProfile()) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    path: list[tuple[int, str]] = []  # (niveau, titre)
    buffer: list[Block] = []
    previous_tail = ""

    def section() -> tuple[str, ...]:
        return tuple(t for _, t in path)

    def emit(text: str, kind: str, blocks: list[Block]) -> None:
        start, end = _pages(blocks)
        if is_navigational(text):
            kind = "navigation"
        chunks.append(ChunkDraft(len(chunks), text, kind, section(), start, end))

    def flush() -> None:
        nonlocal buffer, previous_tail
        if not buffer:
            return
        pieces: list[tuple[str, list[Block]]] = []
        current_text, current_blocks = "", []
        for b in buffer:
            for part in _split_long(b.text, profile.max_chars):
                too_long = len(current_text) + 2 + len(part) > profile.max_chars
                if current_text and too_long and len(current_text) >= profile.min_chars:
                    pieces.append((current_text, current_blocks))
                    current_text, current_blocks = "", []
                current_text = f"{current_text}\n\n{part}" if current_text else part
                current_blocks.append(b)
        if current_text:
            pieces.append((current_text, current_blocks))
        for text, blocks in pieces:
            if previous_tail:
                text = f"… {previous_tail}\n\n{text}"
            emit(text, "ocr" if any(b.ocr for b in blocks) else "text", blocks)
            previous_tail = _tail(text, profile.overlap_chars)
        buffer = []

    for block in doc.blocks:
        if block.kind == "heading":
            flush()
            previous_tail = ""
            level = block.level or 1
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, block.text))
        elif block.kind == "table":
            flush()
            for part in _split_table(block, profile.max_chars):
                emit(part, "table", [block])
        else:
            if buffer and block.page is not None and buffer[-1].page is not None and block.page != buffer[-1].page:
                flush()  # changement de page : nouveau fragment (le chevauchement garde le contexte)
            buffer.append(block)
    flush()
    return chunks
