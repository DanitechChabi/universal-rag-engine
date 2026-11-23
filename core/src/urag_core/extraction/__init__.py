"""Extraction du texte, de la structure et des numéros de page (ADR-0008).

Phase 1 : PDF (pypdfium2), DOCX (python-docx), TXT / MD / CSV.
Les pages PDF sans texte sont signalées (OCR en phase 2).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from importlib.metadata import version as _version
from typing import Literal

BlockKind = Literal["heading", "paragraph", "table", "list"]

MIN_TEXT_CHARS_PER_PAGE = 20


@dataclass(frozen=True)
class Block:
    text: str
    kind: BlockKind = "paragraph"
    page: int | None = None
    level: int = 0  # niveau de titre (1 = le plus haut)


@dataclass
class ExtractedDocument:
    blocks: list[Block]
    page_count: int | None = None
    pages_without_text: list[int] = field(default_factory=list)
    extractor: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


class ExtractionError(Exception):
    pass


class UnsupportedFormatError(ExtractionError):
    pass


_SPACES = re.compile(r"[ \t ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalisation : espaces, césures de fin de ligne, caractères de contrôle."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # césure en fin de ligne
    text = "".join(c for c in text if c == "\n" or c == "\t" or ord(c) >= 32)
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MANY_NEWLINES.sub("\n\n", text).strip()


def _paragraphs(text: str, page: int | None) -> list[Block]:
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        # Lignes courtes successives d'un même paragraphe : on les recolle.
        joined = re.sub(r"(?<![.:;!?])\n(?=[a-zàâäéèêëîïôöùûüç0-9])", " ", para)
        blocks.append(Block(joined, "paragraph", page))
    return blocks


def extract_pdf(path: Path) -> ExtractedDocument:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        raise ExtractionError(f"PDF illisible : {e}") from e
    blocks: list[Block] = []
    empty: list[int] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            raw = textpage.get_text_bounded()
            textpage.close()
            page.close()
            cleaned = clean_text(raw)
            if len(cleaned) < MIN_TEXT_CHARS_PER_PAGE:
                empty.append(index + 1)
                continue
            blocks.extend(_paragraphs(cleaned, index + 1))
        count = len(pdf)
    finally:
        pdf.close()
    warnings = []
    if empty:
        warnings.append(f"{len(empty)} page(s) sans texte : OCR nécessaire (phase 2)")
    return ExtractedDocument(blocks, count, empty, f"pypdfium2/{_version('pypdfium2')}", warnings)


def _docx_heading_level(style_name: str) -> int:
    m = re.match(r"(?:heading|titre)\s*(\d)", style_name.strip().lower())
    if m:
        return int(m.group(1))
    return 1 if style_name.strip().lower() in ("title", "titre") else 0


def extract_docx(path: Path) -> ExtractedDocument:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(str(path))
    except Exception as e:  # le format OOXML peut lever des erreurs variées
        raise ExtractionError(f"DOCX illisible : {e}") from e
    blocks: list[Block] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = clean_text(para.text)
            if not text:
                continue
            style = para.style.name if para.style is not None else ""
            level = _docx_heading_level(style)
            if level:
                blocks.append(Block(text, "heading", None, level))
            elif "list" in style.lower():
                blocks.append(Block(text, "list"))
            else:
                blocks.append(Block(text, "paragraph"))
        elif tag == "tbl":
            table = Table(child, document)
            rows = []
            for row in table.rows:
                cells = [clean_text(c.text).replace("\n", " ") for c in row.cells]
                # Cellules fusionnées : python-docx les répète, on dédoublonne les voisines.
                dedup = [c for i, c in enumerate(cells) if i == 0 or c != cells[i - 1]]
                rows.append(" | ".join(dedup))
            if any(r.strip(" |") for r in rows):
                blocks.append(Block("\n".join(rows), "table"))
    return ExtractedDocument(blocks, None, [], "python-docx",
                             ["pas de numéros de page dans un fichier Word"] if blocks else [])


def extract_text_file(path: Path) -> ExtractedDocument:
    raw = path.read_bytes()
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if path.suffix.lower() == ".csv":
        rows = list(csv.reader(io.StringIO(text)))
        body = "\n".join(" | ".join(r) for r in rows)
        return ExtractedDocument([Block(body, "table")] if body else [], None, [], "csv")
    blocks: list[Block] = []
    for para in re.split(r"\n\s*\n", text):
        para = clean_text(para)
        if not para:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", para) if path.suffix.lower() == ".md" else None
        if m and "\n" not in para:
            blocks.append(Block(m.group(2), "heading", None, len(m.group(1))))
        else:
            blocks.append(Block(para, "paragraph"))
    return ExtractedDocument(blocks, None, [], "text")


EXTRACTORS = {".pdf": extract_pdf, ".docx": extract_docx, ".txt": extract_text_file,
              ".md": extract_text_file, ".csv": extract_text_file}


def extract(path: Path) -> ExtractedDocument:
    extractor = EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        raise UnsupportedFormatError(f"format non pris en charge en phase 1 : {path.suffix}")
    return extractor(path)


_FR = {"le", "la", "les", "des", "du", "de", "et", "est", "une", "un", "pour", "dans", "que", "qui", "au", "aux"}
_EN = {"the", "and", "of", "to", "is", "in", "for", "that", "with", "on", "by", "this", "are", "be"}


def detect_language(text: str) -> str:
    """Détection simple français / anglais (suffisante pour choisir l'analyse plein texte)."""
    words = re.findall(r"[a-zA-Zàâäéèêëîïôöùûüç']+", text.lower()[:5000])
    fr = sum(w in _FR for w in words)
    en = sum(w in _EN for w in words)
    return "en" if en > fr * 1.2 else "fr"
