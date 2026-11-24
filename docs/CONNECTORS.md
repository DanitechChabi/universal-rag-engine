# Connecteurs — Universal RAG Engine

Statut : **contrat de phase 0**. Aucun connecteur n'est implémenté. Le connecteur
M-Files ne sera déclaré opérationnel qu'après des tests sur un vrai coffre
(directive 27.5).

---

## 1. Principe

- Un connecteur sait **parler à une source** : se connecter, lister, lire le contenu,
  lire les droits, détecter les changements. Il ne sait **rien** de la RAG
  (découpage, embeddings, recherche).
- Le cœur (`urag-core`) ne connaît que l'interface commune, dans le paquet
  `urag-connectors-base`. Les connecteurs concrets sont des paquets séparés,
  découverts par un **registre** (points d'entrée Python `urag.connectors`).
  Ajouter une source = installer un paquet, sans modifier le cœur.
- Tout est **normalisé** dans des types communs avant d'entrer dans le cœur.

---

## 2. Interface commune

Correspondance avec la section 5.2 du cahier des charges :

| Opération demandée | Méthode |
|---|---|
| Tester la connexion | `test_connection()` |
| S'authentifier | `open()` |
| Explorer les ressources | `browse(container)` |
| Lister les documents | `list_documents(scope)` |
| Lire les métadonnées | inclus dans `SourceDocument` |
| Télécharger le contenu autorisé | `fetch_content(ref, dest)` |
| Récupérer les permissions | `get_access(refs)` + `list_principals()` |
| Documents modifiés / supprimés, synchroniser | `list_changes(cursor)` |
| Gérer les erreurs | exceptions typées (§2.3) |
| Fermer proprement | `close()` (gestionnaire de contexte) |
| *(en plus)* Revérifier les droits d'un utilisateur au moment de la question | `check_access(principal, refs)` — optionnel |

### 2.1 Types normalisés (extrait)

```python
@dataclass(frozen=True)
class DocumentRef:
    external_id: str           # identifiant stable dans la source
    version: str | None        # version telle que connue de la source

@dataclass(frozen=True)
class SourceDocument:
    ref: DocumentRef
    title: str
    filename: str | None
    extension: str | None
    mime_type: str | None
    size_bytes: int | None
    created_at: datetime | None
    modified_at: datetime | None
    author: str | None
    doc_class: str | None
    location: str | None       # chemin, vue, dossier…
    metadata: dict[str, JsonValue]          # métier normalisé (clés convenues)
    source_metadata: dict[str, JsonValue]   # brut, propre à la source
    content_hash: str | None   # si la source le fournit (sinon calculé à l'ingestion)

@dataclass(frozen=True)
class AccessEntry:
    principal: ExternalPrincipalRef | Literal["space"]   # "space" : membres de l'espace
    allow: bool                                          # False = refus explicite

@dataclass(frozen=True)
class DocumentAccess:
    ref: DocumentRef
    entries: tuple[AccessEntry, ...]
    complete: bool             # False ⇒ document traité comme invisible (fermé par défaut)
    reason: str | None         # pourquoi incomplet (affiché dans le rapport d'erreurs)
    raw: dict[str, JsonValue]  # instantané brut pour l'audit

@dataclass(frozen=True)
class Change:
    kind: Literal["upsert", "delete", "access_changed"]
    ref: DocumentRef
    document: SourceDocument | None
```

### 2.2 Interface

```python
class Connector(Protocol):
    kind: ClassVar[str]                       # "local_files", "mfiles"…
    capabilities: ClassVar[Capabilities]      # incremental, access, late_check, browse

    def __init__(self, config: SourceConfig, secrets: SecretView, log: Logger) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def test_connection(self) -> ConnectionReport: ...

    def browse(self, container: str | None = None) -> list[BrowseItem]: ...
    def list_documents(self, scope: Scope) -> Iterator[SourceDocument]: ...
    def list_changes(self, cursor: SyncCursor | None, scope: Scope) -> ChangeBatch: ...
    def fetch_content(self, ref: DocumentRef, dest: Path) -> FetchedFile: ...

    def list_principals(self) -> PrincipalSnapshot: ...      # utilisateurs, groupes, appartenances
    def get_access(self, refs: Sequence[DocumentRef]) -> list[DocumentAccess]: ...
    def check_access(self, principal: ExternalPrincipalRef,
                     refs: Sequence[DocumentRef]) -> dict[DocumentRef, bool]: ...  # si late_check
```

`ChangeBatch` contient les changements **et** le nouveau curseur. Le curseur n'est
enregistré qu'après le traitement complet du lot : une synchronisation interrompue
reprend au dernier lot terminé (scénario de recette 16).

### 2.3 Erreurs

| Exception | Signification | Réaction du cœur |
|---|---|---|
| `AuthenticationError` | identifiants refusés | source en erreur, administrateur prévenu, pas de nouvelle tentative automatique |
| `TransientError` | réseau, délai, serveur occupé | nouvelle tentative avec attente croissante |
| `NotFoundError` | document disparu entre la liste et la lecture | traité comme suppression |
| `AccessDeniedError` | le compte technique ne peut pas lire l'objet | document marqué « exclu » avec la raison |
| `UnsupportedError` | format ou fonction non pris en charge | document « exclu » |
| `ConnectorError` | autre | document « échec », sans bloquer les autres |

### 2.4 Tests de conformité

Une **suite de tests commune** (`connectors/base/conformance/`) sera exécutée sur
chaque connecteur : idempotence de la liste, curseur repris après interruption,
suppression détectée, droits incomplets ⇒ `complete=False`, fermeture propre.
Pour M-Files, la même suite tourne d'abord sur un **simulateur** puis sur un vrai
coffre.

---

## 3. Connecteur fichiers locaux

- **Racines** : dossiers locaux, partages réseau (chemins UNC `\\serveur\partage`
  sous Windows), montages sur le serveur. Plusieurs racines par source.
- **Exploration** récursive, filtres par extension (liste blanche des formats
  prioritaires), exclusion de sous-dossiers (motifs), taille maximale.
- **Fichiers ignorés** : temporaires et système (`~$*`, `.~lock.*`, `*.tmp`,
  `Thumbs.db`, `desktop.ini`, `.DS_Store`, dossiers cachés, `$RECYCLE.BIN`,
  `System Volume Information`), liens symboliques sortant de la racine.
- **Identifiant externe** : chemin relatif à la racine (normalisé). **Version** :
  taille + date de modification ; l'empreinte SHA-256 est calculée à l'ingestion
  pour éviter les réindexations inutiles.
- **Changements** : comparaison avec l'état connu (curseur = date de la dernière
  exploration complète) ; surveillance en direct facultative (évènements du système
  de fichiers), avec exploration complète périodique de contrôle.
