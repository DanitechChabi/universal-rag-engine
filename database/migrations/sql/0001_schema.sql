-- =============================================================================
-- Universal RAG Engine — schéma de référence PostgreSQL (phase 0)
--
-- Source de vérité pour la conception. À partir de la phase 1, le schéma est
-- appliqué par des migrations Alembic qui doivent produire exactement ce schéma
-- (test de cohérence prévu dans docs/TESTING.md).
--
-- Principes (docs/DATABASE.md, docs/SECURITY.md) :
--   * org_id sur toutes les tables métier ; clés étrangères composites
--     (org_id, id) pour interdire tout lien entre deux organisations ;
--   * Row Level Security forcée : sans organisation courante
--     (SET urag.org_id), aucune ligne n'est visible ni modifiable ;
--   * fermé par défaut : un document dont les droits sont incertains
--     n'a aucune clé d'accès ;
--   * journal d'audit en ajout seul.
--
-- Testé avec PostgreSQL 16 : database/tests/test_schema.sh
-- =============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Configuration plein texte française insensible aux accents.
CREATE TEXT SEARCH CONFIGURATION urag_fr (COPY = french);
ALTER TEXT SEARCH CONFIGURATION urag_fr
    ALTER MAPPING FOR hword, hword_part, word WITH unaccent, french_stem;

-- Organisation courante, fixée par l'application à chaque transaction :
--   SET LOCAL urag.org_id = '<uuid>';
-- Absente ou vide ⇒ NULL ⇒ aucune ligne visible.
CREATE FUNCTION urag_current_org() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT nullif(current_setting('urag.org_id', true), '')::uuid $$;

-- Format des clés d'accès : u:, g:, sp:, xu:, xg: suivis d'un UUID.
CREATE FUNCTION urag_valid_access_keys(keys text[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT coalesce(bool_and(k ~ '^(u|g|sp|xu|xg):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'), true)
          FROM unnest(keys) AS k $$;

-- -----------------------------------------------------------------------------
-- Types
-- -----------------------------------------------------------------------------
CREATE TYPE user_role       AS ENUM ('super_admin', 'org_admin', 'doc_admin', 'user', 'auditor');
CREATE TYPE account_status  AS ENUM ('active', 'disabled');
CREATE TYPE principal_kind  AS ENUM ('user', 'group');
CREATE TYPE source_kind     AS ENUM ('local_files', 'mfiles');
CREATE TYPE source_status   AS ENUM ('active', 'disabled', 'error');
CREATE TYPE index_status    AS ENUM ('pending', 'processing', 'indexed', 'indexed_with_warning',
                                     'failed', 'excluded', 'deleted');
CREATE TYPE acl_status      AS ENUM ('complete', 'uncertain');
CREATE TYPE job_status      AS ENUM ('queued', 'running', 'succeeded', 'failed', 'cancelled');
CREATE TYPE message_role    AS ENUM ('user', 'assistant');
CREATE TYPE model_purpose   AS ENUM ('chat', 'embedding', 'rerank');
CREATE TYPE model_locality  AS ENUM ('local', 'external');
CREATE TYPE provider_kind   AS ENUM ('ollama', 'openai_compatible', 'anthropic', 'gemini', 'openai');
CREATE TYPE ai_policy_mode  AS ENUM ('local_only', 'hybrid', 'cloud_allowed');
CREATE TYPE embedding_state AS ENUM ('building', 'active', 'retired');

-- -----------------------------------------------------------------------------
-- Organisations, utilisateurs, groupes, rôles
-- -----------------------------------------------------------------------------
CREATE TABLE organizations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    login            text NOT NULL CHECK (length(login) BETWEEN 2 AND 120),
    display_name     text NOT NULL,
    email            text,
    password_hash    text,                 -- Argon2id ; NULL si authentification externe (LDAP, plus tard)
    status           account_status NOT NULL DEFAULT 'active',
    failed_logins    integer NOT NULL DEFAULT 0 CHECK (failed_logins >= 0),
    locked_until     timestamptz,
    last_login_at    timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id)
);
-- Identifiant de connexion unique sur l'installation (insensible à la casse).
CREATE UNIQUE INDEX users_login_uq ON users (lower(login));

CREATE TABLE user_roles (
    org_id   uuid NOT NULL,
    user_id  uuid NOT NULL,
    role     user_role NOT NULL,
    PRIMARY KEY (user_id, role),
    FOREIGN KEY (org_id, user_id) REFERENCES users(org_id, id) ON DELETE CASCADE
);

