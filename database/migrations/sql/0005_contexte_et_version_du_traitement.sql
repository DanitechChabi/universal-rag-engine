-- Migration 0005 — phase 3 : contexte du document et version du traitement d'indexation (ADR-0021).

ALTER TABLE document_versions ADD COLUMN context text;
ALTER TABLE document_versions ADD COLUMN pipeline_version integer NOT NULL DEFAULT 1;

-- Un même contenu est réindexé quand le traitement change (découpage, contexte…).
DROP INDEX document_versions_content_uq;
CREATE UNIQUE INDEX document_versions_content_uq
    ON document_versions (document_id, sha256, embedding_profile_id, coalesce(ocr_engine, ''), pipeline_version);
