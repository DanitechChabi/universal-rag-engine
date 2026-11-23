# ADR-0011 — Authentification et sessions

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Section 11.3 : hachage sécurisé, sessions sécurisées, expiration, protection contre les tentatives répétées ; routes `/auth/refresh` prévues.

## Décision

- Argon2id ; longueur minimale 12.
- Jeton d'accès signé de 15 minutes + jeton de rafraîchissement opaque, **haché** en base, **rotatif** ; réutilisation ⇒ révocation de la famille.
- Web : cookies `HttpOnly`, `Secure`, `SameSite=Strict` + jeton anti-CSRF. Desktop : `127.0.0.1` + secret de démarrage.
- Verrouillage progressif ; même message pour compte inconnu et mauvais mot de passe.
- Interface d'authentification extensible pour LDAP / Active Directory (après le MVP).

## Alternatives écartées

Sessions serveur pures (simple mais une lecture base à chaque requête) ; jetons longs sans rotation (révocation difficile).

## Conséquences

Révocation rapide (15 minutes au plus pour un jeton d'accès, immédiate pour le rafraîchissement) sans lecture base à chaque requête.
