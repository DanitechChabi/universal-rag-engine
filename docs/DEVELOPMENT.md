# Développement — Universal RAG Engine

Guide pour lancer la pile de développement, l'API et les tests. Ce n'est pas une
installation de production (phase 7).

## Prérequis

- Python 3.12 et [uv](https://docs.astral.sh/uv/)
- Docker (avec Compose)
- Environ 8 Go d'espace disque pour les modèles (bge-m3 ≈ 1,2 Go, qwen2.5:1.5b ≈ 1 Go)

## 1. Services

```
docker compose up -d                         # PostgreSQL 16, Qdrant 1.15, Ollama
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull qwen2.5:1.5b
uv sync                                       # dépendances Python (versions verrouillées)
```

## 2. Base de données

```
export URAG_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:postgres-dev@127.0.0.1:5432/postgres
uv run urag-admin migrate                     # rôles + schéma (Alembic)
uv run urag-admin app-password                # mot de passe du rôle applicatif urag_app
uv run urag-admin bootstrap --org-name "Mon organisation" --org-slug mon-org --admin-login admin
```

## 3. API et worker

Fichier `.env` (à partir de `.env.example`) :

```
URAG_DATABASE_URL=postgresql+psycopg://urag_app:<mot de passe>@127.0.0.1:5432/postgres
URAG_QDRANT_URL=http://127.0.0.1:6333
URAG_QDRANT_API_KEY=dev-qdrant-key
URAG_OLLAMA_URL=http://127.0.0.1:11434
URAG_MASTER_KEY_FILE=.urag-dev/master.key
URAG_COOKIE_SECURE=false
URAG_TMP_DIR=.urag-dev/tmp
```

Dossiers qu'une source « fichiers locaux » a le droit d'indexer (lus par le connecteur dans
l'environnement du processus, pas dans `.env`) :

```bash
export URAG_LOCAL_FILES_ALLOWED_ROOTS=$HOME/urag-corpus   # plusieurs dossiers : séparés par « : »
```

Sans cette variable, aucune source locale n'est acceptée (fermé par défaut, revue de sécurité
de la phase 8).

```
uv run urag-admin gen-key .urag-dev/master.key
uv run urag-api        # http://127.0.0.1:8000/api/v1/docs
uv run urag-worker     # dans un autre terminal
```

Parcours minimal avec l'API : se connecter (`POST /api/v1/auth/login`), créer un espace
(`POST /spaces`), donner l'accès (`PUT /spaces/{id}/grants`), ajouter une source de type
`local_files` avec `inherit_space_access: true` (`POST /sources`), lancer la
synchronisation (`POST /sources/{id}/sync`), puis interroger (`POST /search`, `POST /chat`).

## 3 bis. Interface web (phase 4)

Prérequis : Node 22 et pnpm. Depuis la racine du dépôt :

```
pnpm install
# API de démonstration : base neuve, petit corpus indexé, modèle de réponse déterministe.
# Les identifiants générés sont écrits dans le fichier --info (hors du dépôt).
uv run python tests/e2e/serveur_de_test.py --port 8000 --info /tmp/urag-demo.json
# Dans un autre terminal : l'interface, qui relaie /api vers le port 8000.
cd apps/web && pnpm exec vite
```

Ouvrir http://127.0.0.1:5173 et se connecter avec un identifiant du fichier `--info`.
Tests : `pnpm exec vitest run` (unitaires) et `pnpm exec playwright test` (parcours de bout en
bout ; lance lui-même l'API de démonstration et l'interface).

## 4. Tests

```
PGUSER=postgres ./database/tests/test_schema.sh   # schéma (superutilisateur PostgreSQL)
uv run pytest -q                                  # unitaires + intégration + vrais modèles
uv run pytest -q core/tests connectors            # unitaires seulement (aucun service requis)
uv run ruff check . && uv run ruff format --check .
```

Les tests d'intégration créent une base neuve, la migrent, et la suppriment à la fin.
Variables : `URAG_TEST_ADMIN_URL`, `URAG_TEST_QDRANT_URL`, `URAG_TEST_QDRANT_KEY`,
`URAG_TEST_OLLAMA_URL`, `URAG_TEST_CHAT_MODEL`. Sans Qdrant ou PostgreSQL ils sont ignorés ;
sans les modèles Ollama, seul le test « vrais modèles » est ignoré.