- **Doublons** : fichiers d'empreinte identique signalés ; indexés une seule fois
  par source si l'administrateur le choisit.
- **Droits** : pas de lecture des droits Windows (NTFS) dans le MVP. Accès par
  espace documentaire, **désactivé par défaut** (`inherit_space_access`), voir
  `SECURITY.md` §2.2. La lecture des droits NTFS est une évolution possible.
- **Rapport d'ingestion** : fichiers trouvés, indexés, ignorés (avec raison),
  en échec.

---

## 4. Connecteur M-Files

### 4.1 Ce qui est certain

M-Files propose plusieurs interfaces officielles de programmation, dont la
disponibilité dépend de la **version** du serveur et de son **installation** :

- le service web REST (M-Files Web Service) ;
- l'API COM / .NET (bibliothèque cliente sous Windows) ;
- une API gRPC dans les versions récentes.

**Aucun point d'accès ni aucune méthode M-Files n'est supposé dans ce document.**
Le choix de l'interface et la liste exacte des appels seront établis à partir de
la documentation officielle correspondant à la version du client, puis vérifiés
sur un coffre de test.

### 4.2 Ce que le connecteur doit couvrir

| Besoin | Remarque |
|---|---|
| Connexion à un serveur et un coffre ; authentification | compte technique à droits limités en lecture ; TLS |
| Classes documentaires, sélection de ce qu'il faut indexer | `browse()` + `Scope` |
| Objets, fichiers (un objet M-Files peut contenir plusieurs fichiers) | chaque fichier → un `SourceDocument` ; identifiant externe = objet + fichier |
| Métadonnées (propriétés) | normalisées + copie brute dans `source_metadata` |
| Versions | nouvelle version ⇒ nouvelle `document_versions`, ancienne invalidée |
| Suppressions, objets détruits ou rendus inaccessibles | `Change(kind="delete")` |
| Changements incrémentaux | selon les possibilités de l'interface retenue (date de modification, journal) |
| Droits | listes de contrôle d'accès des objets, listes nommées, **permissions dépendant des métadonnées (pseudo-utilisateurs)**, refus explicites |
| Utilisateurs et groupes du coffre, appartenances | `list_principals()` ; groupes souvent synchronisés depuis Active Directory |
| Revérification au moment de la question | `check_access()` si l'interface permet de connaître les droits effectifs d'un utilisateur donné |

