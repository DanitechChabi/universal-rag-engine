# Plan de tests — Universal RAG Engine

Statut : **plan de phase 0**. Seuls les tests du schéma de base de données existent
et passent (`database/tests/test_schema.sh`, 39 vérifications sur PostgreSQL 16).

Règle (directive 27.7) : une fonctionnalité n'est terminée que si elle a été
**exécutée et testée** ; chaque phase se termine par un compte rendu (fonctions
réalisées, fichiers, tests exécutés, résultats, anomalies, décisions, suite).

---

## 1. Niveaux de tests

| Niveau | Outil | Où | Quand |
|---|---|---|---|
| Schéma | psql (`test_schema.sh`) | PostgreSQL réel | chaque modification du schéma |
| Unitaires backend | Pytest | sans service externe | chaque commit |
| Intégration backend | Pytest + conteneurs (PostgreSQL, Qdrant, Ollama avec un très petit modèle, Tika) | Docker | chaque commit sur la branche principale |
| Conformité connecteurs | suite commune Pytest | simulateur ; vrai coffre M-Files en recette | chaque modification d'un connecteur |
| Qualité RAG | jeu de questions de référence | pile complète | chaque modification du découpage, de la recherche ou de la consigne |
| Sécurité | Pytest (matrice RBAC, isolation, injection) | pile complète | chaque version |
| Frontend | Vitest | — | chaque commit |
| Bout en bout | Playwright | pile complète | chaque version |
| Charge | Locust | serveur avec GPU | phase 7 puis chaque version majeure |

Intégration continue (GitHub Actions) : lint (ruff, mypy, eslint), tests unitaires,
schéma, intégration, recherche de secrets (gitleaks), vérification des licences
des dépendances.

---

## 2. Tests unitaires prioritaires (section 20.1)

| Domaine | Exemples |
|---|---|
| Extraction | numéros de page conservés ; tableau DOCX restitué ; PDF image détecté ⇒ OCR demandé |
| Découpage | aucun fragment ne coupe un tableau ; titres englobants conservés ; chevauchement respecté ; pages correctes |
| Embeddings | dimension vérifiée contre le profil ; refus d'écrire dans une collection d'un autre profil |
| Recherche | fusion RRF déterministe ; filtres appliqués ; **aucun passage sans clé commune** |
| Permissions | calcul des clés (miroir des tests SQL) ; droits incomplets ⇒ aucune clé |
| Citations | `[7]` inexistant retiré ; page et titre pris dans la base, jamais dans le texte généré |
| Routeur IA | `local_only` ⇒ aucun appel externe, même si le local est en panne ; quota dépassé ⇒ refus |
| Synchronisation | relance ⇒ aucun doublon ; curseur non avancé si lot interrompu |
| Authentification | verrouillage, rotation des jetons, réutilisation ⇒ révocation de la famille |

---

## 3. Scénarios fonctionnels de recette (section 20.3)

Chaque scénario devient un test automatisé (intégration ou bout en bout) :

| # | Scénario | Phase |
|---|---|---|
| 1 | Ajouter une source | 1 (locale), 3 (M-Files) |
| 2 | Indexer un PDF | 1 |
| 3 | Indexer un document Word | 1 |
| 4 | Indexer un document scanné | 2 |
| 5 | Poser une question | 1 |
| 6 | Obtenir une réponse sourcée | 1 |
| 7 | Ouvrir le document original | 3 |
| 8 | Modifier un document | 2 |
| 9 | Réindexer le document | 2 |
| 10 | Supprimer un document | 2 |
| 11 | Vérifier que le document supprimé ne ressort plus | 2 |
| 12 | Changer les permissions | 3 |
| 13 | Vérifier que l'accès est révoqué | 3 |
| 14 | Basculer entre deux modèles IA | 5 |
| 15 | Désactiver l'accès aux API externes | 5 |
| 16 | Reprendre une synchronisation interrompue | 2 |

---

## 4. Qualité des réponses RAG

**Corpus de référence** (à constituer avec le porteur du projet) : 50 à 200
documents représentatifs (PDF natifs, Word, Excel, scans, tableaux), publics ou
anonymisés, en français et en anglais ; **30 à 50 questions** avec la réponse
attendue et les documents qui la justifient, dont des questions sans réponse
possible et des questions multi-documents.

Mesures :

| Mesure | Définition | Objectif initial |
|---|---|---|
| Rappel de la recherche @10 | le bon passage est parmi les 10 premiers | ≥ 85 % |
| Citations valides | références qui pointent vers un passage fourni | 100 % (par construction) |
| Citations pertinentes | la citation soutient bien l'affirmation (revue humaine ou modèle juge) | ≥ 90 % |
| Abstention correcte | « les documents ne permettent pas… » quand il n'y a pas de réponse | ≥ 90 % |
| Exactitude des chiffres | dates, montants, références recopiés à l'identique | 100 % sur l'échantillon |

