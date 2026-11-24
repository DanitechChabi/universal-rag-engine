# Sécurité — Universal RAG Engine

Statut : **règles de conception de phase 0**. Chaque règle est associée à un test
(colonne « Preuve ») ; une règle sans test n'est pas considérée comme respectée
(cahier des charges, section 21 : « aucun critère de sécurité validé sur la seule
base d'une démonstration »).

---

## 1. Menaces prises en compte

| Menace | Exemple | Parade principale |
|---|---|---|
| Fuite entre organisations | un bogue oublie le filtre `org_id` | RLS forcée + clés étrangères composites + filtre Qdrant obligatoire |
| Fuite entre utilisateurs | un collaborateur obtient l'extrait d'un contrat qu'il ne peut pas ouvrir dans M-Files | clés d'accès filtrées **avant** classement + revérification auprès de la source |
| Droits périmés | droit retiré dans M-Files, encore présent dans l'index | resynchronisation des droits + vérification tardive + fermé si doute |
| Escalade de privilèges | un utilisateur appelle une route d'administration | contrôle de rôle sur chaque route, tests systématiques |
| Vol de session | jeton volé | jeton d'accès court, rafraîchissement rotatif avec détection de réutilisation, cookies `HttpOnly` |
| Force brute | essais répétés de mots de passe | verrouillage progressif, limitation du débit, audit |
| Vol de secrets | clé d'API lue en base ou dans les journaux | chiffrement AES-256-GCM, clé maîtresse hors base, secrets jamais renvoyés au frontend ni journalisés |
| Injection de prompt | un document contient « ignore tes instructions et… » | aucun outil pour le modèle, extraits encadrés comme données, citations vérifiées, rendu assaini |
| Exfiltration par la réponse | la réponse contient une image externe qui transmet des données | rendu Markdown sans images ni liens externes générés |
| Envoi non autorisé au cloud | bascule automatique vers une API externe | politique appliquée dans le routeur ; aucune bascule si interdite |
| Injection SQL / entrées | paramètres malveillants | requêtes paramétrées uniquement, validation Pydantic |
| Altération de l'audit | effacement de traces | journal en ajout seul (droits + déclencheur) |

---

## 2. Contrôle d'accès

### 2.1 Rôles (RBAC)

| Action | super_admin | org_admin | doc_admin | user | auditor |
|---|---|---|---|---|---|
| Gérer les organisations, licences | ✔ | | | | |
| Gérer utilisateurs, groupes, rôles de l'organisation | ✔ | ✔ | | | |
| Gérer modèles IA et politique | ✔ | ✔ | | | |
| Gérer espaces, sources, indexation, erreurs | ✔ | ✔ | ✔ | | |
| Poser des questions, gérer **ses** conversations | ✔ | ✔ | ✔ | ✔ | |
| Consulter l'audit et l'activité | ✔ | ✔ | | | ✔ |
| Sauvegarder / restaurer | ✔ | ✔ | | | |

Un rôle d'administration **ne donne pas accès au contenu des documents** : un
`org_admin` ne voit dans les réponses que les documents auxquels ses propres clés
d'accès donnent droit. Un administrateur peut voir les métadonnées et l'état
d'indexation des documents (écran Documents), pas leur contenu.

### 2.2 Droits documentaires (ACL)

- Chaque document porte des **clés d'accès** (`docs/DATABASE.md` §4).
- **Fichiers locaux** : pas de droits propres. Les documents reçoivent la clé
  `sp:<espace>` **seulement si** la source est configurée pour hériter de
  l'espace (`inherit_space_access`). Par défaut : aucune clé, document invisible
  jusqu'à décision de l'administrateur.
- **M-Files** : les droits sont lus depuis la source et traduits en clés
  `xu:` / `xg:`. Si une partie des droits ne peut pas être traduite fidèlement
  (permission dépendant de métadonnées non résolue, refus explicite, objet
  inaccessible au compte technique), le document passe en `acl_status =
  'uncertain'` : **aucune clé, invisible**, et apparaît dans le rapport d'erreurs.
- Les refus explicites (deny) de la source sont résolus à l'indexation : si un
  refus ne peut pas être représenté par des clés positives, le document est
  marqué incertain.

### 2.3 Ordre des contrôles à chaque question

1. Authentification (jeton valide, compte actif, non verrouillé).
2. Organisation courante fixée dans la transaction (`urag.org_id`).
3. Clés d'accès **recalculées** (`urag_user_access_keys`).
4. Recherche Qdrant **avec** filtre `org_id` + `access_keys` + filtres demandés.
5. Recherche lexicale PostgreSQL sur `searchable_chunks` **avec** les mêmes filtres.
6. Relecture des passages dans `searchable_chunks` (revérifie version courante,
   suppression, droits) — un retard de Qdrant ne peut qu'exclure.
7. Pour les sources qui le permettent (`supports_late_check`), **vérification
   tardive** auprès de la source pour les documents retenus. Source injoignable ⇒
   documents exclus (paramétrable par l'administrateur en connaissance de cause).
8. Reranking et génération sur les seuls passages restants.
9. Consultation d'une ancienne conversation : les citations sont affichées, mais
   l'ouverture d'un extrait ou du document **revérifie** les droits actuels.

### 2.4 Cache

Aucun cache de résultats partagé entre utilisateurs. Clé de cache des résultats :
`(org_id, user_id, hachage des clés d'accès, requête, filtres, version de l'index)`.
Un changement de droits change le hachage des clés et invalide le cache.

---

## 3. Authentification et sessions (ADR-0011)

- Mots de passe : **Argon2id** (paramètres OWASP en vigueur), longueur minimale 12,
  comparaison en temps constant.
- Jeton d'accès signé, durée **15 minutes** ; jeton de rafraîchissement opaque,
  **haché** en base, durée 12 heures (paramétrable), **rotation à chaque usage** ;
  la réutilisation d'un ancien jeton révoque toute la famille de sessions.
- Web : cookies `HttpOnly`, `Secure`, `SameSite=Strict` + jeton anti-CSRF pour les
  requêtes qui modifient. Desktop : API liée à `127.0.0.1` avec un secret de
  démarrage partagé entre Tauri et le service local.
- Verrouillage : 5 échecs ⇒ 1 min, puis durée doublée à chaque série (max. 1 h) ;
  message d'erreur identique pour compte inconnu et mauvais mot de passe.
- Comptes désactivés : refus immédiat, sessions révoquées.
- LDAP / Active Directory : interface prévue (ADR-0016), implémentation après le MVP.

---

## 4. Secrets (ADR-0012)

- Chiffrement **AES-256-GCM** avec un nonce aléatoire de 12 octets par secret ;
  l'identifiant du secret et l'organisation sont liés comme données authentifiées.
- **Clé maîtresse hors base** : fichier lisible par le seul compte du service
  (Server), ou coffre du système (Desktop : Windows DPAPI). Jamais dans Git, jamais
  dans les sauvegardes de la base (sauvegardée à part, voir `DEPLOYMENT.md`).
- Rotation : `key_version` ; une tâche rechiffre les secrets avec la nouvelle clé.
- Les secrets ne sont **jamais** renvoyés par l'API (seulement « configuré : oui /
  non » et la date), jamais journalisés, jamais placés dans le contexte du modèle.
- Contrôle avant chaque commit : analyse automatique des secrets (gitleaks) dans
  l'intégration continue et en crochet local.

---

## 5. IA et confidentialité

- Politique par organisation (`ai_policies`) : `local_only` par défaut.
- Le routeur distingue trois types de données : **question**, **extraits
  documentaires**, **historique de conversation**. Chaque appel externe est
  autorisé ou refusé **par type**.
- **Jamais de bascule vers un fournisseur externe** si la politique ne l'autorise
  pas explicitement (`allow_fallback_to_external`), y compris en cas de panne du
  modèle local : l'utilisateur reçoit une erreur claire.
- Si un appel externe est fait et que `notify_user_on_external` est actif,
  l'interface l'indique avant l'envoi (ou affiche un indicateur permanent selon
  la politique).
