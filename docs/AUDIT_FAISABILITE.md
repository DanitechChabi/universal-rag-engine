# Audit de faisabilité technique — Universal RAG Engine

Référence : cahier des charges v1.0. Date : novembre 2026.
Objet : dire ce qui est faisable tel quel, ce qui doit être ajusté, ce qui est risqué,
et ce que le projet demande en temps, en matériel et en accès avant la phase 0.

Les chiffres de durée et de performance sont des **ordres de grandeur** à confirmer
par des mesures (phase 1 et tests de charge). Rien ici n'a encore été testé sur un
serveur M-Files ou sur le matériel cible.

---

## 1. Verdict

**Le projet est techniquement faisable.** Toutes les briques demandées existent, sont
matures et ont des licences compatibles avec une vente du logiciel (section 7).
Un produit de ce type (RAG on-premise multi-sources) est déjà proposé par plusieurs
éditeurs, ce qui confirme que rien n'est hors de portée.

Mais **il n'est pas faisable tel quel dans un délai court**, pour trois raisons :

1. **Le périmètre du MVP est celui d'un produit complet** : deux modes d'installation,
   un connecteur GED avec reproduction des droits, OCR, routeur multi-fournisseurs,
   administration, sauvegarde, licences, tests de charge. C'est un travail de
   **9 à 15 mois** pour un développeur aidé de Claude Code (section 8).
2. **Trois points sont réellement difficiles** : la reproduction des droits M-Files,
   le mode Desktop sans installation manuelle, et la génération locale simultanée
   pour 30 utilisateurs. Ils doivent être prototypés tôt.
3. **Quelques choix de la pile technique posent problème** (Celery et Redis sous
   Windows, Redis pour un produit vendu, Java pour Tika en Desktop). Des
   remplacements simples existent (section 4).

Recommandation : lancer la phase 0 avec les 8 ajustements de la section 4, et
**inverser les phases 6 (Desktop) et 7 (Server)**.

---

## 2. Audit de l'environnement (directive 27.2)

| Élément | Constat |
|---|---|
| Dépôt `universal-rag-engine` | Vide (aucun commit). Rien à préserver ni à reprendre. |
| Python | 3.13 disponible |
| Node / pnpm | Node 22, pnpm 10 : suffisant pour React + TypeScript + Vitest |
| Rust / Cargo | 1.97 : suffisant pour compiler Tauri |
| PostgreSQL | Client et serveur 16 installables ; déjà utilisé avec succès dans StopAddict |
| Java | Présent : Apache Tika peut être testé |
| LibreOffice | Présent : utile pour convertir DOC/XLS/PPT anciens si besoin |
| Docker | Client présent, **démon arrêté** dans cet environnement : à démarrer pour la phase 1 |
| Ollama | Absent ; installable (ollama.com joignable) |
| Hugging Face | Joignable : téléchargement de BGE-M3 et des rerankers possible |
| GPU | **Aucun** dans l'environnement cloud : seuls de petits modèles tourneront ici (CPU) |
| M-Files | **Aucun accès** : bloquant pour valider le connecteur (section 5.1) |

Composants réutilisables : la signature Ed25519 et la vérification de signature
écrites pour StopAddict peuvent servir de base au fichier de licence signé.

Point d'attention : l'environnement cloud n'a ni GPU ni M-Files. Il permet de
développer et tester le cœur (ingestion, recherche, RAG, permissions, API, interface),
pas de valider les performances ni le connecteur M-Files.

---

## 3. Faisabilité par bloc

Légende : 🟢 faisable sans difficulté particulière · 🟡 faisable avec un ajustement
ou une étude · 🔴 risque élevé, à prototyper en premier.

