# ADR-0014 — Model Router : bibliothèque, pas service

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le cahier des charges cite `services/model-router`. Un service séparé ajoute un processus et un saut réseau, pénalisants en Desktop.

## Décision

Le Model Router est le module `urag_core.ai`, utilisé dans les processus api et worker. Les limites de concurrence par modèle sont partagées entre processus via PostgreSQL (verrous consultatifs) ou une file d'attente des générations dans l'api.

## Alternatives écartées

Service HTTP séparé (utile seulement si plusieurs serveurs d'application partagent un pool de GPU : évolution possible).

## Conséquences

Moins de processus ; l'interface du routeur permettra d'en faire un service plus tard sans changer ses appelants.
