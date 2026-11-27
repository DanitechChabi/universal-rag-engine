"""Export des réponses en Markdown, Word et PDF (cahier des charges §8.4 et §10.4).

Le contenu exporté est exactement celui que l'utilisateur peut voir à cet instant
(``conversation_view``) : droits revérifiés, réponse masquée si un document cité n'est plus
accessible, extraits retirés des sources devenues inaccessibles. Les références [n] du texte
renvoient à la liste « Sources » qui suit chaque réponse.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from xml.sax.saxutils import escape

NOTE = "Réponses générées à partir des documents de l'organisation : vérifiez-les dans les sources citées."
MAX_EXCERPT = 400


def _excerpt(text: str | None) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= MAX_EXCERPT else text[: MAX_EXCERPT - 1].rstrip() + "…"


def _source_line(c: dict) -> str:
    if not c["accessible"]:
        return f"[{c['rank']}] document devenu inaccessible"
    parts = [c["title"] or "document", c.get("pages") or "", c.get("source") or ""]
    date = ""
    if c.get("modified"):
        y, m, d = c["modified"].split("-")
        date = f"modifié le {d}/{m}/{y}"
    return f"[{c['rank']}] " + " — ".join(p for p in [*parts, date] if p)


def turns(view: dict) -> list[tuple[str, dict | None]]:
    """(question, réponse) dans l'ordre de la conversation."""
    out: list[tuple[str, dict | None]] = []
    for m in view["messages"]:
        if m["role"] == "user":
            out.append((m["content"], None))
        elif out and out[-1][1] is None:
            out[-1] = (out[-1][0], m)
        else:
            out.append(("", m))
    return out


def header(view: dict, organization: str, author: str) -> list[str]:
    return [
        view["title"] or "Conversation",
        f"{organization} — {author} — exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        NOTE,
    ]


def to_markdown(view: dict, organization: str, author: str) -> bytes:
    title, meta, note = header(view, organization, author)
    lines = [f"# {title}", "", f"_{meta}_", "", f"> {note}", ""]
    for question, answer in turns(view):
        if question:
            lines += [f"## Question : {question}", ""]
        if answer:
            lines += [answer["content"], ""]
            if answer["citations"]:
                lines += ["**Sources**", ""]
                for c in answer["citations"]:
                    lines.append(f"- {_source_line(c)}")
                    if c.get("excerpt"):
                        lines.append(f"  > {_excerpt(c['excerpt'])}")
                lines.append("")
    return "\n".join(lines).encode("utf-8")


def to_docx(view: dict, organization: str, author: str) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor

    title, meta, note = header(view, organization, author)
    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = author
    doc.add_heading(title, level=0)
    p = doc.add_paragraph(meta)
    p.runs[0].italic = True
    p = doc.add_paragraph(note)
    p.runs[0].font.size = Pt(9)
    p.runs[0].font.color.rgb = RGBColor(0x55, 0x60, 0x6E)
    for question, answer in turns(view):
        if question:
            doc.add_heading(question, level=2)
        if answer:
            for para in answer["content"].split("\n"):
                if para.strip():
                    doc.add_paragraph(para)
            if answer["citations"]:
                doc.add_paragraph().add_run("Sources").bold = True
                for c in answer["citations"]:
                    doc.add_paragraph(_source_line(c), style="List Bullet")
                    if c.get("excerpt"):
                        q = doc.add_paragraph(_excerpt(c["excerpt"]))
                        q.paragraph_format.left_indent = Pt(18)
                        q.runs[0].font.size = Pt(9)
                        q.runs[0].italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf_text(text: str) -> str:
    # Polices standard du PDF (WinAnsi) : les caractères hors de ce jeu sont remplacés, jamais perdus en silence.
    safe = text.encode("cp1252", errors="replace").decode("cp1252")
    return escape(safe).replace("\n", "<br/>")


def to_pdf(view: dict, organization: str, author: str) -> bytes:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    title, meta, note = header(view, organization, author)
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=17, spaceAfter=4),
        "meta": ParagraphStyle("m", parent=base["Normal"], fontSize=8.5, textColor=HexColor("#55606E")),
        "q": ParagraphStyle("q", parent=base["Heading3"], spaceBefore=12, textColor=HexColor("#1E4A72")),
        "a": ParagraphStyle("a", parent=base["Normal"], fontSize=10.5, leading=15),
        "src": ParagraphStyle("s", parent=base["Normal"], fontSize=8.5, leading=11, leftIndent=8, spaceBefore=3),
        "ex": ParagraphStyle(
            "e", parent=base["Italic"], fontSize=8, leading=10.5, leftIndent=16, textColor=HexColor("#55606E")
        ),
    }
    story = [
        Paragraph(_pdf_text(title), styles["title"]),
        Paragraph(_pdf_text(meta), styles["meta"]),
        Paragraph(_pdf_text(note), styles["meta"]),
        Spacer(1, 6 * mm),
    ]
    for question, answer in turns(view):
        if question:
            story.append(Paragraph(_pdf_text(question), styles["q"]))
        if answer:
            story.append(Paragraph(_pdf_text(answer["content"]), styles["a"]))
            if answer["citations"]:
                story.append(Paragraph("<b>Sources</b>", styles["src"]))
                for c in answer["citations"]:
                    story.append(Paragraph(_pdf_text(_source_line(c)), styles["src"]))
                    if c.get("excerpt"):
                        story.append(Paragraph(_pdf_text(_excerpt(c["excerpt"])), styles["ex"]))
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4, title=title, author=author, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm
    )
    pdf.build(story)
    return buf.getvalue()


FORMATS = {
    "md": (to_markdown, "text/markdown; charset=utf-8", "md"),
    "docx": (to_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "pdf": (to_pdf, "application/pdf", "pdf"),
}


def filename(title: str | None, ext: str) -> str:
    base = re.sub(r"[^\w\- ]+", "", (title or "conversation"), flags=re.UNICODE).strip()[:60] or "conversation"
    return f"{base.replace(' ', '_')}_{datetime.now():%Y%m%d}.{ext}"
