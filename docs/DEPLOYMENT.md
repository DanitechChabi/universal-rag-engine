# Déploiement — Universal RAG Engine

Statut : **mode Server livré en phase 7** (`infrastructure/`, ADR-0025, `docs/reports/PHASE7.md`) ;
mode Desktop à venir (phase 6). Ordre de réalisation : Server avant Desktop, voir ADR-0013.

---

## 1. Environnements

| Environnement | Usage | Particularités |
|---|---|---|
| Développement cloud (Claude Code) | écrire et tester le cœur | pas de GPU, pas de M-Files ; petits modèles sur CPU ; Docker à démarrer |
| Développement local | Daniel / développeurs | `docker compose up` de la pile de développement |
| Test / recette | validation des phases | serveur avec GPU (loué pour les tests de charge), coffre M-Files de test |
| Production client | installation sur site | Server ou Desktop ; **aucune dépendance obligatoire au cloud** |

Configuration par variables d'environnement (fichier `.env`, modèle dans
`.env.example`) ; aucun secret dans le dépôt.

---

## 2. Mode Server

### 2.1 Services (Docker Compose)

| Service | Image | Exposé | Rôle |
|---|---|---|---|
| `caddy` | Caddy 2.10 (`urag-web`) | **443** (réseau local) | HTTPS, sert le frontend, relaie `/api` seulement |
| `api` | `urag-api` | interne | FastAPI (uvicorn, plusieurs processus) |
| `worker` | `urag-worker` | interne | tâches : synchronisation, ingestion, OCR, embeddings, sauvegarde |
| `postgres` | PostgreSQL 16 | interne | données métier, fragments, file de tâches, audit |
| `qdrant` | Qdrant | interne (clé d'API) | vecteurs |
| `ollama` ou `vllm` | Ollama / vLLM | interne | génération locale (GPU) |
| `tika` (facultatif) | Apache Tika server 3.2 (`apache/tika`, Apache-2.0) | interne | formats anciens DOC, XLS, PPT, RTF, ODT ; activé par `URAG_TIKA_URL` ; sans lui, ces fichiers sont « exclus » avec la raison |

Pas de Redis ni de Celery (ADR-0003). Les modèles d'embedding et de reranking
tournent dans le `worker` (et l'`api` pour l'encodage des questions) via ONNX
Runtime, avec le GPU si disponible. L'OCR par défaut est **Tesseract** (ADR-0017) :
l'image du `worker` doit contenir les paquets système `tesseract-ocr`,
`tesseract-ocr-fra` et `tesseract-ocr-eng` (licence Apache-2.0). Sans eux, le
worker se replie sur RapidOCR, entièrement en Python.

### 2.2 Volumes et fichiers

| Volume | Contenu | Sauvegardé |
|---|---|---|
| `pgdata` | base PostgreSQL | oui (`pg_dump`) |
| `qdrant` | collections | oui (instantanés) — reconstructible depuis PostgreSQL |
| `models` | modèles téléchargés | non (re-téléchargeables ou fournis hors ligne) |
| `tmp` | fichiers temporaires d'extraction | non, purgé |
| `/etc/urag/master.key` | clé maîtresse des secrets | **à part**, hors des sauvegardes de la base |

### 2.3 Installation et mise à jour

Prérequis : Linux 64 bits (Ubuntu Server LTS conseillé), Docker et Docker Compose v2, 16 Go de
mémoire et 40 Go libres au moins ; pilote NVIDIA et NVIDIA Container Toolkit si GPU.

```bash
# 1. Images (construites, ou chargées depuis une archive pour un site hors ligne)
docker build -f infrastructure/docker/app.Dockerfile -t urag-app:latest .
docker build -f infrastructure/docker/web.Dockerfile -t urag-web:latest .
# 2. Installation (secrets, modèles vérifiés, base, migrations, organisation, HTTPS)
sudo infrastructure/scripts/install-server.sh --site rag.cabinet.local \
     --org-name "Cabinet Exemple" --org-slug cabinet --documents-dir /srv/documents
# 3. Contrôle de bout en bout (connexion, source, indexation, recherche)
python infrastructure/scripts/verify-install.py --url https://rag.cabinet.local \
     --login admin --password-file /var/lib/urag/premier-administrateur.txt
```

| Script (`infrastructure/scripts/`) | Rôle |
|---|---|
| `install-server.sh` | vérifications, secrets, `.env` (600), modèles, base, migrations, premier administrateur, démarrage, sauvegarde nocturne, test HTTPS ; relançable sans perte |
| `fetch-models.sh` | modèles ONNX à révision figée, empreintes SHA-256 ; `--from` pour un site hors ligne |
| `upgrade.sh` | sauvegarde vérifiée **obligatoire**, images (`--images archive.tar`), migrations, redémarrage, test de santé |
| `backup.sh`, `restore.sh`, `master-key.sh` | voir §4 |
| `verify-install.py` | essai de bout en bout par HTTPS |

- **Migrations explicites** (`install-server.sh`, `upgrade.sh`), jamais au démarrage de l'API :
  elles suivent toujours une sauvegarde vérifiée (ADR-0025).
- **Certificat** : par défaut, autorité interne du serveur ; installer
  `<données>/caddy/caddy/pki/authorities/local/root.crt` sur les postes (stratégie de groupe).
  Certificat de l'entreprise : `--tls-cert` et `--tls-key`.
- **Dossiers de documents** : montés en lecture seule dans `/documents` ; ils doivent être
  lisibles par l'uid 10001 (`setfacl -R -m u:10001:rX /srv/documents`). Une source « fichiers
  locaux » se déclare sur `/documents/<sous-dossier>`.
- **Proxy d'entreprise** : `docker build --secret id=extra_ca,src=<autorité du proxy>` (le
  certificat ne reste pas dans l'image) ; images de base surchargeables (`--build-arg
  PYTHON_IMAGE=…`, `NODE_IMAGE`, `CADDY_IMAGE`) pour passer par un miroir.
- **Hors ligne** : `docker save` des images, `fetch-models.sh --from`, et `ollama pull` fait
  ailleurs puis copie du dossier `<données>/ollama`.

### 2.4 Dimensionnement

Configuration de référence du cahier des charges (section 4.2). Les limites de
concurrence (générations simultanées, tâches d'ingestion parallèles) sont des
paramètres ; le rapport de tests de charge fixera les valeurs par défaut.

**Client type retenu (décision Q6)** : 50 000 à 500 000 documents, dont 20 à 60 %
de scans. Ordres de grandeur, **premières mesures de la phase 2** ci-dessous :

| Élément | Hypothèse | Estimation pour 500 000 documents |
|---|---|---|
| Fragments | ≈ 20 par document | ≈ 10 millions |
| Vecteurs BGE-M3 (1024 dimensions) | 4 Ko par vecteur en clair | ≈ 40 Go ; ≈ 10 Go avec quantification int8 de Qdrant (à activer) |
| Texte des fragments + index plein texte | — | plusieurs dizaines de Go dans PostgreSQL |
| Pages à passer en OCR | 20 à 60 % des documents, ≈ 5 pages chacun | 0,5 à 1,5 million de pages |
| Durée de l'OCR initial | **2,6 s par page** mesurées (Tesseract, 300 dpi, 1 cœur) | ≈ 15 à 45 jours-cœur : 1 à 3 jours sur 16 cœurs |
| Embeddings | **6,4 passages par seconde** mesurés (ONNX int8, 4 cœurs) | ≈ 18 jours sur 4 cœurs pour 10 millions de fragments ; GPU ou plus de cœurs nécessaires |

Mesure de bout en bout (phase 2, corpus public de 83 documents dont 15 scans, CPU
4 cœurs) : **29 à 35 minutes**, OCR et embeddings compris, soit ≈ 2 fragments par
seconde (`docs/reports/PHASE2.md`).

Conséquences : quantification des vecteurs dans Qdrant dès la phase 1 ; un index
HNSW par organisation (ADR-0019) ; ingestion
par priorité (documents récents d'abord) pour rendre le logiciel utile avant la fin
de l'indexation initiale ; durée d'indexation annoncée au client à partir de la
mesure réelle.

**Modèle de génération local** (ADR-0024) : télécharger `qwen2.5:14b` (GPU de 12 Go et plus)
ou `qwen2.5:7b` (8 Go) dans Ollama, puis le déclarer et le tester dans l'écran « IA » de
l'administration (`ollama pull qwen2.5:14b`). Mesuré sur un Tesla T4 : 7 à 9 s par réponse.

---

## 3. Mode Desktop

### 3.1 Composition

```
Application Tauri (fenêtre, interface React)
 └─ démarre et surveille :
     ├─ urag-desktop-backend  (Python empaqueté : api + worker dans un seul processus)
     ├─ postgres              (binaires portables, données dans le profil utilisateur)
     ├─ qdrant                (binaire)
     └─ ollama                (installé silencieusement s'il est absent, ou fourni)
```

- Ports aléatoires sur `127.0.0.1` uniquement ; secret de démarrage partagé entre
  Tauri et le backend.
- Données dans `%LOCALAPPDATA%\UniversalRAG\` ; clé maîtresse protégée par DPAPI.
- Un profil local = une organisation + un utilisateur administrateur.
- API externes **désactivées** tant qu'elles ne sont pas configurées.

### 3.2 Installateur Windows

- Installateur MSI ou NSIS produit par Tauri, **signé** (certificat de signature de
  code requis avant toute diffusion commerciale).
- Taille estimée : 2 à 3 Go hors modèle de langage ; le modèle de langage est
  téléchargé au premier lancement ou fourni dans une édition hors ligne.
- Mises à jour : module de mise à jour de Tauri, paquets signés ; migrations de
  base au démarrage, sauvegarde automatique avant migration.
- Désinstallation : choix de conserver ou supprimer les données.
- Configuration minimale annoncée : Windows 11, **16 Go de mémoire**, 20 Go
  d'espace libre ; 8 Go possible en mode dégradé (génération externe ou très petit
  modèle).

---

## 4. Sauvegarde et restauration

| Élément | Méthode |
|---|---|
| PostgreSQL | `pg_dump` format personnalisé, compressé, empreinte SHA-256 |
| Qdrant | instantané de chaque collection (restauration en secondes ; reconstruction depuis PostgreSQL en dernier recours) |
| Configuration | `.env` **sans** ses lignes secrètes, `urag.env` |
| Clé maîtresse | **jamais** dans la sauvegarde : `master-key.sh export` (chiffrée par phrase de passe, PBKDF2 600 000 itérations), à conserver sur un autre support |
| Manifeste | date, révision du schéma, empreinte (tronquée) de la clé maîtresse, collections, `verified` |

```bash
sudo infrastructure/scripts/backup.sh [--dest /mnt/partage/urag] [--keep 14]
sudo infrastructure/scripts/master-key.sh export /media/cle-usb/urag-master.key.enc
sudo infrastructure/scripts/restore.sh prepare /var/lib/urag/backups/urag-20261126T021700Z
sudo infrastructure/scripts/restore.sh confirm /var/lib/urag/backups/urag-20261126T021700Z
```

- **Planifiée** chaque nuit à 2 h 17 par l'installation (`/etc/cron.d/urag-backup`, RPO 24 h) ;
  copier aussi les sauvegardes hors du serveur (`--dest` vers un partage ou un disque externe).
- **Vérification** : chaque sauvegarde est restaurée dans une base temporaire ; les nombres de
  lignes de 11 tables sont comparés ; elle n'est marquée `verified` (table `backups`) qu'ensuite.
- **Restauration en deux étapes** : `prepare` contrôle les empreintes et la clé maîtresse et
  affiche un résumé sans rien modifier ; `confirm`, dans l'heure, arrête les services, remplace
  base et index, applique les migrations et journalise `backup.restored`.
- **Serveur perdu** : nouvelle installation, `master-key.sh import`, puis `restore.sh`.
  Procédure **essayée** en phase 7 : serveur détruit, réinstallé et restauré en 20 s (petit corpus).

---

## 5. Supervision

- **Santé** : `GET /api/v1/admin/health` (PostgreSQL, Qdrant) ; sondes Docker de l'API et du
  worker (fichier daté à chaque tour ; une tâche peut durer jusqu'à 15 min).
- **Journaux JSON** (API, worker, Caddy), sans contenu documentaire, question ni secret ; requêtes
  journalisées par modèle de route, sans paramètres ; rotation (5 × 20 Mo par service).
- **Métriques Prometheus** sur `http://api:8000/metrics`, **réseau interne seulement** (jamais
  relayé par Caddy) : requêtes et durées par route, et agrégats lus en base par `urag_metrics()`
  (documents par état, fragments, tâches, plus ancienne tâche en attente, jetons sur 24 h par
  localisation, échecs de connexion sur une heure).
- CPU, mémoire, disque et GPU : exportateurs standards du client (node_exporter, exportateur
  NVIDIA DCGM) ; Grafana facultatif.
