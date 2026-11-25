# Tester Universal RAG Engine sur son PC (Windows)

Guide pas à pas pour essayer le prototype de la phase 1 sur un PC Windows 11. Il n'y a
pas encore d'interface graphique (phase 4) : on utilise la **page de test intégrée de
l'API**, dans le navigateur.

> Ce guide a été vérifié sous Linux. La procédure Windows n'a pas encore été exécutée de
> bout en bout : signalez tout écart, il sera corrigé.

## Ce que vous pourrez faire

- vous connecter ;
- indexer un dossier de documents (PDF à texte, Word, TXT, MD, CSV) ;
- rechercher dans les documents ;
- poser des questions et obtenir des réponses avec les sources citées.

**Limites actuelles** : les PDF scannés ne sont pas encore lus (OCR en phase 2 : ils
apparaissent en « échec : OCR nécessaire ») ; Excel et PowerPoint ne sont pas encore pris
en charge ; sur un PC sans carte graphique, l'indexation est lente (environ 1 fragment par
seconde, soit 1 à 2 minutes pour un document de 20 pages) et une réponse prend de 10 à 60
secondes.

## 1. Installer les outils (une seule fois)

1. **Docker Desktop** : https://www.docker.com/products/docker-desktop — installer, redémarrer,
   lancer Docker Desktop et attendre « Engine running ».
   Avec 8 Go de mémoire, fermez les autres applications pendant le test.
2. **Git** : https://git-scm.com/download/win
3. **uv** (gestionnaire Python) — dans PowerShell :
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   puis fermer et rouvrir PowerShell.

## 2. Récupérer le projet et lancer les services

```powershell
git clone https://github.com/DanitechChabi/universal-rag-engine.git
cd universal-rag-engine
docker compose up -d
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull qwen2.5:1.5b
uv sync
```

Les deux téléchargements de modèles font environ 2,2 Go au total.

## 3. Préparer la base de données

Remplacez `MOT-DE-PASSE-APP` par un mot de passe de votre choix (au moins 12 caractères).

```powershell
$env:URAG_ADMIN_DATABASE_URL = "postgresql+psycopg://postgres:postgres-dev@127.0.0.1:5432/postgres"
uv run urag-admin migrate
uv run urag-admin app-password --password "MOT-DE-PASSE-APP"
uv run urag-admin bootstrap --org-name "Test" --org-slug test --admin-login admin
uv run urag-admin gen-key .urag-dev\master.key
```

La commande `bootstrap` demande le mot de passe de l'administrateur (au moins 12 caractères).

Créez ensuite un fichier `.env` à la racine du projet (Bloc-notes, « Enregistrer sous »,
type « Tous les fichiers ») :

```
URAG_DATABASE_URL=postgresql+psycopg://urag_app:MOT-DE-PASSE-APP@127.0.0.1:5432/postgres
URAG_QDRANT_URL=http://127.0.0.1:6333
URAG_QDRANT_API_KEY=dev-qdrant-key
URAG_OLLAMA_URL=http://127.0.0.1:11434
URAG_MASTER_KEY_FILE=.urag-dev/master.key
URAG_COOKIE_SECURE=false
URAG_TMP_DIR=.urag-dev/tmp
URAG_ACCESS_TOKEN_TTL_MINUTES=120
```

## 4. Démarrer l'API et le worker

Deux fenêtres PowerShell, dans le dossier du projet :

```powershell
uv run urag-api        # fenêtre 1
```

```powershell
uv run urag-worker     # fenêtre 2 : indexe les documents
```

## 5. Tester dans le navigateur

Ouvrez **http://127.0.0.1:8000/api/v1/docs**. Pour chaque étape : cliquer sur la ligne,
puis « Try it out », remplir, « Execute ».

1. **`POST /api/v1/auth/login`** :
   ```json
   {"login": "admin", "password": "votre mot de passe administrateur"}
   ```
   Dans la réponse, copiez la valeur de `access_token` et notez `user_id`.
2. Bouton **Authorize** (en haut à droite) : collez le jeton, « Authorize », « Close ».
3. **`POST /api/v1/spaces`** : `{"name": "Mes documents"}` — notez l'`id` renvoyé.
4. **`PUT /api/v1/spaces/{space_id}/grants`** (avec l'`id` de l'espace) :
   ```json
   [{"principal_type": "user", "principal_id": "VOTRE user_id"}]
   ```
5. **`POST /api/v1/sources`** — mettez quelques PDF ou Word dans un dossier, par exemple
   `C:\Users\Daniel\Documents\test-rag`, puis (barres obliques `/` dans le chemin) :
   ```json
   {"kind": "local_files", "name": "Dossier de test", "space_id": "ID DE L'ESPACE",
    "config": {"roots": ["C:/Users/Daniel/Documents/test-rag"]}, "inherit_space_access": true}
   ```
   Notez l'`id` de la source. Sans `"inherit_space_access": true`, les documents restent
   invisibles pour tout le monde (fermé par défaut).
6. **`POST /api/v1/sources/{source_id}/sync`** : lance l'indexation (la fenêtre du worker
   affiche l'avancement).
7. **`GET /api/v1/documents`** : état de chaque document (`indexed`, `failed`…).
8. **`POST /api/v1/search`** : `{"query": "votre recherche"}` — passages trouvés, avec pages.
9. **`POST /api/v1/chat`** : `{"question": "votre question"}` — la réponse arrive en flux ;
   la page affiche le tout à la fin : évènements `token` (le texte), `citations` (les
   sources) et `done` (réponse finale validée).

Pour tester les droits : créez un deuxième utilisateur (`POST /api/v1/users`) sans
l'ajouter à l'espace, connectez-vous avec lui : il ne doit rien trouver.

## Problèmes fréquents

| Symptôme | Cause probable |
|---|---|
| `docker compose` : « cannot connect » | Docker Desktop n'est pas lancé |
| Port 5432 déjà utilisé | un PostgreSQL est déjà installé sur le PC : l'arrêter, ou changer le port dans `docker-compose.yml` et dans les URL |
| `401` sur toutes les routes | jeton expiré ou non saisi dans « Authorize » |
| Documents en `failed` avec « OCR nécessaire » | PDF scanné : pris en charge en phase 2 |
| Réponse très lente ou erreur « Ollama » | mémoire insuffisante : fermer des applications, ou attribuer plus de mémoire à Docker (fichier `.wslconfig`) |

## Tout arrêter

```powershell
docker compose down        # garde les données
docker compose down -v     # supprime aussi les données et les modèles
```