| Bloc | Avis | Commentaire |
|---|---|---|
| API FastAPI, authentification, rôles | 🟢 | Classique. Hachage Argon2, sessions courtes + jeton de rafraîchissement. |
| Modèle de données PostgreSQL | 🟢 | `org_id` partout dès le départ ; migrations Alembic. |
| Connecteur fichiers locaux | 🟢 | Exploration, empreintes, détection des changements : simple. Partages réseau Windows à tester. |
| Extraction PDF / DOCX / XLSX / PPTX / HTML | 🟢 | Bibliothèques Python matures ; Tika pour les formats anciens. |
| Formats anciens DOC / XLS / PPT, RTF | 🟡 | Tika (Java) ou conversion LibreOffice. Poids à arbitrer en Desktop. |
| OCR des scans | 🟡 | PaddleOCR donne de bons résultats en français mais est lourd à empaqueter sous Windows. Voir ajustement 4. |
| Tableaux et structure | 🟡 | Faisable correctement pour les PDF natifs et Office ; limité sur les scans complexes. Qualité à mesurer sur un corpus réel. |
| Découpage (chunking) configurable | 🟢 | Découpage par titres et paragraphes, avec la page conservée. |
| Embeddings BGE-M3 | 🟢 | Multilingue, bon en français, licence MIT. Lent sur CPU pour de gros volumes. |
| Qdrant | 🟢 | Filtres de sécurité dans la requête ; isolation par organisation. |
| Recherche lexicale | 🟡 | PostgreSQL ne fait pas de BM25 natif. Voir ajustement 5. |
| Recherche hybride + reranking | 🟢 | Fusion des classements (RRF) puis reranker (bge-reranker). |
| Moteur RAG avec citations | 🟢 | Citations vérifiables par construction (identifiants de fragments contrôlés après génération). |
| Contrôle des permissions dans la recherche | 🟢 | Filtre appliqué dans Qdrant et PostgreSQL **avant** le classement. |
| **Reproduction des droits M-Files** | 🔴 | Le point le plus difficile du projet. Voir 5.1. |
| Connecteur M-Files (contenu, métadonnées, versions) | 🟡 | Faisable avec l'API officielle, mais impossible à valider sans coffre de test. |
| Model Router, adaptateurs IA | 🟢 | Ollama, Claude, Gemini, OpenAI : API documentées. Un adaptateur « compatible OpenAI » couvre aussi vLLM et LM Studio. |
| Politiques local / hybride / cloud | 🟢 | Règle appliquée dans le routeur : refus par défaut, jamais de bascule vers le cloud si interdit. |
| Suivi des coûts et limites | 🟢 | Les fournisseurs renvoient le nombre de tokens. |
| Protection contre l'injection de prompt | 🟡 | Ne se résout jamais à 100 %. Risque fortement limité car le MVP ne donne **aucune action** au modèle. Voir 5.4. |
| Interface web React | 🟢 | Volume de travail important mais sans difficulté technique. |
| **Mode Desktop sans installation manuelle** | 🔴 | Faisable, mais c'est le packaging le plus lourd du projet. Voir 5.2. |
| Mode Server Docker Compose | 🟢 | La pile tourne naturellement en conteneurs. |
| **30 utilisateurs, 5 à 8 générations locales simultanées** | 🔴 | Dépend du GPU et du modèle ; demande vLLM plutôt qu'Ollama. Voir 5.3. |
| Supervision, logs structurés | 🟢 | Métriques Prometheus, logs JSON. |
| Sauvegarde / restauration | 🟢 | `pg_dump` + instantanés Qdrant + fichier de configuration chiffré. |
| Licences signées, activation hors ligne | 🟢 | Fichier signé Ed25519, vérifié localement ; déjà fait pour StopAddict. |
| LDAP / Active Directory | 🟡 | Prévu « plus tard », mais en pratique **nécessaire pour M-Files** (voir 5.1). |

---

## 4. Ajustements recommandés à la pile technique

À consigner chacun dans un ADR (`docs/DECISIONS/`) pendant la phase 0.

### Ajustement 1 — Remplacer Celery + Redis par une file de tâches PostgreSQL

- **Celery ne prend plus officiellement en charge Windows**, et **Redis n'a pas de
  version officielle Windows** : bloquant pour le mode Desktop.
- **Licence de Redis** : depuis la version 7.4, Redis n'est plus sous licence libre
  permissive (RSAL/SSPL, puis option AGPL en version 8). L'embarquer dans un
  logiciel vendu sur site pose une question juridique. Valkey (BSD) le remplacerait,
  mais n'a pas non plus de version Windows.
- **Solution** : une file de tâches dans PostgreSQL (`SELECT … FOR UPDATE SKIP
  LOCKED`), maison ou via une bibliothèque légère. Elle fonctionne partout,
  supprime deux services, et reste transactionnelle avec les données. Elle suffit
  largement pour 30 utilisateurs et l'indexation de quelques centaines de milliers
  de documents.

### Ajustement 2 — Un seul socle de données pour les deux modes

PostgreSQL et Qdrant dans les deux modes, plutôt qu'une version allégée (SQLite)
pour le Desktop : un seul code à tester. En Desktop, ils sont **embarqués et lancés
par l'application** (binaires portables de PostgreSQL pour Windows, binaire Qdrant),
sans Docker.

