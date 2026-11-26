#!/usr/bin/env bash
# Fonctions communes aux scripts d'exploitation (sauvegarde, restauration).
# shellcheck disable=SC2034
INFRA=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE="$INFRA/.env"

fail() { echo "ERREUR : $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

load_env() {
  [[ $EUID -eq 0 ]] || fail "à lancer en administrateur (sudo)"
  [[ -f "$ENV_FILE" ]] || fail "$ENV_FILE introuvable : serveur non installé ?"
  set -a; source "$ENV_FILE"; set +a
  COMPOSE=(docker compose --project-directory "$INFRA" -f "$INFRA/compose.yml")
  if docker info 2>/dev/null | grep -qi nvidia; then COMPOSE+=(-f "$INFRA/compose.gpu.yml"); fi
}

# Requête SQL en superutilisateur, dans le conteneur PostgreSQL (aucun port publié).
psql_q() { "${COMPOSE[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1 -U postgres -tA "$@"; }

# Appel de l'API REST de Qdrant depuis le conteneur de l'API (même réseau interne, clé en variable).
#   qdrant MÉTHODE CHEMIN [CORPS_JSON]  → corps de la réponse
qdrant() {
  "${COMPOSE[@]}" exec -T api python - "$1" "$2" "${3:-}" <<'PY'
import os, sys, httpx
method, path, body = sys.argv[1], sys.argv[2], sys.argv[3]
r = httpx.request(method, "http://qdrant:6333" + path, timeout=3600, trust_env=False,
                  headers={"api-key": os.environ["URAG_QDRANT_API_KEY"], "content-type": "application/json"},
                  content=body or None)
sys.stdout.write(r.text)
sys.exit(0 if r.status_code < 300 else 1)
PY
}

# Empreinte de la clé maîtresse (jamais la clé) : vérifie qu'une sauvegarde correspond au serveur.
key_fingerprint() { sha256sum "$URAG_DATA_DIR/master.key" | cut -c1-16; }

# Lignes des tables principales, pour comparer une copie à l'original.
TABLES="organizations users sources documents document_versions chunks conversations messages audit_log secrets ai_providers"
table_counts() {  # base → « table=nombre » par ligne
  local db=$1 t
  for t in $TABLES; do printf '%s=%s\n' "$t" "$(psql_q -d "$db" -c "SELECT count(*) FROM $t")"; done
}
