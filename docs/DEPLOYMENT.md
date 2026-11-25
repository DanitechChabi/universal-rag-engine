# Déploiement — Universal RAG Engine

Statut : **conception de phase 0**. Rien n'est encore empaqueté. Ordre de
réalisation : Server (phase 7) avant Desktop (phase 6), voir ADR-0013.

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
| `caddy` | Caddy | **443** (réseau local) | HTTPS, sert le frontend, relaie `/api` |
| `api` | `urag-api` | interne | FastAPI (uvicorn, plusieurs processus) |
| `worker` | `urag-worker` | interne | tâches : synchronisation, ingestion, OCR, embeddings, sauvegarde |
| `postgres` | PostgreSQL 16 | interne | données métier, fragments, file de tâches, audit |
| `qdrant` | Qdrant | interne (clé d'API) | vecteurs |
| `ollama` ou `vllm` | Ollama / vLLM | interne | génération locale (GPU) |
| `tika` (facultatif) | Apache Tika server | interne | formats anciens DOC, XLS, PPT, RTF |

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

### 2.3 Installation (cible)

1. Ubuntu Server LTS, Docker, pilote NVIDIA + NVIDIA Container Toolkit si GPU.
2. Script `infrastructure/scripts/install-server.sh` : vérification du matériel,
   génération de la clé maîtresse et des mots de passe, création du `.env`,
   démarrage, création du super administrateur, test de santé.
3. **Installation hors ligne** : archive contenant les images Docker et les
   modèles, pour les sites sans Internet.
4. Mise à jour : nouvelles images + migrations Alembic automatiques au démarrage
   de l'`api` (sauvegarde préalable obligatoire, retour arrière documenté).

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
| Qdrant | instantanés de collection (ou reconstruction depuis PostgreSQL) |
| Configuration | `.env` sans secrets + fichiers de configuration |
| Clé maîtresse | exportée séparément, chiffrée par une phrase de passe administrateur |
| Licences | incluses dans PostgreSQL |

- Sauvegarde manuelle (`/admin/backup`) et planifiée (tâche quotidienne par défaut,
  RPO 24 h) vers un emplacement distinct (partage réseau, disque externe).
- **Vérification** : chaque sauvegarde est restaurée automatiquement dans une base
  temporaire et contrôlée (tables, nombre de lignes, empreinte) ; statut `verified`.
- Restauration en deux étapes (préparation puis confirmation), journalisée.
- Procédure testée avant toute mise en production (RTO cible 8 h).

---

## 5. Supervision

- Logs JSON structurés (sans contenu documentaire ni secret), rotation.
- Métriques Prometheus (`/metrics` interne) : requêtes, latences, erreurs, tâches,
  documents, consommation API, CPU, mémoire, disque, GPU/VRAM (exportateur NVIDIA).
- Tableau de bord technique dans l'interface d'administration ; Grafana facultatif
  pour les clients qui en ont un.
