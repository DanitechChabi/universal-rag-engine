-- Migration 0004 — phase 3 : refus explicites des sources (ADR-0020).

CREATE FUNCTION urag_doc_visible(access_keys text[], deny_keys text[], user_keys text[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT access_keys && user_keys AND NOT (deny_keys && user_keys) $$;
GRANT EXECUTE ON FUNCTION urag_doc_visible(text[], text[], text[]) TO urag_app;

ALTER TABLE documents ADD COLUMN deny_keys text[] NOT NULL DEFAULT '{}';
ALTER TABLE documents ADD CONSTRAINT documents_deny_keys_valid CHECK (urag_valid_access_keys(deny_keys));
ALTER TABLE documents ADD CONSTRAINT documents_deny_keys_closed CHECK (acl_status = 'complete' OR deny_keys = '{}');

DROP VIEW searchable_chunks;
CREATE VIEW searchable_chunks WITH (security_barrier = true, security_invoker = true) AS
SELECT c.*, d.source_id, d.access_keys, d.doc_class, d.title, d.source_modified_at, d.deny_keys
FROM chunks c
JOIN documents d ON d.org_id = c.org_id AND d.id = c.document_id
WHERE c.version_id = d.current_version_id
  AND d.deleted_at IS NULL
  AND NOT d.excluded
  AND d.acl_status = 'complete'
  AND d.status IN ('indexed', 'indexed_with_warning');
GRANT SELECT, INSERT, UPDATE, DELETE ON searchable_chunks TO urag_app;
GRANT SELECT ON searchable_chunks TO urag_maintenance;
