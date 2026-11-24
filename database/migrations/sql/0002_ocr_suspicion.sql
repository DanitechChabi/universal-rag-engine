-- Migration 0002 — phase 2 : réindexation quand le moteur OCR change, passages suspects.

-- Une même empreinte peut être réindexée avec un autre moteur OCR (pages scannées enfin lues).
ALTER TABLE document_versions DROP CONSTRAINT document_versions_document_id_sha256_embedding_profile_id_key;
CREATE UNIQUE INDEX document_versions_content_uq
    ON document_versions (document_id, sha256, embedding_profile_id, coalesce(ocr_engine, ''));

-- Passages contenant des consignes adressées à une IA (injection de prompt) : écartés du contexte.
ALTER TABLE chunks ADD COLUMN suspicious boolean NOT NULL DEFAULT false;
ALTER TABLE chunks ADD COLUMN suspicious_reason text;

-- La vue reprend les nouvelles colonnes de chunks.
DROP VIEW searchable_chunks;
CREATE VIEW searchable_chunks WITH (security_barrier = true, security_invoker = true) AS
SELECT c.*, d.source_id, d.access_keys, d.doc_class, d.title, d.source_modified_at
FROM chunks c
JOIN documents d ON d.org_id = c.org_id AND d.id = c.document_id
WHERE c.version_id = d.current_version_id
  AND d.deleted_at IS NULL
  AND NOT d.excluded
  AND d.acl_status = 'complete'
  AND d.status IN ('indexed', 'indexed_with_warning');
GRANT SELECT, INSERT, UPDATE, DELETE ON searchable_chunks TO urag_app;
GRANT SELECT ON searchable_chunks TO urag_maintenance;