- Chaque appel externe est journalisé (`ai.external_call` : fournisseur, modèle,
  tokens, coût) sans le contenu.

---

## 6. Injection de prompt

Le contenu des documents est **toujours** une donnée non fiable.

1. **Aucun outil, aucune action** n'est donné au modèle dans le MVP : il ne peut
   qu'écrire du texte. Le pire effet d'un document piégé est une réponse fausse.
2. Les instructions du système et les extraits sont séparés : extraits placés dans
   un bloc délimité, avec identifiants `[1]…[n]`, précédés d'un rappel que ce bloc
   est une donnée à citer et non des instructions. Les délimiteurs présents dans
   le texte des documents sont neutralisés.
3. Les clés d'API, la configuration et les données d'autres utilisateurs ne sont
   **jamais** dans le contexte : le modèle ne peut pas les révéler.
4. **Citations vérifiées** : seules les références `[n]` correspondant à un extrait
   réellement fourni sont conservées ; numéros de page et noms de documents
   viennent de la base, jamais du texte généré.
5. **Rendu assaini** dans l'interface : Markdown sans HTML brut, sans images, et
   sans liens externes générés par le modèle (seuls les liens de citation construits
   par l'application sont cliquables).
6. Jeu de tests d'injection (`docs/TESTING.md` §5) exécuté à chaque version.

---

## 7. Journal d'audit

Événements enregistrés (section 12.5 du cahier des charges) : connexions,
déconnexions, échecs, création et modification d'utilisateurs et de rôles, ajout et
suppression de sources, synchronisations, consultations documentaires (ouverture
d'un document ou d'un extrait), requêtes IA (sans le texte par défaut),
utilisation d'API externes, modifications de paramètres, sauvegardes et
restaurations.

- **Jamais** de contenu documentaire (réponses, extraits), de mot de passe ou de secret dans `details`.
- Le **texte des questions est journalisé par défaut** (décision Q5), désactivable
  par organisation. Une question peut contenir des informations sensibles : la
  lecture du journal est réservée aux rôles `auditor`, `org_admin` et
  `super_admin`, et les questions sont purgées avec le journal (12 mois par défaut).
- Ajout seul ; purge uniquement par le rôle de maintenance, au-delà d'une durée
  de conservation configurable : **12 mois par défaut** (minimum 30 jours).
- Conversations : conservées **12 mois par défaut**, durée réglable par organisation.

---

## 8. Communications et exposition

- Server : HTTPS obligatoire sur le réseau local (Caddy, certificat de l'entreprise
  ou autorité interne) ; PostgreSQL, Qdrant et Ollama **non exposés** hors du
  réseau interne Docker.
- Qdrant protégé par clé d'API même en réseau interne.
- En-têtes de sécurité (CSP stricte, `X-Content-Type-Options`, `Referrer-Policy`).
- Limitation du débit par utilisateur et par adresse sur la connexion et `/chat`.
- Desktop : aucun port en écoute hors `127.0.0.1`.

---

## 9. Fichiers temporaires

Les fichiers téléchargés pour l'extraction sont écrits dans un dossier propre au
service (droits restreints), supprimés dès la fin de la tâche, et purgés au
démarrage en cas d'arrêt brutal.

---

## 10. Correspondance avec les tests

| Règle | Preuve |
|---|---|
| Isolation des organisations | `database/tests/test_schema.sql` tests 1, 3, 4, 14 (fait) ; tests API et Qdrant (phase 1) |
| Fermé par défaut | test_schema 5, 8 (fait) ; tests connecteurs (phase 3) |
| Révocation immédiate | test_schema 9 (fait) ; scénario 12-13 de recette (phase 3) |
| Audit en ajout seul | test_schema 11, 15 (fait) |
| Politique IA locale par défaut | test_schema 12 (fait) ; tests du routeur (phase 5) |
| Rôles sur chaque route | tests de matrice RBAC générés depuis le tableau §2.1 (phase 1 et 4) |
| Injection de prompt | corpus d'injection (phase 1, puis chaque version) |
| Secrets jamais exposés | tests API + recherche de secrets dans les réponses et journaux (phase 5) |
