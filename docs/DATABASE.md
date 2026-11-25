# Base de données — Universal RAG Engine

Statut : **schéma de référence de phase 0, testé** sur PostgreSQL 16
(`database/tests/test_schema.sh`, 39 vérifications). À partir de la phase 1, les
migrations Alembic devront produire exactement ce schéma.

- Schéma : `database/schemas/schema.sql`
- Rôles PostgreSQL : `database/schemas/roles.sql`
- Tests : `database/tests/test_schema.sql`

Version minimale : **PostgreSQL 15** (utilise `UNIQUE NULLS NOT DISTINCT`,
`ON DELETE SET NULL (colonne)`, vues `security_invoker`). Cible : PostgreSQL 16.

---

## 1. Principes

1. **Isolation par organisation à trois niveaux**
   - chaque table métier a une colonne `org_id` ;
   - les liens entre tables passent par des **clés étrangères composites**
     `(org_id, id)` : il est impossible de rattacher un objet d'une organisation à
     un objet d'une autre, même par erreur de code ;
   - **Row Level Security forcée** : l'application fixe `SET LOCAL urag.org_id`
     au début de chaque transaction ; sans cette valeur, aucune ligne n'est visible
     ni modifiable.
2. **Fermé par défaut** : un document n'est visible que si ses droits sont
   complets (`acl_status = 'complete'`) et qu'au moins une de ses clés d'accès
   correspond à l'utilisateur. Une contrainte interdit des clés d'accès sur un
   document aux droits incertains.
3. **PostgreSQL est la source de vérité.** Qdrant ne contient que des vecteurs et
   des copies des champs de filtre ; il peut être reconstruit depuis PostgreSQL.
4. **Idempotence** : `(source_id, external_id)` unique pour les documents,
   `(document_id, sha256, embedding_profile_id)` unique pour les versions,
   `dedup_key` unique pour les tâches actives.
5. **Aucun secret en clair** : les identifiants sont dans `secrets` (chiffrés) ;
   une contrainte refuse les clés `password`, `api_key`, `token`, `secret` dans la
   configuration d'une source.

---

## 2. Rôles PostgreSQL

| Rôle | Connexion | RLS | Usage |
|---|---|---|---|
| `urag_owner` | non | — | Propriétaire du schéma ; utilisé par les migrations |
| `urag_app` | oui | **soumis** | api et worker ; ne peut ni modifier ni supprimer l'audit, ni créer d'organisation |
| `urag_auth` | non | contourne | Propriétaire de la seule fonction `urag_auth_lookup` (connexion) |
| `urag_maintenance` | non | contourne | Sauvegarde, création d'organisations, purge de l'audit (`urag_audit_purge`, au moins 30 jours) |

---

## 3. Tables

### Identité et accès