CREATE TABLE groups (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    UNIQUE (org_id, name)
);

CREATE TABLE group_members (
    org_id    uuid NOT NULL,
    group_id  uuid NOT NULL,
    user_id   uuid NOT NULL,
    PRIMARY KEY (group_id, user_id),
    FOREIGN KEY (org_id, group_id) REFERENCES groups(org_id, id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, user_id)  REFERENCES users(org_id, id)  ON DELETE CASCADE
);

-- Sessions : seul le hachage du jeton de rafraîchissement est stocké.
CREATE TABLE sessions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL,
    user_id             uuid NOT NULL,
    refresh_token_hash  bytea NOT NULL UNIQUE,
    family_id           uuid NOT NULL,        -- rotation : réutilisation détectée ⇒ famille révoquée
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,
    revoked_at          timestamptz,
    ip                  inet,
    user_agent          text,
    FOREIGN KEY (org_id, user_id) REFERENCES users(org_id, id) ON DELETE CASCADE
);
CREATE INDEX sessions_user_idx ON sessions (user_id) WHERE revoked_at IS NULL;

-- -----------------------------------------------------------------------------
-- Secrets chiffrés (AES-256-GCM, clé maîtresse hors base) — ADR-0012
-- -----------------------------------------------------------------------------
CREATE TABLE secrets (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    purpose      text NOT NULL,                 -- ex. 'source:mfiles', 'provider:anthropic'
    key_version  integer NOT NULL CHECK (key_version > 0),
    nonce        bytea NOT NULL CHECK (length(nonce) = 12),
    ciphertext   bytea NOT NULL,                -- inclut l'étiquette GCM
    created_at   timestamptz NOT NULL DEFAULT now(),
    rotated_at   timestamptz,
    UNIQUE (org_id, id)
);

-- -----------------------------------------------------------------------------
-- Espaces documentaires et sources
-- -----------------------------------------------------------------------------
CREATE TABLE spaces (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name        text NOT NULL,
    description text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    UNIQUE (org_id, name)
);

