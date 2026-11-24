# Compte rendu — Phase 1 : prototype RAG

Date : novembre 2026. Branche : `claude/phase-1-prototype-rag`.
Format imposé par la directive 27.7 du cahier des charges.

## 1. Fonctionnalités réalisées (exécutées et testées)

| Fonctionnalité | Où | Preuve |
|---|---|---|
| Socle Python : espace de travail uv, 5 paquets, versions verrouillées, ruff | `pyproject.toml`, `uv.lock` | `ruff check` et `ruff format --check` au vert |
| Migrations Alembic reproduisant le schéma de référence | `database/migrations/` | utilisées par tous les tests d'intégration |
| Authentification : Argon2id, jeton d'accès 15 min, jeton de rafraîchissement rotatif avec détection de réutilisation, cookies `HttpOnly` + anti-CSRF, verrouillage progressif, message unique en cas d'échec | `services/api/.../routes/auth.py` | tests 16, 17 + tests unitaires |
| Rôles sur les routes (utilisateur, administrateur documentaire, administrateur d'organisation) | `deps.py` | test 15 |
| Interface commune des connecteurs + registre par points d'entrée | `connectors/base` | tests du connecteur |
| Connecteur fichiers locaux : exploration, filtres, fichiers temporaires et système ignorés, liens symboliques ignorés, jamais hors de la racine, fermé par défaut | `connectors/local_files` | 6 tests unitaires, tests 01, 14 |
| Extraction PDF (pages), DOCX (titres, tableaux), TXT, MD, CSV ; détection des PDF scannés | `core/.../extraction` | tests unitaires, test 12 |
| Découpage : sections, tableaux jamais mélangés, grands tableaux avec en-tête répété, chevauchement, **un fragment = une page** | `core/.../chunking` | 4 tests unitaires |
| Embeddings BGE-M3 (via Ollama) liés à un profil versionné ; encodeur déterministe pour les tests | `core/.../embeddings` | test « vrais modèles » |
| Qdrant : filtre d'organisation obligatoire, aucune recherche sans clé d'accès, vecteurs compressés int8 | `core/.../storage/vectors.py` | tests 04, 05 |
| Ingestion idempotente : versions, bascule atomique, anciennes versions invisibles, suppressions, droits recalculés | `core/.../ingestion` | tests 01, 02, 10, 11, 13 |
| File de tâches PostgreSQL et worker (reprises, échecs isolés) | `core/.../jobs`, `services/worker` | tests 01, 02 |
| Recherche hybride : vecteurs + plein texte français + références exactes, fusion RRF, relecture avec revérification des droits | `core/.../retrieval` | test 03 |
| Moteur RAG : contexte numéroté et encadré, consigne versionnée, flux SSE, conversation enregistrée | `core/.../rag`, `routes/chat.py` | tests 06, 07, 08 |
| Citations : références inventées retirées, **citation qui ne justifie pas la phrase corrigée ou retirée**, attribution vérifiable si le modèle oublie de citer | `core/.../citations` | tests unitaires, test 06, test « vrais modèles » |
| Routeur de modèles : adaptateur Ollama, politique locale par défaut, jamais de bascule vers l'externe si interdite | `core/.../ai` | 3 tests unitaires |
| Protection contre l'injection : délimiteurs neutralisés, rendu sans image ni lien externe | `citations` | tests 09, unitaires, « vrais modèles » |
| Audit : connexions, sources, synchronisations, recherches, questions (texte journalisé, décision Q5), jamais de contenu documentaire | `core/.../audit` | test 18 |

## 2. Tests exécutés et résultats

| Suite | Résultat |
|---|---|
| Schéma PostgreSQL (`database/tests/test_schema.sh`) | **42 vérifications passées** |
| Tests unitaires (`core/tests`, `connectors`) | **27 passés** |
| Intégration, pile réelle PostgreSQL 16 + Qdrant 1.15 (`tests/integration/test_phase1.py`) | **18 passés** |
| Chaîne complète avec les vrais modèles (`test_real_models.py`) | **1 passé** |
| Style (`ruff`) | aucun écart |

Scénarios de recette couverts : **1** (ajouter une source), **2** (indexer un PDF),
**3** (indexer un Word), **5** (poser une question), **6** (réponse sourcée) ; en avance :
**8, 9, 10, 11** (modification, réindexation, suppression), **12, 13** (changement de
droits, révocation — au niveau des espaces), **4** partiellement (le scan est détecté et
signalé ; l'OCR arrive en phase 2).

### Première mesure de qualité (`docs/reports/phase1-qualite.json`)

Corpus **synthétique** de 4 documents (contrat PDF, note RH Word, procédure, note piégée),
8 questions dont une sans réponse et une sur le document piégé. Modèles : bge-m3 et
qwen2.5:1.5b sur CPU (4 cœurs).

| Mesure | Résultat |
|---|---|
| Rappel de la recherche (bon document parmi les 6 premiers) | 8/8 |
| Faits exacts dans la réponse | 8/8 |
| Réponse exacte **et** citation pertinente | 8/8 (après correction, voir §3) |
| Abstention correcte (question sans réponse) | 1/1 |
| Document piégé : consigne cachée ignorée, aucun lien externe | oui |
| Durée totale (indexation + 8 questions) | ≈ 80 s |

Ce corpus est trop petit et trop simple pour juger la qualité réelle : la mesure sur le
corpus de référence du porteur du projet reste à faire.

## 3. Anomalies trouvées et corrigées pendant la phase

1. **Citations à cheval sur deux pages** : un fragment pouvait couvrir les pages 1 et 2.
   Corrigé : un fragment ne chevauche plus jamais deux pages.
2. **Le petit modèle oublie de citer** (4 réponses sur 8 sans citation à la première
   mesure). Corrigé : exemple dans la consigne + attribution automatique vérifiable,
   signalée comme « déduite ».
3. **Citation présente mais non pertinente** : une réponse juste citait le mauvais
   document. Détecté en relisant le rapport, pas par la première version de la mesure.
   Corrigé : une phrase dont les chiffres ou références ne figurent pas dans l'extrait
   cité voit sa citation corrigée ou retirée ; la mesure vérifie désormais la pertinence.
4. **Faux positif de chiffres** (« 45 » trouvé dans « 450 000 ») : comparaison des
   nombres en entier.
5. Adresse IP non valide (client de test) refusée par la base : validation avant écriture.

## 4. Anomalies et limites restantes

| Limite | Prévu |
|---|---|
| OCR non implémenté : les PDF scannés sont signalés « échec : OCR nécessaire » | phase 2 |
| Formats XLSX, PPTX, DOC, XLS, PPT, RTF, HTML, images non extraits | phase 2 |
| Comparatif du canal lexical (vecteurs creux BGE-M3 ou BM25 dans Qdrant vs PostgreSQL) **non fait** : PostgreSQL plein texte + références exactes retenus pour l'instant (ADR-0007) | phase 2 |
| Embeddings servis par Ollama et non par ONNX Runtime en local (prévu dans AI_MODELS.md) | à décider en phase 2 (mesure de débit) |
| Reranker non branché | phase 2 |
| Vérification tardive des droits auprès de la source : interface prête, aucun connecteur ne la fournit encore | phase 3 (M-Files) |
| Limitation du débit des routes, matrice complète rôle × route, export des conversations | phases 4 et 7 |
| Secrets des sources (chiffrement prêt et testé) non encore utilisés : le connecteur local n'en a pas besoin | phase 3 |
| Le test GitHub Actions n'a pas encore été exécuté sur GitHub | à vérifier sur la PR |
| Mesure de qualité sur un corpus synthétique seulement | corpus de référence à fournir |

## 5. Décisions prises

- Un fragment ne chevauche jamais deux pages (précision des citations).
- Les citations sont vérifiées contre le texte des extraits (chiffres et références) ;
  une citation corrigée est marquée « déduite » dans l'interface.
- Version du client Qdrant alignée sur le serveur (1.15).
- Fonction `urag_orgs_with_ready_jobs()` ajoutée au schéma : le worker connaît les
  organisations ayant des tâches, sans pouvoir lire leurs données.

## 6. Prochaines tâches (phase 2)

1. OCR (RapidOCR) et formats Excel, PowerPoint, anciens formats (Tika).
2. Comparatif du canal lexical ; reranker ; choix ONNX ou Ollama pour les embeddings.
3. Mesure du débit d'indexation pour dimensionner le client type (Q6).
4. Mesure de qualité sur le corpus de référence du porteur du projet.
