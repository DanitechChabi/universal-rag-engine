# Contrats d'API — Universal RAG Engine

Statut : **contrat de phase 0**. À partir de la phase 1, la description OpenAPI
générée par FastAPI (`/api/v1/openapi.json`) fait foi ; un test vérifie qu'elle
reste conforme à ce document.

---

## 1. Conventions

| Sujet | Règle |
|---|---|
| Préfixe | `/api/v1` ; changement incompatible ⇒ `/api/v2` |
| Format | JSON UTF-8 ; dates ISO 8601 en UTC ; identifiants UUID |
| Authentification | cookie `HttpOnly` (web) ou en-tête `Authorization: Bearer` (Desktop, scripts) |
| Anti-CSRF | en-tête `X-CSRF-Token` obligatoire sur POST, PUT, PATCH, DELETE avec cookie |
| Erreurs | RFC 9457 `application/problem+json` : `type`, `title`, `status`, `detail`, `code` stable (ex. `auth.locked`) — jamais de trace technique ni de donnée d'un autre utilisateur |
| Validation | Pydantic ; champ inconnu ⇒ 422 |
| Pagination | par curseur : `?limit=50&cursor=…` ⇒ `{ "items": [...], "next_cursor": "…" }` ; `limit` ≤ 200 |
| Tri / filtres | paramètres explicites, liste blanche par route |
| Idempotence | en-tête `Idempotency-Key` accepté sur les créations et lancements de tâches |
| Longues opérations | renvoient `202` + identifiant de tâche ; suivi par `/admin/jobs/{id}` |
| Diffusion progressive | `/chat` en Server-Sent Events (`text/event-stream`) |
| Limitation du débit | 429 + `Retry-After` |
| Ressource d'une autre organisation ou non autorisée | **404** (on ne révèle pas son existence), sauf routes d'administration où 403 est explicite |

Rôles : **SA** super_admin · **OA** org_admin · **DA** doc_admin · **U** user ·
**AU** auditor. « Tous » = tout utilisateur authentifié.

---

## 2. Routes

### Authentification

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| POST | `/auth/login` | public | `{login, password}` ⇒ cookies de session + `{user, roles, org}` ; 401 `auth.invalid` (même message pour compte inconnu) ; 423 `auth.locked` |
| POST | `/auth/refresh` | public (jeton de rafraîchissement) | rotation ; réutilisation d'un ancien jeton ⇒ famille révoquée, 401 |
| POST | `/auth/logout` | Tous | révoque la session courante |
| GET | `/auth/me` | Tous | utilisateur, rôles, organisation, politique IA visible (mode, indicateur externe) |
| POST | `/auth/password` | Tous | changement de son mot de passe (ancien requis) ; révoque les autres sessions |

### Utilisateurs, groupes, rôles

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| GET | `/users` | OA, SA | liste paginée, filtre `status`, `q` |
| POST | `/users` | OA, SA | `{login, display_name, email?, roles[], password_temporaire}` ; `super_admin` attribuable seulement par SA |
| GET | `/users/{id}` | OA, SA ; soi-même | — |
| PUT | `/users/{id}` | OA, SA | nom, courriel, rôles, statut ; désactivation ⇒ sessions révoquées |
| DELETE | `/users/{id}` | OA, SA | désactive et anonymise (l'historique d'audit est conservé) |
| GET/POST | `/groups` | OA, SA | — |
| PUT/DELETE | `/groups/{id}` | OA, SA | — |
| PUT | `/groups/{id}/members` | OA, SA | remplace la liste des membres |
| GET/POST | `/users/{id}/links` | OA, SA | liens vers les identités externes (`principal_links`) ; import en lot `POST /principal-links/import` (CSV) |

### Espaces et sources

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| GET/POST | `/spaces` | DA, OA, SA (lecture : Tous pour les espaces accessibles) | — |
| PUT | `/spaces/{id}/grants` | OA, SA | utilisateurs et groupes autorisés |
| GET | `/sources` | DA, OA, SA | statut, dernière synchronisation, nombre de documents, en erreur |
| POST | `/sources` | DA, OA, SA | `{kind, name, space_id, config, credentials?}` ; `credentials` chiffrés, jamais renvoyés |
| GET | `/sources/{id}` | DA, OA, SA | configuration sans secret (`credentials_configured: bool`) |
| PUT | `/sources/{id}` | DA, OA, SA | — |
| DELETE | `/sources/{id}` | DA, OA, SA | retire de l'index (tâche) ; **ne touche jamais la source d'origine** |
| POST | `/sources/{id}/test` | DA, OA, SA | `ConnectionReport` (sans secret) |
| GET | `/sources/{id}/browse?container=` | DA, OA, SA | exploration (classes M-Files, dossiers) |
| POST | `/sources/{id}/sync` | DA, OA, SA | `{mode: "incremental" \| "full"}` ⇒ 202 + tâche |
| POST | `/sources/{id}/disable`, `/enable` | DA, OA, SA | — |

