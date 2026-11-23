# Feuille de route — Universal RAG Engine

Ordre adapté du cahier des charges (section 22) : la phase 7 (Server) passe avant
la phase 6 (Desktop), voir ADR-0013. Durées : ordres de grandeur pour un
développeur aidé de Claude Code (`AUDIT_FAISABILITE.md` §8).

| Phase | Contenu | Durée | Condition de sortie | État |
|---|---|---|---|---|
| 0 | Cadrage : architecture, base, sécurité, connecteurs, IA, API, déploiement, tests, ADR | 2–3 sem. | documents validés par le porteur du projet | **livrée, en attente de validation** |
| 1 | Prototype RAG : socle Python (uv), FastAPI, authentification, migrations, ingestion locale PDF/DOCX, embeddings, Qdrant, recherche hybride filtrée, réponses avec citations | 3–5 sem. | scénarios 1, 2, 3, 5, 6 automatisés ; tests d'isolation et de permissions passés ; première mesure de qualité | à faire |
| 2 | Moteur documentaire : OCR, Excel/PowerPoint/anciens formats, versions, incrémental, erreurs, reprises | 4–6 sem. | scénarios 4, 8–11, 16 | à faire |
| 3 | Connecteurs : fichiers locaux complet ; M-Files (simulateur puis coffre réel) ; droits ; correspondance des identités | 6–10 sem. | scénarios 7, 12, 13 ; suite de conformité sur coffre M-Files réel | à faire — **coffre M-Files requis** |
| 4 | Interface web : chat, conversations, sources, documents, tableau de bord, administration | 6–8 sem. | tests Playwright des parcours principaux | à faire |
| 5 | IA hybride : routeur, Ollama, premier fournisseur externe, politiques, quotas, coûts | 3–4 sem. | scénarios 14, 15 ; tests de politique | à faire — clé d'API de test |
| 7 | Server : Docker Compose de production, HTTPS, supervision, sauvegarde/restauration, tests de charge | 4–6 sem. | installation sur serveur vierge ; restauration testée ; rapport de charge | à faire — **serveur GPU (location)** |
| 6 | Desktop : Tauri, services embarqués, installateur signé, mises à jour | 6–10 sem. | installation sur Windows 11 vierge sans prérequis | à faire — PC Windows 16 Go, certificat de signature |
| 8 | Validation : tests utilisateurs, sécurité, documentation, licences, installations pilotes | 4–8 sem. | critères de recette du MVP (section 21) | à faire |

---

## Décisions en attente (à trancher par le porteur du projet)

| # | Question | Proposition par défaut | Impact |
|---|---|---|---|
| Q1 | LDAP / Active Directory dans le MVP ? | Non ; table de correspondance + import CSV pour M-Files (ADR-0016) | Droits M-Files |
| Q2 | Plusieurs organisations dans l'interface du MVP ? | Non ; `org_id` + RLS partout, une organisation visible (ADR-0015) | Interface d'administration |
| Q3 | Durée de conservation des conversations | 12 mois, paramétrable | Base, confidentialité |
| Q4 | Durée de conservation de l'audit | 12 mois, paramétrable (minimum 30 jours) | Base |
| Q5 | Journaliser le texte des questions ? | Non par défaut | Audit, confidentialité |
| Q6 | Volume du premier client type (documents, pages, part de scans) | à fournir | Dimensionnement, temps d'indexation |
| Q7 | Langues du MVP | français et anglais | Modèles, plein texte |
| Q8 | Accès à un coffre M-Files de test (version, interfaces activées) | à obtenir (Archivexa ?) | Phase 3 |
| Q9 | Fichiers locaux : documents visibles par tous les membres de l'espace par défaut ? | Non (fermé par défaut, l'administrateur active) | Sécurité |
| Q10 | Nom commercial et identité visuelle | à définir | Interface (phase 4) |

---

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
