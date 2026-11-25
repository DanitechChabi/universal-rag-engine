-- Migration 0003 — phase 3 : identités externes.

-- Source simulée (tests du cœur sans M-Files, docs/CONNECTORS.md §4.5).
ALTER TYPE source_kind ADD VALUE 'simulator';

-- Identifiant et courriel dans la source : proposition automatique de correspondance (ADR-0016).
ALTER TABLE external_principals ADD COLUMN login text;
ALTER TABLE external_principals ADD COLUMN email text;

-- Une correspondance proposée mais non confirmée ne donne aucun droit.
CREATE OR REPLACE FUNCTION urag_user_access_keys(p_user uuid) RETURNS text[]
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
        -- Seules les correspondances confirmées donnent des droits (ADR-0016).
        SELECT pl.external_principal_id AS id FROM principal_links pl JOIN me ON pl.user_id = me.id
        WHERE pl.verified
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
