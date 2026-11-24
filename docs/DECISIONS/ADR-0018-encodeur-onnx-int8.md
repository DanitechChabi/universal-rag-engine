# ADR-0018 — Embeddings : BGE-M3 en ONNX quantifié int8, exécuté localement

- Statut : **acceptée** (phase 2, novembre 2026)
- Références : ADR-0005, docs/AI_MODELS.md §3, mesure de référence de la phase 1

## Contexte

La mesure de référence a indexé 83 documents en 58 minutes, à environ 0,9 fragment par seconde
(BGE-M3 servi par Ollama, CPU 4 cœurs). Pour le client type (50 000 à 500 000 documents, décision
Q6), ce débit est rédhibitoire sans GPU.

## Mesure

64 passages réels du corpus (environ 1 100 caractères), même machine :

| Encodeur | Passages par seconde | Similarité cosinus avec Ollama |
|---|---|---|
| BGE-M3 via Ollama | 0,64 | — |
| **BGE-M3 ONNX int8** (export Xenova/bge-m3, licence MIT) | **6,4** | 0,978 en moyenne (minimum 0,971) |

## Décision

- Encodeur recommandé : **ONNX int8 via ONNX Runtime** (`URAG_EMBEDDING_BACKEND=onnx`), sans service
  externe ; Ollama reste possible.
- Le modèle (≈ 570 Mo) est fourni avec l'installation, pas téléchargé en cours de fonctionnement.
- Profil d'embedding distinct (`bge-m3-onnx-int8`) : nouvelle collection Qdrant, réindexation
  complète lors du passage d'un encodeur à l'autre (section 9.6 du cahier des charges).
- La qualité de recherche est vérifiée par la mesure complète (`docs/reports/PHASE2.md`).

## Conséquences

- Indexation environ 10 fois plus rapide sur CPU ; le GPU reste utile pour la génération.
- Une dépendance de plus (`onnxruntime`, `tokenizers`), sans service supplémentaire, utilisable en
  Desktop comme en Server.
