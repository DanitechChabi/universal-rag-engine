# Revue de sécurité — début de la phase 8

Date : novembre 2026. Branche : `claude/phase-8-licences-securite` (empilée sur la phase 7).
Périmètre : tout le code livré (API, worker, cœur, connecteurs, interface, déploiement Server).
Méthode : lecture du code route par route, recherche ciblée (SQL construit, rendu HTML, archives,
secrets), vérification des vulnérabilités connues des dépendances. Ce n'est pas un test
d'intrusion externe, qui reste à faire avant la première installation pilote.

## 1. Défauts trouvés et corrigés

| # | Gravité | Défaut | Correctif | Preuve |
|---|---|---|---|---|
| 1 | **Élevée** | Un **administrateur documentaire** pouvait déclarer une source « fichiers locaux » sur n'importe quel dossier lisible par le service (`/`, clé maîtresse, modèles, dossier d'une autre organisation) et en faire indexer le contenu, puis le lire par la recherche | Dossiers autorisés fixés par l'installation (`URAG_LOCAL_FILES_ALLOWED_ROOTS`, `/documents` en Server), contrôlés par le connecteur à chaque usage (API et worker), liens symboliques résolus ; fermé par défaut (ADR-0026) | `test_phase8` 01 ; `test_local_files` (3 tests) |
| 2 | Moyenne | Des essais de mot de passe **envoyés en parallèle** lisaient tous le même compteur : le blocage après 5 échecs se contournait | Ligne du compte verrouillée pendant la vérification ; pas de vérification pendant le blocage | `test_phase8` 02 (12 essais simultanés : 5 comptés, 7 bloqués) |
| 3 | Moyenne | **Aucune limite par adresse** (essai d'un même mot de passe sur de nombreux comptes), alors que `SECURITY.md` l'annonçait | 20 échecs en 15 min par adresse, tous comptes confondus, puis 429 + `Retry-After` ; compté en base (migration 0010) | `test_phase8` 05, test du schéma |
| 4 | Moyenne | **Bombe de décompression** : un DOCX/XLSX/PPTX de quelques Ko se décompressant en Go épuisait la mémoire du worker, à chaque nouvel essai | Taille décompressée et taux de compression contrôlés avant ouverture ; document « exclu » avec la raison | `test_charge` (64 Mo de zéros dans 64 Ko : refusé) |
| 5 | Faible | Un administrateur d'organisation pouvait **désactiver ou rétrograder le super-administrateur** | Compte protégé (403 `user.protected`) ; le rôle `super_admin` n'est jamais retiré par cet écran | `test_phase8` 04 |
| 6 | Faible | La déconnexion n'effaçait pas les cookies (chemins différents de ceux de la création) ; sans gravité, la session étant révoquée côté serveur | Mêmes chemins et attributs | `test_phase8` 03 |
| 7 | Faible | Le gestionnaire d'erreurs perdait les en-têtes (`Retry-After`) ; l'écran de connexion affichait « mot de passe incorrect » pour un compte verrouillé | En-têtes conservés ; messages distincts (verrouillage, trop d'essais) | `test_phase8` 05, Playwright |

## 2. Points vérifiés sans défaut

| Domaine | Constat |
|---|---|
| Injection SQL | Toutes les requêtes sont paramétrées ; les rares fragments interpolés sont des noms de colonnes ou de tables fixes (jamais une saisie) |
| XSS | Aucun rendu HTML brut dans l'interface (React échappe tout) ; CSP stricte servie par Caddy ; documents ouverts dans un bac à sable (`Content-Security-Policy: sandbox`), HTML et formats actifs proposés au téléchargement |
| CSRF | Jeton double soumission exigé pour toute modification par cookie ; cookies `SameSite=Strict`, `HttpOnly` (sauf le jeton anti-CSRF, par construction) |
| Jetons | Algorithme imposé à la vérification, champs obligatoires ; rafraîchissement haché, rotation, réutilisation ⇒ famille révoquée ; session et rôles relus en base à chaque requête |
| Isolation des organisations | RLS sur toutes les tables (test du schéma, 53 vérifications) ; filtres par organisation dans Qdrant |
| Contrôle d'accès des routes | Chaque route déclare son rôle ; conversations et documents vérifiés par utilisateur (404 identique si absent ou interdit) |
| Exposition | Documentation interactive désactivée ; `/metrics` non publiée par le relais ; journaux sans paramètres, cookies ni en-têtes d'autorisation |
| Saisies | Tailles bornées (questions, CSV d'identités 1 Mo, corps de requête 50 Mo au relais) |
| Secrets | Aucun secret dans les fichiers suivis ni dans l'historique Git (recherche de motifs de clés) ; clés d'API chiffrées (ADR-0012) |
| Vulnérabilités connues | `pip-audit` (base OSV) sur les 80 paquets Python livrés (toutes plateformes) et `pnpm audit --prod` : **aucune** |
| Licences | Voir `docs/LICENCES.md` : aucune AGPL/SSPL/GPL livrée, contrôle automatique en CI |

## 3. Risques résiduels (non corrigés, à arbitrer)

| Risque | Appréciation | Piste |
|---|---|---|
| Un administrateur d'organisation peut faire appeler par le serveur une adresse interne (adresse d'un fournisseur d'IA) | Faible : seule une réponse oui/non revient ; l'administrateur est de confiance dans une installation à une organisation | Liste d'adresses autorisées avant tout hébergement mutualisé |
| Plusieurs organisations sur un même serveur partagent la règle des dossiers autorisés | Sans objet tant qu'une installation sert une organisation (décision Q2) | Dossiers autorisés par organisation, fixés par le super-administrateur |
| Le code 423 révèle qu'un compte existe une fois verrouillé | Faible, courant | Accepté |
| `/admin/health` sans authentification | Faible : état « ok/erreur » des services seulement | Accepté (sondes) |
| Pas de limite de débit par utilisateur sur les questions au-delà de la file d'attente | Faible sur un réseau interne | À revoir si le service est exposé |
| Pas de test d'intrusion externe | — | Avant la première installation pilote |

## 4. Tests exécutés

| Suite | Résultat |
|---|---|
| Python : unitaires, connecteurs, intégration (dont 5 nouveaux tests de sécurité) | **179 passés**, 3 sautés |
| Schéma PostgreSQL | **53 vérifications passées** |
| Interface : Vitest / Playwright | 2 / **9 passés** |
| Licences des dépendances livrées | 91 contrôlées, aucune refusée |
| Vulnérabilités connues (pip-audit, pnpm audit) | aucune |

## 5. Recommandations

1. Ajouter `pip-audit` et `pnpm audit` à chaque livraison (la base de vulnérabilités évolue).
2. Test d'intrusion par un tiers avant la première installation pilote.
3. Avant tout hébergement de plusieurs organisations : dossiers autorisés et adresses de
   fournisseurs autorisées par organisation.

## 6. Vérification sur le serveur d'essai

Image reconstruite, mise à jour par `upgrade.sh` (sauvegarde vérifiée de 113 Mo, migration
0010) : la source existante sur `/documents` reste valide ; les racines `/`, `/run/urag` et
`/documents/../etc` sont refusées (422) ; la recherche fonctionne. Constat hors sécurité : la
première recherche d'un processus prend ≈ 15 s (chargement des modèles au premier appel) ;
précharger les modèles au démarrage de l'API est à faire.