| Table | Rôle |
|---|---|
| `organizations` | Organisations (une seule dans l'interface du MVP, ADR-0015) |
| `users` | Comptes ; identifiant de connexion unique sur l'installation ; mot de passe Argon2id ; verrouillage après échecs |
| `user_roles` | Rôles : `super_admin`, `org_admin`, `doc_admin`, `user`, `auditor` (cumulables) |
| `groups`, `group_members` | Groupes locaux |
| `sessions` | Jetons de rafraîchissement (hachés), famille de rotation, révocation |
| `secrets` | Secrets chiffrés AES-256-GCM (nonce, version de clé) |

### Espaces, sources et identités externes

| Table | Rôle |
|---|---|
| `spaces`, `space_grants` | Espaces documentaires et qui peut les interroger (utilisateur ou groupe) |
| `sources` | Connexions (dossier local, coffre M-Files) : configuration non secrète, curseur de synchronisation, revérification possible des droits |
| `external_principals` | Utilisateurs et groupes de la source (ex. M-Files) |
| `external_group_members` | Appartenance aux groupes externes, synchronisée depuis la source |
| `principal_links` | Correspondance compte local ↔ utilisateur externe (ADR-0016) |

### Documents et index

| Table | Rôle |
|---|---|
| `documents` | Métadonnées normalisées (section 5.2 du cahier des charges), `metadata` (métier), `source_metadata` (propre à la GED), `access_keys`, `acl_status`, statut d'indexation |
| `document_versions` | Une ligne par version indexée : empreinte, profil d'embedding, extracteur, OCR et confiance, avertissements, erreurs ; traçabilité des versions remplacées |
| `chunks` | Texte des fragments, pages, titres englobants, type (texte, tableau, liste, OCR), vecteur plein texte généré (français sans accents ou anglais) |
| `searchable_chunks` (vue) | Fragments interrogeables : version courante, document non supprimé, non exclu, droits complets, indexé |
| `embedding_profiles` | Modèle, révision, dimension, collection Qdrant ; un seul profil actif (section 9.6) |

### Conversations

| Table | Rôle |
|---|---|
| `conversations`, `messages` | Historique ; modèle utilisé, local ou distant, tokens, latence, « réponse insuffisante », avis de l'utilisateur |
| `citations` | Citation numérotée : fragment, document, version, pages, copie de l'extrait |

### IA

| Table | Rôle |
|---|---|
| `ai_providers` | Fournisseurs ; **désactivés par défaut** ; la localité est vérifiée (Ollama = local ; Claude, Gemini, OpenAI = externe) |
| `ai_models` | Configuration par modèle (section 9.4) + coûts unitaires |
| `ai_policies` | Mode `local_only` (défaut), `hybrid`, `cloud_allowed` ; des contraintes empêchent une politique incohérente |
| `usage_records`, `usage_limits` | Consommation et limites par utilisateur ou organisation |

### Exploitation

| Table | Rôle |
|---|---|
| `jobs` | File de tâches (ADR-0003) : priorité, reprises, battement de cœur, annulation, progression |
| `audit_log` | Journal d'audit **en ajout seul** (droits + déclencheur) |
| `licenses` | Licences signées Ed25519 |
| `settings` | Paramètres par organisation (paramètres RAG, conservation…) |
| `backups` | Historique des sauvegardes et vérifications |

---

## 4. Clés d'accès

`urag_user_access_keys(user_id)` renvoie l'ensemble des clés d'un utilisateur actif
de l'organisation courante :

| Clé | Origine |
|---|---|
| `u:<user_id>` | l'utilisateur |
| `g:<group_id>` | ses groupes locaux |
| `sp:<space_id>` | les espaces accordés à lui ou à ses groupes |
| `xu:<external_principal_id>` | ses identités externes liées |
| `xg:<external_principal_id>` | les groupes externes de ces identités |

Un fragment est interrogeable par l'utilisateur si
`searchable_chunks.access_keys && urag_user_access_keys(user)`. Les mêmes clés
sont copiées dans les points Qdrant pour filtrer la recherche vectorielle.

Les clés sont **recalculées à chaque question** : un retrait de groupe, la
désactivation d'un compte ou la suppression d'un lien prennent effet
immédiatement (tests 9 du schéma).

---

## 5. Correspondance avec Qdrant

Une collection par profil d'embedding (`embedding_profiles.collection_name`), indexée
**par organisation** : `hnsw_config = {m: 0, payload_m: 16}`, pas de graphe global (ADR-0019).
Chaque point a pour identifiant `chunks.id` et pour charge utile :

| Champ | Index Qdrant | Rôle |
|---|---|---|
| `org_id` | `keyword`, `is_tenant` | isolation (filtre obligatoire) |
| `access_keys` | `keyword` | filtre de sécurité |
| `document_id`, `version_id`, `source_id`, `space_id` | `keyword` | filtres et invalidation |
| `doc_class`, `mime_type`, `author` | `keyword` | filtres documentaires |
| `modified_at` | `datetime` | filtre par date |
| `language` | `keyword` | — |

Pas de texte dans Qdrant : les passages sont relus dans PostgreSQL via la vue
`searchable_chunks`, ce qui **revérifie** version courante, suppression et droits
même si Qdrant est en retard.

Quand les droits d'un document changent, la mise à jour de `documents.access_keys`
et de la charge utile Qdrant (`set_payload` filtré par `document_id`) se fait dans
la même tâche ; la vérification dans PostgreSQL garantit qu'un retard de Qdrant
ne peut qu'**exclure** un résultat, jamais en exposer un.

---

## 6. Évolutions prévues

- Partitionnement de `audit_log` et `usage_records` par mois si le volume l'exige.
- Index HNSW de Qdrant : réglé par organisation en phase 2 (ADR-0019) ; à revoir sur un coffre
  réel aux droits très fragmentés.
- Colonnes LDAP / Active Directory dans `users` (identifiant d'annuaire) quand
  l'authentification externe sera ajoutée.
