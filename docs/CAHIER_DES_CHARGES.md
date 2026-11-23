# Cahier des charges fonctionnel et technique — Universal RAG Engine

**Plateforme universelle d'intelligence documentaire – Desktop & On-Premise Server**

- Version : 1.0
- Statut : Document de référence pour la conception et le développement
- Nature du projet : Logiciel professionnel d'intelligence documentaire basé sur la technologie RAG (Retrieval-Augmented Generation)
- Cible : Entreprises, banques, assurances, administrations, cabinets professionnels et organisations disposant de volumes documentaires importants.

> Ce document est la reproduction fidèle du cahier des charges v1.0 fourni par le porteur du projet.
> Les ajustements issus de l'audit de faisabilité ne le modifient pas : ils sont consignés dans
> `docs/AUDIT_FAISABILITE.md` et dans les fiches de décision `docs/DECISIONS/`.

---

## 1. Présentation générale du projet

### 1.1. Contexte

Les organisations produisent, reçoivent et conservent quotidiennement des quantités importantes de documents : contrats, dossiers administratifs, dossiers clients, pièces justificatives, correspondances, rapports, factures, archives numérisées, documents techniques et documents réglementaires.

Ces documents sont généralement dispersés entre plusieurs environnements :

- Systèmes de gestion électronique de documents (GED).
- Solutions de gestion des archives.
- Serveurs de fichiers internes.
- Ordinateurs des collaborateurs.
- Espaces de stockage partagés.
- Plateformes collaboratives.
- Bases documentaires spécialisées.

Les utilisateurs rencontrent plusieurs difficultés :

- Recherche documentaire chronophage.
- Difficulté à retrouver des informations précises.
- Nécessité d'ouvrir plusieurs documents pour obtenir une réponse.
- Absence de vision transversale sur les informations.
- Difficulté à exploiter les métadonnées documentaires.
- Répétition des mêmes recherches.
- Dépendance aux connaissances individuelles des collaborateurs.

Les moteurs de recherche classiques reposent principalement sur des mots-clés et ne comprennent pas toujours le sens des questions formulées en langage naturel.

Les modèles d'intelligence artificielle générative permettent de dépasser certaines de ces limites, mais leur utilisation dans les organisations pose des questions de confidentialité, de souveraineté des données et de coûts.

### 1.2. Solution proposée

Le projet consiste à développer une plateforme universelle d'intelligence documentaire fondée sur l'architecture RAG.

La plateforme devra pouvoir se connecter à différentes sources documentaires, extraire les informations pertinentes, les indexer et permettre aux utilisateurs d'interroger leurs documents en langage naturel.

Elle devra être indépendante :

- Du système de gestion documentaire utilisé.
- Du fournisseur de modèle d'intelligence artificielle.
- Du système d'exploitation, dans les limites des plateformes supportées.
- Du mode de déploiement.

La solution devra fonctionner selon deux modes :

- **Mode Desktop** : application installée sur un ordinateur et capable de traiter des documents localement.
- **Mode Server** : installation sur un serveur de l'organisation, accessible depuis plusieurs postes du réseau local.

La plateforme devra également proposer un fonctionnement hybride permettant d'utiliser des modèles IA locaux ou des fournisseurs externes via API.

### 1.3. Vision du produit

Créer une plateforme permettant à une organisation de disposer d'un assistant intelligent unique pour exploiter l'ensemble de ses ressources documentaires, sans être obligée de remplacer ses logiciels existants.

Le logiciel doit agir comme une couche intelligente située au-dessus des systèmes documentaires existants.

Il ne doit pas devenir une nouvelle GED ni remplacer les systèmes de conservation des documents.

Il doit permettre de comprendre, rechercher, analyser et exploiter les informations contenues dans ces systèmes.

### 1.4. Objectifs généraux

1. Centraliser l'accès intelligent à plusieurs sources documentaires.
2. Permettre des recherches en langage naturel.
3. Fournir des réponses fondées sur les documents réellement disponibles.
4. Afficher les sources et les références utilisées.
5. Respecter les droits d'accès aux documents.
6. Réduire le temps consacré à la recherche documentaire.
7. Permettre l'analyse de plusieurs documents simultanément.
8. Proposer une infrastructure indépendante du cloud.
9. Permettre l'installation sur un ordinateur ou un serveur.
10. Offrir une architecture extensible à de nouveaux connecteurs et modèles IA.
11. Permettre la commercialisation du logiciel auprès de plusieurs organisations.

---

## 2. Périmètre du projet

### 2.1. Fonctionnalités incluses

La première version devra intégrer :

- Gestion des utilisateurs.
- Authentification.
- Gestion des rôles et permissions.
- Gestion des sources documentaires.
- Connecteur M-Files.
- Connecteur de fichiers locaux.
- Extraction documentaire.
- OCR.
- Indexation documentaire.
- Gestion des embeddings.
- Recherche vectorielle.
- Recherche lexicale.
- Recherche hybride.
- Moteur RAG.
- Interface conversationnelle.
- Citations documentaires.
- Historique des conversations.
- Gestion des modèles IA.
- Routeur de modèles.
- Configuration des API externes.
- Configuration des modèles locaux.
- Tableau de bord administratif.
- Journalisation.
- Surveillance des tâches d'indexation.
- Installation Desktop.
- Installation Server.
- Gestion des sauvegardes.
- Documentation technique et utilisateur.

### 2.2. Fonctionnalités exclues du MVP

Les éléments suivants ne doivent pas retarder la première version :

- Édition collaborative des documents.
- Remplacement d'une GED existante.
- Signature électronique.
- Workflow complet de validation documentaire.
- Archivage légal et gestion de la durée de conservation.
- Envoi automatique de documents à des tiers.
- Modification automatique des documents originaux.
- Agent autonome capable d'exécuter des actions dans les systèmes métiers.
- Analyse prédictive avancée.
- Application mobile native.

Ces fonctionnalités pourront être étudiées dans des versions ultérieures.

---

## 3. Architecture générale

### 3.1. Principe architectural

Le logiciel devra être construit selon une architecture modulaire.

Le moteur RAG devra être indépendant de l'interface, des connecteurs et des fournisseurs d'IA.

Les différents modules devront communiquer à travers des interfaces clairement définies.

L'objectif est de pouvoir remplacer un composant sans devoir reconstruire toute l'application.

### 3.2. Architecture logique

La plateforme devra comporter les couches suivantes :

**A. Couche présentation** — Responsable de l'interaction avec les utilisateurs. Composants :

- Interface Web.
- Application Desktop.
- Interface d'administration.
- Interface de configuration.
- Interface de consultation des sources.

**B. Couche API** — Responsable de l'exposition des fonctionnalités du logiciel. Composants :

- API REST.
- Authentification.
- Autorisation.
- Gestion des utilisateurs.
- Gestion des conversations.
- Gestion des connecteurs.
- Gestion des tâches.
- Gestion des modèles IA.

**C. Couche métier** — Contient les fonctions principales :

