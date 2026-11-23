# ADR-0002 — Orchestration RAG interne plutôt que LlamaIndex

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le cahier des charges laisse le choix entre LlamaIndex et une architecture interne. Le contrôle des droits doit être au cœur de la recherche et vérifiable (sections 11.2 et 27.8).

## Décision

Orchestrateur RAG **interne** et léger dans `urag_core.rag` : recherche filtrée, fusion, reranking, construction du contexte, génération, validation des citations. Des pièces isolées de bibliothèques tierces peuvent être utilisées (extracteurs, découpeurs) si elles apportent un gain mesuré.

## Alternatives écartées

LlamaIndex ou LangChain comme cœur : rapides pour un prototype, mais couches d'abstraction qui changent souvent et rendent le chemin des filtres de sécurité moins lisible et moins testable.

## Conséquences

Un peu plus de code à écrire (quelques centaines de lignes), en échange d'un contrôle complet et de tests directs sur le filtrage des droits.
