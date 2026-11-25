"""Extraction du texte, de la structure et des numéros de page (ADR-0008).

PDF (pypdfium2, OCR des pages sans texte), images PNG / JPEG (OCR), DOCX (python-docx),
XLSX (openpyxl), PPTX (python-pptx), HTML (analyseur de la bibliothèque standard),
TXT / MD / CSV. Formats anciens (DOC, XLS, PPT, RTF) : Tika, prévu (ADR-0008).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from importlib.metadata import version as _version
from pathlib import Path
from typing import Literal

BlockKind = Literal["heading", "paragraph", "table", "list"]

MIN_TEXT_CHARS_PER_PAGE = 20


@dataclass(frozen=True)
class Block:
    text: str
    kind: BlockKind = "paragraph"
    page: int | None = None
    level: int = 0  # niveau de titre (1 = le plus haut)
    ocr: bool = False  # texte issu de la reconnaissance optique


@dataclass
class ExtractedDocument:
    blocks: list[Block]
    page_count: int | None = None
    pages_without_text: list[int] = field(default_factory=list)
    extractor: str = ""
    warnings: list[str] = field(default_factory=list)
    ocr_engine: str | None = None
    ocr_min_confidence: float | None = None

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
        # Les éléments de liste numérotée (« 1 BANGE BANK », « 2) Article ») restent sur leur ligne.
        joined = re.sub(r"(?<![.:;!?])\n(?=[a-zàâäéèêëîïôöùûüç]|[0-9](?!\d{0,2}[.)]?\s+[A-ZÀ-Ý]))", " ", para)
        blocks.append(Block(joined, "paragraph", page))
    return blocks


def _ocr_blocks(page_text: str, page: int | None) -> list[Block]:
    return [Block(b.text, "paragraph", page, ocr=True) for b in _paragraphs(clean_text(page_text), page)]


def extract_pdf(path: Path, ocr=None) -> ExtractedDocument:
    import pypdfium2 as pdfium

    from ..ocr import LOW_CONFIDENCE, RENDER_DPI

    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        raise ExtractionError(f"PDF illisible : {e}") from e
    blocks: list[Block] = []
    empty: list[int] = []
    low: list[int] = []
    confidences: list[float] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            raw = textpage.get_text_bounded()
            textpage.close()
            cleaned = clean_text(raw)
            if len(cleaned) >= MIN_TEXT_CHARS_PER_PAGE:
                blocks.extend(_paragraphs(cleaned, index + 1))
            elif ocr is not None:
                result = ocr.recognize(page.render(scale=RENDER_DPI / 72).to_pil())
                confidences.append(result.confidence)
                if result.confidence < LOW_CONFIDENCE:
                    low.append(index + 1)
                if len(result.text.strip()) >= MIN_TEXT_CHARS_PER_PAGE:
                    blocks.extend(_ocr_blocks(result.text, index + 1))
                else:
                    empty.append(index + 1)
            else:
                empty.append(index + 1)
            page.close()
        count = len(pdf)
    finally:
        pdf.close()
    warnings = []
    if empty:
        reason = "aucun texte reconnu" if ocr is not None else "OCR désactivé"
        warnings.append(f"{len(empty)} page(s) sans texte ({reason})")
    if low:
        warnings.append(f"qualité OCR insuffisante page(s) {', '.join(map(str, low))}")
    return ExtractedDocument(
        blocks,
        count,
        empty,
        f"pypdfium2/{_version('pypdfium2')}",
        warnings,
        ocr.name if confidences else None,
        min(confidences) if confidences else None,
    )


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
    return ExtractedDocument(
        blocks, None, [], "python-docx", ["pas de numéros de page dans un fichier Word"] if blocks else []
    )


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


def extract_image(path: Path, ocr=None) -> ExtractedDocument:
    from PIL import Image

    from ..ocr import LOW_CONFIDENCE

    if ocr is None:
        return ExtractedDocument([], 1, [1], "image", ["image : OCR désactivé"])
    try:
        with Image.open(path) as im:
            result = ocr.recognize(im.convert("RGB"))
    except OSError as e:
        raise ExtractionError(f"image illisible : {e}") from e
    warnings = ["qualité OCR insuffisante"] if result.confidence < LOW_CONFIDENCE else []
    blocks = _ocr_blocks(result.text, 1) if len(result.text.strip()) >= MIN_TEXT_CHARS_PER_PAGE else []
    return ExtractedDocument(blocks, 1, [] if blocks else [1], "image", warnings, ocr.name, result.confidence)


def extract_xlsx(path: Path) -> ExtractedDocument:
    """Une feuille = une section ; ses lignes forment un tableau (en-tête répété au découpage)."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 - formats OOXML variés
        raise ExtractionError(f"XLSX illisible : {e}") from e
    blocks: list[Block] = []
    for sheet in wb.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else clean_text(str(v)).replace("\n", " ") for v in row]
            while cells and not cells[-1]:
                cells.pop()
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            blocks.append(Block(sheet.title, "heading", None, 1))
            blocks.append(Block("\n".join(rows), "table"))
    wb.close()
    return ExtractedDocument(blocks, None, [], f"openpyxl/{_version('openpyxl')}")


