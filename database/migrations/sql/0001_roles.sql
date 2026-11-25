-- =============================================================================
-- Rôles PostgreSQL (niveau cluster) — à exécuter une fois, avant schema.sql.
-- Les mots de passe sont définis à l'installation (jamais dans Git) :
--   ALTER ROLE urag_app PASSWORD '…';
-- =============================================================================
DO $$
BEGIN
    -- Propriétaire du schéma : utilisé seulement par les migrations.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'urag_owner') THEN
        CREATE ROLE urag_owner NOLOGIN;
    END IF;
    -- Rôle de l'application (api, worker) : soumis à la RLS, aucun privilège particulier.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'urag_app') THEN
        CREATE ROLE urag_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
    -- Propriétaire de la seule fonction de recherche de compte à la connexion.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'urag_auth') THEN
        CREATE ROLE urag_auth NOLOGIN BYPASSRLS;
    END IF;
    -- Maintenance : sauvegarde, purge de l'audit selon la durée de conservation.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'urag_maintenance') THEN
        CREATE ROLE urag_maintenance NOLOGIN BYPASSRLS;
    END IF;
END $$;
