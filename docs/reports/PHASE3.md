# Compte rendu — Phase 3 : connecteurs, droits et identités

Date : novembre 2026. Branche : `claude/phase-3-connecteurs`, construite sur la branche de la
phase 2 (PR #3 non encore fusionnée).
Format imposé par la directive 27.7 du cahier des charges.

**Rappel (décision Q8) :** aucun coffre M-Files n'est disponible. Le cœur est développé et testé
contre une **source simulée** qui respecte le contrat des connecteurs ; le connecteur M-Files
n'est **pas implémenté** et n'est pas déclaré opérationnel.

## 1. Fonctionnalités réalisées (exécutées et testées)

| Fonctionnalité | Où | Preuve |
|---|---|---|
| **Ouvrir le document original** (scénario 7) : droits revérifiés, 404 identique pour absent, supprimé ou interdit, fichier relu dans la source et servi sous CSP `sandbox`, types actifs (HTML…) en téléchargement, audit | `routes/documents.py` | tests 22 et 23 |
| **Identités externes** : utilisateurs, groupes et appartenances de la source recopiés à chaque synchronisation ; identité disparue ⇒ liens supprimés | `ingestion._sync_principals` | `test_phase3` 01, 08 |
| **Correspondance des comptes** (ADR-0016) : propositions automatiques (identifiant ou courriel identique, sans ambiguïté) **sans aucun droit avant confirmation** ; lier, confirmer, délier, import CSV tout ou rien ; réservé à l'administrateur d'organisation | `routes/identities.py`, migration 0003 | `test_phase3` 01, 02, 03, 05, 09 ; schéma |
| **Droits par document** depuis la source, y compris par groupe | `permissions.document_keys` | `test_phase3` 03 à 08 |
| **Refus explicites** (ADR-0020) : clé de refus prioritaire ; refus non résolu ⇒ invisible pour tous | migration 0004, `urag_doc_visible` | schéma, unitaires, Qdrant, `test_phase3` 04, 05 |
| **Droits revérifiés auprès de la source** à chaque recherche, question et ouverture (sources qui le permettent) ; source injoignable ⇒ rien n'est montré | `permissions.late_check` | `test_phase3` 03b, 03c |
| **Synchronisation incrémentale** : lots de changements, curseur enregistré dans la même transaction, reprise après coupure sans perte ni doublon (scénario 16) ; synchronisation complète de contrôle | `ingestion._sync_incremental` | `test_phase3` 06, 10 |
| **Source simulée** (paquet de développement) et **suite de conformité commune** appliquée aux fichiers locaux et à la source simulée | `connectors/simulator`, `urag_connectors_base.conformance` | 11 tests de conformité par connecteur, plus 1 test des droits effectifs |
| **Reclassement** des candidats (bge-reranker-v2-m3, ONNX int8 local), après le filtrage des droits (ADR-0021) | `core/.../rerank` | unitaires, mesure |
| **Contexte du document** (titre et date) dans le texte encodé, le reclassement et l'en-tête transmis au modèle ; écarté s'il est piégé | `extraction.document_context` | unitaires, test 06 |
| **Version du traitement d'indexation** : réindexation automatique quand le traitement change | migration 0005 | migrations, mesure |
| **Formats anciens** DOC, XLS, PPT, RTF, ODT via Apache Tika (facultatif) | `extraction.extract_with_tika` | 2 tests |
| **Étude de l'API M-Files** sur la documentation officielle (ADR-0022, proposée) | `docs/DECISIONS` | — |

## 2. Tests exécutés et résultats

| Suite | Résultat |
|---|---|
| Schéma PostgreSQL (`database/tests/test_schema.sh`) | **48 vérifications passées** |
| Tests unitaires et de conformité (`core`, `connectors`, `services/api/tests`) | **72** (dont 3 sautés : fonctions absentes des fichiers locaux) |
| Intégration, pile réelle PostgreSQL 16 + Qdrant 1.15 (+ Tika 3.2) | **41** : phase 1-2 (23), phase 3 (12), Qdrant (4), migrations (1), vrais modèles (1) |
| Style (`ruff`) | aucun écart |

Scénarios de recette couverts dans cette phase : **7** (ouvrir le document original), **12**
(changer les permissions) et **13** (accès révoqué) au niveau du document, avec une source
simulée ; **16** (reprise d'une synchronisation interrompue) pour la synchronisation
incrémentale.

### Mesure de qualité (corpus public, 40 questions)

Même corpus (83 documents BCEAO, SGG Bénin, FSB, dont 15 scans) et mêmes 40 questions,
réindexé avec le traitement de la phase 3 (contexte du document) et le reclassement.
Générateur : Gemini flash-lite (API externe, politique `cloud_allowed` sur ce corpus public).
Rapport : `docs/reports/eval-phase3-gemini.json`.

| Mesure | Phase 1 | Phase 2 | **Phase 3** |
|---|---|---|---|
| Bon document parmi les 6 premiers | 65 % | 95 % | **100 %** |
| Réponse exacte | 60 % | 85 % | **92,5 %** |
| Réponse exacte **et** citation pertinente | 55 % | 82,5 % | **87,5 %** |
| Questions sur des tableaux (exact et cité) | 40 % | 60 % | **80 %** |
| Questions sans réponse : abstention correcte | 3/3 | 3/3 | 3/3 |
| Montant piégé repris, liens externes | 0, 0 | 0, 0 | 0, 0 |
| Indexation des 83 documents (CPU 4 cœurs) | 58 min | 29 à 35 min | 42 min (réindexation, machine chargée) |

Sur les 5 échecs restants : **3 coupures réseau** de l'API Gemini (signalées comme erreur, pas
de réponse tronquée) ; **2 citations retirées** sur des réponses justes : Q29 (« 2025-19 »
contre « 2025 — 19 » lu par OCR, corrigé après la mesure, test unitaire) et Q22 (phrase qui
combine deux faits tirés de deux passages, un seul cité : la vérification reste stricte).

Une première mesure (`eval-phase3-gemini-avant-correctif.json`, 77,5 %) a révélé que la
vérification des citations ignorait le contexte du document : la date « fin décembre 2025 »
venait du contexte, la citation de réponses justes était retirée (anomalie 8).

qwen2.5 1,5B n'a pas été remesuré : la phase 2 a établi qu'il ne convient pas comme modèle de
réponse (0 abstention correcte sur 3).

## 3. Anomalies trouvées et corrigées pendant la phase

1. **Correspondances non confirmées qui donnaient des droits** : la fonction de calcul des clés
   ne vérifiait pas `verified`. Corrigé (migration 0003, test SQL).
2. **Refus explicite rendant le document invisible pour tous** : inutilisable avec une GED
   réelle. Clés de refus (ADR-0020).
3. **Route d'ouverture absente** alors que les citations y renvoyaient. Créée (scénario 7).
4. **Index sauvegardés au schéma ancien** inutilisables par la mesure : migrations appliquées
   après restauration.
5. **Un même contenu ne pouvait pas être réindexé** après une amélioration du traitement
   (index d'unicité) : version du traitement (migration 0005).
6. Un changement de droits non journalisé par la source n'est pas vu par la synchronisation
   incrémentale : synchronisation complète de contrôle documentée et disponible.
7. La CI de la phase 2 échouait (ligne trop longue, Tesseract absent) : corrigé.
8. **Citations justes retirées** : la vérification des chiffres ne regardait que le passage, pas le
   contexte du document transmis au modèle (77,5 % → 87,5 % après correction).
9. **Tirets entre chiffres** (« 2025 — 19 » en OCR, « 2025-19 » dans la réponse) : normalisés.

## 4. Anomalies et limites restantes

| Limite | Prévu |
|---|---|
| **Connecteur M-Files non implémenté** : aucun coffre de test (Q8) ; licence du paquet `mfiles-grpc`, refus explicites et droits effectifs d'un autre utilisateur à vérifier (ADR-0022) | dès qu'un coffre est disponible |
| Synchronisation complète de contrôle : déclenchement manuel ou par l'API, pas encore planifiée | phase 7 (planification des tâches) |
| Droits NTFS des fichiers locaux non lus (accès par espace seulement) | après le MVP |
| Interface d'administration des correspondances : API seulement | phase 4 |
| Comparatif du canal lexical (vecteurs creux, BM25 dans Qdrant) non fait | après la mesure sur le corpus du porteur du projet |
| Modèle de réponse local de taille suffisante non choisi | phase 5 (GPU) |

## 5. Décisions prises

- **ADR-0020** : clés de refus, règle unique `urag_doc_visible`.
- **ADR-0021** : reclassement des candidats, contexte du document, version du traitement.
- **ADR-0022** (proposée) : API gRPC pour M-Files, sous réserve de vérifications sur un coffre.
- Les correspondances proposées automatiquement ne donnent aucun droit avant confirmation.
- La source simulée est un paquet de développement, jamais livré dans le produit.

## 6. Prochaines tâches

1. Obtenir un coffre M-Files de test (compte technique de lecture, deux comptes utilisateurs,
   droits variés) pour valider ADR-0022 et implémenter le connecteur.
2. Phase 4 : interface web (chat, sources, documents, correspondance des comptes).
3. Planifier la synchronisation complète de contrôle et la purge (phase 7).
