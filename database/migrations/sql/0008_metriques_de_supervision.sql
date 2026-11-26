-- Migration 0008 — métriques de supervision (docs/DEPLOYMENT.md §5).
-- Agrégats de toute l'installation, sans contenu ni identifiant : nombres seulement.
-- Exécutée avec les droits de urag_maintenance (lecture seule, contourne la RLS pour compter).
CREATE FUNCTION urag_metrics() RETURNS TABLE (metric text, label text, value double precision)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT 'organizations', '', count(*)::float8 FROM organizations
    UNION ALL SELECT 'sources', status::text, count(*) FROM sources GROUP BY status
    UNION ALL SELECT 'documents', status::text, count(*) FROM documents WHERE deleted_at IS NULL GROUP BY status
    UNION ALL SELECT 'chunks', '', count(*) FROM chunks
    UNION ALL SELECT 'jobs', status::text, count(*) FROM jobs GROUP BY status
    UNION ALL SELECT 'oldest_ready_job_seconds', '',
        coalesce(extract(epoch FROM now() - min(run_after)), 0) FROM jobs WHERE status = 'queued' AND run_after <= now()
    UNION ALL SELECT 'tokens_24h', locality::text, sum(tokens_in + tokens_out) FROM usage_records
        WHERE created_at > now() - interval '24 hours' GROUP BY locality
    UNION ALL SELECT 'login_failures_1h', '', count(*) FROM audit_log
        WHERE action = 'auth.login' AND outcome = 'failure' AND created_at > now() - interval '1 hour'
$$;
ALTER FUNCTION urag_metrics() OWNER TO urag_maintenance;
REVOKE EXECUTE ON FUNCTION urag_metrics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION urag_metrics() TO urag_app;