-- Qui peut interroger un espace (en plus des droits propres à chaque document).
CREATE TABLE space_grants (
    org_id          uuid NOT NULL,
    space_id        uuid NOT NULL,
    principal_type  principal_kind NOT NULL,
    principal_id    uuid NOT NULL,      -- users.id ou groups.id (vérifié par l'application)
    PRIMARY KEY (space_id, principal_type, principal_id),
    FOREIGN KEY (org_id, space_id) REFERENCES spaces(org_id, id) ON DELETE CASCADE
);

CREATE TABLE sources (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid NOT NULL,
    space_id           uuid NOT NULL,
    kind               source_kind NOT NULL,
    name               text NOT NULL,
    config             jsonb NOT NULL DEFAULT '{}'::jsonb,   -- paramètres non secrets uniquement
    secret_id          uuid,                                 -- identifiants de connexion chiffrés
    status             source_status NOT NULL DEFAULT 'active',
    enabled            boolean NOT NULL DEFAULT true,
    -- Fermé par défaut : sans droits propres aux documents (fichiers locaux),
    -- les documents héritent des membres de l'espace seulement si l'administrateur l'a voulu.
    inherit_space_access boolean NOT NULL DEFAULT false,
    supports_late_check  boolean NOT NULL DEFAULT false,     -- revérification des droits à la question
    sync_cursor        jsonb,                                -- curseur de synchronisation incrémentale
    last_sync_at       timestamptz,
    last_sync_status   text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    FOREIGN KEY (org_id, space_id)  REFERENCES spaces(org_id, id)  ON DELETE RESTRICT,
    FOREIGN KEY (org_id, secret_id) REFERENCES secrets(org_id, id) ON DELETE RESTRICT,
    CHECK (NOT (config ?| ARRAY['password', 'api_key', 'token', 'secret']))
);

-- -----------------------------------------------------------------------------
-- Identités externes (ex. utilisateurs et groupes M-Files) — ADR-0016
-- -----------------------------------------------------------------------------
CREATE TABLE external_principals (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    source_id     uuid NOT NULL,
    kind          principal_kind NOT NULL,
    external_id   text NOT NULL,
    display_name  text,
    synced_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    UNIQUE (source_id, kind, external_id),
    FOREIGN KEY (org_id, source_id) REFERENCES sources(org_id, id) ON DELETE CASCADE
);

-- Appartenance des utilisateurs externes aux groupes externes (synchronisée depuis la source).
CREATE TABLE external_group_members (
    org_id                 uuid NOT NULL,
    external_group_id      uuid NOT NULL,
    external_user_id       uuid NOT NULL,
    PRIMARY KEY (external_group_id, external_user_id),
    FOREIGN KEY (org_id, external_group_id) REFERENCES external_principals(org_id, id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, external_user_id)  REFERENCES external_principals(org_id, id) ON DELETE CASCADE
);

-- Correspondance compte local ↔ utilisateur externe (saisie, import, ou LDAP plus tard).
CREATE TABLE principal_links (
    org_id                 uuid NOT NULL,
    user_id                uuid NOT NULL,
    external_principal_id  uuid NOT NULL,
    verified               boolean NOT NULL DEFAULT false,
    created_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, external_principal_id),
    UNIQUE (external_principal_id),       -- une identité externe ⇒ un seul compte local
    FOREIGN KEY (org_id, user_id)               REFERENCES users(org_id, id)               ON DELETE CASCADE,
    FOREIGN KEY (org_id, external_principal_id) REFERENCES external_principals(org_id, id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------------------
-- Profils d'embedding (dimension et version enregistrées) — section 9.6
-- -----------------------------------------------------------------------------
CREATE TABLE embedding_profiles (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name       text NOT NULL,
    model_revision   text NOT NULL,
    dimension        integer NOT NULL CHECK (dimension > 0),
    has_sparse       boolean NOT NULL DEFAULT false,
    collection_name  text NOT NULL UNIQUE CHECK (collection_name ~ '^[a-z0-9_]{1,64}$'),
    state            embedding_state NOT NULL DEFAULT 'building',
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (model_name, model_revision)
);
-- Un seul profil actif à la fois (réindexation : nouveau profil « building », puis bascule).
CREATE UNIQUE INDEX embedding_profiles_one_active ON embedding_profiles ((true)) WHERE state = 'active';

-- -----------------------------------------------------------------------------
-- Documents, versions, fragments
-- -----------------------------------------------------------------------------
CREATE TABLE documents (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL,
    source_id           uuid NOT NULL,
    external_id         text NOT NULL,
    title               text NOT NULL,
    filename            text,
    extension           text,
    mime_type           text,
    size_bytes          bigint CHECK (size_bytes >= 0),
    source_created_at   timestamptz,
    source_modified_at  timestamptz,
    source_version      text,                  -- version telle que connue de la source
    author              text,
    doc_class           text,
    location            text,                  -- chemin ou emplacement dans la source
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,   -- métadonnées métier normalisées
    source_metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- champ extensible propre à la GED
    sha256              bytea CHECK (sha256 IS NULL OR length(sha256) = 32),
    -- Droits : clés d'accès effectives (docs/SECURITY.md). Vide ⇒ personne.
    access_keys         text[] NOT NULL DEFAULT '{}',
    acl_status          acl_status NOT NULL DEFAULT 'uncertain',
    acl_snapshot        jsonb,                 -- droits bruts de la source, pour l'audit
    acl_synced_at       timestamptz,
    status              index_status NOT NULL DEFAULT 'pending',
    status_detail       text,
    current_version_id  uuid,
    excluded            boolean NOT NULL DEFAULT false,
    deleted_at          timestamptz,           -- supprimé de la source ou retiré de l'index
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    UNIQUE (source_id, external_id),           -- idempotence de la synchronisation
    FOREIGN KEY (org_id, source_id) REFERENCES sources(org_id, id) ON DELETE CASCADE,
    CHECK (acl_status = 'complete' OR access_keys = '{}'),        -- fermé par défaut
    CHECK (urag_valid_access_keys(access_keys))
);
CREATE INDEX documents_access_keys_gin ON documents USING gin (access_keys);
CREATE INDEX documents_source_status_idx ON documents (source_id, status);
CREATE INDEX documents_title_trgm ON documents USING gin (title gin_trgm_ops);

CREATE TABLE document_versions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                uuid NOT NULL,
    document_id           uuid NOT NULL,
    source_version        text,
    sha256                bytea NOT NULL CHECK (length(sha256) = 32),
    embedding_profile_id  uuid REFERENCES embedding_profiles(id),
    extractor             text,                -- ex. 'pypdfium2/4.x', pour réindexer si l'outil évolue
    ocr_engine            text,                -- NULL si pas d'OCR
    ocr_min_confidence    real CHECK (ocr_min_confidence BETWEEN 0 AND 1),
    page_count            integer CHECK (page_count >= 0),
    chunk_count           integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    language              text,
    status                index_status NOT NULL DEFAULT 'processing',
    warnings              jsonb NOT NULL DEFAULT '[]'::jsonb,
    error                 text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    indexed_at            timestamptz,
    superseded_at         timestamptz,         -- remplacée par une version plus récente (traçabilité)
    UNIQUE (org_id, id),
    UNIQUE (document_id, sha256, embedding_profile_id),   -- idempotence
    FOREIGN KEY (org_id, document_id) REFERENCES documents(org_id, id) ON DELETE CASCADE
);

ALTER TABLE documents
    ADD CONSTRAINT documents_current_version_fk
    FOREIGN KEY (org_id, current_version_id) REFERENCES document_versions(org_id, id)
    ON DELETE SET NULL (current_version_id) DEFERRABLE INITIALLY DEFERRED;

-- Le texte des fragments est stocké ici (source unique) ; Qdrant ne garde que
-- les vecteurs et les champs de filtre. ADR-0005.
CREATE TABLE chunks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- = identifiant du point Qdrant
    org_id        uuid NOT NULL,
    document_id   uuid NOT NULL,
    version_id    uuid NOT NULL,
    ordinal       integer NOT NULL CHECK (ordinal >= 0),
    text          text NOT NULL,
    page_start    integer CHECK (page_start >= 1),
    page_end      integer CHECK (page_end >= page_start),
    section_path  text[],                     -- titres englobants
    kind          text NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'table', 'list', 'ocr')),
    language      text,
    token_count   integer CHECK (token_count >= 0),
    tsv           tsvector GENERATED ALWAYS AS (
                      to_tsvector(CASE WHEN language = 'en' THEN 'english'::regconfig
                                       ELSE 'urag_fr'::regconfig END, text)) STORED,
    UNIQUE (org_id, id),
    UNIQUE (version_id, ordinal),
    FOREIGN KEY (org_id, document_id) REFERENCES documents(org_id, id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, version_id)  REFERENCES document_versions(org_id, id) ON DELETE CASCADE
);
CREATE INDEX chunks_tsv_gin  ON chunks USING gin (tsv);
CREATE INDEX chunks_trgm_gin ON chunks USING gin (text gin_trgm_ops);   -- références exactes
CREATE INDEX chunks_document_idx ON chunks (document_id);

