# ADR-0012 — Chiffrement des secrets

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Les clés d'API et identifiants de sources doivent être chiffrés au repos et jamais exposés (sections 5.3, 9.4, 12.1).

## Décision

AES-256-GCM (bibliothèque `cryptography`), nonce aléatoire de 12 octets, identifiant du secret et organisation en données authentifiées. Clé maîtresse **hors base** : fichier protégé (Server) ou DPAPI (Desktop). `key_version` pour la rotation. Secrets jamais renvoyés par l'API ni journalisés.

## Alternatives écartées

Chiffrement dans PostgreSQL (`pgcrypto`) : la clé transiterait dans les requêtes SQL ; coffre externe (HashiCorp Vault) : service lourd, possible plus tard pour les grands comptes.

## Conséquences

La clé maîtresse doit être sauvegardée séparément (procédure dans `DEPLOYMENT.md`) ; sa perte rend les secrets illisibles (à ressaisir).
