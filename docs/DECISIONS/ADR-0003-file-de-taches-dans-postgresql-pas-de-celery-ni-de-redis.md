# ADR-0003 — File de tâches dans PostgreSQL (pas de Celery ni de Redis)

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le cahier des charges propose Celery et Redis « ou équivalent ». Celery ne prend plus officiellement en charge Windows, Redis n'a pas de version officielle Windows, et sa licence depuis la version 7.4 n'est plus permissive (RSAL/SSPL, AGPL en option) : problématique pour un produit vendu et pour le mode Desktop.

## Décision

File de tâches dans la table `jobs` de PostgreSQL : prise de tâche par `SELECT … FOR UPDATE SKIP LOCKED`, priorités, reprises avec attente croissante, battement de cœur (tâches orphelines reprises), annulation, progression, clé de déduplication des tâches actives. Implémentation maison légère dans `urag_core.jobs`.

## Alternatives écartées

Celery + Redis ; Celery + RabbitMQ (service de plus) ; Dramatiq ; Valkey (pas de version Windows).

## Conséquences

Deux services de moins ; fonctionne à l'identique sur Windows et Linux ; tâches transactionnelles avec les données. Suffisant pour la charge visée (30 utilisateurs, centaines de milliers de documents). Testé : prise SKIP LOCKED et unicité des tâches actives (`test_schema.sql` test 13).
