# ADR-0024 — Modèle de génération local recommandé

- Statut : **acceptée** (phase 5, novembre 2026)
- Complète : ADR-0010 (génération locale avec Ollama), ADR-0014 (routeur de modèles)
- Références : `docs/reports/COMPARAISON-MODELES-LOCAUX.md`, `docs/reports/eval-phase5-kaggle-*.json`

## Contexte

En politique « local uniquement » (le défaut), la qualité des réponses dépend entièrement du
modèle installé chez le client. Six modèles ouverts ont été comparés sur GPU (Tesla T4) avec
les mêmes extraits et la même grille que le modèle externe de référence (Gemini, 97,5 %).

## Décision

1. **Modèle recommandé : Qwen2.5 14B Instruct** (`qwen2.5:14b`, licence Apache-2.0) :
   92,5 % de réponses exactes et bien citées, abstention correcte sur les trois questions sans
   réponse, environ 9 Go de mémoire graphique en Q4_K_M.
2. **Petites cartes (8 Go)** : `qwen2.5:7b` (Apache-2.0, 90,0 %, abstention correcte).
3. Le produit **n'impose pas** de modèle : l'administrateur choisit dans l'écran « IA ». Les
   autres modèles mesurés restent utilisables, avec ces réserves documentées :
   - `qwen3:8b` (Apache-2.0, 95,0 %) a inventé une réponse à une question sans réponse ;
     à remesurer avant d'en faire un défaut ;
   - `gemma3:12b` (95,0 %) et `llama3.1:8b` sont soumis à des licences propres à leur
     éditeur, avec des restrictions d'usage : choix laissé au client, jamais embarqués par défaut.
4. Toute recommandation future passe par la même mesure (`eval/kaggle`, `eval/score_answers.py`).

## Alternatives écartées

- **gemma3:12b par défaut**, meilleur score local : licence non standard et modèle plus lent
  (10 s par question sur T4) pour un écart d'une question.
- **qwen3:8b par défaut** : meilleur rapport score/vitesse, mais une affirmation inventée sur
  trois questions sans réponse ; pour un moteur documentaire, l'abstention prime sur un point de score.
- Choisir sur un banc d'essai public généraliste : non représentatif du français administratif,
  des documents numérisés et des citations exigées ici.

## Conséquences

- `DEPLOYMENT.md` et `AI_MODELS.md` indiquent `qwen2.5:14b` (ou `qwen2.5:7b`) à télécharger.
- La vérification des citations contrôle les chiffres, pas leur sens (cas Q40) : la consigne
  du modèle et le jeu de questions sans réponse restent les garde-fous, à enrichir.
- La note sur 40 questions est grossière (2,5 points par question) : le corpus d'évaluation
  doit grandir, notamment en questions sans réponse.
