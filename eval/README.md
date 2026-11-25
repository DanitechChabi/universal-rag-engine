# Corpus public de mesure

Mesure de la qualité des réponses sur des documents réels et publics (docs/TESTING.md §4).
Les documents ne sont **pas** versionnés : seuls la liste des sources, les empreintes, les
questions et les scripts le sont.

| Fichier | Contenu |
|---|---|
| `corpus/sources.json` | 89 documents : 21 lois et décrets du Bénin (scannés, sgg.gouv.bj), 57 documents BCEAO / UMOA (bceao.int), 11 rapports du Conseil de stabilité financière en anglais (fsb.org). Ensemble `base` (82 documents, ≈ 1 600 pages) et `volumineux` (7 documents de 140 à 1 047 pages, exclus de la mesure courante faute de GPU) |
| `corpus/manifest.lock.json` | empreinte SHA-256 et taille de chaque fichier téléchargé |
| `corpus/synthetic/` | document piégé écrit pour les tests (consigne cachée, faux montant, lien d'exfiltration) |
| `corpus/questions.json` | 40 questions avec réponse attendue, documents acceptés et passage source exact |
| `download_corpus.py` | téléchargement et vérification des empreintes |
| `run_eval.py` | indexation sur une base neuve, questions, rapport dans `docs/reports/eval-<label>.json` |

## Composition des questions

| Catégorie | Nombre | Ce qui est mesuré |
|---|---|---|
| factuel_natif | 15 | chiffres, dates, articles dans des PDF à texte natif |
| tableau | 5 | valeurs lues dans des tableaux (listes d'établissements, adjudications, rapport annuel) |
| factuel_scan | 10 | documents scannés : **sans OCR, réponse impossible** (mesure du gain de la phase 2) |
| anglais | 3 | documents et questions en anglais |
| anglais_vers_francais | 1 | question en anglais, réponse dans un document français scanné |
| multi_documents | 3 | comparaison de deux notes BCEAO |
| sans_reponse | 3 | l'information n'existe pas dans le corpus : abstention attendue |

Les questions ont été rédigées par Claude en lisant les documents (texte extrait, ou image pour
les scans). **À faire valider par échantillon** par le porteur du projet : un système évalué par
l'auteur de l'examen risque d'être jugé trop favorablement.

## Utilisation

```
python3 -I eval/download_corpus.py --dest ~/urag-corpus/files
uv run python eval/run_eval.py --files ~/urag-corpus/files --label <nom>
```

Licences : textes officiels et publications d'institutions publiques, utilisés pour des tests
internes uniquement et jamais redistribués par ce dépôt.
