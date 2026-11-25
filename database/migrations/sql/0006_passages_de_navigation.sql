-- Migration 0006 — sommaires, tables des matières, listes de tableaux et index (« navigation ») :
-- reconnus à l'indexation et placés après les passages de contenu au classement.
ALTER TABLE chunks DROP CONSTRAINT chunks_kind_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_kind_check CHECK (kind IN ('text', 'table', 'list', 'ocr', 'navigation'));
