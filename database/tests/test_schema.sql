-- Tests du schéma de référence. Exécuté par test_schema.sh sur une base neuve.
\set ON_ERROR_STOP on
SET client_min_messages = warning;

-- Outils de test --------------------------------------------------------------
CREATE FUNCTION pg_temp.expect_error(q text, expected_sqlstate text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE q;
    RAISE EXCEPTION 'ÉCHEC : la requête aurait dû échouer (%): %', expected_sqlstate, q;
EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = 'P0001' AND SQLERRM LIKE 'ÉCHEC%' THEN RAISE; END IF;
    IF expected_sqlstate IS NOT NULL AND SQLSTATE <> expected_sqlstate THEN
        RAISE EXCEPTION 'ÉCHEC : sqlstate % attendu, % obtenu (%) pour : %', expected_sqlstate, SQLSTATE, SQLERRM, q;
    END IF;
    RAISE NOTICE 'ok  refus attendu [%] %', SQLSTATE, regexp_replace(left(q, 70), '\s+', ' ', 'g');
END $$;

CREATE FUNCTION pg_temp.check(cond boolean, label text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF cond IS NOT TRUE THEN RAISE EXCEPTION 'ÉCHEC : %', label; END IF;
    RAISE NOTICE 'ok  %', label;
END $$;
SET client_min_messages = notice;

-- Données de test (superutilisateur : la RLS ne s'applique pas ici) -------------
-- Organisation A : a000…   Organisation B : b000…
INSERT INTO organizations (id, name, slug) VALUES
  ('a0000000-0000-0000-0000-000000000001', 'Banque A', 'banque-a'),
  ('b0000000-0000-0000-0000-000000000001', 'Assurance B', 'assurance-b');

INSERT INTO users (id, org_id, login, display_name, password_hash) VALUES
  ('a1000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'alice', 'Alice', 'argon2id$test'),
  ('a1000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'arnaud', 'Arnaud', 'argon2id$test'),
  ('b1000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'bruno', 'Bruno', 'argon2id$test');

INSERT INTO groups (id, org_id, name) VALUES
  ('a2000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'Juridique');
INSERT INTO group_members (org_id, group_id, user_id) VALUES
  ('a0000000-0000-0000-0000-000000000001', 'a2000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001');

INSERT INTO spaces (id, org_id, name) VALUES
  ('a3000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'Contrats'),
  ('b3000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'Sinistres');
INSERT INTO space_grants VALUES
  ('a0000000-0000-0000-0000-000000000001', 'a3000000-0000-0000-0000-000000000001', 'group', 'a2000000-0000-0000-0000-000000000001');

INSERT INTO sources (id, org_id, space_id, kind, name) VALUES
  ('a4000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'a3000000-0000-0000-0000-000000000001', 'mfiles', 'Coffre M-Files'),
  ('b4000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'b3000000-0000-0000-0000-000000000001', 'local_files', 'Partage sinistres');

-- Identités M-Files : utilisateur externe lié à Alice, membre d'un groupe externe.
INSERT INTO external_principals (id, org_id, source_id, kind, external_id) VALUES
  ('a5000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'user', '42'),
  ('a5000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'group', '7');
INSERT INTO external_group_members VALUES
  ('a0000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000002', 'a5000000-0000-0000-0000-000000000001');
INSERT INTO principal_links (org_id, user_id, external_principal_id, verified) VALUES
  ('a0000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', 'a5000000-0000-0000-0000-000000000001', true);

INSERT INTO embedding_profiles (id, model_name, model_revision, dimension, collection_name, state) VALUES
  ('e0000000-0000-0000-0000-000000000001', 'BAAI/bge-m3', 'r1', 1024, 'chunks_bge_m3_r1', 'active');

-- Documents de A : D1 visible par le groupe externe 7, D2 droits incertains,
-- D3 supprimé, D4 visible seulement par Arnaud. Document de B : DB1.
INSERT INTO documents (id, org_id, source_id, external_id, title, access_keys, acl_status, status) VALUES
  ('a6000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'doc-1',
   'Contrat de bail 2024', ARRAY['xg:a5000000-0000-0000-0000-000000000002'], 'complete', 'indexed'),
  ('a6000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'doc-2',
   'Note confidentielle', '{}', 'uncertain', 'indexed'),
  ('a6000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'doc-3',
   'Ancien contrat supprimé', ARRAY['u:a1000000-0000-0000-0000-000000000001'], 'complete', 'indexed'),
  ('a6000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001', 'doc-4',
   'Contrat de travail Arnaud', ARRAY['u:a1000000-0000-0000-0000-000000000002'], 'complete', 'indexed'),
  ('b6000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'b4000000-0000-0000-0000-000000000001', 'sin-1',
   'Déclaration de sinistre', ARRAY['sp:b3000000-0000-0000-0000-000000000001'], 'complete', 'indexed');

INSERT INTO document_versions (id, org_id, document_id, sha256, embedding_profile_id, status)
SELECT md5('v' || d.id)::uuid, d.org_id, d.id, sha256(d.id::text::bytea), 'e0000000-0000-0000-0000-000000000001', 'indexed'
FROM documents d;
-- Version obsolète de D1 (ne doit jamais ressortir).
INSERT INTO document_versions (id, org_id, document_id, sha256, embedding_profile_id, status, superseded_at) VALUES
  ('a8000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'a6000000-0000-0000-0000-000000000001',
   sha256('ancienne'::bytea), 'e0000000-0000-0000-0000-000000000001', 'indexed', now());
UPDATE documents SET current_version_id = md5('v' || id)::uuid;
UPDATE documents SET deleted_at = now() WHERE id = 'a6000000-0000-0000-0000-000000000003';

INSERT INTO chunks (org_id, document_id, version_id, ordinal, text, page_start, page_end, language)
SELECT d.org_id, d.id, d.current_version_id, 0,
       'Le loyer mensuel est fixé à 450 000 FCFA. Échéance du contrat : 31/12/2026. Référence CTR-2024-0153. ' || d.title,
       1, 1, 'fr'
FROM documents d;
INSERT INTO chunks (org_id, document_id, version_id, ordinal, text, page_start, page_end, language) VALUES
  ('a0000000-0000-0000-0000-000000000001', 'a6000000-0000-0000-0000-000000000001', 'a8000000-0000-0000-0000-000000000001', 0,
   'ANCIENNE VERSION : loyer 300 000 FCFA', 1, 1, 'fr');

INSERT INTO audit_log (org_id, action, created_at) VALUES
  ('a0000000-0000-0000-0000-000000000001', 'test.ancien', now() - interval '400 days'),
  ('a0000000-0000-0000-0000-000000000001', 'test.recent', now());

-- =============================================================================
-- À partir d'ici : rôle applicatif, soumis à la RLS.
-- =============================================================================
SET ROLE urag_app;

-- 1. Sans organisation courante : rien n'est visible, rien n'est modifiable.
SELECT pg_temp.check((SELECT count(*) FROM documents) = 0, 'sans organisation courante, aucun document visible');
SELECT pg_temp.check((SELECT count(*) FROM users) = 0, 'sans organisation courante, aucun utilisateur visible');
SELECT pg_temp.expect_error($$INSERT INTO spaces (org_id, name) VALUES ('a0000000-0000-0000-0000-000000000001', 'x')$$, '42501');

-- 2. La connexion fonctionne sans organisation (seule exception, limitée).
SELECT pg_temp.check((SELECT org_id FROM urag_auth_lookup('ALICE')) = 'a0000000-0000-0000-0000-000000000001',
                     'recherche du compte à la connexion, insensible à la casse');
SELECT pg_temp.check((SELECT count(*) FROM urag_auth_lookup('inconnu')) = 0, 'compte inconnu : aucun résultat');

-- 3. Organisation A : ne voit que ses données.
SET urag.org_id = 'a0000000-0000-0000-0000-000000000001';
SELECT pg_temp.check((SELECT count(*) FROM documents) = 4, 'A voit ses 4 documents');
SELECT pg_temp.check((SELECT count(*) FROM documents WHERE org_id = 'b0000000-0000-0000-0000-000000000001') = 0, 'A ne voit aucun document de B');
SELECT pg_temp.check((SELECT count(*) FROM organizations) = 1, 'A ne voit que sa propre organisation');
SELECT pg_temp.expect_error($$INSERT INTO spaces (org_id, name) VALUES ('b0000000-0000-0000-0000-000000000001', 'intrus')$$, '42501');
WITH u AS (UPDATE documents SET title = 'piraté' WHERE org_id = 'b0000000-0000-0000-0000-000000000001' RETURNING 1)
SELECT pg_temp.check(count(*) = 0, 'A ne peut pas modifier un document de B') FROM u;

-- 4. Liens entre organisations impossibles (clés étrangères composites).
SELECT pg_temp.expect_error($$INSERT INTO sources (org_id, space_id, kind, name)
    VALUES ('a0000000-0000-0000-0000-000000000001', 'b3000000-0000-0000-0000-000000000001', 'local_files', 'x')$$, '23503');

-- 5. Fermé par défaut et format des clés.
SELECT pg_temp.expect_error($$UPDATE documents SET access_keys = ARRAY['u:a1000000-0000-0000-0000-000000000001']
    WHERE id = 'a6000000-0000-0000-0000-000000000002'$$, '23514');
SELECT pg_temp.expect_error($$UPDATE documents SET access_keys = ARRAY['tout_le_monde']
    WHERE id = 'a6000000-0000-0000-0000-000000000001'$$, '23514');

-- 6. Pas de secret dans la configuration d'une source.
SELECT pg_temp.expect_error($$INSERT INTO sources (org_id, space_id, kind, name, config)
    VALUES ('a0000000-0000-0000-0000-000000000001', 'a3000000-0000-0000-0000-000000000001', 'mfiles', 'x', '{"password": "abc"}')$$, '23514');

-- 7. Clés d'accès calculées pour Alice : elle-même, son groupe, l'espace accordé
--    à son groupe, son identité M-Files et le groupe M-Files de cette identité.
SELECT pg_temp.check(
    (SELECT urag_user_access_keys('a1000000-0000-0000-0000-000000000001')) @> ARRAY[
        'u:a1000000-0000-0000-0000-000000000001', 'g:a2000000-0000-0000-0000-000000000001',
        'sp:a3000000-0000-0000-0000-000000000001', 'xu:a5000000-0000-0000-0000-000000000001',
        'xg:a5000000-0000-0000-0000-000000000002']
    AND cardinality(urag_user_access_keys('a1000000-0000-0000-0000-000000000001')) = 5,
    'clés d''accès d''Alice (u, g, sp, xu, xg)');
SELECT pg_temp.check(cardinality(urag_user_access_keys('b1000000-0000-0000-0000-000000000001')) = 0,
    'aucune clé pour un utilisateur d''une autre organisation');

-- 7 bis. Correspondance proposée automatiquement, non confirmée : aucun droit (ADR-0016).
INSERT INTO external_principals (id, org_id, source_id, kind, external_id, login, email) VALUES
  ('a5000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', 'a4000000-0000-0000-0000-000000000001',
   'user', '43', 'arnaud', 'arnaud@exemple.test');
INSERT INTO principal_links (org_id, user_id, external_principal_id, verified) VALUES
  ('a0000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000002', 'a5000000-0000-0000-0000-000000000003', false);
SELECT pg_temp.check(NOT urag_user_access_keys('a1000000-0000-0000-0000-000000000002')
    @> ARRAY['xu:a5000000-0000-0000-0000-000000000003'],
    'correspondance non confirmée : pas de clé xu');
UPDATE principal_links SET verified = true WHERE external_principal_id = 'a5000000-0000-0000-0000-000000000003';
SELECT pg_temp.check(urag_user_access_keys('a1000000-0000-0000-0000-000000000002')
    @> ARRAY['xu:a5000000-0000-0000-0000-000000000003'],
    'correspondance confirmée : clé xu');
DELETE FROM principal_links WHERE external_principal_id = 'a5000000-0000-0000-0000-000000000003';

-- 8. Fragments interrogeables par Alice : seulement D1, version courante.
CREATE TEMP TABLE alice_hits AS
SELECT document_id, text FROM searchable_chunks
WHERE access_keys && urag_user_access_keys('a1000000-0000-0000-0000-000000000001');
SELECT pg_temp.check((SELECT array_agg(DISTINCT document_id) FROM alice_hits) = ARRAY['a6000000-0000-0000-0000-000000000001'::uuid],
    'Alice ne voit que D1 (pas D2 incertain, D3 supprimé, D4 d''Arnaud)');
SELECT pg_temp.check(NOT EXISTS (SELECT 1 FROM alice_hits WHERE text LIKE 'ANCIENNE VERSION%'), 'l''ancienne version de D1 ne ressort jamais');

-- 9. Révocation immédiate : Alice quitte le groupe externe ⇒ plus rien.
DELETE FROM external_group_members WHERE external_user_id = 'a5000000-0000-0000-0000-000000000001';
SELECT pg_temp.check(NOT EXISTS (SELECT 1 FROM searchable_chunks
    WHERE access_keys && urag_user_access_keys('a1000000-0000-0000-0000-000000000001')), 'révocation effective à la question suivante');
UPDATE users SET status = 'disabled' WHERE id = 'a1000000-0000-0000-0000-000000000002';
SELECT pg_temp.check(cardinality(urag_user_access_keys('a1000000-0000-0000-0000-000000000002')) = 0, 'compte désactivé : aucune clé');

-- 10. Recherche plein texte française, insensible aux accents et au pluriel ;
--     référence exacte par trigrammes.
SELECT pg_temp.check((SELECT count(*) FROM chunks WHERE tsv @@ websearch_to_tsquery('urag_fr', 'echeance des contrats')) >= 1,
    'plein texte : « echeance des contrats » trouve « Échéance du contrat »');
SELECT pg_temp.check((SELECT count(*) FROM chunks WHERE text ILIKE '%CTR-2024-0153%') >= 1, 'référence exacte retrouvée');
SELECT pg_temp.check((SELECT max(word_similarity('CTR-2024-0153', text)) FROM chunks) = 1, 'similarité pg_trgm : référence exacte au score maximal');
SELECT pg_temp.check((SELECT max(word_similarity('CTR-2024-0135', text)) FROM chunks) < 1, 'similarité pg_trgm : référence voisine classée plus bas');

-- 11. Journal d'audit : ajout seul.
INSERT INTO audit_log (org_id, action) VALUES ('a0000000-0000-0000-0000-000000000001', 'auth.login');
SELECT pg_temp.expect_error($$UPDATE audit_log SET action = 'falsifié'$$, '42501');
SELECT pg_temp.expect_error($$DELETE FROM audit_log$$, '42501');
SELECT pg_temp.expect_error($$SELECT urag_audit_purge(interval '365 days')$$, '42501');

-- 12. Politique IA : « local uniquement » interdit tout envoi externe.
INSERT INTO ai_policies (org_id) VALUES ('a0000000-0000-0000-0000-000000000001');
SELECT pg_temp.check((SELECT mode FROM ai_policies) = 'local_only', 'politique par défaut : local uniquement');
SELECT pg_temp.expect_error($$UPDATE ai_policies SET allow_external_documents = true$$, '23514');
SELECT pg_temp.expect_error($$INSERT INTO ai_providers (org_id, kind, name, locality)
    VALUES ('a0000000-0000-0000-0000-000000000001', 'anthropic', 'Claude', 'local')$$, '23514');
WITH p AS (INSERT INTO ai_providers (org_id, kind, name, locality)
    VALUES ('a0000000-0000-0000-0000-000000000001', 'anthropic', 'Claude', 'external') RETURNING enabled)
SELECT pg_temp.check(NOT enabled, 'un fournisseur ajouté est désactivé par défaut') FROM p;

-- 13. File de tâches : une seule tâche active par clé, prise sans blocage.
INSERT INTO jobs (org_id, kind, dedup_key) VALUES ('a0000000-0000-0000-0000-000000000001', 'sync_source', 'sync:a4');
SELECT pg_temp.expect_error($$INSERT INTO jobs (org_id, kind, dedup_key) VALUES ('a0000000-0000-0000-0000-000000000001', 'sync_source', 'sync:a4')$$, '23505');
WITH next AS (
        SELECT id FROM jobs WHERE status = 'queued' AND run_after <= now()
        ORDER BY priority, run_after, id FOR UPDATE SKIP LOCKED LIMIT 1),
     taken AS (
        UPDATE jobs SET status = 'running', locked_by = 'w1', locked_at = now(), attempts = attempts + 1
        FROM next WHERE jobs.id = next.id RETURNING jobs.status)
SELECT pg_temp.check(count(*) = 1 AND bool_and(status = 'running'), 'prise d''une tâche avec SKIP LOCKED') FROM taken;

SET urag.org_id = '';
SELECT pg_temp.check((SELECT count(*) FROM jobs) = 0, 'worker sans organisation : aucune tâche visible');
SELECT pg_temp.check(NOT EXISTS (SELECT 1 FROM urag_orgs_with_ready_jobs()),
    'aucune organisation listée quand aucune tâche n''est prête');
SET urag.org_id = 'a0000000-0000-0000-0000-000000000001';
INSERT INTO jobs (org_id, kind) VALUES ('a0000000-0000-0000-0000-000000000001', 'ingest_document');
SET urag.org_id = '';
SELECT pg_temp.check((SELECT array_agg(o) FROM urag_orgs_with_ready_jobs() o) = ARRAY['a0000000-0000-0000-0000-000000000001'::uuid],
    'le worker trouve l''organisation qui a une tâche prête');

-- 14. Organisation B : isolée de A.
SET urag.org_id = 'b0000000-0000-0000-0000-000000000001';
SELECT pg_temp.check((SELECT count(*) FROM documents) = 1, 'B ne voit que son document');
SELECT pg_temp.check((SELECT count(*) FROM audit_log) = 0, 'B ne voit pas le journal de A');
SELECT pg_temp.check((SELECT count(*) FROM jobs) = 0, 'B ne voit pas les tâches de A');

RESET ROLE;

-- 15. Maintenance : purge de l'audit au-delà de la durée de conservation.
SELECT pg_temp.check(urag_audit_purge(interval '365 days') = 1, 'purge de l''audit (> 365 jours) par la maintenance');
SELECT pg_temp.expect_error($$SELECT urag_audit_purge(interval '1 day')$$, 'P0001');

-- 16. Un seul profil d'embedding actif.
SELECT pg_temp.expect_error($$INSERT INTO embedding_profiles (model_name, model_revision, dimension, collection_name, state)
    VALUES ('autre', 'r1', 768, 'chunks_autre', 'active')$$, '23505');

\echo 'TOUS LES TESTS DU SCHÉMA SONT PASSÉS'