def extract_pptx(path: Path) -> ExtractedDocument:
    """Une diapositive = une page (numéro de diapositive conservé pour les citations)."""
    from pptx import Presentation

    try:
        deck = Presentation(str(path))
    except Exception as e:  # noqa: BLE001
        raise ExtractionError(f"PPTX illisible : {e}") from e
    blocks: list[Block] = []
    for number, slide in enumerate(deck.slides, start=1):
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = clean_text(shape.text_frame.text)
                if text:
                    is_title = shape == getattr(slide.shapes, "title", None)
                    blocks.append(Block(text, "heading" if is_title else "paragraph", number, 2 if is_title else 0))
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [" | ".join(clean_text(c.text) for c in r.cells) for r in shape.table.rows]
                blocks.append(Block("\n".join(rows), "table", number))
        if slide.has_notes_slide:
            notes = clean_text(slide.notes_slide.notes_text_frame.text)
            if notes:
                blocks.append(Block(notes, "paragraph", number))
    return ExtractedDocument(blocks, len(deck.slides), [], f"python-pptx/{_version('python-pptx')}")


def extract_html(path: Path) -> ExtractedDocument:
    """Titres h1-h6, paragraphes, listes et tableaux ; scripts et styles ignorés."""
    from html.parser import HTMLParser

    raw = path.read_bytes().decode("utf-8", errors="replace")
    blocks: list[Block] = []

    class Parser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.skip = 0
            self.buf: list[str] = []
            self.level = 0
            self.row: list[str] | None = None
            self.rows: list[str] = []

        def flush(self, kind: str = "paragraph") -> None:
            text = clean_text(" ".join(self.buf))
            self.buf = []
            if text:
                blocks.append(Block(text, "heading" if self.level else kind, None, self.level))

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "noscript", "template"):
                self.skip += 1
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.flush()
                self.level = int(tag[1])
            elif tag in ("p", "div", "li", "br", "section", "article"):
                self.flush("list" if tag == "li" else "paragraph")
            elif tag == "tr":
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.buf = []

        def handle_endtag(self, tag):
            if tag in ("script", "style", "noscript", "template"):
                self.skip = max(0, self.skip - 1)
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.flush()
                self.level = 0
            elif tag in ("td", "th") and self.row is not None:
                self.row.append(clean_text(" ".join(self.buf)))
                self.buf = []
            elif tag == "tr" and self.row is not None:
                if any(self.row):
                    self.rows.append(" | ".join(self.row))
                self.row = None
            elif tag == "table":
                if self.rows:
                    blocks.append(Block("\n".join(self.rows), "table"))
                self.rows = []
            elif tag in ("p", "li", "div"):
                self.flush("list" if tag == "li" else "paragraph")

        def handle_data(self, data):
            if not self.skip:
                self.buf.append(data)

    parser = Parser()
    parser.feed(raw)
    parser.flush()
    return ExtractedDocument(blocks, None, [], "html.parser")


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".xlsx": extract_xlsx,
    ".pptx": extract_pptx,
    ".html": extract_html,
    ".htm": extract_html,
    ".png": extract_image,
    ".jpg": extract_image,
    ".jpeg": extract_image,
    ".txt": extract_text_file,
    ".md": extract_text_file,
    ".csv": extract_text_file,
}
OCR_CAPABLE = {extract_pdf, extract_image}


def extract(path: Path, ocr=None) -> ExtractedDocument:
    """Extrait un document ; ``ocr`` (moteur OCR) est utilisé pour les pages et images sans texte."""
    extractor = EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        raise UnsupportedFormatError(f"format non pris en charge : {path.suffix}")
    return extractor(path, ocr) if extractor in OCR_CAPABLE else extractor(path)


_FR = {"le", "la", "les", "des", "du", "de", "et", "est", "une", "un", "pour", "dans", "que", "qui", "au", "aux"}
_EN = {"the", "and", "of", "to", "is", "in", "for", "that", "with", "on", "by", "this", "are", "be"}


def detect_language(text: str) -> str:
    """Détection simple français / anglais (suffisante pour choisir l'analyse plein texte)."""
    words = re.findall(r"[a-zA-Zàâäéèêëîïôöùûüç']+", text.lower()[:5000])
    fr = sum(w in _FR for w in words)
    en = sum(w in _EN for w in words)
    return "en" if en > fr * 1.2 else "fr"