-- Fragments interrogeables : version courante, document non supprimé, non exclu, droits complets.
CREATE VIEW searchable_chunks WITH (security_barrier = true, security_invoker = true) AS
SELECT c.*, d.source_id, d.access_keys, d.doc_class, d.title, d.source_modified_at
FROM chunks c
JOIN documents d ON d.org_id = c.org_id AND d.id = c.document_id
WHERE c.version_id = d.current_version_id
  AND d.deleted_at IS NULL
  AND NOT d.excluded
  AND d.acl_status = 'complete'
  AND d.status IN ('indexed', 'indexed_with_warning');

-- -----------------------------------------------------------------------------
-- Conversations, messages, citations
-- -----------------------------------------------------------------------------
CREATE TABLE conversations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL,
    user_id     uuid NOT NULL,
    title       text NOT NULL DEFAULT 'Nouvelle conversation',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    deleted_at  timestamptz,
    UNIQUE (org_id, id),
    FOREIGN KEY (org_id, user_id) REFERENCES users(org_id, id) ON DELETE CASCADE
);
CREATE INDEX conversations_user_idx ON conversations (user_id, updated_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE messages (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid NOT NULL,
    conversation_id  uuid NOT NULL,
    role             message_role NOT NULL,
    content          text NOT NULL,
    model_id         uuid,
    locality         model_locality,
    tokens_in        integer CHECK (tokens_in >= 0),
    tokens_out       integer CHECK (tokens_out >= 0),
    latency_ms       integer CHECK (latency_ms >= 0),
    insufficient     boolean NOT NULL DEFAULT false,   -- « les documents ne permettent pas de répondre »
    feedback         smallint CHECK (feedback IN (-1, 1)),
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    FOREIGN KEY (org_id, conversation_id) REFERENCES conversations(org_id, id) ON DELETE CASCADE
);
CREATE INDEX messages_conversation_idx ON messages (conversation_id, created_at);

-- Une citation garde une copie de l'extrait : la conversation reste lisible si le
-- document change, mais l'accès au document est revérifié à chaque consultation.
CREATE TABLE citations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL,
    message_id   uuid NOT NULL,
    rank         integer NOT NULL CHECK (rank >= 1),
    chunk_id     uuid,                     -- NULL si le fragment a depuis été supprimé
    document_id  uuid NOT NULL,
    version_id   uuid,
    page_start   integer,
    page_end     integer,
    excerpt      text NOT NULL,
    UNIQUE (message_id, rank),
    FOREIGN KEY (org_id, message_id)  REFERENCES messages(org_id, id)  ON DELETE CASCADE,
    FOREIGN KEY (org_id, document_id) REFERENCES documents(org_id, id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, chunk_id)    REFERENCES chunks(org_id, id)    ON DELETE SET NULL (chunk_id)
);

