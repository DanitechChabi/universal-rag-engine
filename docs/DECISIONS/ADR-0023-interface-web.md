# ADR-0023 — Interface web : socle technique et règles de sécurité

- Statut : **acceptée** (phase 4, novembre 2026)
- Complète : ADR-0001 (outillage), ADR-0011 (authentification et sessions)
- Références : cahier des charges §10, docs/ARCHITECTURE.md (React + TypeScript + Vite,
  TanStack Query), docs/SECURITY.md §3 et §6

## Contexte

La phase 4 livre l'interface web du mode Server (et, plus tard, celle de l'application Desktop,
qui réutilisera le même code dans Tauri). Le cahier des charges demande une interface
professionnelle, sobre, responsive, en mode clair et sombre, avec réponse progressive, sources,
extraits, ouverture du document original, historique et annulation.

## Décision

**Outils** (versions exactes verrouillées dans `pnpm-lock.yaml`, licences MIT ou Apache-2.0) :
React 19, TypeScript 5.9, Vite 8, TanStack Query 5, React Router 8 ; tests Vitest + Testing
Library (composants) et Playwright 1.63 (parcours de bout en bout contre l'API réelle).
Gestionnaire de paquets : pnpm. Dossier : `apps/web`.

**Pas de bibliothèque de composants graphiques** : feuille de style propre, avec des jetons de
couleur, d'espacement et de typographie (modes clair et sombre). L'interface reste légère, sans
dépendance à surveiller ni licence à vérifier, et réutilisable telle quelle dans Tauri.

**Sécurité côté navigateur :**

- Même origine que l'API (`/api/v1`) : Vite relaie les requêtes en développement, Caddy en
  production. Aucune autorisation CORS.
- Session **uniquement par cookies `HttpOnly`** posés par l'API : le code JavaScript ne lit ni
  ne stocke jamais de jeton (pas de `localStorage`). Chaque requête qui modifie envoie l'en-tête
  `X-CSRF-Token` lu dans le cookie `urag_csrf`. Sur une réponse 401, une seule tentative de
  rafraîchissement, puis retour à l'écran de connexion.
- **Aucun HTML injecté** : les réponses du modèle et les extraits sont affichés comme du texte
  (échappement de React, jamais `dangerouslySetInnerHTML`) ; les références `[n]` deviennent des
  boutons vers la source. Pas d'image ni de lien externe rendus depuis une réponse (doublé côté
  API, docs/SECURITY.md §6).
- Réponse progressive par `fetch` en flux (le chat est un `POST`, que `EventSource` ne permet
  pas) ; annulation par `AbortController`.
- Politique de sécurité du contenu stricte de l'API conservée (`default-src 'self'`) : pas de
  script ni de feuille de style en ligne, pas de police ni de ressource externe.

**Textes** : en français, regroupés dans un seul fichier, pour une traduction ultérieure.

## Alternatives écartées

- **Bibliothèque de composants** (MUI, Ant Design…) : poids et surface de dépendances élevés
  pour une interface sobre ; style difficile à rendre propre au produit.
- **Jeton d'accès en mémoire ou dans `localStorage`** : exposé à un script injecté ; les cookies
  `HttpOnly` avec jeton anti-CSRF sont déjà en place côté API (ADR-0011).
- **Rendu Markdown des réponses** : surface d'injection supplémentaire ; reporté, avec une
  liste blanche stricte, si le besoin est confirmé.
- **Next.js ou rendu côté serveur** : inutile pour une application interne derrière connexion,
  et incompatible avec la réutilisation dans Tauri.

## Conséquences

- Node 22 et pnpm deviennent nécessaires pour construire l'interface (pas pour l'exécuter : les
  fichiers construits sont servis par Caddy).
- Les parcours principaux sont testés par Playwright contre la pile réelle (condition de sortie
  de la phase 4).
