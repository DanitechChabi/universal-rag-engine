-- Échecs de connexion récents depuis une adresse, toutes organisations confondues : limite
-- contre l'essai d'un même mot de passe sur de nombreux comptes (docs/SECURITY.md §3).
CREATE INDEX audit_log_login_failures ON audit_log (ip, created_at)
    WHERE action = 'auth.login' AND outcome = 'failure';

CREATE FUNCTION urag_login_failures_from(client_ip inet, window_seconds integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT count(*)::integer FROM audit_log
    WHERE action = 'auth.login' AND outcome = 'failure' AND ip = client_ip
      AND created_at > now() - make_interval(secs => window_seconds)
$$;
ALTER FUNCTION urag_login_failures_from(inet, integer) OWNER TO urag_maintenance;
REVOKE EXECUTE ON FUNCTION urag_login_failures_from(inet, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION urag_login_failures_from(inet, integer) TO urag_app;