-- -----------------------------------------------------------------------------
-- Fournisseurs et modèles IA, politique, consommation
-- -----------------------------------------------------------------------------
CREATE TABLE ai_providers (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      uuid NOT NULL,
    kind        provider_kind NOT NULL,
    name        text NOT NULL,
    endpoint    text,
    locality    model_locality NOT NULL,
    secret_id   uuid,
    enabled     boolean NOT NULL DEFAULT false,   -- désactivé tant que non configuré
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, id),
    UNIQUE (org_id, name),
    FOREIGN KEY (org_id, secret_id) REFERENCES secrets(org_id, id) ON DELETE RESTRICT,
    CHECK (kind <> 'ollama' OR locality = 'local'),
    CHECK (kind NOT IN ('anthropic', 'gemini', 'openai') OR locality = 'external')
);

CREATE TABLE ai_models (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            uuid NOT NULL,
    provider_id       uuid NOT NULL,
    name              text NOT NULL,
    purpose           model_purpose NOT NULL,
    context_window    integer CHECK (context_window > 0),
    max_output_tokens integer CHECK (max_output_tokens > 0),
    temperature       real CHECK (temperature BETWEEN 0 AND 2),
    timeout_s         integer NOT NULL DEFAULT 120 CHECK (timeout_s > 0),
    max_concurrency   integer NOT NULL DEFAULT 1 CHECK (max_concurrency > 0),
    priority          integer NOT NULL DEFAULT 100,
    enabled           boolean NOT NULL DEFAULT false,
    available         boolean NOT NULL DEFAULT false,   -- dernier test de disponibilité
    last_checked_at   timestamptz,
    input_cost_per_mtok   numeric(12, 6),               -- estimation des coûts (API externes)
    output_cost_per_mtok  numeric(12, 6),
    UNIQUE (org_id, id),
    UNIQUE (provider_id, name, purpose),
    FOREIGN KEY (org_id, provider_id) REFERENCES ai_providers(org_id, id) ON DELETE CASCADE
);

ALTER TABLE messages
    ADD CONSTRAINT messages_model_fk FOREIGN KEY (org_id, model_id)
    REFERENCES ai_models(org_id, id) ON DELETE SET NULL (model_id);

-- Une politique par organisation. Par défaut : local uniquement.
CREATE TABLE ai_policies (
    org_id                        uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    mode                          ai_policy_mode NOT NULL DEFAULT 'local_only',
    allow_external_questions      boolean NOT NULL DEFAULT false,
    allow_external_documents      boolean NOT NULL DEFAULT false,
    notify_user_on_external       boolean NOT NULL DEFAULT true,
    allow_fallback_to_external    boolean NOT NULL DEFAULT false,
    updated_at                    timestamptz NOT NULL DEFAULT now(),
    CHECK (mode <> 'local_only' OR NOT (allow_external_questions OR allow_external_documents
                                         OR allow_fallback_to_external)),
    CHECK (mode = 'cloud_allowed' OR NOT allow_external_documents OR mode = 'hybrid')
);