### Ajustement 3 — Orchestration RAG interne, sans LlamaIndex dans le cœur

Le filtrage des permissions doit être au cœur de la recherche, et vérifiable par
des tests. Un framework RAG ajoute des couches qui changent souvent et rendent ce
contrôle moins lisible. Recommandation : un orchestrateur interne simple (quelques
centaines de lignes), en réutilisant seulement des pièces isolées (extracteurs,
découpeurs) si elles apportent quelque chose.

### Ajustement 4 — OCR : RapidOCR (modèles PaddleOCR au format ONNX)

Mêmes modèles de reconnaissance que PaddleOCR, mais exécutés avec ONNX Runtime,
beaucoup plus léger à installer sous Windows et sans PaddlePaddle. Tesseract
(langue française) reste une solution de secours. Le choix final se fait sur un
échantillon de vrais scans.

### Ajustement 5 — Recherche lexicale : vecteurs « sparse » BGE-M3 + PostgreSQL

- BGE-M3 produit aussi des poids lexicaux (vecteurs creux) : Qdrant les stocke à
  côté des vecteurs denses et fait la recherche hybride en une seule requête, avec
  les mêmes filtres de sécurité.
- Pour les **identifiants exacts** (numéros de dossier, références de contrat,
  montants), PostgreSQL avec `pg_trgm` et la recherche plein texte française, car
  les embeddings retrouvent mal les chaînes exactes.

### Ajustement 6 — Génération serveur : vLLM en option, via l'adaptateur « compatible OpenAI »

Ollama est idéal pour le Desktop et pour démarrer. Pour 5 à 8 générations
simultanées sur un GPU, vLLM tient beaucoup mieux la charge (traitement par lots
continu). Aucun code spécifique : vLLM expose une API compatible OpenAI.

### Ajustement 7 — Extraction : bibliothèques Python d'abord, Tika pour le reste

`pypdfium2`, `python-docx`, `openpyxl`, `python-pptx` couvrent les formats
prioritaires avec les numéros de page. Tika (Java) seulement pour DOC, XLS, PPT,
RTF et les formats rares : en Server dans un conteneur, en Desktop avec un Java
minimal embarqué (environ 50 Mo) ou désactivé. **Éviter PyMuPDF** : sa licence
AGPL est incompatible avec un logiciel fermé vendu, sauf licence commerciale.

### Ajustement 8 — Ordre des phases : Server avant Desktop

Les phases 1 à 5 se développent naturellement sur la pile Docker, qui est déjà
le mode Server. Le Desktop demande un empaquetage spécifique (service Python
embarqué, bases embarquées, installateur, mises à jour) : le faire en dernier évite
de l'empaqueter plusieurs fois pendant que le cœur change. Les clients visés
(banques, assurances, administrations) achèteront d'abord le mode Server.

---

## 5. Les quatre risques majeurs

### 5.1 Reproduction des droits M-Files 🔴

**Ce qui le rend difficile :**
- M-Files combine plusieurs mécanismes : listes de contrôle d'accès par objet,
  listes nommées réutilisables, et **permissions dépendant des métadonnées**
  (« pseudo-utilisateurs » : par exemple « le responsable du dossier », défini par
  une propriété du document). Ces dernières changent dès qu'une métadonnée change.
- Les utilisateurs et groupes M-Files sont souvent synchronisés depuis Active
  Directory. **Pour appliquer les droits M-Files, il faut savoir quel utilisateur
  M-Files correspond à chaque utilisateur de la RAG.** Sans LDAP/AD ou une table de
  correspondance fiable, c'est impossible. Le cahier des charges repousse LDAP/AD à
  plus tard : c'est une contradiction à corriger.

**Approche recommandée, « fermée par défaut » :**
1. À l'indexation, recopier les droits calculés (utilisateurs et groupes autorisés)
   dans chaque fragment ; un document dont les droits sont incertains n'est visible
   par personne.
2. À chaque question, **revérifier auprès de M-Files** les droits de l'utilisateur
   sur les quelques documents retenus avant de générer la réponse. Les droits
   recopiés servent de pré-filtre rapide ; M-Files reste la référence.
3. Resynchroniser régulièrement les droits, pas seulement le contenu.

**Interfaces M-Files à étudier** (sans rien supposer avant d'avoir la documentation
de la version du client) : le service web REST (MFWS), l'API COM / .NET, et l'API
gRPC des versions récentes. Le choix dépend de la version et de l'installation du
client.

