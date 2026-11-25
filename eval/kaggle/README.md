# Mesurer des modèles locaux sur un GPU Kaggle

Sert uniquement au **corpus public** de mesure : aucun document d'un client ne passe par Kaggle.

1. Ici, exporter les messages et extraits que le moteur enverrait au modèle (même index, même
   reclassement que la mesure de référence) :

   ```
   uv run python eval/run_eval.py --files <corpus> --label export --embedding onnx --model-dir <bge-m3> \
       --ocr tesseract --rerank-dir <reranker> --from-dump <index.dump> \
       --chat-provider export --export-prompts prompts.json
   ```

2. Publier `prompts.json` comme jeu de données Kaggle **privé**, puis lancer `generer_reponses.py`
   comme notebook avec GPU et Internet (compte Kaggle vérifié par téléphone, sinon Kaggle n'accorde
   ni GPU ni Internet). Les modèles sont servis par Ollama, avec les réglages de la mesure locale.

3. Récupérer `answers.json` et le noter avec la même grille que les autres mesures :

   ```
   uv run python eval/score_answers.py --prompts prompts.json --answers answers.json --label phase5-kaggle
   ```

La clé d'API Kaggle n'est jamais écrite dans le dépôt : elle est lue dans la variable
d'environnement `KAGGLE_API_TOKEN`.
