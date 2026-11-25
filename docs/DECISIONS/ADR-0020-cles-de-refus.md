# ADR-0020 — Refus explicites des sources : clés de refus

- Statut : **acceptée** (phase 3, novembre 2026)
- Complète : ADR-0006 (clés d'accès, fermé par défaut), ADR-0016 (identités externes)
- Références : docs/SECURITY.md §2, docs/CONNECTORS.md §4.3

## Contexte

Les GED, M-Files compris, permettent de refuser explicitement l'accès à une personne ou à
un groupe, même s'il est autorisé par ailleurs (par exemple « Juridique » autorisé, sauf
Bruno). Jusqu'ici, un tel refus ne pouvait pas être représenté par des clés d'accès
positives : le document était marqué « droits incertains » et devenait **invisible pour
tous**. C'est sûr, mais inutilisable avec une GED réelle, où ces refus sont courants.

## Décision

- Chaque document porte, en plus de ses clés d'accès, des **clés de refus** (`deny_keys`,
  même format : `xu:` ou `xg:` suivi d'un identifiant).
- Une seule règle de visibilité, dans la fonction SQL `urag_doc_visible(accès, refus,
  clés de l'utilisateur)` : au moins une clé d'accès commune **et aucune** clé de refus
  commune. Le refus l'emporte toujours. Elle est utilisée par la recherche plein texte,
  la relecture des passages, l'ouverture des documents et la réouverture des citations.
- Qdrant : champ `deny_keys` indexé, exclu par une condition `must_not` sur les clés de
  l'utilisateur.
- Restent **invisibles pour tous** (fermé par défaut) : un refus visant une identité que
  la source ne permet pas de résoudre, un refus visant tout l'espace, des droits
  incomplets.
- Les droits revérifiés auprès de la source à la question (`check_access`) restent la
  référence quand la source le permet ; les clés sont un pré-filtre.

## Alternatives écartées

- **Garder « invisible pour tous »** : inacceptable fonctionnellement dès le premier coffre.
- **Développer les refus en clés positives** (toutes les personnes du groupe sauf Bruno) :
  explosion du nombre de clés et dépendance à l'état des groupes au moment de l'indexation ;
  un nouvel arrivant dans le groupe ne serait pas couvert sans réindexation.
- **S'en remettre uniquement à la revérification auprès de la source** : impossible pour les
  sources qui ne la permettent pas, et coûteux à chaque question.

## Conséquences

- Migration 0004 : colonne `documents.deny_keys` (vide par défaut), contraintes de format et
  « fermé par défaut » (`acl_status = 'complete' OR deny_keys = '{}'`), vue
  `searchable_chunks` étendue, fonction `urag_doc_visible`.
- Les points Qdrant existants sans `deny_keys` restent visibles normalement (aucun refus).
- Tests : schéma (refus prioritaire, format, fermé par défaut), unitaires (calcul des clés),
  Qdrant (point exclu par un refus), intégration (Bruno exclu, Alice autorisée par le groupe).
