# Compte rendu — Phase 7 : mode Server

Date : novembre 2026. Branche : `claude/phase-7-server`, construite sur la branche de la phase 5
(PR #6, elle-même empilée sur les PR précédentes). Format imposé par la directive 27.7 du
cahier des charges. Décision d'architecture : ADR-0025.

## 1. Fonctionnalités réalisées (exécutées et testées)

| Fonctionnalité | Où | Preuve |
|---|---|---|
| **Deux images** : `urag-app` (API, worker, `urag-admin`, Tesseract ; compte non privilégié uid 10001 ; dépendances de production seulement) et `urag-web` (Caddy 2.10 + interface construite) ; images de base surchargeables (miroirs), certificat de proxy d'entreprise utilisé à la construction seulement | `infrastructure/docker/` | images construites et exécutées sur le serveur d'essai |
| **Compose de production** : PostgreSQL, Qdrant et Tika sur un réseau **sans accès à Internet** ; API, worker et Ollama avec sortie ; seul HTTPS est publié ; variante GPU | `infrastructure/compose*.yml` | installation d'essai |
| **HTTPS par Caddy** : autorité interne par défaut ou certificat de l'entreprise ; CSP stricte, HSTS ; seul `/api/*` est relayé (`/metrics` jamais publié) ; flux de réponse non mis en tampon | `infrastructure/caddy/Caddyfile` | en-têtes vérifiés, `test_phase7` 02 |
| **Installation en une commande** : contrôles préalables (mémoire, disque, lisibilité des dossiers de documents par l'uid 10001), secrets générés (`.env` 600), clé maîtresse lisible par le seul compte de l'application, migrations, organisation et premier administrateur (mot de passe dans un fichier 600, jamais sur une ligne de commande), modèles vérifiés par SHA-256, sauvegarde nocturne, test de santé ; nombre de processus de l'API choisi selon la mémoire | `scripts/install-server.sh`, `fetch-models.sh` | installation de zéro : réussie ; 3 PDF indexés en 10 s |
| **Sauvegarde vérifiée** : `pg_dump` + instantanés Qdrant, empreintes SHA-256, **restauration automatique dans une base temporaire et comparaison des lignes** avant de marquer « vérifiée » ; clé maîtresse jamais incluse | `scripts/backup.sh` | 112 Mo en 16 s (corpus complet) |
| **Restauration en deux étapes** (« prepare », puis « confirm » dans l'heure), refusée si la clé maîtresse du serveur n'est pas celle de la sauvegarde ; export de la clé chiffré par phrase de passe (PBKDF2 600 000 tours) | `restore.sh`, `master-key.sh` | essai de sinistre ci-dessous |
| **Mise à jour** : sauvegarde vérifiée obligatoire, images, migrations explicites, redémarrage, test de santé | `scripts/upgrade.sh` | 5 mises à jour du serveur d'essai, dont la migration 0009 |
| **Supervision sans contenu** : `/metrics` Prometheus (requêtes et durées par modèle de route, multiprocessus) ; agrégats de toute l'installation par `urag_metrics()` (migration 0008) ; journaux JSON en rotation, sans paramètres de requête ; sondes de santé de l'API et du worker | `metrics.py`, `logs.py` | `test_phase7` 01 à 03 |
| **Tenue en charge** : un calcul ONNX à la fois par processus, sans réserve mémoire ni attente active ; recherches admises avant l'ouverture d'une connexion à la base, puis refus propre (503 « serveur occupé ») au-delà de 60 s d'attente ; message dédié dans l'assistant | `retrieval`, `rerank`, `embeddings`, `rag` | `test_charge` (4), `test_phase7` 04, tests de charge |
| **Reprise des tâches abandonnées** même quand aucune autre tâche n'est prête (migration 0009) | `worker/main.py` | `test_phase7` 05, schéma, serveur d'essai |
| **Outils de charge** : générateur (recherche ou question complète, 1 à 20 utilisateurs, p50/p95/p99, premier morceau) et faux GPU « compatible OpenAI » | `eval/charge/` | rapports `charge-phase7-*.json` |

## 2. Tests exécutés et résultats

| Suite | Résultat |
|---|---|
| Schéma PostgreSQL | **52 vérifications passées** |
| Python : unitaires, conformité des connecteurs, intégration (PostgreSQL 16, Qdrant 1.15, Tika 3.2) | **151 passés**, 3 sautés (fonctions absentes des fichiers locaux) |
| Interface : Vitest | **2 passés** |
| Parcours de bout en bout Playwright contre la vraie API | **9 passés** |
| Style (`ruff check`, `ruff format`, `tsc`) | aucun écart |

### Essais sur le serveur d'essai (conteneurs, 4 cœurs, 16 Go, sans GPU)

1. **Installation de zéro** (`install-server.sh`, site `urag.test.local`, port 8443) : réussie ;
   connexion du premier administrateur, recherche et réponse citée par l'interface en HTTPS.
2. **Sinistre complet** : export de la clé maîtresse et sauvegarde, destruction de tout
   (conteneurs, volumes, données), réinstallation, import de la clé, restauration en deux
   étapes (20 s). L'ancien administrateur se reconnecte et retrouve ses documents et la même
   réponse. Restauration **refusée** tant que la clé maîtresse ne correspondait pas.
3. **Corpus public complet** (92 documents, dont des scans) indexé en conteneurs : 12 941
   fragments, ≈ 25 s par document sur 4 cœurs ; 92/92 indexés après correctifs (§3).
4. **Mises à jour** (`upgrade.sh`) : 5 passages, sauvegarde vérifiée à chaque fois, aucune perte.

### Tests de charge (`docs/reports/charge-phase7-*.json`, graphique `charge-phase7.png`)

Même serveur, corpus complet, 60 s par niveau. Génération par un **GPU simulé** (premier jeton
0,4 s, 40 jetons/s) pour mesurer le moteur seul ; le GPU réel est mesuré à part
(`COMPARAISON-MODELES-LOCAUX.md`).

| Utilisateurs | Recherches/min | Durée médiane | Questions/min | 1er morceau médian | Échecs |
|---|---|---|---|---|---|
| 1 | 6,7 | 8,7 s | 5,2 | 8,8 s | 0 |
| 5 | 9,5 | 38 s | 9,4 | 32 s | 0 |
| 10 | 8,8 | 42 s | 7,6 | 45 s | 1 question « serveur occupé » |
| 20 | 9,1 | 43 s | 10,6 | 81 s | 36 % des recherches, 14 % des questions : refus 503 propres |

**Lecture.** Le débit est **stable** (≈ 9 à 10 par minute) quel que soit le nombre d'utilisateurs,
sans perte de processus ni de connexion : au-delà de la capacité, les demandes attendent puis
sont refusées proprement. La limite vient du **reclassement sur CPU** (bge-reranker-v2-m3 sur
20 passages : 0,9 s pour des passages courts, **5,4 s pour des passages de 300 mots** comme ceux
du corpus réel) et non de la génération : le GPU simulé n'a jamais eu plus de 4 générations
simultanées. Avant correctifs, le même essai perdait des processus dès 5 utilisateurs et
échouait à 100 % à 20 (graphique).

## 3. Anomalies trouvées et corrigées pendant la phase

| Anomalie | Cause | Correctif |
|---|---|---|
| Ollama ne démarrait pas sur Kaggle | `zstd` absent | installé avant Ollama |
| Documents illisibles dans le conteneur | dossier créé en 700, uid 10001 exclu | 755, et lisibilité vérifiée **dans un conteneur** par l'installateur |
| Scripts arrêtés à la détection du GPU | test `&&` sous `set -e` | `if` explicite (même règle pour le calcul des processus) |
| La restauration téléchargeait `postgres:16` | images choisies à l'installation non mémorisées | écrites dans `.env` |
| `verify-install.py` en échec après 15 min | expiration de la session | reconnexion sur 401 |
| **3 gros PDF jamais indexés** (plus de 1 500 fragments) | tous les vecteurs en une requête, délai dépassé pendant l'OCR | envoi par lots de 256 (test) |
| Limite de générations simultanées remise à zéro | sémaphores recréés à chaque reconstruction du routeur | partagés par processus |
| Remplacement d'une clé d'API : erreur 500 | champ `api_key` refusé par l'audit | `cle_remplacee` |
| **Processus de l'API tués par le système** (12,7 Go) dès 5 utilisateurs | calculs ONNX simultanés (≈ 0,5 Go chacun, sans gain de débit) ; réserve mémoire d'ONNX ; 4 processus chargeant chacun ≈ 2,5 Go de modèles | un calcul à la fois, options ONNX, processus selon la mémoire |
| **Connexions à la base épuisées** (500 après 30 s) | recherches en attente gardant leur connexion | admission avant la connexion, refus 503 |
| **Tâche bloquée indéfiniment** après redémarrage du worker | la reprise ne visitait que les organisations ayant une tâche prête | `urag_orgs_with_stale_jobs()` (migration 0009) |

Les trois dernières ne se voyaient qu'en conditions réelles (corpus complet, charge, redémarrage) :
c'est l'apport principal de la phase.

## 4. Limites restantes

- **Pas d'essai sur une machine vierge physique ni sur un vrai GPU** : l'installation a été jouée
  dans des conteneurs sur une machine de développement. À faire sur un serveur loué
  (ROADMAP) : installation, débit de génération réel, tests de charge avec le modèle retenu.
- **Capacité sur CPU seul : ≈ 10 recherches ou questions par minute sur 4 cœurs**, limitée par le
  reclassement. Pistes (décision à prendre, §6) : reclasser 10 passages au lieu de 20 ou couper à
  256 jetons (≈ 3 à 5 fois plus rapide, qualité à remesurer) ; reclassement sur GPU (ONNX Runtime
  CUDA) ; plus de cœurs.
- Durée d'attente de 8 à 9 s pour un utilisateur seul sur ce serveur (reclassement sur 2 fils par
  processus) : acceptable pour un essai, pas pour un usage quotidien sans GPU.
- La limite de générations simultanées s'entend par processus de l'API (ADR-0025).
- Relais HTTPS ↔ API et API ↔ base non chiffrés sur le réseau interne de Docker : l'hôte fait
  partie du périmètre de confiance.

## 5. Décisions prises

- ADR-0025 : déploiement Server (images, réseaux, secrets, migrations explicites, sauvegarde
  vérifiée, supervision sans contenu).
- Processus de l'API = (mémoire visible en Go − 9) / 3, entre 1 et 4 ; fils ONNX = cœurs / processus.
- 4 recherches simultanées par processus, attente maximale 60 s, puis 503 : en surcharge, le
  service ralentit puis refuse, il ne tombe pas.

## 6. Prochaines tâches

1. **Décision** : réglage du reclassement sur CPU (10 passages, 256 jetons) après mesure de la
   qualité sur les 40 questions d'évaluation ; ou reclassement sur GPU.
2. Serveur GPU loué : installation de zéro, modèle `qwen2.5:14b`, tests de charge réels.
3. Phase 6 (Desktop), selon la feuille de route.
