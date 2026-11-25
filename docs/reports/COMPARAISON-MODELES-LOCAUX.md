# Comparaison des modèles de génération locaux (phase 5)

Date : 25 novembre 2026. Décision qui en découle : [ADR-0024](../DECISIONS/ADR-0024-modele-local-par-defaut.md).

## Protocole

- **Mêmes extraits pour tous** : export de la phase 4 (`run_eval.py --chat-provider export`),
  40 questions du corpus public, 6 extraits par question, reclassement activé. Seul le modèle
  qui rédige la réponse change ; la recherche n'intervient pas dans l'écart.
- **Matériel** : notebook Kaggle (`eval/kaggle/generer_reponses.py`), 2 × NVIDIA Tesla T4
  (16 Go chacune), Ollama, quantification par défaut d'Ollama (Q4_K_M), température 0,
  contexte de 8 192 jetons, 400 jetons de réponse au plus, mode « réflexion » coupé pour qwen3.
- **Notation** : `eval/score_answers.py`, c'est-à-dire **la même validation des citations que le
  moteur** et la même grille que `run_eval.py`. Les rapports détaillés sont dans
  `docs/reports/eval-phase5-kaggle-<modèle>.json`.
- Seul le corpus public a quitté l'environnement de développement ; aucune donnée client.

## Résultats

| Modèle | Licence | Réponse exacte | **Exacte et bien citée** | Questions sans réponse (abstention correcte) | Durée par question (T4) |
|---|---|---|---|---|---|
| Gemini flash-lite (externe, rappel phase 4) | service payant | 100 % | **97,5 %** | 3 / 3 | — |
| gemma3:12b | Gemma Terms of Use | 97,5 % | **95,0 %** | 3 / 3 | 10,0 s |
| qwen3:8b | Apache-2.0 | 95,0 % | **95,0 %** | **2 / 3** | 6,4 s |
| qwen2.5:14b | Apache-2.0 | 97,5 % | **92,5 %** | 3 / 3 | 8,5 s |
| qwen2.5:7b | Apache-2.0 | 95,0 % | **90,0 %** | 3 / 3 | 7,0 s |
| llama3.1:8b | Llama 3.1 Community License | 92,5 % | **87,5 %** | 2 / 3 | 5,6 s |
| mistral-nemo:12b | Apache-2.0 | 85,0 % | **80,0 %** | 3 / 3 | 5,6 s |

Aucun modèle n'a recopié le document piège ni inséré de lien externe.

## Lecture

1. **Les modèles locaux de 7 à 14 milliards de paramètres suffisent** avec ces extraits : 90 à
   95 % de réponses exactes et bien citées, contre 97,5 % pour Gemini. L'ancien essai avec
   qwen 1,5B (inutilisable) venait de la taille du modèle, pas du moteur.
2. **Erreur la plus grave : qwen3:8b invente une réponse à Q40** (« inflation prévue pour
   décembre 2027 : 2,3 % »). Le chiffre existe dans l'extrait, mais il s'agit de la croissance
   prévue par la Réserve fédérale américaine. La vérification des citations ne peut pas le
   détecter : elle contrôle que les chiffres figurent dans l'extrait cité, pas leur sens. Les
   modèles Qwen2.5 et Gemma s'abstiennent correctement sur les trois questions sans réponse.
3. **Q22 échoue pour presque tous** (réponse juste, une seule des deux sources citée), comme
   avec Gemini : c'est une limite de la question multi-documents, pas d'un modèle.
4. Avec 40 questions, **une question vaut 2,5 points** : les écarts entre gemma3, qwen3 et
   qwen2.5:14b (1 à 2 questions) ne sont pas significatifs. L'abstention correcte et la licence
   départagent.

## Anomalie trouvée et corrigée

Les six modèles échouaient à Q08 avec une réponse juste : ils recopiaient la date de la question
(« 7 septembre 2026 ») alors que l'extrait l'écrit « 07/09/2026 ». La citation était alors jugée
non justifiée et retirée. La vérification reconnaît désormais une même date écrite sous une
autre forme (« 7 septembre 2026 », « September 7, 2026 », « 07/09/2026 », « 1er janvier 2024 ») ;
la phrase de la réponse n'est pas transformée, si bien que la vérification ne devient jamais
plus stricte. Une autre date ou un autre chiffre (« 3.2973 » au lieu de « 3,2973 ») ne justifie
toujours rien. Test unitaire : `test_dates_sous_une_autre_forme_equivalentes`. Les notes
ci-dessus sont celles obtenues après correctif (gain d'une question pour chaque modèle).

## Reproduire

Voir `eval/kaggle/README.md`. La note se recalcule sans GPU :

    uv run python eval/score_answers.py --prompts prompts-phase4.json --answers answers.json --label phase5-kaggle
