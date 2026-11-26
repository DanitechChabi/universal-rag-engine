-- Organisations ayant une tâche « en cours » dont le worker ne donne plus signe de vie : le worker
-- les parcourt pour remettre ces tâches en file, même quand aucune autre tâche n'est prête.
CREATE FUNCTION urag_orgs_with_stale_jobs(stale_after_seconds integer) RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT DISTINCT org_id FROM jobs
    WHERE status = 'running' AND heartbeat_at < now() - make_interval(secs => stale_after_seconds)
$$;
ALTER FUNCTION urag_orgs_with_stale_jobs(integer) OWNER TO urag_maintenance;
REVOKE EXECUTE ON FUNCTION urag_orgs_with_stale_jobs(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION urag_orgs_with_stale_jobs(integer) TO urag_app;
