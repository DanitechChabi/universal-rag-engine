"""Reconnaissance de texte des pages scannées (ADR-0017).

Deux moteurs derrière la même interface :
- ``TesseractEngine`` (défaut) : paragraphes conservés, meilleur sur les scans du corpus ;
- ``RapidOcrEngine`` : modèles PaddleOCR en ONNX, sans logiciel système (utile en Desktop).

Chaque page renvoie son texte (paragraphes séparés par une ligne vide) et un score de
confiance entre 0 et 1, enregistré avec la version indexée.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Protocol

LOW_CONFIDENCE = 0.60  # en dessous : « indexé avec avertissement »
RENDER_DPI = 300


@dataclass(frozen=True)
class OcrPage:
    text: str
    confidence: float  # 0 à 1


class OcrEngine(Protocol):
    name: str

    def recognize(self, image) -> OcrPage: ...  # image PIL


class OcrUnavailableError(RuntimeError):
    pass


class TesseractEngine:
    def __init__(self, languages: str = "fra+eng") -> None:
        import pytesseract

        if shutil.which("tesseract") is None:
            raise OcrUnavailableError("la commande tesseract n'est pas installée")
        self._tess = pytesseract
        self.languages = languages
        self.name = f"tesseract/{pytesseract.get_tesseract_version()}/{languages}"

    def recognize(self, image) -> OcrPage:
        data = self._tess.image_to_data(image, lang=self.languages, output_type=self._tess.Output.DICT)
        paragraphs: dict[tuple[int, int], dict[int, list[str]]] = {}
        confidences: list[float] = []
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            conf = float(data["conf"][i])
            if not word or conf < 0:
                continue
            confidences.append(conf)
            key = (data["block_num"][i], data["par_num"][i])
            paragraphs.setdefault(key, {}).setdefault(data["line_num"][i], []).append(word)
        text = "\n\n".join(
            "\n".join(" ".join(words) for _, words in sorted(lines.items())) for _, lines in sorted(paragraphs.items())
        )
        confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0
        return OcrPage(text, round(confidence, 3))


class RapidOcrEngine:
    def __init__(self) -> None:
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

        self._engine = RapidOCR(
            params={
                "Rec.lang_type": LangRec.LATIN,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
            }
        )
        self.name = "rapidocr/PP-OCRv5-latin-mobile"

    def recognize(self, image) -> OcrPage:
        result = self._engine(image)
        texts = list(result.txts or ())
        scores = list(result.scores or ())
        confidence = sum(scores) / len(scores) if scores else 0.0
        return OcrPage("\n".join(texts), round(float(confidence), 3))


def build_engine(name: str | None) -> OcrEngine | None:
    """``tesseract`` (défaut), ``rapidocr`` ou ``none``. Repli sur RapidOCR si Tesseract est absent."""
    name = (name or "tesseract").lower()
    if name == "none":
        return None
    if name == "rapidocr":
        return RapidOcrEngine()
    try:
        return TesseractEngine()
    except OcrUnavailableError:
        return RapidOcrEngine()
