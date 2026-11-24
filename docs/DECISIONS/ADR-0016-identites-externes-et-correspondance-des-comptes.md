# ADR-0016 — Identités externes et correspondance des comptes

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Pour appliquer les droits M-Files, il faut savoir quel utilisateur M-Files correspond à chaque compte local. LDAP / Active Directory est repoussé après le MVP par le cahier des charges.

## Décision

- Tables `external_principals`, `external_group_members` (synchronisées depuis la source) et `principal_links` (correspondance).
- MVP : correspondance saisie par l'administrateur ou importée (CSV), proposition automatique par identifiant ou courriel identique, à confirmer (`verified`).
- Un compte sans correspondance ne voit **aucun** document de la source.
- Après le MVP : LDAP / Active Directory pour l'authentification et la correspondance automatique.

## Alternatives écartées

Supposer que les identifiants sont identiques partout (risque de fuite) ; LDAP dès le MVP (à reconsidérer si le premier client l'exige, voir question Q1).

## Conséquences

Travail administratif à l'installation, mais aucune supposition dangereuse. Testé au niveau SQL (clés `xu:` et `xg:`).
