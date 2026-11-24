#!/usr/bin/env bash
# Applique roles.sql + schema.sql sur une base neuve puis exécute test_schema.sql.
# Usage : PGUSER=postgres ./database/tests/test_schema.sh   (superutilisateur requis)
set -euo pipefail
cd "$(dirname "$0")/.."
DB="urag_schema_test_$$"
trap 'dropdb --if-exists "$DB" >/dev/null 2>&1 || true' EXIT
createdb "$DB"
psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -f schemas/roles.sql
psql -X -q -v ON_ERROR_STOP=1 -d "$DB" -f schemas/schema.sql
psql -X -q -t -A -v ON_ERROR_STOP=1 -d "$DB" -f tests/test_schema.sql 2>&1 | sed -e "s/^psql:[^ ]* NOTICE:  //" -e "/^$/d"