**Prérequis bloquant :** un coffre M-Files de test, avec un compte technique et des
utilisateurs aux droits différents. Sans cela, le connecteur peut être écrit et
testé sur une simulation, mais **pas déclaré opérationnel** (directive 27.5). Si
Archivexa intègre déjà M-Files chez des clients, c'est le meilleur point d'accès.

**Point concurrentiel :** M-Files propose son propre assistant IA intégré (Aino).
L'argument différenciant de ce projet doit donc être le multi-sources, le
fonctionnement 100 % local et l'indépendance vis-à-vis des fournisseurs.

### 5.2 Mode Desktop « sans rien installer » 🔴

Ce que l'installateur Windows doit embarquer ou installer :

| Composant | Taille approximative |
|---|---|
| Application Tauri + interface | < 20 Mo |
| Service Python empaqueté (FastAPI, extraction, ONNX Runtime) | 300 à 600 Mo |
| PostgreSQL portable | ≈ 200 Mo |
| Qdrant | ≈ 50 Mo |
| Modèles d'embedding + reranker + OCR | ≈ 1,5 à 2,5 Go |
| Ollama + un modèle de langage 3 à 8 milliards de paramètres | 2 à 6 Go (téléchargé au premier lancement) |

Soit **2 à 3 Go installés, plus le modèle de langage**. C'est faisable mais lourd.

