# ADR-0005 — Répartition PostgreSQL / Qdrant

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Le texte des fragments, les métadonnées et les droits doivent rester cohérents ; Qdrant doit permettre l'isolation des organisations et la gestion des versions d'embedding (sections 7.1, 9.6, 13.2).

## Décision

- **PostgreSQL = source de vérité** : documents, versions, texte des fragments, droits.
- **Qdrant** : vecteurs + copie des champs de filtre (`org_id`, `access_keys`, identifiants, classe, date…), **sans texte**.
- Une collection Qdrant **par profil d'embedding** ; isolation par organisation via le champ `org_id` indexé en mode locataire (`is_tenant`), filtre **obligatoire** ajouté par la couche `storage` (aucune requête Qdrant possible sans).
- Les passages trouvés sont relus dans la vue `searchable_chunks`, qui revérifie version courante, suppression et droits.
- Accès base : SQLAlchemy 2 (cœur, requêtes explicites) ; migrations Alembic.

## Alternatives écartées

Texte dans Qdrant (duplication, deux sources de vérité) ; une collection par organisation (lourd à gérer, mauvais pour beaucoup de petites organisations).

## Conséquences

Qdrant peut être reconstruit depuis PostgreSQL ; un retard de Qdrant ne peut qu'exclure un résultat, jamais exposer un document non autorisé.
