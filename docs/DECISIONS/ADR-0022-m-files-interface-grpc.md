# ADR-0022 — M-Files : interface de programmation retenue (étude documentaire)

- Statut : **proposée** — à confirmer sur un coffre de test (décision Q8 : aucun coffre disponible)
- Complète : docs/CONNECTORS.md §4 (étape 2 du plan de développement)
- Règle appliquée : aucune interface ni méthode M-Files n'est supposée ; chaque fait ci-dessous
  vient d'une page officielle de developer.m-files.com, lue le 25 novembre 2026.

## Contexte

Le connecteur M-Files doit : lister les documents d'un coffre et leurs versions, télécharger
les fichiers, **lire les droits de chaque objet**, lister **les utilisateurs, les groupes et
leurs membres**, détecter les changements, et si possible revérifier les droits d'un
utilisateur au moment de la question. Les droits sont le point le plus difficile du projet
(AUDIT_FAISABILITE.md §5.1).

## Faits établis (documentation officielle)

| Besoin | API REST (M-Files Web Service) | API gRPC |
|---|---|---|
| Recommandation de l'éditeur | « For new development, use the gRPC API » [1] | interface « complete and direct » du serveur [1] |
| Hors Windows (service Python) | oui, HTTP(S) [2] | oui ; démarrage rapide Python, paquet `mfiles-grpc` [6] |
| Authentification | jeton `POST /REST/server/authenticationtokens`, OAuth [3] | `IRPCLogin.LogIn` : compte M-Files, Windows, OAuth/OIDC (Login Service) [7] |
| Recherche, objets supprimés | `GET /REST/objects`, `d=include` [4] | `IRPCSearch.SearchObjects`, condition « supprimé » [6] |
| Changements | pas de filtre par date de modification documenté [4] | tri sur la propriété 21 « Last modified » [6] |
| Téléchargement de fichiers | `GET /REST/objects/(type)/(id)/(version)/files/(file)/content` [5] | `DownloadFile_Begin` / `_ReadBlock` / `_Stop` [1] |
| **Droits d'un objet** | **aucune ressource documentée** [5] | `IRPCObjectOperations.GetSecurity`, ACL nommées `IRPCNamedACLs.GetNamedACLs` [8] |
| **Utilisateurs, groupes, membres** | **aucune ressource documentée** [5] | `IRPCUsersAdmin`, `IRPCUserGroupsAdmin` (services d'administration) [9] |
| Pseudo-utilisateurs (droits dépendant des métadonnées) | non trouvé | décrits (ex. l'utilisateur de la propriété « Owner ») [8] |
| Refus explicite | non trouvé | **non trouvé** dans les pages lues [8] |
| Droits effectifs d'un *autre* utilisateur | non trouvé | `GetEffectivePermissions` et `CheckAccess` existent, mais la page ne dit pas s'ils acceptent un utilisateur donné [8] |
| Version minimale du serveur | — | non trouvée ; méthode absente ⇒ réponse `UNIMPLEMENTED` [10] |

## Décision proposée

- **API gRPC** pour le connecteur : c'est la recommandation de l'éditeur et la seule des deux
  interfaces dont la documentation couvre les droits des objets et les utilisateurs et
  groupes. L'API REST ne suffit pas au besoin principal (droits).
- Compte technique en **lecture**, avec les droits d'administration strictement nécessaires
  pour lire utilisateurs et groupes (services `*Admin`) — à valider avec l'administrateur
  du coffre.
- Tant que les points ci-dessous ne sont pas vérifiés sur un coffre : connecteur **non
  implémenté**, aucune méthode supposée ; le cœur est testé avec la source simulée
  (CONNECTORS.md §2.5).

## À vérifier avant toute implémentation

1. **Licence du paquet `mfiles-grpc`** (règle du projet : aucune dépendance AGPL/SSPL) et
   conditions d'utilisation de l'API : non trouvées dans les pages lues.
2. Représentation des **refus explicites** et des pseudo-utilisateurs dans la réponse de
   `GetSecurity`, et correspondance avec les clés d'accès et de refus (ADR-0020).
3. `GetEffectivePermissions` / `CheckAccess` pour **un autre utilisateur** que le compte
   technique : sinon, pas de revérification à la question (`late_check = False`) et
   resynchronisation des droits plus fréquente.
4. Moyen fiable de détecter les **changements de droits** (une modification de droits
   change-t-elle « Last modified » ?) : sinon, synchronisation complète de contrôle.
5. Version de M-Files Server du premier client, mode d'authentification (SSO ou non),
   port gRPC ouvert (7766 par défaut sur site [11]).

## Alternatives écartées

- **API REST seule** : pas de droits ni d'utilisateurs documentés ; on ne peut pas appliquer
  les droits M-Files, condition non négociable du projet.
- **API COM / .NET** : « Can only be run on Windows » [1] ; imposerait un service Windows.
- **Vault Application Framework** : s'exécute dans M-Files, pas une intégration externe [1].

## Sources

[1] https://developer.m-files.com/APIs/ — [2] https://developer.m-files.com/APIs/REST-API/ —
[3] https://developer.m-files.com/APIs/REST-API/Authentication/ —
[4] https://developer.m-files.com/APIs/REST-API/Searching/ et /Paging-And-Sorting/ —
[5] https://developer.m-files.com/APIs/REST-API/Reference/resources/ et sous-pages objects —
[6] https://developer.m-files.com/APIs/gRPC-API/guides/quickstart-python/ —
[7] https://developer.m-files.com/APIs/gRPC-API/runtime/authentication/ —
[8] https://developer.m-files.com/APIs/gRPC-API/concepts/permissions/ —
[9] https://developer.m-files.com/APIs/gRPC-API/admin/ —
[10] https://developer.m-files.com/APIs/gRPC-API/runtime/versioning/ —
[11] https://developer.m-files.com/APIs/gRPC-API/runtime/connecting/