- Orchestrateur RAG.
- Gestionnaire d'ingestion.
- Gestionnaire de documents.
- Gestionnaire de permissions.
- Moteur de recherche.
- Gestionnaire de conversations.
- Routeur IA.
- Gestionnaire des citations.
- Gestionnaire de synchronisation.

**D. Couche connecteurs** — Permet la communication avec les différentes sources. Chaque connecteur devra respecter une interface commune.

**E. Couche intelligence artificielle** — Gère :

- Les modèles de langage.
- Les modèles d'embeddings.
- Les modèles de reranking.
- Les modèles OCR et d'extraction.
- Les fournisseurs IA externes.
- Les modèles exécutés localement.

**F. Couche données** — Gère :

- Les documents indexés.
- Les fragments documentaires.
- Les embeddings.
- Les métadonnées.
- Les utilisateurs.
- Les permissions.
- Les conversations.
- Les journaux d'audit.
- Les configurations.

### 3.3. Architecture de référence

Le système devra s'appuyer sur les technologies suivantes, sous réserve de validation pendant le développement.

| Composant | Technologie privilégiée |
|---|---|
| Backend | Python |
| Framework API | FastAPI |
| Frontend | React |
| Langage frontend | TypeScript |
| Desktop | Tauri |
| Base relationnelle | PostgreSQL |
| Base vectorielle | Qdrant |
| Modèles locaux | Ollama |
| Embeddings | BGE-M3 ou modèle équivalent |
| Extraction documentaire | Apache Tika |
| OCR | PaddleOCR |
| Orchestration RAG | LlamaIndex ou architecture interne |
| Conteneurisation | Docker |
| Déploiement | Docker Compose |
| Gestion des tâches | Celery ou système équivalent |
| File de messages | Redis ou solution équivalente |
| Tests backend | Pytest |
| Tests frontend | Vitest |
| Tests de bout en bout | Playwright |

Il est interdit de multiplier les frameworks sans justification technique.

Le choix définitif des bibliothèques devra être documenté.

---

## 4. Architecture des deux modes d'installation

### 4.1. Mode Desktop

Le mode Desktop devra permettre à un utilisateur d'installer le logiciel directement sur son ordinateur.

**Systèmes supportés**

- Windows 11 en priorité.
- Linux dans un second temps.
- macOS à envisager ultérieurement.

**Fonctionnement**

L'application devra embarquer ou installer automatiquement les composants nécessaires.

Architecture souhaitée :

- Application Tauri.
- Interface React.
- Backend Python exécuté comme service local.
- Base de données locale.
- Index vectoriel local.
- Gestion des fichiers locaux.
- Moteur IA local via Ollama.
- Connexion facultative à des API externes.

**Exigences**

L'utilisateur devra pouvoir :

1. Installer l'application.
2. Créer son profil local.
3. Choisir un dossier documentaire.
4. Ajouter des fichiers.
5. Lancer l'indexation.
6. Interroger ses documents.
7. Consulter les références.
8. Supprimer une source.
9. Réindexer un dossier.
10. Configurer le modèle IA.

Le logiciel devra fonctionner sans connexion Internet lorsque les modèles nécessaires sont déjà téléchargés et configurés.

Les API externes devront être désactivées par défaut tant qu'elles ne sont pas configurées.

**Installation**

Prévoir :

- Un installateur Windows.
- Un mécanisme de mise à jour.
- Une procédure de désinstallation.
- Une conservation maîtrisée des données lors des mises à jour.
- Une option de sauvegarde et restauration.

L'application ne devra pas nécessiter une installation manuelle de Python, PostgreSQL, Qdrant ou Docker par l'utilisateur final.

Le packaging devra gérer les dépendances nécessaires ou installer les services requis.

### 4.2. Mode Server

Le mode Server devra permettre une installation sur l'infrastructure d'une entreprise.

**Objectif** : permettre à 10 à 30 utilisateurs de se connecter simultanément au même moteur documentaire.

**Architecture** — Le serveur devra héberger :

- Backend FastAPI.
- Frontend React.
- PostgreSQL.
- Qdrant.
- Service d'indexation.
- Gestionnaire de tâches.
- Ollama.
- Routeur de modèles.
- Service de surveillance.
- Service de sauvegarde.

Les utilisateurs devront accéder à l'application depuis un navigateur Web, sur le réseau local.

**Configuration initiale recommandée**

- Processeur : Ryzen 9 ou Intel Core i9 récent.
- RAM : 64 Go recommandés.
- GPU NVIDIA : 24 à 32 Go de VRAM souhaitables.
- SSD système : 1 To.
- SSD index et données applicatives : 2 To ou plus selon le volume.
- Réseau : Ethernet Gigabit minimum.
- Système : Ubuntu Server LTS.

Cette configuration constitue une cible de référence et non une obligation absolue.

Le système devra pouvoir fonctionner sur une machine moins puissante en limitant le nombre de générations IA simultanées et en utilisant davantage les API externes.

La capacité réelle devra être validée par des tests de charge.

**Utilisateurs simultanés** — Objectif initial :

- 30 utilisateurs connectés.
- 5 à 8 générations locales simultanées visées avec un matériel adapté.
- File d'attente pour les demandes supplémentaires.
- Possibilité de configurer les limites par utilisateur et par organisation.

Les performances ne devront pas être garanties sans tests avec le modèle et le matériel réellement retenus.

---

## 5. Système de connecteurs documentaires

### 5.1. Objectif

La plateforme devra proposer un système de connecteurs indépendants.

L'administrateur devra pouvoir ajouter une nouvelle source documentaire sans modifier le cœur du moteur RAG.

Chaque connecteur devra respecter une interface commune.

### 5.2. Interface commune des connecteurs

Chaque connecteur devra implémenter les opérations suivantes :

- Tester la connexion.
- S'authentifier auprès de la source.
- Explorer les ressources disponibles.
- Lister les documents.
- Lire les métadonnées.
- Télécharger ou extraire le contenu autorisé.
- Récupérer les permissions.
- Identifier les documents modifiés.
- Identifier les documents supprimés.
- Synchroniser les modifications.
- Gérer les erreurs.
- Fermer proprement la connexion.

Chaque document devra être représenté par un modèle normalisé indépendant de sa source.

**Métadonnées normalisées minimales**

- Identifiant interne.
- Identifiant externe.
- Identifiant de la source.
- Nom du document.
- Nom du fichier.
- Extension.
- Type MIME.
- Taille.
- Date de création.
- Date de modification.
- Version.
- Auteur ou propriétaire si disponible.
- Classe documentaire.
- Métadonnées métier.
- Chemin ou emplacement.
- Identifiants des groupes autorisés.
- Identifiants des utilisateurs autorisés.
- Empreinte cryptographique.
- Statut d'indexation.

Les métadonnées spécifiques à une GED devront également être conservées dans un champ extensible.

### 5.3. Connecteur M-Files

Le connecteur M-Files constitue le premier connecteur prioritaire.

**Objectif** : permettre à l'administrateur de connecter un coffre M-Files à la plateforme.

**Technologies** — Étudier en priorité les interfaces officielles M-Files :

- gRPC.
- Web Service REST.
- API COM/.NET lorsque cela est nécessaire.

