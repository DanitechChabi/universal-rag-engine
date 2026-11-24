# Règles de travail — Universal RAG Engine

Référence : `docs/CAHIER_DES_CHARGES.md`, en particulier la section 27 (directives
impératives). Résumé à appliquer à chaque session :

- **Langue** : documentation, messages de commit et échanges en français.
- **Phase par phase** (`docs/ROADMAP.md`). Pas de gros volume de code sans
  architecture validée ; pas de fonctionnalité cosmétique avant un moteur
  documentaire fonctionnel.
- **Une fonctionnalité n'est terminée que si elle a été exécutée et testée.**
  Chaque phase se termine par un compte rendu : fonctions réalisées, fichiers,
  tests exécutés et résultats, anomalies, décisions, suite.
- **Sécurité d'abord** : filtrage des droits dans la recherche dès le départ ;
  fermé par défaut ; `org_id` + RLS partout ; API externes désactivables et
  désactivées par défaut.
- **Ne jamais inventer** d'intégration ni de point d'accès M-Files ; s'appuyer
  sur la documentation officielle et un coffre de test.
- **Secrets** : jamais dans le code ni dans Git ; `.env.example` sans valeur
  sensible ; vérifier les fichiers avant chaque commit.
- **Décisions** : toute décision structurante = une fiche dans `docs/DECISIONS/`.
- **Licences** : aucune dépendance AGPL/SSPL dans le produit (ex. PyMuPDF, Redis ≥ 7.4).
- **Schéma** : toute modification de `database/schemas/schema.sql` doit garder
  `database/tests/test_schema.sh` au vert.
