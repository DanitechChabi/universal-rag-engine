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

Deux réglages du reclassement ont été mesurés après correctifs : 20 passages reclassés (réglage
d'origine, `charge-phase7-*-20-candidats.json`) puis **10 passages** (nouveau défaut, voir
ci-dessous ; `charge-phase7-recherche.json`, `charge-phase7-question.json`).

| Utilisateurs | Recherches/min (20 → **10**) | Durée médiane | Questions/min (20 → **10**) | 1er morceau médian | Échecs avec 10 passages |
|---|---|---|---|---|---|
| 1 | 6,7 → **12,5** | 8,7 → **4,4 s** | 5,2 → **7,8** | 8,8 → **4,7 s** | 0 |
| 5 | 9,5 → **20,4** | 38 → **14 s** | 9,4 → **18,5** | 32 → **13 s** | 0 |
| 10 | 8,8 → **20,7** | 42 → **19 s** | 7,6 → **20,2** | 45 → **20 s** | 0 |
| 20 | 9,1 → **19,6** | 43 → **41 s** | 10,6 → **17,1** | 81 → **42 s** | 0 recherche ; 5 questions sur 37 « serveur occupé » |

**Lecture.** Le débit est **stable** quel que soit le nombre d'utilisateurs, sans perte de
processus ni de connexion : au-delà de la capacité, les demandes attendent puis sont refusées
proprement. La limite vient du **reclassement sur CPU** (bge-reranker-v2-m3 : 0,9 s pour 20
passages courts, **5,4 s pour 20 passages de 300 mots** comme ceux du corpus réel) et non de la
génération : le GPU simulé n'a jamais eu plus de 4 générations simultanées. Avant correctifs,
le même essai perdait des processus dès 5 utilisateurs et échouait à 100 % à 20 (graphique).

### Qualité du reclassement selon son réglage (`eval/reclassement.py`, `reclassement-phase7.json`)

Sur l'index réel du serveur et les 37 questions avec réponse : la réponse figure-t-elle dans les
6 passages transmis au modèle, et à quel rang (le modèle de génération n'intervient pas) ?

| Réglage | Réponse transmise | Réponse en tête | Rang réciproque moyen | Durée médiane |
|---|---|---|---|---|
| Sans reclassement | 36/37 | 26 | 0,777 | 0,3 s |
| 20 passages, 512 jetons (ancien défaut) | 37/37 | 33 | 0,912 | 6,1 s |
| **10 passages, 512 jetons (nouveau défaut)** | **37/37** | **33** | **0,914** | **3,2 s** |
| 20 passages, 256 jetons | 35/37 | 29 | 0,838 | 3,2 s |
| 10 passages, 256 jetons | 36/37 | 29 | 0,843 | 1,8 s |

Même qualité avec 10 passages, deux fois moins de temps : nouveau défaut (révision de l'ADR-0021).
Couper les passages à 256 jetons fait perdre des réponses (Q20, Q35) : écarté.

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
- **Capacité sur CPU seul : ≈ 20 recherches ou questions par minute sur 4 cœurs**, limitée par le
  reclassement ; un utilisateur seul attend ≈ 4,5 s avant le début de la réponse. Pistes au-delà :
  reclassement sur GPU (ONNX Runtime CUDA), plus de cœurs.
- Qualité du reclassement mesurée sur 37 questions d'un corpus public : à remesurer sur un corpus
  client plus grand avant de figer le réglage.
- La limite de générations simultanées s'entend par processus de l'API (ADR-0025).
- Relais HTTPS ↔ API et API ↔ base non chiffrés sur le réseau interne de Docker : l'hôte fait
  partie du périmètre de confiance.

## 5. Décisions prises

- ADR-0025 : déploiement Server (images, réseaux, secrets, migrations explicites, sauvegarde
  vérifiée, supervision sans contenu).
- Processus de l'API = (mémoire visible en Go − 9) / 3, entre 1 et 4 ; fils ONNX = cœurs / processus.
- 4 recherches simultanées par processus, attente maximale 60 s, puis 503 : en surcharge, le
  service ralentit puis refuse, il ne tombe pas.
- Reclassement de **10 candidats au lieu de 20** (révision de l'ADR-0021) : même qualité mesurée,
  capacité doublée.

## 6. Prochaines tâches

1. Reclassement sur GPU quand un GPU est présent (ONNX Runtime CUDA), à mesurer sur le serveur loué.
2. Serveur GPU loué : installation de zéro, modèle `qwen2.5:14b`, tests de charge réels.
3. Phase 6 (Desktop), selon la feuille de route.
