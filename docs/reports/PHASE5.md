# Compte rendu — Phase 5 : IA hybride

Date : novembre 2026. Branche : `claude/phase-5-ia-hybride`, construite sur la branche de la
phase 4 (PR #5, elle-même empilée sur les PR #4 et #3).
Format imposé par la directive 27.7 du cahier des charges.

## 1. Fonctionnalités réalisées (exécutées et testées)

| Fonctionnalité (cahier des charges §9) | Où | Preuve |
|---|---|---|
| **Modèles configurés par organisation** : fournisseurs et modèles en base (tables existantes, aucune migration), modèle de l'installation utilisé à défaut, cache de 30 s invalidé à chaque modification | `ai/catalog.py`, `state.py` | `test_phase5` 01 |
| Adaptateur **« compatible OpenAI »** (vLLM, LM Studio, llama.cpp, OpenAI…) en plus d'Ollama et de Gemini : réponse progressive, jetons consommés, fin de génération | `ai/__init__.py` | `test_phase5` 01 à 05 (vrai serveur HTTP de test) |
| **Clés d'API chiffrées** (AES-GCM, ADR-0012), déchiffrées en mémoire seulement pour l'appel, jamais renvoyées par l'API ni journalisées ; aucune clé envoyée à un serveur local | `routes/ai_admin.py` | `test_phase5` 01, 02, 03 |
| Un modèle n'est proposé qu'après un **test de disponibilité** réussi | `POST /admin/ai/models/{id}/test` | `test_phase5` 01 |
| **Politique** : local uniquement (défaut), hybride, externe autorisé ; politique incohérente refusée (contrainte de la base) | `PUT /admin/ai/policy` | `test_phase5` 02, 04 |
| **Scénario 14** : choisir un modèle externe dans l'assistant quand la politique l'autorise ; avertissement avant tout envoi vers un service externe | `Assistant.tsx`, `GET /models` | `test_phase5` 03, Playwright 9 |
| **Scénario 15** : « local uniquement » coupe l'externe **à effet immédiat**, même si l'utilisateur l'a demandé | routeur, `allow_external` | `test_phase5` 04, Playwright 9 |
| **Plafonds** par jour ou par mois (jetons et coût) : dépassés, les modèles externes sont écartés et l'assistant le signale | `usage/__init__.py` | `test_phase5` 05 |
| **Consommation et coûts** : jetons et coût estimé enregistrés à chaque appel (prix par million de jetons saisis par l'administrateur) ; audit `ai.external_call` **sans contenu** | `rag._finish` | `test_phase5` 03 |
| Écran d'administration « Modèles d'IA » : politique, fournisseurs (clé masquée), modèles, plafonds et leur état, consommation du mois | `AdminAI.tsx` | Playwright 9 |
| Administration réservée aux administrateurs | `routes/ai_admin.py` | `test_phase5` 06 |
| **Adaptateur Anthropic (Claude)** par le SDK officiel : flux progressif, jetons et coût, repli côté serveur en cas de refus de sécurité, refus ou coupure signalés comme incomplets ; aucun identifiant lu dans l'environnement du serveur | `AnthropicAdapter` | `test_anthropic_adapter` (5), `test_phase5` 07 |
| **Choix du modèle local mesuré sur GPU** (Kaggle, 2 × Tesla T4) : six modèles ouverts, mêmes extraits, même notation que le moteur | `eval/kaggle`, `eval/score_answers.py` | `COMPARAISON-MODELES-LOCAUX.md`, ADR-0024 |

## 2. Tests exécutés et résultats

| Suite | Résultat |
|---|---|
| Schéma PostgreSQL | **48 vérifications passées** |
| Python : unitaires, conformité des connecteurs, intégration (PostgreSQL 16, Qdrant 1.15, Tika 3.2) | **138 passés**, 3 sautés (fonctions absentes des fichiers locaux) |
| Interface : Vitest | **2 passés** |
| **Parcours de bout en bout Playwright** contre la vraie API | **9 passés** (dont scénarios 14 et 15) |
| Style (`ruff check`, `ruff format`) | aucun écart |

Condition de sortie de la phase (`ROADMAP.md`) : **scénarios 14 et 15, tests de politique —
remplie.**

### Mesure de qualité des modèles locaux (40 questions, réponses exactes et bien citées)

| Modèle | Score | Licence |
|---|---|---|
| Gemini flash-lite (externe, référence phase 4) | 97,5 % | service payant |
| gemma3:12b | 95,0 % | Gemma Terms of Use |
| qwen3:8b | 95,0 % (une réponse inventée) | Apache-2.0 |
| **qwen2.5:14b — recommandé** | **92,5 %** | Apache-2.0 |
| qwen2.5:7b — cartes de 8 Go | 90,0 % | Apache-2.0 |
| llama3.1:8b | 87,5 % | Llama 3.1 Community License |
| mistral-nemo:12b | 80,0 % | Apache-2.0 |

## 3. Anomalies trouvées et corrigées pendant la phase

1. **Citation juste retirée quand la date est réécrite** (« 7 septembre 2026 » contre
   « 07/09/2026 » dans le document) : les six modèles locaux perdaient Q08. Les dates sont
   reconnues sous leurs différentes formes, sans rendre la vérification plus stricte
   (`test_dates_sous_une_autre_forme_equivalentes`).
2. Notebook Kaggle : l'installateur d'Ollama exige `zstd`, absent de l'image ; et un compte
   non vérifié par téléphone n'a ni GPU ni Internet (documenté dans `eval/kaggle/README.md`).

## 4. Limites restantes

| Limite | Prévu |
|---|---|
| La vérification des citations contrôle les chiffres, pas leur sens : qwen3:8b a attribué à l'UEMOA un chiffre de la Réserve fédérale (Q40) | consigne et questions sans réponse à enrichir (phase 8) |
| Mesure sur 40 questions (2,5 points par question) | corpus d'évaluation à agrandir |
| Modèles locaux mesurés hors du moteur (mêmes extraits et mêmes messages), pas encore servis par le moteur sur un serveur GPU | phase 7 (serveur GPU, tests de charge) |
| Coût estimé à partir des prix saisis par l'administrateur, pas de la facture du fournisseur | assumé |
| Export PDF/DOCX des réponses (reporté de la phase 4) | phase 8 |

## 5. Décisions prises

- **ADR-0024** : modèle local recommandé `qwen2.5:14b` (Apache-2.0), `qwen2.5:7b` sur 8 Go ;
  aucun modèle à licence propre embarqué par défaut ; toute recommandation passe par la même mesure.
- Un modèle externe n'est jamais utilisé si la politique, le plafond ou l'absence de test
  le refusent : le routeur retombe sur un modèle local, jamais l'inverse.
- L'audit des appels externes ne contient ni la question ni la réponse ni les extraits.
- Anthropic passe par son SDK officiel (licence Apache-2.0, dépendances BSD, MIT et Apache), et
  non par une couche « compatible OpenAI » : seule l'API Messages expose le repli côté serveur
  et la raison d'arrêt `refusal`.

## 6. Prochaines tâches

1. Phase 7 (Server) : Docker Compose de production, HTTPS, supervision, sauvegarde et
   restauration, tests de charge sur un serveur GPU loué.
2. Connecteur M-Files dès qu'un coffre de test est disponible.
