# ADR-0013 — Server avant Desktop

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le plan du cahier des charges place le Desktop (phase 6) avant le Server (phase 7). Les phases 1 à 5 se développent sur la pile Docker, qui est déjà le mode Server.

## Décision

Réaliser la phase 7 (Server) **avant** la phase 6 (Desktop).

## Alternatives écartées

Ordre initial (empaquetage Desktop pendant que le cœur évolue encore, donc refait plusieurs fois).

## Conséquences

Le produit est installable chez un premier client (cible principale : banques, assurances, administrations) plus tôt ; le Desktop, le plus coûteux à empaqueter, arrive sur un cœur stabilisé.