CREATE TABLE usage_records (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id         uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id        uuid,
    model_id       uuid,
    purpose        model_purpose NOT NULL,
    locality       model_locality NOT NULL,
    tokens_in      integer NOT NULL DEFAULT 0,
    tokens_out     integer NOT NULL DEFAULT 0,
    cost_estimate  numeric(12, 6),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usage_records_org_time ON usage_records (org_id, created_at);

CREATE TABLE usage_limits (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         uuid,                      -- NULL = limite de l'organisation
    period          text NOT NULL CHECK (period IN ('day', 'month')),
    max_tokens      bigint CHECK (max_tokens > 0),
    max_cost        numeric(12, 2) CHECK (max_cost > 0),
    alert_ratio     real NOT NULL DEFAULT 0.8 CHECK (alert_ratio > 0 AND alert_ratio <= 1),
    disable_on_exceed boolean NOT NULL DEFAULT true,
    UNIQUE NULLS NOT DISTINCT (org_id, user_id, period)
);

-- -----------------------------------------------------------------------------
-- File de tâches (ADR-0003)
-- -----------------------------------------------------------------------------
CREATE TABLE jobs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind          text NOT NULL,              -- 'sync_source', 'ingest_document', 'backup'…
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    dedup_key     text,                       -- une seule tâche active par clé
    priority      smallint NOT NULL DEFAULT 100,   -- plus petit = plus prioritaire
    status        job_status NOT NULL DEFAULT 'queued',
    attempts      integer NOT NULL DEFAULT 0,
    max_attempts  integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    run_after     timestamptz NOT NULL DEFAULT now(),
    locked_by     text,
    locked_at     timestamptz,
    heartbeat_at  timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    progress      real CHECK (progress BETWEEN 0 AND 1),
    last_error    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz
);
CREATE INDEX jobs_ready_idx ON jobs (priority, run_after, id) WHERE status = 'queued';
CREATE UNIQUE INDEX jobs_dedup_active ON jobs (org_id, dedup_key)
    WHERE dedup_key IS NOT NULL AND status IN ('queued', 'running');

-- -----------------------------------------------------------------------------
-- Audit (ajout seul), licences, paramètres, sauvegardes
-- -----------------------------------------------------------------------------
CREATE TABLE audit_log (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    actor_user_id uuid,
    action        text NOT NULL,              -- ex. 'auth.login', 'source.create', 'ai.external_call'
    outcome       text NOT NULL DEFAULT 'success' CHECK (outcome IN ('success', 'failure', 'denied')),
    target_type   text,
    target_id     text,
    ip            inet,
    details       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- jamais de contenu documentaire ni de secret
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_org_time ON audit_log (org_id, created_at DESC);

CREATE FUNCTION urag_audit_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    -- Seule la purge selon la durée de conservation (urag_audit_purge, exécutée
    -- avec les droits de urag_maintenance) peut supprimer des lignes.
    IF TG_OP = 'DELETE' AND current_user = 'urag_maintenance' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_log est en ajout seul (%)', TG_OP;
END $$;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION urag_audit_append_only();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION urag_audit_append_only();

CREATE FUNCTION urag_audit_purge(p_older_than interval) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n bigint;
BEGIN
    IF p_older_than < interval '30 days' THEN
        RAISE EXCEPTION 'durée de conservation trop courte : %', p_older_than;
    END IF;
    DELETE FROM audit_log WHERE created_at < now() - p_older_than;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

CREATE TABLE licenses (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    license_id     text NOT NULL UNIQUE,
    license_type   text NOT NULL,
    payload        jsonb NOT NULL,            -- contenu signé tel que reçu
    signature      bytea NOT NULL,            -- Ed25519
    activated_at   timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz,
    max_users      integer CHECK (max_users > 0),
    max_sources    integer CHECK (max_sources > 0),
    features       text[] NOT NULL DEFAULT '{}',
    status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked', 'superseded'))
);

CREATE TABLE settings (
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key         text NOT NULL,
    value       jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  uuid,
    PRIMARY KEY (org_id, key)
);

CREATE TABLE backups (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind         text NOT NULL CHECK (kind IN ('manual', 'scheduled')),
    status       text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'verified')),
    location     text NOT NULL,
    sha256       bytea,
    size_bytes   bigint,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    error        text
);

