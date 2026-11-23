# ADR-0001 — Monorepo, outillage et versions

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le cahier des charges impose un monorepo (section 19), des versions verrouillées et des modules indépendants.

## Décision

- Monorepo selon la structure de la section 19, avec des noms de dossiers compatibles Python (`local_files`).
- Python **3.12** (large compatibilité des roues binaires : ONNX Runtime, PyInstaller) ; espace de travail **uv**, versions verrouillées dans `uv.lock`.
- Paquets Python : `urag-core`, `urag-connectors-base`, un paquet par connecteur, `urag-api`, `urag-worker`.
- Ingestion et routeur IA sont des **modules de `urag-core`**, pas des services (`services/ingestion` et `services/model-router` du cahier des charges ne sont pas créés).
- Frontend : pnpm, Node 22 LTS.
- Règles de dépendance vérifiées automatiquement (import-linter).

## Alternatives écartées

Un paquet par sous-dossier de `core/` (trop de paquets pour un bénéfice faible) ; Poetry (plus lent, espaces de travail moins simples).

## Conséquences

Un seul outil Python ; les frontières entre modules restent contrôlées par des règles d'import plutôt que par des paquets séparés.
