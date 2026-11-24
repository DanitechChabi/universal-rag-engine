# ADR-0010 — Génération locale : Ollama, vLLM en option serveur

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Ollama est demandé. Pour 5 à 8 générations simultanées sur un GPU, un moteur avec traitement par lots continu tient mieux la charge (section 4.2).

## Décision

- Ollama : moteur par défaut (Desktop et Server).
- vLLM : option recommandée en Server avec GPU, via l'adaptateur **compatible OpenAI** (aucun code spécifique).
- Le choix est une configuration ; les tests de charge (phase 7) fixeront la recommandation.

## Alternatives écartées

Ollama seul (concurrence limitée) ; vLLM seul (pas adapté au Desktop Windows).

## Conséquences

Un adaptateur de plus à tester, mais il couvre aussi LM Studio et llama.cpp.