**Limite matérielle :** sur un PC de bureau typique (8 Go de mémoire, sans GPU,
comme l'EliteBook), faire tourner en même temps PostgreSQL, Qdrant, l'OCR, les
embeddings et un modèle de langage sera lent et à la limite de la mémoire. Il faut
**16 Go de mémoire au minimum** pour le Desktop avec IA locale, ou utiliser une API
externe pour la génération (si la politique l'autorise).

**Coût caché :** un certificat de signature de code Windows est nécessaire pour un
logiciel vendu (sinon Windows affiche un avertissement de sécurité à l'installation).

### 5.3 Performances serveur 🔴

- La cible (5 à 8 générations simultanées sur un GPU de 24 à 32 Go) est réaliste
  avec un modèle d'environ 8 à 14 milliards de paramètres quantifié et vLLM, mais
  **doit être mesurée** : la longueur du contexte RAG (plusieurs pages d'extraits)
  pèse beaucoup sur la mémoire du GPU.
- Les embeddings et le reranker partagent le GPU avec la génération : prévoir une
  file d'attente et des limites, comme le demande le cahier des charges.
- La recherche en moins de 3 secondes (hors génération) est réaliste jusqu'à
  plusieurs millions de fragments sur un SSD.
- Le temps d'indexation initiale sera le vrai sujet chez le client : un gros fonds
  scanné (OCR) peut prendre des jours. Il faut le mesurer en phase 2 et l'annoncer.

### 5.4 Injection de prompt et fuite de données 🟡

- Le MVP ne donne **aucun outil ni aucune action** au modèle : un document piégé
  ne peut ni lancer d'action, ni lire une clé (les clés ne sont jamais dans le
  contexte du modèle), ni contourner les droits (filtrés avant la génération).
- Risques restants : une réponse trompeuse, ou une fuite par l'affichage
  (lien ou image externe insérés dans la réponse). Parades : extraits encadrés comme
  données, interdiction d'afficher des images ou liens externes générés, citations
  vérifiées par identifiant.
- Fuite entre utilisateurs : le cache ne doit jamais être partagé entre personnes ;
  les permissions sont revérifiées à chaque question, y compris dans une
  conversation existante.

---

## 6. Points du cahier des charges à préciser

1. **LDAP / Active Directory** : à remonter dans le MVP si M-Files est dans le MVP
   (au minimum une table de correspondance utilisateurs RAG ↔ utilisateurs M-Files).
2. **Multi-organisations** : en installation sur site, un serveur sert en général
   une seule organisation. Recommandation : `org_id` partout dans les données et les
   filtres (sécurité), mais une seule organisation dans l'interface du MVP.
3. **Lien vers le document original** : pour M-Files, ouvrir le document demande
   un lien M-Files (client lourd ou web) que l'utilisateur doit pouvoir ouvrir avec
   ses propres droits. À préciser selon l'installation du client.
4. **Langues** : français et anglais pour le MVP (BGE-M3 et les modèles cités les
   couvrent bien).
5. **Conservation des conversations** : durée par défaut à fixer (elles contiennent
   des extraits de documents confidentiels).
6. **Volume de référence** : combien de documents et de pages pour le premier client
   type ? Ce chiffre dimensionne tout (disque, temps d'indexation, GPU).

---

## 7. Licences des composants (produit vendu)

| Composant | Licence | Avis |
|---|---|---|
| FastAPI, React, Tauri, Vite, Vitest, Playwright | MIT / Apache 2.0 | OK |
| PostgreSQL | PostgreSQL (permissive) | OK |
| Qdrant | Apache 2.0 | OK |
| Ollama | MIT | OK |
| vLLM | Apache 2.0 | OK |
| Apache Tika | Apache 2.0 | OK |
| PaddleOCR / RapidOCR | Apache 2.0 | OK |
| BGE-M3, bge-reranker | MIT | OK |
| Celery | BSD | OK, mais non retenu (Windows) |
| Redis 7.4 et plus | RSAL / SSPL / AGPL | **À éviter** dans un produit vendu |
| PyMuPDF | AGPL ou commerciale | **À éviter** (pypdfium2 à la place) |
| Modèles Qwen | Apache 2.0 pour la plupart, licence propre pour certaines tailles | À vérifier modèle par modèle |
| Modèles Llama | Licence Meta (conditions d'usage) | Utilisable, conditions à respecter |
| Modèles Gemma | Conditions Google Gemma | Utilisable, conditions à respecter |

Une liste complète des dépendances et licences sera tenue à jour (livrable 29).

---

## 8. Charge de travail estimée

Pour un développeur à temps plein aidé de Claude Code, avec accès aux environnements
de test. Ordre de grandeur, à recaler après la phase 1.

| Phase | Durée estimée | Condition |
|---|---|---|
| 0 — Cadrage, ADR, schémas, plan de tests | 2 à 3 semaines | — |
| 1 — Prototype RAG (ingestion, Qdrant, recherche, citations, permissions de base) | 3 à 5 semaines | — |
| 2 — Moteur documentaire (OCR, versions, incrémental, erreurs) | 4 à 6 semaines | Corpus de vrais documents |
| 3 — Connecteurs local + M-Files + droits | 6 à 10 semaines | **Coffre M-Files de test** |
| 4 — Interface web | 6 à 8 semaines | — |
| 5 — IA hybride (routeur, Ollama, 1 fournisseur, politiques, coûts) | 3 à 4 semaines | Une clé d'API pour les tests |
| 7 — Server (Docker, supervision, sauvegarde, tests de charge) | 4 à 6 semaines | **Machine avec GPU** pour les mesures |
| 6 — Desktop (Tauri, services embarqués, installateur, mises à jour) | 6 à 10 semaines | PC Windows 11 de test |
| 8 — Validation, sécurité, documentation, licences | 4 à 8 semaines | Utilisateurs pilotes |
| **Total** | **≈ 9 à 15 mois** | |

**Première démonstration utile** (fin de phase 1, environ 5 à 8 semaines) : on
dépose des PDF et des Word, on pose des questions, on obtient des réponses avec
citations, et un utilisateur ne voit que ses documents.

---

## 9. Budget et accès nécessaires

Le développement peut démarrer **sans dépense** : briques libres, petits modèles
sur CPU, offres gratuites des API pour les essais (à vérifier selon le fournisseur).
Les dépenses arrivent plus tard :

| Besoin | Quand | Remarque |
|---|---|---|
| Coffre M-Files de test | Phase 3 | Via Archivexa ou un client partenaire, si possible |
| Machine avec GPU (24 Go et plus) | Phase 7 | Location à l'heure suffisante pour les tests de charge |
| Clé d'API (Claude, Gemini ou OpenAI) | Phase 5 | Offres gratuites ou petits montants pour les tests |
| Certificat de signature de code Windows | Avant la première vente Desktop | Abonnement annuel |
| PC Windows 11 avec 16 Go de mémoire | Phase 6 | Pour valider le Desktop |

---

## 10. Prochaines étapes proposées

1. Valider ou refuser les 8 ajustements (section 4) et les 6 précisions (section 6).
2. Phase 0 : créer les documents de référence demandés (27.4) — architecture,
   base de données, sécurité, connecteurs, modèles IA, déploiement, feuille de
   route, tests — et un ADR par décision.
3. Rassembler un **corpus de test** : 50 à 200 documents représentatifs (PDF natifs,
   Word, Excel, scans), anonymisés ou publics, avec 30 à 50 questions et leurs
   réponses attendues pour mesurer la qualité.
4. Demander dès maintenant l'accès à un coffre M-Files de test, car c'est le délai
   le plus long et le plus incertain.
