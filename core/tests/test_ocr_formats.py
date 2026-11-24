import shutil

import pytest
from urag_core.chunking import chunk_document
from urag_core.extraction import extract
from urag_core.ocr import LOW_CONFIDENCE, RapidOcrEngine, TesseractEngine

from tests.fixtures.documents import write_html, write_pptx, write_scanned_pdf, write_scanned_png, write_xlsx

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract non installé")


@needs_tesseract
def test_pdf_scanne_lu_par_ocr(tmp_path):
    pdf = write_scanned_pdf(tmp_path / "scan.pdf")
    assert extract(pdf).pages_without_text == [1]  # sans OCR : rien
    doc = extract(pdf, TesseractEngine())
    text = doc.text
    assert "250 millions" in text and "12 mars 2026" in text
    assert doc.ocr_engine.startswith("tesseract") and doc.ocr_min_confidence > LOW_CONFIDENCE
    assert all(b.page == 1 and b.ocr for b in doc.blocks)
    chunks = chunk_document(doc)
    assert chunks and all(c.kind == "ocr" and c.page_start == 1 for c in chunks)


@needs_tesseract
def test_image_lue_par_ocr(tmp_path):
    doc = extract(write_scanned_png(tmp_path / "facture.png"), TesseractEngine())
    assert "deux ans" in doc.text and doc.page_count == 1


def test_rapidocr_lit_aussi_le_scan(tmp_path):
    doc = extract(write_scanned_pdf(tmp_path / "scan.pdf"), RapidOcrEngine())
    assert "250" in doc.text and "millions" in doc.text


def test_excel_feuilles_et_tableaux(tmp_path):
    doc = extract(write_xlsx(tmp_path / "taux.xlsx"))
    headings = [b.text for b in doc.blocks if b.kind == "heading"]
    assert headings == ["Taux 2026", "Notes"]
    table = next(b for b in doc.blocks if b.kind == "table")
    assert "Bénin | 1.2 | 6.4" in table.text
    chunk = next(c for c in chunk_document(doc) if c.kind == "table")
    assert chunk.section_path == ("Taux 2026",)


def test_powerpoint_diapositives_comme_pages(tmp_path):
    doc = extract(write_pptx(tmp_path / "plan.pptx"))
    assert doc.page_count == 2
    assert any("12 nouvelles agences" in b.text and b.page == 1 for b in doc.blocks)
    assert any(b.kind == "table" and "Informatique | 1,5 milliard FCFA" in b.text and b.page == 2 for b in doc.blocks)


def test_html_sans_scripts_ni_styles(tmp_path):
    doc = extract(write_html(tmp_path / "guide.html"))
    text = doc.text
    assert "alert" not in text and "color:red" not in text
    assert [b.text for b in doc.blocks if b.kind == "heading"] == ["Guide du client", "Frais"]
    assert any(b.kind == "table" and "Virement | 500 FCFA" in b.text for b in doc.blocks)
    assert any(b.kind == "list" and b.text == "Carte bancaire" for b in doc.blocks)
