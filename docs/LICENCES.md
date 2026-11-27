# Licences des composants (livrable 29)

Statut : **audit de novembre 2026** (début de la phase 8). Règle du projet (`CLAUDE.md`,
cahier des charges §27) : aucune dépendance AGPL ou SSPL dans le produit. Ce document couvre
tout ce qui est livré au client : paquets Python et JavaScript, images Docker, paquets système
et modèles.

## 1. Contrôle automatique

`tools/verifier_licences.py` lit les licences des dépendances **livrées** (paquets Python de
production de l'API et du worker d'après `uv.lock`, paquets JavaScript intégrés à l'interface
construite) et **échoue** sur toute licence AGPL, SSPL, GPL, BUSL, RSAL, Commons Clause, non
commerciale ou inconnue. Il tourne dans l'intégration continue (`.github/workflows/tests.yml`) :
une nouvelle dépendance interdite bloque la fusion. Inventaire généré :
`docs/reports/licences-dependances.md`.

Résultat de l'audit : **91 dépendances livrées, aucune refusée**.

| Classe | Nombre | Paquets |
|---|---|---|
| Permissive (MIT, BSD, Apache-2.0, PSF, ISC…) | 83 | dont les 11 paquets de l'interface web (React, React Router, TanStack Query : MIT) |
| Copyleft faible | 4 | `psycopg`, `psycopg-binary` (LGPL-3.0) ; `certifi`, `tqdm` (MPL-2.0) |
| Autre système (Windows, navigateur) | 4 | `colorama`, `pywin32`, `tzdata`, `httpx2-jsfetch` : non installés sous Linux, à contrôler à la construction du mode Desktop |

## 2. Composants à copyleft faible : pourquoi ils sont acceptables, et à quelles conditions

| Composant | Licence | Utilisation | Obligation |
|---|---|---|---|
| psycopg 3 (pilote PostgreSQL) | LGPL-3.0 | bibliothèque non modifiée, chargée dynamiquement | fournir le texte de la licence ; l'utilisateur doit pouvoir remplacer la bibliothèque. Serveur : paquet Python remplaçable dans l'image. **Desktop : ne pas l'intégrer dans un exécutable monolithique** sans garder ce remplacement possible (phase 6) |
| certifi, tqdm | MPL-2.0 | non modifiés | fournir le texte ; publier nos modifications de ces fichiers (aucune) |
| FFmpeg, libvpx… intégrés à `opencv-python-headless` | LGPL-2.1 / BSD | dépendance de RapidOCR (moteur OCR facultatif, ADR-0017) | fournir les textes (`cv2/LICENSE-3RD-PARTY.txt`). Piste : rendre RapidOCR facultatif à l'installation retirerait OpenCV et FFmpeg de l'image par défaut (Tesseract est le moteur par défaut) |
| libgfortran, libquadmath (intégrées à OpenBLAS / OpenCV) | GPL-3.0 **avec exception d'exécution GCC** | bibliothèques d'exécution | aucune contrainte sur notre code (exception prévue pour ce cas) ; fournir les textes |

## 3. Images Docker et paquets système

| Image | Contenu principal | Licence | Remarque |
|---|---|---|---|
| `urag-app` (la nôtre) | Debian 12 (python:3.12-slim), Python 3.12, Tesseract 5.3 + données fra/eng, Leptonica | PSF, Apache-2.0, BSD-2 (Leptonica) | 162 paquets Debian, dont des programmes sous GPL (bash, coreutils…) |
| `urag-web` (la nôtre) | Caddy 2.10 sur Alpine | Apache-2.0 ; BusyBox (GPL-2.0) dans Alpine | — |
| `postgres:16` | PostgreSQL | PostgreSQL License (permissive) | image officielle |
| `qdrant/qdrant:v1.15.4` | Qdrant | Apache-2.0 | — |
| `ollama/ollama:0.12.3` | Ollama | MIT | — |
| `apache/tika:3.2.3.0` | Apache Tika + Java | Apache-2.0 ; OpenJDK GPL-2.0 avec *Classpath exception* | — |

Les programmes sous GPL des images (outils du système de base) sont des **programmes distincts**,
livrés à côté du nôtre et non liés à notre code : la GPL ne s'étend pas à notre logiciel
(« agrégation »). Obligation quand nous **distribuons** une image (archive hors ligne
`docker save`, registre privé fourni au client) : rendre disponible le code source de ces
paquets. Debian le publie pour chaque version (`snapshot.debian.org`) ; la notice livrée
indiquera les paquets, leurs versions et cette source, et une offre écrite d'en fournir copie.
Quand le client télécharge lui-même les images officielles (installation en ligne), c'est
l'éditeur de l'image qui distribue.

## 4. Modèles

Licences lues sur les fiches Hugging Face (novembre 2026) :

| Modèle | Rôle | Licence | Remarque |
|---|---|---|---|
| BAAI/bge-m3 (export ONNX `Xenova/bge-m3`) | encodage | MIT (export : MIT déclarée) | — |
| BAAI/bge-reranker-v2-m3 (export ONNX `onnx-community/bge-reranker-v2-m3-ONNX`) | reclassement | Apache-2.0 (modèle d'origine) | **l'export ne déclare pas de licence** : œuvre dérivée d'un modèle Apache-2.0, à livrer avec la licence et la mention de BAAI. Plus sûr : produire notre propre export depuis le modèle d'origine (action ci-dessous) |
| Qwen2.5-14B-Instruct, 7B, 1.5B | génération (ADR-0024 ; 1.5B en développement) | Apache-2.0 | — |
| Qwen2.5-3B-Instruct | — | **licence propre (« other »)** | **à ne pas proposer** sans lecture de ses conditions |
| Llama, Gemma et autres | au choix du client | conditions propres à chaque éditeur | à vérifier avant toute recommandation ; jamais livrés par défaut |

Les modèles ne sont pas intégrés au code : ils sont téléchargés à l'installation à des
révisions figées et vérifiés par SHA-256 (`fetch-models.sh`), ou fournis dans le paquet hors
ligne avec leurs licences.

## 5. Actions restantes

1. **Notice des tiers** livrée avec le produit (`THIRD-PARTY-NOTICES`) : textes complets des
   licences, générés depuis les métadonnées des paquets, des images et des modèles — à produire
   avec le paquet de livraison (phase 8).
2. **Export ONNX du reclassement par nos soins** depuis BAAI/bge-reranker-v2-m3, avec licence et
   empreinte, pour ne plus dépendre d'un export sans licence déclarée.
3. **Desktop (phase 6)** : contrôler les dépendances Windows et garder psycopg remplaçable.
4. Licence de notre propre logiciel et contrat de licence client : à décider par le porteur du
   projet (hors de ce document).

Ce document est une analyse technique, pas un avis juridique : une relecture par un juriste est
recommandée avant la première vente.
