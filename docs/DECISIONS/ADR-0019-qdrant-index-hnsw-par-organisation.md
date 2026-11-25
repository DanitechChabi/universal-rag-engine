# ADR-0019 — Qdrant : un index HNSW par organisation, pas de graphe global

- Statut : **acceptée** (phase 2, novembre 2026)
- Complète : ADR-0005 (répartition PostgreSQL / Qdrant)
- Références : documentation officielle Qdrant, guide « Multitenancy » (réglages `payload_m` et `m: 0`
  avec un champ `is_tenant`) ; docs/DATABASE.md §5

## Contexte

La mesure finale de la phase 2 a été moins bonne que la mesure intermédiaire (Gemini : 67,5 % de
réponses exactes et bien citées contre 77,5 %), alors que les fragments concernés étaient presque
identiques (seuls des retours à la ligne différaient). L'analyse a montré que :

- le vecteur stocké de chaque fragment est correct (cosinus 0,96 avec un recalcul, écart dû à la
  quantification int8) ;
- en recherche **exacte**, le bon fragment est au rang 1 ;
- en recherche **approximative** (HNSW, réglage par défaut de Qdrant), il passe au-delà du rang 30
  dès que la collection contient une **deuxième organisation**.

Cause : avec le réglage par défaut, Qdrant construit un seul graphe pour toute la collection. Une
recherche filtrée sur une organisation qui ne représente qu'une partie des points parcourt ce graphe
global et en perd une partie. C'est exactement la situation du produit : une collection par profil
d'embedding, partagée par toutes les organisations (ADR-0005).

| Question (corpus public) | Rang du bon fragment, graphe global | Recherche exacte | Graphe par organisation |
|---|---|---|---|
| Q31 (nombre de réponses à la consultation du FSB) | au-delà de 30 | 1 | 1 |
| Q24 (seuil de déclaration à la CENTIF) | au-delà de 30 | 1 | 1 |
| Q20 (part de l'épargne des femmes) | 6 et 10 | 6 et 11 | 6 et 11 |

## Décision

- Les collections sont créées avec `hnsw_config = {m: 0, payload_m: 16}` : pas de graphe global, un
  graphe par valeur du champ locataire `org_id` (déjà indexé avec `is_tenant`).
- Toute recherche passe déjà par le filtre `org_id` obligatoire (couche `storage`) : l'absence de
  graphe global ne prive d'aucune requête légitime.
- `VectorStore.ensure_collection` met à jour une collection existante créée avec l'ancien réglage
  (`update_collection`) ; Qdrant reconstruit alors les index en arrière-plan.

## Alternatives écartées

- **Recherche exacte systématique** : rappel parfait mais coût linéaire en nombre de points, inadapté
  à 500 000 documents (décision Q6).
- **Augmenter `hnsw_ef` ou réévaluer (rescore)** : testé, sans effet ; le défaut vient de la
  structure du graphe, pas de la précision de la recherche.
- **Une collection par organisation** : isolation plus forte mais multiplie les collections et les
  migrations de profil d'embedding ; le guide Qdrant la déconseille au-delà de quelques locataires.

## Conséquences

- Le rappel ne dépend plus du nombre d'organisations présentes dans la collection.
- Un filtre supplémentaire à l'intérieur d'une organisation (`access_keys`, source, classe) reste
  géré par les index de charge utile ; à surveiller sur un coffre réel avec des droits très
  fragmentés (phase 3).
- Test : `tests/integration/test_vectors.py` (réglage à la création, migration d'une collection
  existante, recherche limitée à l'organisation). Le rappel lui-même est vérifié par la mesure
  `eval/run_eval.py`.