Le choix devra tenir compte de la version de M-Files, du mode d'installation, de l'authentification et des fonctionnalités disponibles dans l'environnement client.

**Fonctionnalités attendues**

1. Enregistrement d'une connexion M-Files.
2. Configuration de l'adresse du serveur.
3. Configuration du coffre.
4. Authentification sécurisée.
5. Vérification de la connexion.
6. Exploration des classes documentaires.
7. Sélection des catégories à indexer.
8. Récupération des documents autorisés.
9. Extraction des fichiers.
10. Récupération des métadonnées.
11. Récupération des informations de sécurité.
12. Synchronisation des documents.
13. Détection des nouvelles versions.
14. Détection des suppressions.
15. Réindexation sélective.
16. Journalisation des erreurs.

**Gestion des versions** — Lorsqu'un document est modifié dans M-Files :

- Identifier sa nouvelle version.
- Extraire son nouveau contenu.
- Supprimer ou invalider les anciens fragments.
- Générer les nouveaux embeddings.
- Mettre à jour les métadonnées.
- Conserver la traçabilité des versions.

**Gestion des droits** — La plateforme devra reproduire les restrictions d'accès de M-Files. Il faudra notamment étudier :

- Les droits hérités.
- Les permissions propres aux objets.
- Les groupes.
- Les utilisateurs.
- Les changements de droits.
- Les documents confidentiels.
- Les documents dont les permissions évoluent.

Il ne faudra jamais supposer que tous les utilisateurs de la RAG ont accès à tous les documents indexés.

Si le connecteur ne peut pas récupérer fidèlement une information de permission, le document devra être traité de manière restrictive et ne pas être exposé aux utilisateurs non autorisés.

**Sécurité**

- Ne pas enregistrer les mots de passe en clair.
- Chiffrer les secrets de connexion.
- Limiter les droits du compte technique.
- Utiliser TLS lorsque disponible.
- Journaliser les connexions.
- Éviter toute exposition publique du serveur M-Files.

### 5.4. Connecteur de fichiers locaux

Ce connecteur devra permettre l'ajout de dossiers depuis :

- Windows.
- Linux.
- Répertoires partagés du réseau local.
- Stockages montés sur le serveur.

Formats prioritaires :

- PDF.
- DOCX.
- DOC.
- XLSX.
- XLS.
- PPTX.
- PPT.
- TXT.
- CSV.
- RTF.
- HTML.
- Images PNG et JPEG.
- Documents scannés.

Fonctionnalités :

- Sélection des dossiers.
- Exploration récursive.
- Filtrage par extension.
- Exclusion de sous-dossiers.
- Détection des doublons.
- Détection des modifications.
- Surveillance facultative des répertoires.
- Réindexation.
- Suppression de la source.
- Rapport d'ingestion.

Le logiciel devra éviter d'indexer les fichiers temporaires et les fichiers système.

### 5.5. Connecteurs futurs

L'architecture devra permettre d'ajouter :

- Alfresco.
- SharePoint.
- OneDrive.
- Google Drive.
- Nextcloud.
- Serveurs FTP/SFTP.
- Autres GED.
- Bases documentaires SQL.
- Stockages compatibles S3.
- API métiers.

Ces connecteurs ne sont pas tous obligatoires dans le MVP.

---

## 6. Moteur d'ingestion documentaire

### 6.1. Objectif

Le moteur d'ingestion est responsable de la transformation des documents en données exploitables par la RAG.

Il devra être asynchrone et indépendant de l'interface utilisateur.

### 6.2. Étapes d'ingestion

1. Détection du document.
2. Vérification du format.
3. Vérification de l'intégrité.
4. Calcul de l'empreinte du fichier.
5. Extraction des métadonnées.
6. Extraction du texte.
7. OCR si nécessaire.
8. Normalisation du contenu.
9. Nettoyage du texte.
10. Détection de la langue.
11. Découpage en fragments.
12. Création des embeddings.
13. Enregistrement des fragments.
14. Enregistrement des métadonnées.
15. Association des permissions.
16. Validation de l'indexation.

### 6.3. Gestion des documents numérisés

Le système devra détecter les PDF contenant uniquement des images.

Lorsque le texte n'est pas extractible :

- Déclencher un traitement OCR.
- Reconnaître le texte.
- Préserver l'association entre le texte et la page originale.
- Conserver le numéro de page.
- Signaler les documents présentant une qualité OCR insuffisante.

Il faudra permettre la réindexation des documents lorsque le moteur OCR évolue.

### 6.4. Découpage documentaire

Le découpage devra être configurable.

Paramètres :

- Taille des fragments.
- Chevauchement.
- Nombre maximal de caractères ou de tokens.
- Respect des paragraphes.
- Respect des titres.
- Conservation des tableaux.
- Conservation des références de pages.

Le découpage devra éviter de séparer inutilement les informations logiquement liées.

Les paramètres devront pouvoir être adaptés aux types de documents.

### 6.5. Tableaux et documents complexes

Le système devra préserver autant que possible :

- Les tableaux.
- Les titres.
- Les sections.
- Les listes.
- Les en-têtes.
- Les numéros de page.
- Les références documentaires.

Les documents contenant des tableaux devront bénéficier d'une extraction structurée lorsque cela est possible.

Les résultats devront conserver la provenance des informations.

### 6.6. Gestion des erreurs

Chaque document devra avoir un statut :

- En attente.
- En cours.
- Indexé.
- Indexé avec avertissement.
- Échec.
- Exclu.
- Supprimé.

Un échec d'indexation ne devra pas bloquer les autres documents.

Le système devra permettre une nouvelle tentative.

---

## 7. Moteur d'indexation et de recherche

### 7.1. Base vectorielle

Qdrant sera utilisé pour stocker les embeddings et permettre les recherches sémantiques.

Chaque fragment devra contenir :

- Son identifiant.
- L'identifiant du document.
- L'identifiant de la source.
- Le contenu du fragment.
- L'embedding.
- Le numéro de page.
- Les métadonnées utiles.
- Les informations de sécurité.
- La version du document.
- L'identifiant de l'organisation.

Les données devront être organisées de manière à assurer l'isolation des organisations et des espaces documentaires.

### 7.2. Recherche lexicale

La plateforme devra aussi proposer une recherche par mots-clés.

Elle devra être capable de retrouver :

- Un numéro de dossier.
- Une référence de contrat.
- Un nom.
- Une date.
- Un montant.
- Un terme précis.
- Un identifiant administratif.

PostgreSQL pourra être utilisé pour la recherche lexicale initiale, avec une évolution possible vers un moteur spécialisé si nécessaire.

### 7.3. Recherche hybride

Le système devra combiner :

- Recherche vectorielle.
- Recherche lexicale.
- Filtres documentaires.
- Filtres de sécurité.
- Reranking.

Les résultats devront être classés selon leur pertinence.

Les paramètres de recherche devront être configurables par l'administrateur.

### 7.4. Recherche filtrée

Filtres obligatoires :

