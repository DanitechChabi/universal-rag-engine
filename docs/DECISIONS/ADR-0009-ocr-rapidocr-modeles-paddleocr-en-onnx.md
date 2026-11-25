# ADR-0009 — OCR : RapidOCR (modèles PaddleOCR en ONNX)

- Statut : **acceptée** (phase 0, novembre 2026) — choix par défaut remplacé par ADR-0017 après mesure
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

PaddleOCR est demandé et reconnaît bien le français, mais PaddlePaddle est lourd à installer et à empaqueter sous Windows.

## Décision

**RapidOCR** : mêmes modèles de détection et reconnaissance que PaddleOCR, exécutés par ONNX Runtime (CPU ou GPU). Tesseract (français) en secours. Score de confiance par page enregistré (`ocr_min_confidence`) ; en dessous d'un seuil, le document passe « indexé avec avertissement ». Choix confirmé sur un échantillon de vrais scans en phase 2.

## Alternatives écartées

PaddleOCR natif (dépendance PaddlePaddle lourde) ; Tesseract seul (qualité inférieure sur les scans difficiles) ; services OCR en ligne (contraire à l'indépendance du cloud).

## Conséquences

Qualité de PaddleOCR avec un empaquetage léger ; même moteur d'exécution (ONNX) que les embeddings et le reranker.
