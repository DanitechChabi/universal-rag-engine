"""Outil d'administration : clé maîtresse, migrations, création de l'organisation et de l'administrateur.

Les commandes de base de données utilisent l'URL d'administration
(URAG_ADMIN_DATABASE_URL, propriétaire du schéma), jamais celle de l'application.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from urag_core.security import PasswordHasher, generate_master_key

DATABASE_DIR = Path(os.environ.get("URAG_DATABASE_DIR", Path(__file__).resolve().parents[4] / "database"))


def admin_url(args) -> str:
    url = args.admin_url or os.environ.get("URAG_ADMIN_DATABASE_URL")
    if not url:
        sys.exit("URL d'administration manquante (--admin-url ou URAG_ADMIN_DATABASE_URL)")
    return url


def cmd_gen_key(args) -> None:
    generate_master_key(Path(args.path))
    print(f"clé maîtresse créée : {args.path} (à sauvegarder séparément)")


def cmd_migrate(args) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(DATABASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DATABASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", admin_url(args).replace("%", "%%"))
    command.upgrade(cfg, "head")
    print("schéma à jour")


def cmd_app_password(args) -> None:
    password = args.password or getpass.getpass("Mot de passe du rôle urag_app : ")
    with create_engine(admin_url(args)).begin() as conn:
        quoted = conn.exec_driver_sql("SELECT quote_literal(%s)", (password,)).scalar_one()
        conn.exec_driver_sql(f"ALTER ROLE urag_app PASSWORD {quoted}")
    print("mot de passe de urag_app défini")


_ROLE_NAME = re.compile(r"^urag_run_[a-z0-9]{6,32}$")


def create_run_role(url: str, role: str, password: str) -> None:
    """Compte de connexion propre à une exécution (tests, mesure), membre de urag_app.

    Il hérite exactement des droits de urag_app et reste soumis à la RLS, sans modifier le
    mot de passe de urag_app, commun à toutes les bases du serveur.
    """
    if not _ROLE_NAME.match(role):
        raise ValueError("nom de rôle invalide")
    with create_engine(url).begin() as conn:
        quoted = conn.exec_driver_sql("SELECT quote_literal(%s)", (password,)).scalar_one()
        conn.exec_driver_sql(
            f"CREATE ROLE {role} LOGIN PASSWORD {quoted} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
            "INHERIT IN ROLE urag_app"
        )


def drop_run_role(url: str, role: str) -> None:
    if not _ROLE_NAME.match(role):
        raise ValueError("nom de rôle invalide")
    with create_engine(url, isolation_level="AUTOCOMMIT").connect() as conn:
        conn.exec_driver_sql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = '{role}'")
        conn.exec_driver_sql(f"DROP ROLE IF EXISTS {role}")


def bootstrap(url: str, org_name: str, org_slug: str, login: str, password: str, display_name: str) -> dict:
    """Crée l'organisation, sa politique (local uniquement), et le premier administrateur."""
    hashed = PasswordHasher().hash(password)
    with create_engine(url).begin() as conn:
        org_id = conn.execute(
            text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"), {"n": org_name, "s": org_slug}
        ).scalar_one()
        conn.execute(text("INSERT INTO ai_policies (org_id) VALUES (:o)"), {"o": org_id})
        user_id = conn.execute(
            text("""INSERT INTO users (org_id, login, display_name, password_hash)
                                       VALUES (:o, :l, :d, :p) RETURNING id"""),
            {"o": org_id, "l": login, "d": display_name, "p": hashed},
        ).scalar_one()
        for role in ("org_admin", "doc_admin", "user"):
            conn.execute(
                text("INSERT INTO user_roles (org_id, user_id, role) VALUES (:o, :u, CAST(:r AS user_role))"),
                {"o": org_id, "u": user_id, "r": role},
            )
        conn.execute(
            text("""INSERT INTO audit_log (org_id, actor_user_id, action, details)
                             VALUES (:o, :u, 'install.bootstrap', '{}'::jsonb)"""),
            {"o": org_id, "u": user_id},
        )
    return {"org_id": org_id, "user_id": user_id}


def cmd_bootstrap(args) -> None:
    password = args.admin_password or getpass.getpass("Mot de passe de l'administrateur : ")
    ids = bootstrap(
        admin_url(args), args.org_name, args.org_slug, args.admin_login, password, args.admin_name or args.admin_login
    )
    print(f"organisation {ids['org_id']} et administrateur {ids['user_id']} créés")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="urag-admin")
    p.add_argument("--admin-url")
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("gen-key", help="créer la clé maîtresse des secrets")
    s.add_argument("path")
    s.set_defaults(func=cmd_gen_key)
    sub.add_parser("migrate", help="appliquer les migrations").set_defaults(func=cmd_migrate)
    s = sub.add_parser("app-password", help="définir le mot de passe du rôle urag_app")
    s.add_argument("--password")
    s.set_defaults(func=cmd_app_password)
    s = sub.add_parser("bootstrap", help="créer l'organisation et le premier administrateur")
    s.add_argument("--org-name", required=True)
    s.add_argument("--org-slug", required=True)
    s.add_argument("--admin-login", required=True)
    s.add_argument("--admin-name")
    s.add_argument("--admin-password")
    s.set_defaults(func=cmd_bootstrap)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