- Source documentaire.
- Type de document.
- Classe documentaire.
- Date.
- Auteur.
- Métadonnées.
- Organisation.
- Espace documentaire.
- Permissions.
- Version.

### 7.5. Reranking

Prévoir une étape facultative de reclassement des passages.

Le reranker devra pouvoir fonctionner avec un modèle local ou un service externe autorisé.

Il ne devra jamais supprimer les contrôles de permissions appliqués en amont.

---

## 8. Moteur RAG

### 8.1. Fonctionnement général

Lorsqu'un utilisateur pose une question :

1. Recevoir la question.
2. Identifier l'utilisateur.
3. Charger ses permissions.
4. Identifier les sources accessibles.
5. Analyser la question.
6. Effectuer les recherches documentaires.
7. Filtrer les résultats.
8. Classer les passages.
9. Constituer le contexte.
10. Sélectionner le modèle IA.
11. Générer la réponse.
12. Vérifier la présence des références.
13. Afficher la réponse.
14. Enregistrer la conversation selon les paramètres de conservation.

### 8.2. Qualité des réponses

Le modèle devra être explicitement invité à :

- Répondre uniquement à partir des informations fournies lorsque la question concerne les documents.
- Ne pas inventer des informations.
- Signaler l'absence d'informations suffisantes.
- Distinguer les faits des interprétations.
- Mentionner les contradictions éventuelles.
- Indiquer les sources utilisées.
- Conserver les dates, montants et références exactes.
- Signaler les documents illisibles ou incomplets.

La réponse devra pouvoir indiquer :

« Les documents disponibles ne permettent pas de répondre avec suffisamment de certitude. »

### 8.3. Citations documentaires

Chaque réponse devra afficher les sources utilisées.

Une citation devra contenir, lorsque disponible :

- Nom du document.
- Identifiant du document.
- Source documentaire.
- Numéro de page.
- Extrait pertinent.
- Date ou version.
- Lien d'accès au document original.

L'utilisateur devra pouvoir cliquer sur une référence pour ouvrir le document original, sous réserve de ses droits d'accès.

La plateforme ne devra pas inventer de références ou de numéros de page.

### 8.4. Gestion des conversations

Fonctionnalités :

- Nouvelle conversation.
- Historique.
- Renommage.
- Suppression.
- Recherche dans l'historique.
- Consultation des sources précédentes.
- Export des réponses.
- Copie du contenu.
- Conservation du contexte conversationnel.

Les conversations ne devront jamais donner accès à des documents dont l'utilisateur a perdu les permissions.

Lors d'une nouvelle question, les autorisations devront être vérifiées à nouveau.

### 8.5. Questions multi-documents

Le moteur devra permettre :

- Comparaison de contrats.
- Synthèse de plusieurs rapports.
- Recherche de dossiers similaires.
- Extraction d'informations communes.
- Détection de différences.
- Analyse chronologique.
- Recherche de documents liés.
- Synthèse d'un dossier administratif.

Les résultats devront citer chaque document contribuant à la réponse.

---

## 9. Intelligence artificielle et architecture hybride

### 9.1. Objectif

Le logiciel devra être indépendant des fournisseurs de modèles IA.

Aucun fournisseur ne devra être imposé de manière permanente.

### 9.2. Fournisseurs à prendre en charge

**Modèles locaux**

- Ollama.
- Modèles Qwen.
- Modèles Gemma.
- Modèles Llama.
- Autres modèles compatibles.

**Fournisseurs externes**

- Google Gemini API.
- Anthropic Claude API.
- OpenAI API.
- Ollama Cloud.
- Autres fournisseurs compatibles.

Les fournisseurs devront être intégrés au moyen d'adaptateurs indépendants.

La disponibilité de chaque modèle devra être vérifiée avant de l'afficher comme sélectionnable.

### 9.3. Model Router

Créer un module central appelé Model Router.

Responsabilités :

- Enregistrer les fournisseurs.
- Gérer les modèles disponibles.
- Vérifier leur disponibilité.
- Gérer les clés API.
- Sélectionner le modèle.
- Appliquer les politiques de confidentialité.
- Gérer les limites de consommation.
- Gérer les erreurs.
- Mesurer les temps de réponse.
- Mesurer les coûts lorsque disponibles.
- Gérer les bascules autorisées.

### 9.4. Configuration des modèles

Chaque modèle devra disposer d'une configuration indépendante :

- Nom du fournisseur.
- Nom du modèle.
- Type : local ou distant.
- Endpoint.
- Clé API.
- Température.
- Taille maximale du contexte.
- Limite de tokens.
- Timeout.
- Nombre de requêtes simultanées.
- Statut actif/inactif.
- Priorité.
- Politique de confidentialité.

Les clés API devront être chiffrées au repos.

Elles ne devront jamais être exposées dans le frontend.

### 9.5. Politique d'utilisation

L'administrateur devra choisir parmi plusieurs modes :

- **Mode local uniquement** : aucune donnée documentaire ne doit être envoyée à un fournisseur externe.
- **Mode hybride contrôlé** : l'IA locale est utilisée par défaut. Les API externes ne sont utilisées que si une politique explicite l'autorise.
- **Mode cloud autorisé** : l'administrateur autorise l'envoi de certains contextes documentaires vers des fournisseurs externes.

Le système devra distinguer les données de la question et les extraits documentaires.

L'utilisateur devra être informé lorsque sa demande implique l'utilisation d'un fournisseur externe, selon la politique de l'organisation.

Une bascule automatique vers le cloud ne devra jamais se produire si la politique interdit les transferts externes.

### 9.6. Modèles d'embeddings

Le moteur d'embeddings devra être indépendant du modèle génératif.

Il faudra notamment prendre en charge :

- Modèles locaux.
- Modèles externes si autorisés.
- Modèles multilingues.
- Documents en français.
- Documents en anglais.
- Possibilité d'autres langues.

La dimension vectorielle devra être enregistrée avec la version du modèle.

Tout changement de modèle d'embedding nécessitera une stratégie de réindexation.

Le logiciel ne devra pas mélanger des embeddings incompatibles dans une même collection sans mécanisme de séparation.

### 9.7. Gestion des coûts

Pour les API externes, prévoir :

- Suivi des tokens.
- Estimation des coûts.
- Historique de consommation.
- Limites par utilisateur.
- Limites par organisation.
- Alertes de dépassement.
- Désactivation des API à partir d'un seuil configurable.

---

## 10. Interface utilisateur

### 10.1. Identité visuelle

L'interface devra être professionnelle, moderne et minimaliste.

Principes :

- Interface claire.
- Navigation intuitive.
- Design responsive.
- Typographie lisible.
- Hiérarchie visuelle cohérente.
- Faible surcharge visuelle.
- Adaptation aux écrans professionnels.
- Mode clair et mode sombre.

Le logiciel devra disposer d'une identité visuelle propre, indépendante des fournisseurs IA.

### 10.2. Écran de connexion

Afficher :

- Logo du logiciel.
- Nom de l'organisation.
- Identifiant.
- Mot de passe.
- Option de récupération de compte si configurée.
- Message d'erreur explicite.

### 10.3. Tableau de bord

Afficher :

