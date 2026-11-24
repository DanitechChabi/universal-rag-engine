# ADR-0015 — Organisations : org_id partout, une seule organisation dans l'interface du MVP

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le cahier des charges demande l'isolation des organisations et un super administrateur qui les gère. Une installation sur site sert en général une seule organisation.

## Décision

- `org_id` sur toutes les tables, clés étrangères composites, **RLS forcée** (testé), filtre Qdrant obligatoire.
- Un compte appartient à une seule organisation.
- L'interface du MVP n'affiche qu'une organisation ; la gestion multi-organisations existe dans l'API (super administrateur) et sera exposée plus tard.

## Alternatives écartées

Pas de multi-organisation (refonte coûteuse plus tard) ; multi-organisation complète dans l'interface dès le MVP (travail d'interface sans client qui en ait besoin).

## Conséquences

La sécurité multi-organisation est en place dès le départ, sans coût d'interface immédiat.
