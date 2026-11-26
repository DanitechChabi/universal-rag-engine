# ADR-0025 — Déploiement Server : images, réseau, secrets, sauvegarde, supervision

- Statut : **acceptée** (phase 7, novembre 2026)
- Complète : ADR-0003 (file de tâches en base), ADR-0012 (chiffrement des secrets), ADR-0013 (Server avant Desktop)
- Références : docs/DEPLOYMENT.md, `infrastructure/`, docs/reports/PHASE7.md

## Contexte

Le mode Server s'installe chez le client, souvent sur un serveur du réseau local, parfois sans
accès à Internet, administré par un prestataire informatique et non par un spécialiste. Il doit
être installable, sauvegardable, restaurable et supervisable sans dépendre d'un service en ligne.

## Décision

1. **Deux images.** `urag-app` (API, worker et outil `urag-admin`, Tesseract compris), compte non
   privilégié (uid 10001), dépendances de production seulement ; `urag-web` : Caddy (Apache-2.0)
   avec l'interface construite. Images de base surchargeables (miroirs). Le certificat d'un
   proxy d'entreprise sert à la construction seulement (secret BuildKit), jamais dans l'image.
2. **HTTPS par Caddy**, seul port publié. Par défaut, autorité de certification propre au serveur
   (réseau local, aucune dépendance externe), dont le certificat racine est installé sur les
   postes ; sinon le certificat de l'entreprise. Interface servie avec une CSP stricte ; seul
   `/api/*` est relayé, si bien que `/metrics` et la documentation interne ne sont pas publiés.
3. **Deux réseaux.** PostgreSQL, Qdrant et Tika sur un réseau Docker **sans accès à Internet** ;
   l'API, le worker et Ollama ont une sortie (fournisseurs externes si la politique les autorise,
   téléchargement des modèles).
4. **Secrets.** Générés à l'installation dans `infrastructure/.env` (root, 600), utilisés par
   Compose pour les substitutions seulement : chaque conteneur ne reçoit que les siens (le mot
   de passe du superutilisateur PostgreSQL n'est donné qu'à PostgreSQL). Clé maîtresse dans un
   fichier lisible par le seul compte de l'application ; **jamais dans les sauvegardes** ; export
   séparé chiffré par phrase de passe. Mots de passe jamais sur une ligne de commande.
5. **Migrations explicites**, pas au démarrage de l'API : faites par `install-server.sh` et
   `upgrade.sh`, après une sauvegarde vérifiée obligatoire (plusieurs processus de l'API qui
   migreraient en même temps au démarrage, sans sauvegarde préalable, sont écartés).
6. **Sauvegarde vérifiée** : `pg_dump` (format personnalisé) et instantanés Qdrant, empreintes
   SHA-256, restauration automatique dans une base temporaire et comparaison des lignes avant de
   marquer la sauvegarde « vérifiée ». Restauration en deux étapes (« prepare », puis « confirm »
   dans l'heure), refusée si la clé maîtresse du serveur n'est pas celle de la sauvegarde.
7. **Supervision sans contenu** : `/metrics` Prometheus interne, par modèle de route (jamais un
   chemin réel ni un paramètre) ; agrégats lus en base par la fonction `urag_metrics()` (droits
   de maintenance, nombres seulement) ; journaux JSON en rotation ; sondes de santé de l'API et
   du worker.

## Alternatives écartées

- **Kubernetes / Helm** : disproportionné pour un serveur unique chez une PME ou une
  administration ; Compose suffit et reste lisible par un prestataire.
- **Nginx ou Traefik** : possibles, mais Caddy fournit l'autorité interne et le renouvellement
  des certificats sans configuration supplémentaire.
- **Reconstruire l'index Qdrant depuis PostgreSQL au lieu de le sauvegarder** : réencoder des
  millions de fragments prend des jours sur CPU (docs/DEPLOYMENT.md §2.4) ; l'instantané se
  restaure en secondes. La reconstruction reste possible en dernier recours.
- **Secrets Docker** : en Compose sans Swarm, ce sont de simples montages de fichiers, sans
  gestion du propriétaire ; aucun gain sur un `.env` en 600 réservé à root.
- **Let's Encrypt par défaut** : exige que le serveur soit joignable depuis Internet, ce qui est
  rarement souhaitable pour un moteur documentaire interne ; reste possible en adaptant le
  Caddyfile (nom public, directive `tls` retirée).

## Conséquences

- Les dossiers de documents sont montés en lecture seule et doivent être lisibles par l'uid 10001.
- La limite de générations simultanées (`max_concurrency`) s'entend **par processus de l'API** ;
  au-delà, Ollama ou vLLM mettent eux-mêmes en file. Le total est donc `processus × limite`.
- Chaque processus de l'API charge ses propres modèles d'encodage et de reclassement
  (≈ 2,5 Go) : leur nombre est fixé selon la mémoire à l'installation, et les recherches sont
  admises dans une file bornée (refus 503 au-delà), mesures à l'appui (docs/reports/PHASE7.md).
- Le relais HTTPS et la base n'étant pas chiffrés entre eux sur le réseau interne de Docker, le
  serveur hôte fait partie du périmètre de confiance (comme pour tout service local).
