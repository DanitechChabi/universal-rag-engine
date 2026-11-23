# ADR-0004 — Même socle de données en Desktop et en Server

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le mode Desktop ne doit demander aucune installation manuelle (section 4.1). Utiliser SQLite en Desktop et PostgreSQL en Server doublerait le code d'accès aux données et les tests.

## Décision

PostgreSQL et Qdrant dans les **deux** modes. En Desktop, ils sont embarqués (binaires portables de PostgreSQL pour Windows, binaire Qdrant) et démarrés par l'application, sans Docker.

## Alternatives écartées

SQLite + Qdrant en mode local intégré à Python : plus léger mais deux chemins de code, pas de RLS, plein texte différent.

## Conséquences

Installateur plus lourd (≈ 250 Mo de plus), mais un seul code, une seule batterie de tests, et la même sécurité (RLS) partout.
