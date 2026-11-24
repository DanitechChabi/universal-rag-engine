# ADR-0006 — Modèle de permissions : clés d'accès, fermé par défaut, vérification tardive

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Les droits doivent être contrôlés avant la récupération des fragments et avant la génération, les révocations doivent être prises en compte, et un doute doit conduire à la restriction (sections 5.3, 11.2).

## Décision

- Chaque document porte des **clés d'accès** (`u:`, `g:`, `sp:`, `xu:`, `xg:`) ; un utilisateur a un ensemble de clés **recalculé à chaque question**.
- Filtre « au moins une clé commune » appliqué dans Qdrant **et** dans PostgreSQL avant tout classement.
- `acl_status = 'uncertain'` ⇒ aucune clé (contrainte en base) ⇒ invisible.
- Revérification auprès de la source (`check_access`) pour les connecteurs qui le permettent ; source injoignable ⇒ exclusion par défaut.
- Défense en profondeur : RLS par organisation sous le filtre applicatif.

## Alternatives écartées

Interroger la source à chaque question pour tous les candidats (trop lent, dépend de la disponibilité de la GED) ; copier les droits sans revérification (risque de droits périmés).

## Conséquences

Mécanisme uniforme pour tous les connecteurs. Testé au niveau SQL : clés calculées, documents incertains, supprimés, anciennes versions et révocation (`test_schema.sql` tests 5, 7, 8, 9).
