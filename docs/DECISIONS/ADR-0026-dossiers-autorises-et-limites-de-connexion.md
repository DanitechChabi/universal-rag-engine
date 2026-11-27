# ADR-0026 — Dossiers indexables fixés par l'installation ; limites de connexion

- Statut : **acceptée** (phase 8, revue de sécurité, novembre 2026)
- Complète : ADR-0011 (authentification), ADR-0025 (déploiement Server)
- Références : docs/reports/SECURITE-PHASE8.md, docs/SECURITY.md §3 et §8

## Contexte

La revue de sécurité de la phase 8 a montré :

1. qu'un administrateur documentaire pouvait déclarer une source « fichiers locaux » sur
   n'importe quel dossier lisible par le service (`/`, la clé maîtresse, les modèles, le dossier
   d'une autre organisation) et en faire indexer le contenu ;
2. que des essais de mot de passe envoyés en parallèle contournaient le blocage après 5 échecs,
   et qu'aucune limite ne visait l'essai d'un même mot de passe sur de nombreux comptes, alors
   que docs/SECURITY.md l'annonçait.

## Décision

1. **Dossiers autorisés fixés par l'installation**, dans la variable d'environnement
   `URAG_LOCAL_FILES_ALLOWED_ROOTS` du service (Server : `/documents`, le dossier monté), jamais
   dans la configuration de la source. Le **connecteur** refuse toute racine hors de ces dossiers
   (après résolution des liens symboliques), à chaque instanciation : l'API à la création de la
   source (422 `source.root_not_allowed`) comme le worker à chaque usage. Sans la variable, aucune
   source locale n'est acceptée (fermé par défaut).
2. **Essais d'un même compte traités l'un après l'autre** : la ligne du compte est verrouillée
   en base (`SELECT … FOR UPDATE`) pendant la vérification ; pendant un blocage, le mot de passe
   n'est pas vérifié.
3. **Limite par adresse** : au-delà de 20 échecs en 15 minutes depuis une adresse, tous comptes
   confondus, la connexion répond 429 avec `Retry-After`, avant toute vérification. Le compte est
   fait en base (`urag_login_failures_from`, migration 0010) à partir du journal d'audit : la
   limite vaut pour tous les processus de l'API, sans service supplémentaire.

## Alternatives écartées

- **Liste de dossiers dans la configuration de l'organisation** : modifiable par un
  administrateur de l'organisation, donc par la personne même que la règle doit limiter.
- **Limitation du débit en mémoire de chaque processus** : contournable en répartissant les
  essais sur les processus, perdue au redémarrage.
- **Redis pour les compteurs** : service de plus, et licence incompatible depuis la version 7.4
  (CLAUDE.md).
- **Module de limitation de Caddy** : non inclus dans l'image officielle ; ne verrait pas les
  échecs, seulement les requêtes.

## Conséquences

- Développement et tests : la variable doit être définie (`docs/DEVELOPMENT.md` ; les tests
  autorisent le dossier temporaire du système).
- Plusieurs organisations sur un serveur : la règle est commune à l'installation ; donner à
  chacune un sous-dossier distinct et vérifier les racines déclarées. Une liste par organisation,
  fixée par le super-administrateur, reste à faire avant tout hébergement mutualisé.
- Les échecs depuis une adresse partagée (NAT d'entreprise) comptent ensemble : 20 en 15 minutes
  laisse de la marge pour les erreurs de frappe ordinaires ; réglable
  (`URAG_LOGIN_MAX_FAILURES_PER_IP`).
