# Universal RAG Engine

Plateforme d'intelligence documentaire fondée sur la RAG (Retrieval-Augmented
Generation) : elle se connecte aux sources documentaires d'une organisation
(dossiers, GED M-Files…), indexe leur contenu et répond aux questions en langage
naturel, **avec les sources citées** et **dans le respect des droits d'accès**.
Deux modes : Desktop (un poste) et Server (sur site, 10 à 30 utilisateurs), sans
dépendance obligatoire au cloud.

## État

**Phase 1 (prototype RAG) livrée** : indexation de PDF et de Word depuis des dossiers,
recherche hybride filtrée par les droits, réponses en flux continu avec citations
vérifiées, authentification et rôles. Compte rendu : [docs/reports/PHASE1.md](docs/reports/PHASE1.md).
Démarrage : [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

| Document | Contenu |
|---|---|
| [Cahier des charges](docs/CAHIER_DES_CHARGES.md) | référence fonctionnelle et technique v1.0 |
| [Audit de faisabilité](docs/AUDIT_FAISABILITE.md) | verdict, risques, ajustements, charge, budget |
| [Architecture](docs/ARCHITECTURE.md) | modules, flux, organisation du dépôt, choix techniques |
| [Base de données](docs/DATABASE.md) | schéma, isolation, clés d'accès, correspondance Qdrant |
| [Sécurité](docs/SECURITY.md) | menaces, contrôle d'accès, sessions, secrets, injection de prompt, audit |
| [Connecteurs](docs/CONNECTORS.md) | interface commune, fichiers locaux, M-Files |
| [Modèles d'IA](docs/AI_MODELS.md) | routeur, politiques, embeddings, licences |
| [Contrats d'API](docs/API.md) | conventions, routes, rôles, flux de réponse |
| [Déploiement](docs/DEPLOYMENT.md) | Server, Desktop, sauvegarde, supervision |
| [Essai gratuit](docs/ESSAI-CODESPACES.md) | Essayer le produit dans GitHub Codespaces, sans carte bancaire |
| [Plan de tests](docs/TESTING.md) | niveaux, scénarios, qualité RAG, sécurité, charge |
| [Feuille de route](docs/ROADMAP.md) | phases, conditions de sortie, décisions |
| [Développement](docs/DEVELOPMENT.md) | lancer la pile, l'API, le worker et les tests |
| [Tester sur son PC](docs/TESTER.md) | guide pas à pas Windows, page de test dans le navigateur |
| [Compte rendu phase 1](docs/reports/PHASE1.md) | réalisé, tests, mesure de qualité, limites |
| [Décisions (ADR)](docs/DECISIONS/README.md) | 16 fiches de décision |

## Tester le schéma de base de données

Prérequis : PostgreSQL 15 ou plus récent, accès superutilisateur.

```
PGUSER=postgres ./database/tests/test_schema.sh
```

Le script crée une base temporaire, applique `database/schemas/roles.sql` et
`database/schemas/schema.sql`, exécute les vérifications puis supprime la base.

## Structure (cible)

```
apps/            web (React) et desktop (Tauri)
services/        api (FastAPI) et worker (tâches)
core/            moteur : ingestion, recherche, RAG, permissions, citations, routeur IA
connectors/      interface commune, fichiers locaux, M-Files
database/        schéma de référence, migrations, tests
infrastructure/  Docker, déploiement, supervision
docs/            documentation et décisions
```