- Nombre de sources connectées.
- Nombre de documents indexés.
- Nombre de fragments.
- Nombre de tâches en cours.
- Nombre d'erreurs.
- État des services.
- Modèle IA actif.
- Utilisation des API.
- Activité récente.

### 10.4. Interface conversationnelle

Fonctionnalités :

- Zone de saisie.
- Envoi de question.
- Réponse progressive lorsque le fournisseur le permet.
- Affichage des sources.
- Consultation des extraits.
- Ouverture du document original.
- Historique.
- Annulation d'une génération.
- Copie d'une réponse.
- Export en PDF ou DOCX.
- Indication du modèle utilisé.
- Indication du mode local ou distant.

### 10.5. Interface des sources

Afficher :

- Nom de la source.
- Type de connecteur.
- Statut.
- Date de dernière synchronisation.
- Nombre de documents.
- Nombre de documents en erreur.
- Paramètres.
- Bouton de synchronisation.
- Bouton de désactivation.
- Bouton de suppression.

### 10.6. Interface des documents

Afficher :

- Liste des documents indexés.
- Nom.
- Source.
- Format.
- Date de modification.
- Version.
- Statut d'indexation.
- Erreurs.
- Permissions.
- Nombre de fragments.

Actions :

- Consulter les métadonnées.
- Réindexer.
- Exclure.
- Retirer de l'index.
- Voir l'historique.
- Retrouver la source originale.

La suppression d'un document dans l'index ne devra pas supprimer le document original dans sa GED.

### 10.7. Interface d'administration

Elle devra permettre :

- Gestion des utilisateurs.
- Gestion des rôles.
- Gestion des groupes.
- Gestion des sources.
- Gestion des modèles IA.
- Gestion des permissions.
- Gestion des paramètres RAG.
- Gestion des tâches.
- Gestion des journaux.
- Gestion des sauvegardes.
- Gestion des licences.

---

## 11. Gestion des utilisateurs et des permissions

### 11.1. Rôles

Prévoir au minimum :

**Super administrateur**

- Configuration globale.
- Gestion des organisations.
- Gestion des licences.
- Administration des installations.

**Administrateur d'organisation**

- Gestion des utilisateurs de son organisation.
- Gestion des connecteurs.
- Gestion des paramètres.
- Gestion des modèles autorisés.

**Administrateur documentaire**

- Gestion des sources.
- Gestion de l'indexation.
- Consultation des erreurs.
- Gestion des espaces documentaires.

**Utilisateur**

- Recherche documentaire.
- Consultation des réponses.
- Gestion de ses conversations.

**Auditeur**

- Consultation des journaux autorisés.
- Consultation des historiques d'activité.
- Aucun droit de modification par défaut.

### 11.2. Contrôle d'accès

Le système devra mettre en place un contrôle d'accès fondé sur les rôles et les permissions documentaires.

Il devra combiner :

- RBAC : contrôle d'accès par rôle.
- ACL : contrôle d'accès par document ou ressource.
- Isolation par organisation.
- Permissions par source.
- Permissions par groupe.

Les permissions devront être contrôlées avant la récupération des fragments et avant la génération de la réponse.

Il faudra également gérer les changements de permissions et les révocations.

Les résultats du cache ne devront jamais être réutilisés entre utilisateurs si cela peut exposer des données non autorisées.

### 11.3. Authentification

Prévoir :

- Identifiants et mots de passe.
- Hachage sécurisé des mots de passe.
- Sessions sécurisées.
- Expiration des sessions.
- Déconnexion.
- Protection contre les tentatives répétées.
- Gestion des comptes désactivés.

Prévoir une compatibilité future avec LDAP et Active Directory.

---

## 12. Sécurité et confidentialité

La sécurité constitue une exigence fondamentale du produit.

### 12.1. Protection des données

- Chiffrement des communications.
- Chiffrement des secrets.
- Gestion sécurisée des clés.
- Protection des sauvegardes.
- Isolation des organisations.
- Contrôle d'accès systématique.
- Gestion des sessions.
- Journalisation.
- Protection contre les accès non autorisés.

### 12.2. Protection des données sensibles

Les documents originaux devront rester dans leur source documentaire.

L'index local devra conserver uniquement les données nécessaires à la recherche et à la génération des réponses.

Les données temporaires devront être supprimées selon une politique de conservation.

Les extraits envoyés aux API externes devront être soumis à des règles explicites.

### 12.3. Prompt injection

Le système devra se protéger contre les instructions malveillantes contenues dans les documents.

Le contenu documentaire devra toujours être traité comme une donnée non fiable.

Il ne devra jamais pouvoir :

- Modifier les instructions système.
- Obtenir les clés API.
- Déclencher des actions administratives.
- Contourner les permissions.
- Accéder à des documents non autorisés.

Les documents devront être isolés du contexte d'instructions du modèle.

### 12.4. Protection des API

- Authentification.
- Autorisation.
- Limitation du débit.
- Validation des entrées.
- Protection contre les injections.
- Gestion des erreurs.
- Journalisation.
- Protection contre les abus.

### 12.5. Audit

Enregistrer au minimum :

- Connexions.
- Déconnexions.
- Échecs d'authentification.
- Création d'utilisateurs.
- Modifications des rôles.
- Ajout de sources.
- Suppression de sources.
- Synchronisations.
- Consultations documentaires.
- Requêtes IA.
- Utilisation des API externes.
- Modifications des paramètres.
- Opérations de sauvegarde et restauration.

Ne pas journaliser systématiquement les contenus documentaires sensibles ou les secrets.

La durée de conservation des journaux devra être configurable.

---

## 13. Gestion des données

### 13.1. PostgreSQL

PostgreSQL devra gérer :

- Organisations.
- Utilisateurs.
- Groupes.
- Rôles.
- Permissions.
- Sources.
- Documents.
- Versions.
- Métadonnées.
- Conversations.
- Messages.
- Citations.
- Modèles IA.
- Fournisseurs.
- Tâches.
- Journaux d'audit.
- Licences.
- Paramètres.

### 13.2. Qdrant

Qdrant devra stocker :

- Embeddings.
- Fragments documentaires.
- Identifiants de documents.
- Identifiants de sources.
- Métadonnées de recherche.
- Informations nécessaires aux filtres de sécurité.

Les collections devront être organisées selon une stratégie permettant l'isolation des organisations et la gestion des versions d'embeddings.

### 13.3. Stockage des documents

Le système devra éviter de dupliquer inutilement les documents originaux.

Les fichiers pourront être :

- Consultés directement depuis leur source.
- Conservés temporairement pendant l'extraction.
- Stockés localement lorsque la source est un dossier local et que cela est nécessaire.

Les fichiers temporaires devront être protégés et supprimés selon des règles définies.

### 13.4. Synchronisation

La synchronisation devra gérer :

- Première indexation.
- Synchronisation complète.
- Synchronisation incrémentale.
- Documents modifiés.
- Documents supprimés.
- Changements de permissions.
- Erreurs temporaires.
- Reprise après interruption.

Le système devra être idempotent : relancer une synchronisation ne devra pas créer des doublons.

