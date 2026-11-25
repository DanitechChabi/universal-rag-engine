# ADR-0017 — OCR : Tesseract par défaut, RapidOCR en alternative

- Statut : **acceptée** (phase 2, novembre 2026) — remplace le choix par défaut d'ADR-0009
- Références : ADR-0009, banc d'essai sur le corpus public (`eval/`)

## Contexte

ADR-0009 retenait RapidOCR (modèles PaddleOCR en ONNX), Tesseract en secours, « choix à confirmer
sur un échantillon de vrais scans ». La mesure a été faite en phase 2.

## Mesure

9 pages réellement scannées du corpus public (avis et décision BCEAO, lois du Bénin), rendues à
300 dpi, 15 faits attendus par les questions de référence (montants, dates, définitions) :

| Moteur | Faits retrouvés | Durée par page (CPU 4 cœurs) | Mise en page |
|---|---|---|---|
| Tesseract 5.3, français | **15 / 15** | **2,6 s** | paragraphes séparés, texte complet |
| RapidOCR PP-OCRv5 latin (mobile) | 15 / 15 | 3,3 s | lignes collées, **une ligne entière omise** sur une page |
| RapidOCR PP-OCRv4 latin (mobile) | 15 / 15 | 3,8 s | — |

## Décision

- **Tesseract (français + anglais) par défaut** : même exactitude, plus rapide, et il restitue les
  paragraphes, ce dont dépend le découpage en fragments.
- **RapidOCR en alternative** (`URAG_OCR_ENGINE=rapidocr`) et en repli automatique si Tesseract
  n'est pas installé : il ne demande aucun logiciel système, utile pour le Desktop (phase 6).
- Rendu des pages à 300 dpi ; confiance moyenne par page enregistrée (`ocr_min_confidence`) ;
  en dessous de 0,60, le document est « indexé avec avertissement ».
- Le moteur OCR fait partie de l'identité d'une version indexée : un changement de moteur, ou son
  activation, fait relire les pages scannées (migration 0002).

## Conséquences

- Mode Server : paquet `tesseract-ocr` + `tesseract-ocr-fra` dans l'image du worker (licence Apache 2.0).
- Mode Desktop : Tesseract à embarquer, ou RapidOCR (décision en phase 6).
- Les deux moteurs restent testés (`core/tests/test_ocr_formats.py`).
