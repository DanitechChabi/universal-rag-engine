# Compte rendu — Phase 2 : moteur documentaire

Date : novembre 2026. Branche : `claude/phase-2-moteur-documentaire` (comprend aussi le corpus
public d'évaluation, branche `claude/corpus-evaluation`).
Format imposé par la directive 27.7 du cahier des charges.

## 1. Fonctionnalités réalisées (exécutées et testées)

| Fonctionnalité | Où | Preuve |
|---|---|---|
| **OCR** des pages sans texte (PDF scannés, PDF mixtes, images PNG/JPEG) : rendu à 300 dpi, Tesseract fra+eng par défaut, RapidOCR en alternative, paragraphes conservés, score de confiance enregistré avec la version | `core/.../ocr`, `extraction` | tests unitaires OCR, tests 19 et 20, mesure (10 questions sur scans) |
| Page non lue ou confiance OCR faible (< 0,60) : document « indexé avec avertissement » | `ingestion` | test 20 (page non lue) ; la confiance faible n'est vérifiée que par la mesure (15 documents) |
| **Activation de l'OCR après coup** : les documents indexés sans OCR sont relus automatiquement à la synchronisation suivante | `ingestion.sync_source` | test 20 |
| Formats **Excel** (feuilles, tableaux avec en-tête), **PowerPoint** (une diapositive = une page), **HTML** (sans scripts ni styles) | `extraction` | 3 tests unitaires |
| **Encodeur BGE-M3 ONNX int8** local, 10 fois plus rapide qu'Ollama | `embeddings.OnnxEncoder`, `build_encoder` | test unitaire, mesure de débit (ADR-0018) |
| **Passages piégés** (consignes adressées à une IA) : détectés à l'indexation, jamais envoyés au modèle, signalés dans la recherche, audités | `core/.../injection`, `rag`, migration 0002 | 2 tests unitaires, mesure (document piège : 0 reprise) |
| Versions : nouvelle version seulement si le contenu, le profil d'embedding ou le moteur OCR change (index unique en base) | migration 0002, `ingestion` | tests 10, 11 et 20 |
| **Reprise après l'arrêt brutal d'un worker** : la tâche est reprise, sans fragment en double | `jobs`, `services/worker` | test 21 |
| Réponses : **flux interrompu signalé** comme une erreur (et non une réponse tronquée), langue de la réponse imposée selon la question | `ai.GeminiAdapter`, `rag` | tests unitaires, mesure |
| Découpage : listes numérotées conservées ligne par ligne, plus de fragment minuscule, un fragment ne chevauche jamais deux pages | `chunking`, `extraction` | test unitaire des listes |
| **Qdrant : un index HNSW par organisation** (anomalie 1 ci-dessous) | `storage/vectors.py` | 3 tests d'intégration (ADR-0019) |
| Page de test de l'API (Swagger) servie localement, sous CSP, avec bouton *Authorize* | `services/api` | 2 tests |
| Mesure de qualité reproductible sur un **corpus public** (83 documents BCEAO, SGG Bénin, FSB ; 40 questions ; document piège) | `eval/` | rapports `docs/reports/eval-*.json` |

## 2. Tests exécutés et résultats

| Suite | Résultat |
|---|---|
| Schéma PostgreSQL (`database/tests/test_schema.sh`) | **42 vérifications passées** |
| Tests unitaires (`core/tests`, `connectors`, `services/api/tests`) | **41 passés** |
| Intégration, pile réelle PostgreSQL 16 + Qdrant 1.15 (`tests/integration`) | **26 passés** : 21 scénarios, migrations = schéma de référence, 3 tests Qdrant, chaîne avec les vrais modèles |
| Style (`ruff check`, `ruff format --check`) | aucun écart |

Scénarios de recette de la phase 2 couverts : **4** (document scanné, tests 19 et 20), **8, 9, 10,
11** (modification, réindexation, suppression, absence après suppression), **16** (reprise après
interruption, test 21).

### Mesure de qualité sur le corpus public (`eval/`, 40 questions)

Score principal : réponse exacte **et** citation d'un document qui la justifie. Matériel : CPU
4 cœurs, sans GPU. qwen2.5 1,5B tourne en local ; Gemini flash-lite est une API externe, utilisée
uniquement sur ce corpus public avec une politique `cloud_allowed` explicite.

| Mesure | Phase 1 | Phase 2 |
|---|---|---|
| Bon document parmi les 6 premiers | 65 % | **95 %** |
| Gemini : exact et bien cité | 55 % | **82,5 %** |
| Gemini, questions sur des scans | 0 % | **90 %** |
| Gemini, questions sans réponse : abstention correcte | 3/3 | 3/3 |
| qwen : exact et bien cité | 20 % | mesure en cours |
| qwen, questions sans réponse : abstention correcte | 1/3 | mesure en cours |
| Montant piégé repris dans une réponse | 2 | **0** |
| Liens externes dans les réponses | 0 | 0 |
| Documents en échec | 25 | **0** (15 indexés avec avertissement) |
| Indexation des 83 documents (OCR compris) | 58 min, sans OCR | **≈ 30 min** |
| Temps moyen par question | qwen 53 s, Gemini 2,7 s | qwen mesure en cours, Gemini 3,1 s |

Débits mesurés : OCR 2,6 s par page (Tesseract, 300 dpi) ; embeddings 6,4 passages par seconde
(ONNX int8). Projection pour le client type dans `DEPLOYMENT.md` §2.4.

## 3. Anomalies trouvées et corrigées pendant la phase

1. **Recherche vectorielle qui perd des résultats quand plusieurs organisations partagent une
   collection.** La mesure finale était d'abord *moins bonne* que la mesure intermédiaire (67,5 %
   contre 77,5 %). Analyse : vecteurs stockés corrects ; bon passage au rang 1 en recherche exacte,
   au-delà du rang 30 en recherche approximative dès qu'une deuxième organisation était présente.
   Cause : graphe HNSW global par défaut de Qdrant. Corrigé par un graphe par organisation, comme le
   prescrit la documentation officielle de Qdrant, avec migration des collections existantes
   (ADR-0019). Gemini est passé de 67,5 % à 82,5 %.