### Identités externes (ADR-0016)

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| GET | `/sources/{id}/identities` | OA | utilisateurs et groupes de la source, appartenances, compte lié et état (`verified`) ; compteurs « à confirmer » et « sans compte » |
| PUT | `/principal-links` | OA | `{user_id, external_principal_id}` ⇒ lien **confirmé** (remplace une proposition) ; un groupe ne se lie pas ; audit `identity.link` |
| POST | `/principal-links/{external_principal_id}/confirm` | OA | confirme une proposition automatique ; audit `identity.confirm` |
| DELETE | `/principal-links/{external_principal_id}` | OA | supprime le lien, effet immédiat ; audit `identity.unlink` |
| POST | `/sources/{id}/principal-links/import` | OA | `{csv}` « login_local;identifiant_externe » ; tout ou rien (une ligne invalide ⇒ 422, rien d'importé) |

Les propositions automatiques (identifiant ou courriel identique, un seul compte possible)
sont créées à la synchronisation et **ne donnent aucun droit** avant confirmation.

### Documents

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| GET | `/documents` | DA, OA, SA | métadonnées et état d'indexation ; filtres source, statut, format, date, classe |
| GET | `/documents/{id}` | DA, OA, SA | métadonnées, versions, erreurs, droits résumés, nombre de fragments — **pas le contenu** |
| POST | `/documents/{id}/reindex` | DA, OA, SA | 202 + tâche |
| POST | `/documents/{id}/exclude`, `/include` | DA, OA, SA | — |
| DELETE | `/documents/{id}/index` | DA, OA, SA | retire de l'index ; le document original n'est jamais supprimé |
| GET | `/documents/{id}/open` | Tous | **revérifie les droits** puis redirige vers la source (lien fourni par le connecteur) ou sert le fichier relu dans la source, sous CSP `sandbox` ; types actifs (HTML…) en téléchargement ; 404 identique pour absent, supprimé ou interdit ; audit `document.open` / `document.open_denied` |
| GET | `/chunks/{id}` | Tous | extrait d'une citation, **droits revérifiés** |

### Recherche et conversations

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| POST | `/search` | U et + | `{query, filters?, limit?}` ⇒ passages autorisés avec score, document, pages (sans génération) |
| POST | `/chat` | U et + | `{conversation_id?, question, filters?, model_id?}` ⇒ flux SSE (§3) |
| POST | `/chat/{message_id}/cancel` | auteur | interrompt la génération |
| GET | `/conversations` | auteur | ses conversations ; `q` : recherche littérale dans les titres et ses propres questions (jamais dans les réponses) |
| GET | `/conversations/{id}` | auteur | messages + citations (droits revérifiés : extrait retiré et réponse masquée, `masked`, si un document cité n'est plus accessible) |
| PATCH | `/conversations/{id}` | auteur | renommer (`{title}`) |
| DELETE | `/conversations/{id}` | auteur | suppression réelle (messages et citations effacés ; audit `conversation.delete`) |
| GET | `/conversations/{id}/export?format=pdf\|docx\|md` | auteur | export |
| POST | `/messages/{id}/feedback` | auteur | `{value: 1 \| -1, comment?}` (signaler une réponse incorrecte) |

`/chat/{id}` du cahier des charges est couvert par `/conversations/{id}`.

### Modèles IA (phase 5)

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| GET | `/admin/ai` | OA | politique, fournisseurs (sans clé : `key_configured`), modèles, plafonds et leur état, consommation du mois |
| PUT | `/admin/ai/policy` | OA | `{mode, allow_external_questions, allow_external_documents, allow_fallback_to_external, notify_user_on_external}` ; incohérence ⇒ 422 ; effet immédiat (scénario 15) |
| POST | `/admin/ai/providers` | OA | `{kind, name, endpoint?, locality?, api_key?}` ; Ollama toujours local, OpenAI et Gemini toujours externes ; clé chiffrée, jamais renvoyée |
| PATCH / DELETE | `/admin/ai/providers/{id}` | OA | nom, adresse, activation, nouvelle clé (l'ancienne est supprimée) |
| POST | `/admin/ai/models` | OA | `{provider_id, name, priority, temperature?, max_output_tokens?, context_window?, max_concurrency?, input_cost_per_mtok?, output_cost_per_mtok?}` |
| PATCH / DELETE | `/admin/ai/models/{id}` | OA | — |
| POST | `/admin/ai/models/{id}/test` | OA | test de disponibilité sans envoi de contenu ; un modèle n'est proposé qu'après un test réussi |
| PUT | `/admin/ai/limits` | OA | plafonds de consommation **externe** par jour et par mois (jetons ou coût estimé), alerte à 80 %, coupure de l'externe au dépassement |
| GET | `/models` | U et + | modèles que l'utilisateur peut choisir maintenant (politique et plafonds appliqués) ; `external_blocked_by_limit`, `notify_on_external` (scénario 14) |

Le chat accepte `model_id` : s'il n'est plus autorisé, le modèle autorisé de plus haute priorité répond.

### Administration et exploitation

| Méthode | Route | Rôles | Contrat |
|---|---|---|---|
| GET | `/admin/health` | public restreint (réseau local) : `{status}` ; OA, SA : détail par service | état de PostgreSQL, Qdrant, Ollama, connecteurs, worker |
| GET | `/admin/metrics` | OA, SA | indicateurs du tableau de bord (section 15) ; `/metrics` Prometheus sur le réseau interne |
| GET | `/admin/dashboard` | OA, SA, DA | chiffres de la section 10.3 |
| GET | `/admin/audit` | AU, OA, SA | journal filtré, paginé, exportable |
| GET | `/admin/jobs`, `/admin/jobs/{id}` | DA, OA, SA | file de tâches, progression |
| POST | `/admin/jobs/{id}/retry`, `/cancel` | DA, OA, SA | — |
| GET/PUT | `/admin/settings` | OA, SA | paramètres RAG (découpage, recherche, conservation) |
| POST | `/admin/backup` | OA, SA | 202 + tâche |
| GET | `/admin/backups` | OA, SA | historique |
| POST | `/admin/restore` | SA | restauration depuis une sauvegarde vérifiée ; procédure en deux étapes (préparer, confirmer) |
| GET/POST | `/admin/license` | SA (écriture), OA (lecture) | état, import d'un fichier de licence signé |
| GET/POST | `/admin/organizations` | SA | gestion des organisations (masquée dans l'interface du MVP) |

---

## 3. Flux `/chat` (Server-Sent Events)

Ordre des évènements :

```
event: meta        data: {"message_id": "...", "conversation_id": "...",
                          "model": {"id": "...", "name": "qwen3:8b", "locality": "local"}}
event: sources     data: {"candidates": 12}                 # nombre de passages autorisés retenus
event: token       data: {"text": "Le loyer mensuel est "}  # répété
event: citations   data: {"items": [{"rank": 1, "document_id": "...", "title": "Contrat de bail 2024",
                          "source": "Coffre M-Files", "pages": [3, 3], "excerpt": "...",
                          "version": "5", "open_url": "/api/v1/documents/…/open"}]}
event: done        data: {"insufficient": false, "tokens_in": 3120, "tokens_out": 210,
                          "removed_citations": 0}
```

- Si la politique impose de prévenir avant un appel externe, un évènement
  `external_notice` est envoyé avant tout `token`.
- `error` (problem+json) peut survenir à tout moment ; la génération est alors
  arrêtée proprement.
- Les citations ne sont envoyées qu'**après** validation : seules les références
  correspondant à un passage fourni sont conservées (`removed_citations` compte
  les références écartées).

---

## 4. Tests de contrat prévus

- Matrice **rôle × route** générée depuis les tableaux ci-dessus : chaque route est
  appelée avec chaque rôle ; le code attendu (200/403/404) est vérifié.
- Toute route sur un identifiant est testée avec un identifiant d'une autre
  organisation ⇒ 404.
- Aucune réponse ne contient de champ `password`, `password_hash`, `api_key`,
  `ciphertext`, `credentials` (vérification automatique sur toutes les réponses
  des tests).