---

## 14. Gestion des tâches et des performances

### 14.1. Traitements asynchrones

Les opérations longues ne devront pas bloquer les requêtes utilisateurs.

Prévoir des tâches pour :

- Ingestion.
- OCR.
- Extraction.
- Embeddings.
- Indexation.
- Synchronisation.
- Réindexation.
- Nettoyage.
- Sauvegarde.

### 14.2. File d'attente

Mettre en place une file de traitement avec :

- Priorités.
- Nombre maximal de tâches simultanées.
- Nouvelles tentatives.
- Gestion des échecs.
- Annulation lorsque possible.
- Suivi de progression.

### 14.3. Optimisation

Prévoir :

- Cache des résultats autorisés.
- Cache des métadonnées.
- Limitation du contexte.
- Pagination.
- Recherche filtrée.
- Traitement par lots.
- Indexation incrémentale.
- Gestion des limites GPU.
- File d'attente des générations IA.

### 14.4. Objectifs de performance

Les valeurs suivantes constituent des objectifs à mesurer et à valider sur un environnement de référence :

- Interface utilisable par 30 utilisateurs connectés.
- Temps de recherche documentaire visé inférieur à 3 secondes hors génération IA, sur un index de référence correctement dimensionné.
- Réponse IA progressive lorsque possible.
- Traitement asynchrone des documents volumineux.
- Aucun blocage global en cas d'échec d'un document.
- Reprise après interruption d'un traitement.
- Absence de fuite de données entre utilisateurs.

Les performances de génération dépendront du GPU, du modèle, du contexte et de la charge.

---

## 15. Observabilité et supervision

Le logiciel devra intégrer un tableau de bord technique.

Indicateurs :

- État du backend.
- État de PostgreSQL.
- État de Qdrant.
- État d'Ollama.
- État des connecteurs.
- Utilisation CPU.
- Utilisation RAM.
- Utilisation GPU et VRAM.
- Espace disque.
- Nombre de requêtes.
- Temps moyen de réponse.
- Taux d'erreurs.
- Nombre de tâches en attente.
- Nombre de documents indexés.
- Consommation des API.

Les erreurs devront être consultables par les administrateurs.

Prévoir un système de logs structurés.

Aucune donnée confidentielle ne devra être affichée dans les journaux techniques sans justification.

---

## 16. Sauvegarde et restauration

Le logiciel devra intégrer une stratégie de sauvegarde.

Éléments à sauvegarder :

- PostgreSQL.
- Collections Qdrant.
- Paramètres.
- Configurations des sources.
- Clés chiffrées selon le mécanisme retenu.
- Historique nécessaire.
- Licences.

Prévoir :

- Sauvegarde manuelle.
- Sauvegarde automatique.
- Planification.
- Export.
- Restauration.
- Vérification de l'intégrité.
- Journalisation des opérations.

Les sauvegardes devront être stockées dans un emplacement distinct du serveur principal lorsque possible.

La restauration devra être testée avant toute mise en production.

Objectifs initiaux à paramétrer :

- RPO cible : 24 heures maximum.
- RTO cible : 8 heures maximum.

Ces objectifs devront être adaptés aux exigences de chaque entreprise.

---

## 17. Licences et commercialisation

La plateforme devra être conçue pour être commercialisée.

### 17.1. Gestion des licences

Prévoir :

- Identifiant de licence.
- Organisation.
- Type de licence.
- Date d'activation.
- Date d'expiration.
- Nombre maximal d'utilisateurs.
- Nombre maximal de sources.
- Fonctionnalités autorisées.
- Statut.
- Historique.

### 17.2. Activation

Le logiciel devra pouvoir être activé au moyen d'une clé ou d'un fichier de licence signé.

Pour les installations totalement isolées d'Internet, prévoir une activation hors ligne.

La vérification des licences ne devra pas rendre inutilisable une installation locale lorsque le serveur de licence est temporairement inaccessible.

### 17.3. Modèles de commercialisation futurs

- Licence Desktop individuelle.
- Licence Server.
- Licence entreprise.
- Licence par nombre d'utilisateurs.
- Licence par nombre de sources.
- Contrat de maintenance.
- Prestations d'intégration.
- Modules complémentaires.

La facturation ne fait pas partie du MVP.

---

## 18. API interne

Le backend devra exposer une API REST documentée.

Endpoints indicatifs :

**Authentification**

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

**Utilisateurs**

- `GET /api/v1/users`
- `POST /api/v1/users`
- `GET /api/v1/users/{id}`
- `PUT /api/v1/users/{id}`
- `DELETE /api/v1/users/{id}`

**Sources**

- `GET /api/v1/sources`
- `POST /api/v1/sources`
- `GET /api/v1/sources/{id}`
- `PUT /api/v1/sources/{id}`
- `DELETE /api/v1/sources/{id}`
- `POST /api/v1/sources/{id}/test`
- `POST /api/v1/sources/{id}/sync`

**Documents**

- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`
- `POST /api/v1/documents/{id}/reindex`
- `DELETE /api/v1/documents/{id}/index`

**Recherche**

- `POST /api/v1/search`
- `POST /api/v1/chat`
- `GET /api/v1/chat/{id}`
- `GET /api/v1/conversations`

**Modèles IA**

- `GET /api/v1/models`
- `POST /api/v1/models`
- `PUT /api/v1/models/{id}`
- `POST /api/v1/models/{id}/test`
- `GET /api/v1/providers`

**Administration**

- `GET /api/v1/admin/health`
- `GET /api/v1/admin/metrics`
- `GET /api/v1/admin/audit`
- `GET /api/v1/admin/jobs`
- `POST /api/v1/admin/backup`
- `POST /api/v1/admin/restore`

Les routes définitives devront respecter une convention cohérente, avec validation des entrées, authentification et contrôle des permissions.

---

## 19. Structure du projet logiciel

Le dépôt devra être organisé en monorepo.

Structure indicative :

```
universal-rag/
├── apps/
│   ├── web/
│   └── desktop/
├── services/
│   ├── api/
│   ├── ingestion/
│   ├── worker/
│   └── model-router/
├── core/
│   ├── rag/
│   ├── retrieval/
│   ├── embeddings/
│   ├── chunking/
│   ├── security/
│   ├── permissions/
│   └── citations/
├── connectors/
│   ├── base/
│   ├── mfiles/
│   ├── local-files/
│   ├── alfresco/
│   └── sharepoint/
├── infrastructure/
│   ├── docker/
│   ├── deployment/
│   ├── scripts/
│   └── monitoring/
├── database/
│   ├── migrations/
│   └── schemas/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── performance/
│   └── e2e/
├── docs/
│   ├── architecture/
│   ├── installation/
│   ├── administration/
│   └── api/
├── scripts/
├── README.md
├── docker-compose.yml
└── .env.example
```

Les modules devront être indépendants et testables.

Les connecteurs ne devront pas contenir la logique centrale du moteur RAG.

Le frontend ne devra pas communiquer directement avec les bases de données.

---

## 20. Tests et qualité

### 20.1. Tests unitaires

Tester :

- Extraction.
- Chunking.
- Embeddings.
- Recherche.
- Permissions.
- Citations.
- Gestion des modèles.
- Synchronisation.
- Authentification.

### 20.2. Tests d'intégration

Tester :

- Backend et PostgreSQL.
- Backend et Qdrant.
- Backend et Ollama.
- Backend et API externes.
- Connecteur M-Files.
- Connecteur local.
- OCR et extraction.

### 20.3. Tests fonctionnels

Scénarios obligatoires :

1. Ajouter une source.
2. Indexer un PDF.
3. Indexer un document Word.
4. Indexer un document scanné.
5. Poser une question.
6. Obtenir une réponse sourcée.
7. Ouvrir le document original.
8. Modifier un document.
9. Réindexer le document.
10. Supprimer un document.
11. Vérifier que le document supprimé ne ressort plus.
12. Changer les permissions.
13. Vérifier que l'accès est révoqué.
14. Basculer entre deux modèles IA.
15. Désactiver l'accès aux API externes.
16. Reprendre une synchronisation interrompue.

### 20.4. Tests de sécurité

Tester notamment :

- Accès non autorisé.
- Escalade de privilèges.
- Fuite interorganisationnelle.
- Exposition de clés API.
- Contournement des permissions.
- Injection dans les requêtes.
- Prompt injection documentaire.
- Manipulation des citations.
- Accès aux conversations d'autres utilisateurs.

### 20.5. Tests de charge

Prévoir des simulations avec :

- 10 utilisateurs.
- 20 utilisateurs.
- 30 utilisateurs.
- Plusieurs générations simultanées.
- Plusieurs indexations simultanées.
- Un mélange de recherches et de générations.

Mesurer :

- Temps de réponse.
- CPU.
- RAM.
- VRAM.
- Saturation des files.
- Taux d'erreurs.
- Consommation des API.

Les résultats devront faire l'objet d'un rapport.

---

## 21. Critères de recette du MVP

Le MVP sera considéré comme fonctionnel lorsque les conditions suivantes seront remplies.

**Installation**

- Installation Desktop opérationnelle.
- Installation Server opérationnelle.
- Démarrage automatique des services requis.
- Documentation d'installation disponible.

**Sources documentaires**

- Connexion à un dossier local.
- Connexion à M-Files dans un environnement de test autorisé.
- Extraction des métadonnées.
- Synchronisation.
- Gestion des modifications.
- Gestion des suppressions.

**Intelligence documentaire**

- Indexation de PDF, Word et Excel.
- OCR des documents scannés.
- Recherche vectorielle.
- Recherche lexicale.
- Recherche hybride.
- Réponses en langage naturel.
- Citations vérifiables.

**Intelligence artificielle**

- Modèle local via Ollama.
- Au moins un fournisseur externe.
- Routeur de modèles.
- Configuration des politiques d'utilisation.
- Désactivation des appels externes.

**Sécurité**

- Authentification.
- Rôles.
- Contrôle des permissions.
- Isolation des organisations.
- Journalisation.
- Gestion des secrets.

**Exploitation**

- Tableau de bord.
- Sauvegarde.
- Restauration.
- Gestion des erreurs.
- Tests de charge.
- Documentation.

Aucun critère de sécurité ne devra être considéré comme validé sur la seule base d'une démonstration fonctionnelle.

---

## 22. Plan de développement

Le développement devra être réalisé progressivement.

**Phase 0 : cadrage technique**

Objectifs :

- Valider les choix technologiques.
- Étudier l'API M-Files.
- Définir les interfaces des connecteurs.
- Définir les modèles de données.
- Définir les règles de sécurité.
- Définir les tests de référence.

Livrables :

- Architecture détaillée.
- Schéma de base de données.
- Contrats d'API.
- Plan de tests.
- ADR (Architecture Decision Records).

**Phase 1 : prototype RAG**

Objectifs : backend FastAPI, ingestion locale, extraction PDF et DOCX, embeddings, Qdrant, recherche, réponses avec citations.

Livrable : première RAG fonctionnelle sur des documents de test.

**Phase 2 : moteur documentaire**

Objectifs : OCR, gestion des métadonnées, indexation incrémentale, gestion des versions, synchronisation, gestion des erreurs.

Livrable : moteur documentaire stable.

**Phase 3 : connecteurs**

Objectifs : connecteur de fichiers locaux complet, connecteur M-Files, gestion des permissions, gestion des synchronisations.

Livrable : connexion aux premières sources documentaires.

**Phase 4 : interface utilisateur**

Objectifs : interface de chat, gestion des conversations, gestion des sources, gestion des documents, tableau de bord, administration.

Livrable : application Web fonctionnelle.

**Phase 5 : intelligence artificielle hybride**

Objectifs : Ollama, Model Router, premier fournisseur externe, gestion des secrets, politiques de confidentialité, limitation des consommations.

Livrable : moteur IA interchangeable.

**Phase 6 : Desktop**

Objectifs : intégration Tauri, backend local, stockage local, installateur, configuration, mise à jour.

Livrable : application Desktop installable.

**Phase 7 : Server**

Objectifs : Docker Compose, configuration serveur, gestion multi-utilisateurs, supervision, sauvegarde, sécurité, tests de charge.

Livrable : déploiement On-Premise opérationnel.

**Phase 8 : validation et commercialisation**

Objectifs : tests utilisateurs, tests de sécurité, correction des anomalies, documentation, gestion des licences, préparation des installations clients.

Livrable : première version commercialisable.

---

## 23. Livrables attendus

Le projet devra fournir :

1. Code source complet.
2. Dépôt Git structuré.
3. Backend documenté.
4. Frontend documenté.
5. Moteur RAG indépendant.
6. Connecteur M-Files.
7. Connecteur fichiers locaux.
8. Adaptateurs IA.
9. Application Desktop.
10. Application Server.
11. Schéma de base de données.
12. Scripts de migration.
13. Fichiers Docker.
14. Scripts d'installation.
15. Installateur Desktop.
16. Configuration serveur.
17. Tests unitaires.
18. Tests d'intégration.
19. Tests de sécurité.
20. Rapport de tests de charge.
21. Documentation API.
22. Guide utilisateur.
23. Guide administrateur.
24. Guide de dépannage.
25. Procédure de sauvegarde.
26. Procédure de restauration.
27. Fichier de configuration exemple.
28. Documentation des connecteurs.
29. Liste des dépendances et licences.
30. Documentation de l'architecture.

---

## 24. Exigences de qualité et de maintenabilité

Le logiciel devra respecter les principes suivants :

- Code modulaire.
- Typage lorsque possible.
- Documentation des fonctions importantes.
- Gestion centralisée des erreurs.
- Logs structurés.
- Tests automatisés.
- Configuration externalisée.
- Absence de secrets dans le code.
- Migrations de base de données versionnées.
- Dépendances maîtrisées.
- Versions verrouillées.
- Gestion des environnements.
- Séparation développement, test et production.
- Compatibilité avec les mises à jour.
- Aucune dépendance obligatoire à un service cloud.

Toute fonctionnalité importante devra être testable indépendamment.

Les décisions architecturales majeures devront être documentées.

---

## 25. Contraintes et risques du projet

### 25.1. Dépendance à M-Files

Les capacités du connecteur dépendront de la version de M-Files, des interfaces activées, des droits et de la configuration du client.

Une étude technique sur un environnement M-Files réel sera nécessaire.

### 25.2. Ressources matérielles

La génération locale dépendra du GPU, de la mémoire disponible et du modèle.

Le logiciel devra permettre de limiter la concurrence et de basculer vers une API externe uniquement lorsque cela est autorisé.

### 25.3. Qualité OCR

Les documents anciens, inclinés, de mauvaise qualité ou manuscrits peuvent produire des erreurs.

Le logiciel devra signaler les limites de reconnaissance.

### 25.4. Qualité des réponses

Une RAG ne garantit pas automatiquement l'exactitude des réponses.

Il faudra mesurer la qualité de la récupération documentaire et de la génération, utiliser des jeux de questions de référence et permettre de signaler les réponses incorrectes.

### 25.5. Sécurité des permissions

La reproduction des droits d'accès de différentes GED représente une difficulté technique importante.

Chaque connecteur devra faire l'objet de tests spécifiques.

### 25.6. Utilisation des API externes

Les coûts, limites de requêtes, conditions de conservation et conditions de traitement des fournisseurs devront être examinés avant chaque intégration.

---

## 26. Évolutions futures

Après stabilisation du MVP, envisager :

**A. Nouveaux connecteurs** : Alfresco, SharePoint, Google Drive, OneDrive, Nextcloud, autres GED.

**B. Analyse documentaire avancée** : extraction automatique de champs, identification des échéances, comparaison de contrats, détection des doublons, détection des incohérences, analyse des dossiers, génération de rapports.

**C. Agents documentaires spécialisés** : assistant juridique, assistant archivistique, assistant RH, assistant conformité, assistant marchés publics, assistant bancaire.

**D. Automatisation** : alertes documentaires, suivi des échéances, rapports périodiques, notifications, workflows de validation.

**E. Commercialisation avancée** : gestion des abonnements, gestion des licences, portail client, administration multi-organisations, modules payants, déploiement automatisé.

---

## 27. Directives impératives pour Claude Code

Le présent cahier des charges constitue la référence fonctionnelle et technique du projet.

Claude Code devra respecter les directives suivantes.

### 27.1. Ne pas tout développer en une seule opération

Le projet devra être développé phase par phase.

Il est interdit de générer une grande quantité de code sans architecture préalable, sans tests et sans validation.

### 27.2. Commencer par un audit de l'environnement

Avant toute implémentation :

- Examiner le dépôt Git.
- Identifier les outils disponibles.
- Vérifier les versions.
- Examiner les dépendances.
- Détecter les contraintes.
- Identifier les composants réutilisables.

Ne pas supprimer ou remplacer des éléments existants sans justification.

### 27.3. Produire un plan d'exécution

Avant de développer :

- Proposer une architecture.
- Décrire les modules.
- Définir les interfaces.
- Proposer le schéma de base de données.
- Identifier les risques.
- Définir les tests.
- Découper le travail en tâches.

Le plan devra être validé avant les opérations structurantes.

### 27.4. Créer les documents de référence

Créer dans le dépôt :

- `docs/CAHIER_DES_CHARGES.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/SECURITY.md`
- `docs/CONNECTORS.md`
- `docs/AI_MODELS.md`
- `docs/DEPLOYMENT.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `docs/DECISIONS/`

