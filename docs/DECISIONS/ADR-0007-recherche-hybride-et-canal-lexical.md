# ADR-0007 — Recherche hybride et canal lexical

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

La recherche doit retrouver aussi bien le sens d'une question que des références exactes (numéros de dossier, montants) (section 7.2). PostgreSQL ne fait pas de BM25 natif.

## Décision

- Canal **dense** : BGE-M3 dans Qdrant.
- Canal **lexical** : plein texte PostgreSQL (configuration française sans accents, testée) + similarité de trigrammes (`pg_trgm`) pour les références exactes.
- **Fusion** par rang réciproque (RRF), puis reranking facultatif.
- **À évaluer en phase 1** : vecteurs creux BGE-M3 dans Qdrant (si l'exécution hors PyTorch est possible) ou BM25 creux dans Qdrant, comparés au plein texte PostgreSQL sur le corpus de référence. La décision finale sera ajoutée à cette fiche.

## Alternatives écartées

Elasticsearch / OpenSearch (service lourd de plus, Java) ; extension BM25 tierce pour PostgreSQL (licence et disponibilité à vérifier).

## Conséquences

Aucun service supplémentaire ; le canal lexical reçoit les mêmes filtres de sécurité via `searchable_chunks`.
