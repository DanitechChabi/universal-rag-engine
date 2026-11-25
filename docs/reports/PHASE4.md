# Compte rendu — Phase 4 : interface web

Date : novembre 2026. Branche : `claude/phase-4-interface-web`, construite sur la branche de la
phase 3 (PR #4, elle-même empilée sur la PR #3).
Format imposé par la directive 27.7 du cahier des charges.

## 1. Fonctionnalités réalisées (exécutées et testées)

| Fonctionnalité (cahier des charges §10) | Où | Preuve |
|---|---|---|
| Socle : React 19, TypeScript, Vite, TanStack Query, sans bibliothèque de composants ; modes clair, sombre et système (ADR-0023) | `apps/web` | construction, Playwright |
| **Connexion** (§10.2) : message d'erreur explicite, session uniquement par cookies `HttpOnly`, aucun jeton lisible par le JavaScript, jeton anti-CSRF, une tentative de rafraîchissement | `api.ts`, `auth.tsx`, `Login.tsx` | Playwright 1 |
| Navigation selon les rôles ; pages protégées (« Vous n'avez pas accès ») | `Layout.tsx`, `App.tsx` | Playwright 4 |
| **Assistant** (§10.4) : réponse progressive, références `[n]` cliquables, extraits, ouverture du document original, historique, arrêt d'une génération, copie, modèle utilisé (local ou externe) | `Assistant.tsx`, `chat.ts` | Playwright 2, 3, 6 ; Vitest |
| Aucun HTML interprété dans les réponses et les extraits (texte échappé, références découpées) | `chat.ts` | Vitest |
| **Sources** (§10.5) : statut, dernière synchronisation, documents, erreurs ; synchroniser, tester, désactiver, supprimer de l'index | `Sources.tsx`, API | `test_phase4` 06, 07 |
| **Documents** (§10.6) : liste filtrable et paginée, fiche (métadonnées, droits résumés, historique des versions), réindexer, exclure, réintégrer, retirer de l'index, ouvrir l'original ; jamais le contenu dans la fiche | `Documents.tsx`, `routes/documents.py` | `test_phase4` 01 à 05, Playwright 5 |
| **Tableau de bord** (§10.3) : sources, documents, fragments, tâches, erreurs, services, modèle actif, politique d'IA, usage sur 30 jours, activité récente (sans le texte des questions) | `Dashboard.tsx`, `routes/dashboard.py` | `test_phase4` 08, Playwright 7 |
| **Administration** (§10.7) : utilisateurs (rôles, désactivation, création), espaces et autorisations, correspondance des comptes (confirmer, lier, délier, import CSV), tâches | `Admin.tsx` | `test_phase4` 09, 10, Playwright 6 |
| **Révocation immédiate** : session, statut du compte et rôles relus à chaque requête | `deps.py` | `test_phase4` 09 |
| Serveur de démonstration et de test : vraie API, base neuve, corpus indexé, modèle déterministe | `tests/e2e/serveur_de_test.py` | utilisé par Playwright |

## 2. Tests exécutés et résultats

| Suite | Résultat |
|---|---|
| Schéma PostgreSQL | **48 vérifications passées** |
| Python : unitaires, conformité des connecteurs, intégration (PostgreSQL 16, Qdrant 1.15, Tika 3.2) | **121 passés**, 3 sautés (fonctions absentes des fichiers locaux) |
| Interface : types (`tsc`), Vitest | **2 passés** |
| **Parcours de bout en bout Playwright** contre la vraie API | **7 passés** |
| Style (`ruff`) | aucun écart |

Condition de sortie de la phase (`ROADMAP.md`) : **tests Playwright des parcours principaux —
remplie.** Les parcours sont aussi ajoutés à l'intégration continue.

## 3. Anomalies trouvées et corrigées pendant la phase

1. **Rôle retiré encore actif jusqu'à 15 minutes** (rôles lus dans le jeton) : session, compte et
   rôles sont désormais relus en base à chaque requête (trouvé par `test_phase4` 09).
2. **Recherche de documents : « % » agissait comme joker SQL** et renvoyait tout : recherche
   littérale (trouvé par `test_phase4` 01).
3. **Un document exclu était réindexé** par la synchronisation suivante : il reste exclu.
4. **Course dans l'assistant** : « Nouvelle conversation » suivi d'une question rapide effaçait
   la réponse en cours (trouvé par Playwright).
5. **Espace supprimé avant « : » et « ; »** dans les réponses (typographie française) : corrigé.
6. Historique : pages des citations et type de modèle ajoutés à l'API.
7. Un fichier généré par TypeScript avait été commité : retiré et ignoré.

## 4. Limites restantes

| Limite | Prévu |
|---|---|
| Export des réponses en PDF ou DOCX (§10.4) | phase 5 ou 8 |
| Récupération de compte (§10.2, « si configurée ») : non configurée dans le MVP | après le MVP (LDAP/AD) |
| Groupes d'utilisateurs : pas d'écran (les autorisations d'espace se font par utilisateur) | phase 7 |
| Gestion des modèles d'IA, paramètres RAG, journaux, sauvegardes, licences (§10.7) | phases 5, 7 et 8 |
| Interface en français seulement (textes regroupés, traduction possible) | selon les clients |
| Questions de suite non reformulées (« Et sa durée ? ») | prochaine tâche |

## 5. Décisions prises

- **ADR-0023** : socle de l'interface et règles de sécurité côté navigateur (cookies `HttpOnly`
  seulement, aucun HTML injecté, même origine que l'API, CSP stricte).
- Révocation immédiate des rôles et des sessions à chaque requête (`SECURITY.md` §3).
- « Exclure » masque un document en gardant son index ; « Retirer de l'index » supprime ses
  fragments et vecteurs ; dans les deux cas, le document d'origine n'est jamais touché.
- Une source désactivée n'est plus synchronisée, mais ses documents restent consultables.

## 6. Prochaines tâches

1. Reformuler les questions de suite à partir de l'historique de la conversation (modèle local).
2. Écarter les pages de sommaire et d'index du classement.
3. Phase 5 : routeur d'IA hybride, choix d'un modèle local mesuré sur GPU, quotas et coûts.
4. Connecteur M-Files dès qu'un coffre de test est disponible.
