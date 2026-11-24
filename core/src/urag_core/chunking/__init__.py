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

    def embedding_text(self, title: str) -> str:
        """Texte encodé : titre du document et section en tête, pour situer le passage."""
        head = " > ".join((title, *self.section_path))
        return f"{head}\n{self.text}"


@dataclass(frozen=True)
class ChunkingProfile:
    max_chars: int = 1200
    overlap_chars: int = 150


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
    """Coupe un paragraphe trop long en phrases, sinon en mots."""
    if len(text) <= max_chars:
        return [text]
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
        chunks.append(ChunkDraft(len(chunks), text, kind, section(), start, end))

    def flush() -> None:
        nonlocal buffer, previous_tail
        if not buffer:
            return
        pieces: list[tuple[str, list[Block]]] = []
        current_text, current_blocks = "", []
        for b in buffer:
            for part in _split_long(b.text, profile.max_chars):
                if current_text and len(current_text) + 2 + len(part) > profile.max_chars:
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