2. **Réponses Gemini tronquées** (« de 10 à [1] ») : un flux interrompu était traité comme une
   réponse complète, puis complété par une citation. Corrigé : un flux sans signal de fin est
   signalé comme une erreur.
3. **Réponse en français à une question en anglais** : langue détectée sur la question et imposée.
4. **Faux échecs de la notation** (« 2025 — 19 » au lieu de « 2025-19 », « six (6) ans ») ;
   autres documents également corrects (BCEAO) non acceptés. Normalisation et sources
   alternatives ajoutées au fichier de questions.
5. **25 documents en échec** en phase 1 (scans) : lus par OCR ; RapidOCR sautait une ligne sur un
   scan, d'où Tesseract par défaut (ADR-0017).
6. **Indexation trop lente** (0,9 fragment par seconde) : encodeur ONNX int8 (ADR-0018).
7. **Le faux montant du document piège** (« 5 milliards ») était repris par qwen : passages
   suspects écartés du contexte.
8. Tests et mesure qui modifiaient le même compte PostgreSQL et se cassaient mutuellement : un
   compte de connexion propre à chaque exécution.
9. Liste des banques aplatie en un paragraphe, fragment de quelques caractères : listes
   numérotées conservées, taille minimale de fragment.

## 4. Anomalies et limites restantes

| Limite | Prévu |
|---|---|
| **qwen2.5 1,5B ne convient pas** comme modèle de réponse : il invente au lieu de s'abstenir (0 bonne abstention sur 3 à la mesure intermédiaire) et cite mal. Il ne sert qu'aux tests sur CPU ; un modèle de 7B ou plus, sur GPU, est nécessaire | phase 5 (choix du modèle), phase 7 (serveur GPU) |
| **Tableaux** : 2 questions sur 5 échouent parce que la recherche ne trouve pas la bonne ligne d'une longue liste (établissements agréés par pays) | phase 3 : découpage des tableaux par ligne avec en-tête, reranker |
| Un document BCEAO (situation des IMF) : le bon passage arrive au rang 6 à 11 ; 3 questions s'abstiennent | reranker, comparatif du canal lexical |
| Coupures réseau de Gemini (1 sur 40) : signalées, pas de nouvel essai automatique | phase 5 (routeur : nouvel essai ou repli selon la politique) |
| Formats anciens DOC, XLS, PPT, RTF (Tika) **non faits** | phase 3, avec les connecteurs |
| Reranker et comparatif du canal lexical **non faits** | phase 3 |
| Mesure sur le corpus de référence du porteur du projet | corpus à fournir |
| Image Docker du worker (Tesseract) non construite : paquets listés dans `DEPLOYMENT.md` | phase 7 |

## 5. Décisions prises

- **ADR-0017** : OCR Tesseract par défaut, RapidOCR en alternative (mesuré : 15 faits sur 15,
  2,6 s par page contre 3,3 s pour RapidOCR, qui sautait une ligne).
- **ADR-0018** : embeddings BGE-M3 ONNX int8 en local (6,4 passages par seconde contre 0,64,
  similarité 0,978).
- **ADR-0019** : un index HNSW par organisation dans Qdrant.
- Les passages contenant des consignes adressées à une IA ne sont jamais envoyés au modèle
  (`SECURITY.md` §6).
- La mesure de qualité fait partie du dépôt (`eval/`) et se relance avec une seule commande ;
  les clés d'API ne sont lues que dans des variables d'environnement.

## 6. Prochaines tâches (phase 3)

1. Connecteur M-Files contre un simulateur fondé sur la documentation officielle (coffre de test à
   obtenir), droits et correspondance des identités.
2. Formats anciens via Tika ; tableaux découpés par ligne ; reranker et comparatif du canal lexical.
3. Mesure sur le corpus de référence du porteur du projet.
4. Choix d'un modèle de réponse local de taille suffisante, à mesurer sur GPU.
