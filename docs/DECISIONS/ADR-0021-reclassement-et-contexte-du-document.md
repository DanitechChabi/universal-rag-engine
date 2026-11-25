# ADR-0021 — Reclassement des candidats et contexte du document

- Statut : **acceptée** (phase 3, novembre 2026)
- Complète : ADR-0007 (recherche hybride), ADR-0018 (encodeur ONNX)
- Références : docs/AI_MODELS.md §1, mesure `docs/reports/eval-phase3-gemini.json`

## Contexte

Après la phase 2, cinq questions du corpus public échouaient alors que la bonne réponse
existait dans l'index. Le diagnostic (rang du passage contenant la réponse parmi les 30
candidats) montre deux causes distinctes :

| Question | Rang du bon passage | Cause |
|---|---|---|
| Q06 (nombre de banques au Bénin) | 8 | bon passage trouvé, mais trop bas pour les 6 transmis au modèle |
| Q20 (part de l'épargne des femmes) | 11 | idem |
| Q07 (établissements de monnaie électronique au Bénin) | au-delà de 30 | le passage ne contient ni le pays ni la date, présents plus haut dans le document |
| Q02 (encours des dépôts à fin décembre 2025) | au-delà de 30 | idem ; trois rapports trimestriels de la même série se ressemblent |

## Décision

1. **Reclassement** facultatif des 20 premiers candidats par un *cross-encoder* :
   BAAI/bge-reranker-v2-m3 (licence Apache-2.0), export ONNX quantifié int8
   (`onnx-community/bge-reranker-v2-m3-ONNX`), exécuté localement avec ONNX Runtime.
   Il s'applique **après** le filtrage des droits et la revérification auprès de la
   source : il ne lit jamais un passage que l'utilisateur ne peut pas lire. Réglage
   `rerank_backend = onnx` (défaut : `none`).
2. **Contexte du document** : titre déclaré dans le fichier (propriétés PDF ou Word, s'il est
   parlant) et lignes de titre en majuscules du début de la première page, sans
   coordonnées ni adresse. Il est rappelé dans le texte encodé de chaque passage, dans le
   texte lu par le reclassement et dans l'en-tête de l'extrait transmis au modèle (qui
   sait ainsi qu'un montant date de « fin décembre 2025 »). Un contexte contenant des
   consignes adressées à une IA est écarté.
3. **Version du traitement d'indexation** (`document_versions.pipeline_version`) : quand
   l'extraction, le découpage ou le texte encodé changent, la constante
   `PIPELINE_VERSION` augmente et les documents concernés sont réindexés à la
   synchronisation suivante, même si leur contenu n'a pas changé.

## Mesures

- Rang du bon passage avec reclassement (même index) : Q06 8 → **1**, Q20 11 → **3** ;
  les questions déjà au rang 1 le restent (Q01, Q24, Q31).
- Débit du reclassement : 20 passages courts en 0,8 s (CPU 4 cœurs).
- Effet global : voir le compte rendu de la phase 3.

## Alternatives écartées

- **Augmenter le nombre de passages transmis au modèle** : plus de bruit et de coût pour
  chaque question, sans régler les passages absents des candidats.
- **Contexte rédigé par un modèle de langue pour chaque document** (« contextual
  retrieval ») : coûteux à l'indexation sur CPU, et le résumé d'un petit modèle local peut
  être faux ; à reconsidérer avec un GPU.
- **Reclassement avant le filtrage des droits** : exclu, le modèle verrait des passages
  interdits à l'utilisateur.

## Conséquences

- Migration 0005 : `document_versions.context`, `document_versions.pipeline_version`,
  index d'unicité étendu à la version du traitement.
- Le modèle de reclassement (570 Mo) s'ajoute aux modèles à livrer avec le produit.
- Tests : unitaires (contexte, texte encodé, ordre du reclassement, modèle réel si
  présent), intégration (en-tête de l'extrait).