### 4.3 Stratégie pour les droits

1. Lire les droits de chaque objet et les traduire en `AccessEntry`.
2. Résoudre les permissions dépendant des métadonnées vers des utilisateurs ou
   groupes concrets **au moment de l'indexation** ; si la résolution échoue ou est
   ambiguë ⇒ `complete=False`.
3. Resynchroniser les droits à intervalle régulier (paramétrable) et à chaque
   modification d'objet détectée.
4. À chaque question, `check_access()` sur les documents retenus si possible.
5. Relier les utilisateurs M-Files aux comptes locaux (`principal_links`) :
   import manuel ou par fichier dans le MVP, Active Directory ensuite (ADR-0016).
   Un utilisateur local sans lien ne voit **aucun** document M-Files.

### 4.4 Informations nécessaires avant l'implémentation

- Version exacte de M-Files Server et mode d'installation (sur site, cloud).
- Interfaces activées (service web REST, gRPC) et méthode d'authentification
  (compte M-Files, Windows, fédérée).
- Un **coffre de test** avec : plusieurs classes, des documents à plusieurs
  versions, des fichiers multiples par objet, des droits variés (dont une
  permission dépendant d'une métadonnée et un refus explicite), au moins trois
  utilisateurs et deux groupes.
- Un compte technique de lecture et deux comptes utilisateurs de test.
- La documentation officielle de l'API pour cette version.

### 4.5 Plan de développement

Décision Q8 : **aucun coffre M-Files n'est disponible pour l'instant.** Les étapes
1 et 2 avancent ; les étapes 3 et 4 attendent un coffre de test. D'ici là, le
connecteur M-Files est présenté comme « en développement, non validé ».


1. Implémenter le connecteur contre un **simulateur** qui respecte le contrat
   (permet de tester tout le cœur sans M-Files).
2. Étude de l'API sur la documentation officielle de la version cible ; ADR du
   choix d'interface.
3. Implémentation réelle, suite de conformité sur le coffre de test.
4. Tests de droits spécifiques : chaque utilisateur de test pose les mêmes
   questions ; les réponses ne doivent citer que ce qu'il peut ouvrir dans M-Files.

---

## 5. Connecteurs futurs

Alfresco, SharePoint, OneDrive, Google Drive, Nextcloud, SFTP, S3, bases SQL : même
interface, même suite de conformité. La difficulté principale sera toujours la
traduction des droits ; la règle « incertain ⇒ invisible » s'applique à tous.
