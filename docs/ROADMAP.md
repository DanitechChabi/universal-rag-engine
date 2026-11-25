# Feuille de route — Universal RAG Engine

Ordre adapté du cahier des charges (section 22) : la phase 7 (Server) passe avant
la phase 6 (Desktop), voir ADR-0013. Durées : ordres de grandeur pour un
développeur aidé de Claude Code (`AUDIT_FAISABILITE.md` §8).

| Phase | Contenu | Durée | Condition de sortie | État |
|---|---|---|---|---|
| 0 | Cadrage : architecture, base, sécurité, connecteurs, IA, API, déploiement, tests, ADR | 2–3 sem. | documents validés par le porteur du projet | **livrée** (PR #1) |
| 1 | Prototype RAG : socle Python (uv), FastAPI, authentification, migrations, ingestion locale PDF/DOCX, embeddings, Qdrant, recherche hybride filtrée, réponses avec citations | 3–5 sem. | scénarios 1, 2, 3, 5, 6 automatisés ; tests d'isolation et de permissions passés ; première mesure de qualité | **livrée** (`docs/reports/PHASE1.md`) ; comparatif du canal lexical reporté en phase 2 |
| 2 | Moteur documentaire : OCR, Excel/PowerPoint/anciens formats, versions, incrémental, erreurs, reprises | 4–6 sem. | scénarios 4, 8–11, 16 | **livrée** (`docs/reports/PHASE2.md`) ; formats anciens (Tika), reranker et comparatif du canal lexical reportés en phase 3 |
| 3 | Connecteurs : fichiers locaux complet ; M-Files contre un simulateur (pas de coffre disponible, Q8) ; droits ; correspondance des identités | 6–10 sem. | scénarios 7, 12, 13 ; suite de conformité sur le simulateur ; **validation M-Files réelle reportée** jusqu'à l'obtention d'un coffre | à faire — coffre M-Files à obtenir |
| 4 | Interface web : chat, conversations, sources, documents, tableau de bord, administration | 6–8 sem. | tests Playwright des parcours principaux | à faire |
| 5 | IA hybride : routeur, Ollama, premier fournisseur externe, politiques, quotas, coûts | 3–4 sem. | scénarios 14, 15 ; tests de politique | à faire — clé d'API de test |
| 7 | Server : Docker Compose de production, HTTPS, supervision, sauvegarde/restauration, tests de charge | 4–6 sem. | installation sur serveur vierge ; restauration testée ; rapport de charge | à faire — **serveur GPU (location)** |
| 6 | Desktop : Tauri, services embarqués, installateur signé, mises à jour | 6–10 sem. | installation sur Windows 11 vierge sans prérequis | à faire — PC Windows 16 Go, certificat de signature |
| 8 | Validation : tests utilisateurs, sécurité, documentation, licences, installations pilotes | 4–8 sem. | critères de recette du MVP (section 21) | à faire |

---

## Décisions du porteur du projet (novembre 2026)

| # | Question | Décision | Conséquence |
|---|---|---|---|
| Q1 | LDAP / Active Directory dans le MVP | **Non** : table de correspondance, saisie ou import CSV (ADR-0016) | LDAP/AD après le MVP |
| Q2 | Plusieurs organisations dans l'interface | **Non** : une organisation visible ; `org_id` + RLS partout (ADR-0015) | Gestion multi-organisations via l'API seulement |
| Q3 | Conservation des conversations | **12 mois**, réglable par organisation | Tâche de purge planifiée |
| Q4 | Conservation de l'audit | **12 mois**, réglable (minimum 30 jours) | `urag_audit_purge` planifiée |
| Q5 | Texte des questions dans l'audit | **Oui par défaut**, désactivable par organisation | Le journal devient sensible : lecture réservée aux auditeurs et administrateurs, purge à 12 mois, jamais les réponses ni les extraits (`SECURITY.md` §7) |
| Q6 | Volume du premier client type | **50 000 à 500 000 documents**, **20 à 60 % de scans** | Dimensionnement et durée d'indexation à mesurer en phase 2 (`DEPLOYMENT.md` §2.4) |
| Q7 | Langues | **Français et anglais** | Plein texte `urag_fr` + `english` (déjà dans le schéma) |
| Q8 | Coffre M-Files de test | **Pas d'accès pour l'instant** | Phase 3 : connecteur développé contre un simulateur ; **non déclaré opérationnel** tant qu'il n'est pas validé sur un vrai coffre |
| Q9 | Visibilité par défaut des dossiers locaux | **Personne** tant que l'administrateur n'ouvre pas le dossier à l'espace | `inherit_space_access = false` par défaut (déjà dans le schéma) |
| Q10 | Nom commercial | **« Universal RAG Engine », provisoire** | Nom et logo à décider avant la phase 4 |

## Prochaine étape immédiate : phase 1

1. Socle Python : espace de travail uv, paquets `urag-core`, `urag-connectors-base`,
   `urag-api`, `urag-worker` ; ruff, mypy, Pytest ; intégration continue.
2. Migration Alembic initiale reproduisant `database/schemas/schema.sql`, avec test
   de comparaison.
3. Authentification (Argon2id, jetons, verrouillage) et contexte d'organisation
   par transaction.
4. Connecteur fichiers locaux minimal + extraction PDF/DOCX avec pages.
5. Découpage, embeddings BGE-M3 (ONNX), Qdrant avec filtres de sécurité.
6. Recherche hybride + orchestrateur RAG avec un petit modèle Ollama + citations
   vérifiées.
7. Comparatif du canal lexical (ADR-0007) et première mesure de qualité sur un
   petit corpus.