Les objectifs seront ajustés après la première mesure (phase 1).

---

## 5. Sécurité (section 20.4)

| Test | Méthode |
|---|---|
| Accès non autorisé | matrice rôle × route (`API.md` §4) |
| Escalade de privilèges | un `org_admin` tente d'attribuer `super_admin`, un `user` appelle les routes d'administration |
| Fuite inter-organisations | deux organisations, mêmes questions, aucune référence croisée ; identifiants d'une autre organisation ⇒ 404 ; tests RLS (fait) |
| Contournement des permissions | utilisateurs aux droits différents posent les mêmes questions ; vérification que chaque citation est accessible à l'auteur |
| Révocation | retrait d'un groupe entre deux questions d'une même conversation |
| Exposition de clés | recherche de motifs de secrets dans toutes les réponses API et les journaux de test |
| Injection dans les requêtes | entrées malformées, SQL, très longues |
| Injection de prompt documentaire | corpus de documents piégés (consignes cachées, faux délimiteurs, demandes de révéler la consigne ou d'afficher une image externe) : la réponse ne doit ni suivre la consigne, ni produire de lien ou d'image externe, ni citer un document non fourni |
| Manipulation des citations | le modèle écrit `[99]` ou invente un titre : retiré |
| Conversations d'autrui | lecture, export, suppression d'une conversation d'un autre utilisateur ⇒ 404 |

---

## 6. Charge (section 20.5)

Scénarios Locust à 10, 20 et 30 utilisateurs : recherches seules, générations
seules, mélange, pendant une ingestion. Mesures : latence (médiane, 95e centile),
débit de tokens, CPU, mémoire, VRAM, longueur des files, erreurs, consommation API.
Matériel et modèle consignés dans le rapport (livrable 20).

---

## 7. Ce qui existe déjà

| Test | Fichier | Résultat |
|---|---|---|
| Schéma PostgreSQL : RLS, clés composites, fermé par défaut, clés d'accès, révocation, plein texte français, audit en ajout seul, politique IA, file de tâches, profil d'embedding unique | `database/tests/test_schema.sql` | **48 vérifications passées** (PostgreSQL 16) |
| Unitaires : extraction, découpage, OCR, formats Excel/PowerPoint/HTML et anciens formats (Tika), contexte du document, encodeur ONNX, reclassement, passages piégés, sécurité, droits et refus, citations, recherche, routeur, page de test de l'API | `core/tests`, `services/api/tests` | **44 passés** |
| Connecteurs : connecteur fichiers locaux et suite de conformité commune (fichiers locaux, source simulée) | `connectors/` | **29** (3 sautés : fonctions absentes des fichiers locaux) |
| Intégration sur pile réelle : scénarios 1–13, 16 (OCR, ouverture du document original, reprise après arrêt d'un worker), isolation, rôles, sessions, audit | `tests/integration/test_phase1.py` | **23 passés** |
| Intégration phase 3 (source simulée) : identités externes et correspondances, droits par document et par groupe, refus explicites, revérification à la question, scénarios 12, 13, 16 (synchronisation incrémentale) | `tests/integration/test_phase3.py` | **12 passés** |
| Intégration phase 4 : API des écrans (documents filtrés et paginés, fiche sans contenu, exclure, retirer de l'index, sources, tableau de bord sans contenu, comptes, révocation immédiate des rôles) | `tests/integration/test_phase4.py` | **10 passés** |
| Migrations Alembic identiques au schéma de référence | `tests/integration/test_migrations.py` | **1 passé** |
| Qdrant : index HNSW par organisation, migration des collections, isolation, clés de refus | `tests/integration/test_vectors.py` | **4 passés** |
| Mesure de qualité sur le corpus public (40 questions) | `eval/run_eval.py` | rapports `docs/reports/eval-*.json`, synthèse dans `docs/reports/PHASE2.md` |
| Chaîne complète avec bge-m3 et qwen2.5:1.5b, mesure de qualité | `tests/integration/test_real_models.py` | **1 passé** (rapport `docs/reports/phase1-qualite.json`) |
| Interface web : flux de réponse, références sans HTML interprété | `apps/web/src/*.test.ts` (Vitest) | **2 passés** |
| Parcours de bout en bout contre la vraie API (connexion, réponse sourcée, ouverture du document, arrêt, utilisateur sans droit, exclusion, correspondance des comptes, tableau de bord) | `apps/web/tests/e2e` (Playwright) | **7 passés** |