-- -----------------------------------------------------------------------------
-- Clés d'accès d'un utilisateur (docs/SECURITY.md §2)
--   u:<user>, g:<groupe>, sp:<espace accordé>, xu:<identité externe liée>,
--   xg:<groupe externe de cette identité>
-- Recalculées à chaque question : un retrait de droit prend effet immédiatement.
-- -----------------------------------------------------------------------------
CREATE FUNCTION urag_user_access_keys(p_user uuid) RETURNS text[]
    LANGUAGE sql STABLE SECURITY INVOKER AS $$
    WITH me AS (
        SELECT id, org_id FROM users
        WHERE id = p_user AND status = 'active' AND org_id = urag_current_org()
    ),
    my_groups AS (
        SELECT gm.group_id FROM group_members gm JOIN me ON gm.user_id = me.id
    ),
    my_spaces AS (
        SELECT sg.space_id FROM space_grants sg, me
        WHERE (sg.principal_type = 'user' AND sg.principal_id = me.id)
           OR (sg.principal_type = 'group' AND sg.principal_id IN (SELECT group_id FROM my_groups))
    ),
    my_external AS (
        SELECT pl.external_principal_id AS id FROM principal_links pl JOIN me ON pl.user_id = me.id
    ),
    my_external_groups AS (
        SELECT egm.external_group_id AS id FROM external_group_members egm
        WHERE egm.external_user_id IN (SELECT id FROM my_external)
    )
    SELECT coalesce(array_agg(k), '{}') FROM (
        SELECT 'u:'  || id FROM me
        UNION SELECT 'g:'  || group_id FROM my_groups
        UNION SELECT 'sp:' || space_id FROM my_spaces
        UNION SELECT 'xu:' || id FROM my_external
        UNION SELECT 'xg:' || id FROM my_external_groups
    ) AS keys(k)
$$;

-- -----------------------------------------------------------------------------
-- Connexion : recherche du compte avant de connaître l'organisation.
-- Seule exception à la RLS, limitée aux champs nécessaires à l'authentification.
-- -----------------------------------------------------------------------------
CREATE FUNCTION urag_auth_lookup(p_login text)
    RETURNS TABLE (user_id uuid, org_id uuid, password_hash text, status account_status,
                   failed_logins integer, locked_until timestamptz)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT id, org_id, password_hash, status, failed_logins, locked_until
    FROM users WHERE lower(login) = lower(p_login)
$$;

-- -----------------------------------------------------------------------------
-- Worker : organisations ayant des tâches prêtes (identifiants seulement).
-- Le worker traite ensuite chaque organisation dans sa propre transaction (RLS).
-- -----------------------------------------------------------------------------
CREATE FUNCTION urag_orgs_with_ready_jobs() RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT DISTINCT org_id FROM jobs WHERE status = 'queued' AND run_after <= now()
$$;

-- -----------------------------------------------------------------------------
-- Row Level Security : isolation stricte par organisation
-- -----------------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'users', 'user_roles', 'groups', 'group_members', 'sessions', 'secrets',
        'spaces', 'space_grants', 'sources', 'external_principals', 'external_group_members',
        'principal_links', 'documents', 'document_versions', 'chunks', 'conversations',
        'messages', 'citations', 'ai_providers', 'ai_models', 'ai_policies', 'usage_records',
        'usage_limits', 'jobs', 'audit_log', 'licenses', 'settings', 'backups'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY org_isolation ON %I USING (org_id = urag_current_org()) '
            'WITH CHECK (org_id = urag_current_org())', t);
    END LOOP;
END $$;

-- organizations : chaque organisation ne voit qu'elle-même.
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY org_self ON organizations USING (id = urag_current_org()) WITH CHECK (id = urag_current_org());

-- -----------------------------------------------------------------------------
-- Droits des rôles (roles.sql doit avoir été exécuté)
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO urag_app, urag_auth, urag_maintenance;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO urag_app;
REVOKE UPDATE, DELETE ON audit_log FROM urag_app;            -- ajout seul
REVOKE INSERT, UPDATE, DELETE ON organizations FROM urag_app; -- création par le super administrateur (maintenance)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO urag_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO urag_app;

GRANT SELECT ON users TO urag_auth;
ALTER FUNCTION urag_auth_lookup(text) OWNER TO urag_auth;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO urag_maintenance;
GRANT INSERT ON organizations TO urag_maintenance;
GRANT DELETE ON audit_log TO urag_maintenance;
ALTER FUNCTION urag_audit_purge(interval) OWNER TO urag_maintenance;
GRANT SELECT ON jobs TO urag_maintenance;
ALTER FUNCTION urag_orgs_with_ready_jobs() OWNER TO urag_maintenance;
REVOKE EXECUTE ON FUNCTION urag_audit_purge(interval) FROM PUBLIC, urag_app;

COMMIT;