### 27.5. Interdiction d'inventer des intégrations

Ne pas prétendre qu'un connecteur fonctionne sans test réel.

Ne pas inventer des endpoints M-Files.

Vérifier les documentations officielles et les versions réellement disponibles.

Si un accès à un serveur M-Files est nécessaire, préparer un adaptateur testable et demander les informations nécessaires avant de déclarer l'intégration opérationnelle.

### 27.6. Gestion des secrets

- Ne jamais inscrire de clés API dans le code.
- Ne jamais inscrire de mots de passe dans Git.
- Fournir un fichier `.env.example`.
- Utiliser des secrets chiffrés.
- Vérifier les fichiers avant chaque commit.

### 27.7. Validation continue

Chaque phase devra être accompagnée :

- Des fonctionnalités réalisées.
- Des fichiers créés ou modifiés.
- Des tests exécutés.
- Des résultats.
- Des anomalies restantes.
- Des décisions prises.
- Des prochaines tâches.

Aucune fonctionnalité ne devra être déclarée terminée uniquement parce que le code a été généré.

Elle devra avoir été exécutée et testée.

### 27.8. Priorité absolue à la sécurité

Les contrôles de permissions devront être implémentés dès la conception du moteur RAG, et non ajoutés après la création du chatbot.

Les API externes devront être désactivables.

Aucune donnée documentaire ne devra être envoyée vers un service externe sans respecter les paramètres de confidentialité.

### 27.9. Environnement de développement

Le développement initial pourra utiliser :

- Claude Code.
- GitHub.
- Des environnements de développement cloud.
- Des conteneurs de test.
- Des modèles IA accessibles par API.

Il ne faudra pas confondre l'environnement cloud de développement avec le futur environnement On-Premise.

Le code devra être portable et déployable sur une infrastructure locale.

### 27.10. Règle de progression

Développer dans cet ordre :

1. Architecture.
2. Modèle de données.
3. Ingestion documentaire.
4. Recherche.
5. Moteur RAG.
6. Citations.
7. Connecteur local.
8. Connecteur M-Files.
9. Permissions.
10. Model Router.
11. Interface Web.
12. Desktop.
13. Server.
14. Sécurité.
15. Tests de charge.
16. Packaging et documentation.

Ne pas commencer par les animations, les fonctionnalités cosmétiques ou les modules commerciaux avant d'avoir un moteur documentaire fonctionnel.

---

## 28. Définition finale du produit

À l'issue du projet, Universal RAG Engine devra être une plateforme professionnelle capable de se connecter à plusieurs environnements documentaires, d'en exploiter les informations et de fournir des réponses contextualisées en langage naturel.

La plateforme devra pouvoir fonctionner :

- Sur un ordinateur individuel.
- Sur un serveur local.
- Dans un réseau d'entreprise.
- Avec un modèle IA local.
- Avec un modèle IA externe autorisé.
- Avec plusieurs fournisseurs IA.
- Avec plusieurs sources documentaires.
- Avec plusieurs utilisateurs.
- Avec des règles de sécurité adaptées aux organisations.

**Principe fondateur :**

« Une seule plateforme d'intelligence documentaire, plusieurs sources, plusieurs modèles d'intelligence artificielle et deux modes de déploiement, sans dépendance obligatoire au cloud. »

**Résultat attendu :** un logiciel indépendant, modulaire, sécurisé, extensible, maintenable et commercialisable auprès des organisations qui souhaitent exploiter intelligemment leur patrimoine documentaire sans remplacer leurs systèmes existants.

---

*Fin du cahier des charges — Document de référence – Universal RAG Engine – Version 1.0*
