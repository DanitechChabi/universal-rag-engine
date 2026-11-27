# ADR-0027 — Échanges ordinaires : réponse naturelle du modèle, sans document ni fait

- Statut : **acceptée** (phase 8, novembre 2026)
- Complète : docs/SECURITY.md §5 et §6 (réponses citées, injection de prompt)
- Références : `core/src/urag_core/rag/__init__.py` (`social_intent`, `_converse`), docs/SECURITY.md §6

## Contexte

Tout message passait par la recherche documentaire : « Bonjour » ou « Merci » obtenaient
« Les documents disponibles ne permettent pas de répondre… », après une recherche et une génération
inutiles. Le porteur du projet veut un assistant **conversationnel et authentique**, pas des
réponses préécrites, sans renoncer à la règle centrale : aucun fait sans source citée.

## Décision

1. **Reconnaissance des échanges ordinaires** (`social_intent`) : salutation, remerciement,
   au revoir, politesse, questions sur l'assistant (« qui es-tu ? », « que peux-tu faire ? »),
   en français et en anglais. Un message n'est retenu que s'il ne contient **que** ces mots (et
   aucun chiffre) : « Bonjour, quel est le taux directeur ? » reste une question documentaire.
   Aucune des 40 questions d'évaluation n'est prise pour un échange ordinaire (test).
2. **Réponse du modèle, pas un modèle de phrase** : le modèle autorisé par la politique répond
   librement, avec la conversation en cours, le prénom de l'interlocuteur, le nom de
   l'organisation et **les titres** (seulement) de quelques documents que l'utilisateur peut
   consulter, droits appliqués. Consignes : naturel, une à trois phrases, vouvoiement sauf
   tutoiement de l'utilisateur, ne pas se présenter deux fois, **n'affirmer aucun fait**.
3. **Garde-fou** : une réponse qui contient un nombre absent du message, du prénom et des titres
   est remplacée par une présentation sobre ; liens et images retirés comme ailleurs. Pas de
   recherche, pas d'extrait transmis, pas de citation ; message et réponse enregistrés dans la
   conversation ; audit `ai.conversation` (nature de l'échange seulement, jamais le texte).

## Alternatives écartées

- **Phrases préécrites** : sûres mais mécaniques ; refusées par le porteur du projet.
- **Classement de chaque message par le modèle** : un appel de plus à chaque question (plusieurs
  secondes sur CPU) et un risque de faire passer une vraie question pour une politesse.
- **Laisser le modèle documentaire répondre librement aux politesses** : sa consigne lui impose
  de répondre « documents insuffisants » ; l'assouplir affaiblirait la règle de citation.

## Conséquences

- Une salutation coûte un appel au modèle (court) ; avec un modèle externe autorisé, le
  message et les titres partent chez ce fournisseur, comme une question.
- Les petits modèles (essai sur CPU) restent moins fins dans le ton que le modèle recommandé.
