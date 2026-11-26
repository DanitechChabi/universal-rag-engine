#!/usr/bin/env bash
# Restauration en deux étapes (docs/DEPLOYMENT.md §4, ADR-0025).
#
#   sudo restore.sh prepare DOSSIER_DE_SAUVEGARDE   contrôle et résumé ; ne modifie rien
#   sudo restore.sh confirm DOSSIER_DE_SAUVEGARDE   remplace la base et l'index par la sauvegarde
#
# « confirm » n'est accepté que dans l'heure qui suit un « prepare » réussi du même dossier.
# Prérequis : serveur installé (install-server.sh) et clé maîtresse de la sauvegarde en place
# (master-key.sh import) ; sinon les secrets restaurés seraient illisibles.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
ACTION=${1:?usage : restore.sh prepare|confirm DOSSIER}
DIR=$(cd "${2:?dossier de sauvegarde manquant}" && pwd)
load_env
MARK="$URAG_DATA_DIR/backups/.restauration-preparee"

check() {
  [[ -f "$DIR/manifest.json" && -f "$DIR/urag.dump" ]] || fail "ce n'est pas une sauvegarde Universal RAG Engine"
  (cd "$DIR" && sha256sum -c --quiet SHA256SUMS) || fail "empreintes incorrectes : sauvegarde abîmée ou modifiée"
  python3 - "$DIR/manifest.json" "$(key_fingerprint)" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
if not m.get("verified"):
    sys.exit("ERREUR : sauvegarde non vérifiée")
if m["master_key_fingerprint"] != sys.argv[2]:
    sys.exit("ERREUR : la clé maîtresse du serveur n'est pas celle de la sauvegarde (master-key.sh import)")
print(f"sauvegarde du {m['date']} ({m['kind']}), schéma {m['schema_revision']}, "
      f"{len(m['qdrant_collections'])} collection(s) d'index")
PY
}

case "$ACTION" in
prepare)
  step "Contrôle de la sauvegarde"
  check
  echo "contenu :"; sed 's/^/  /' "$DIR/lignes.txt"
  echo "état actuel du serveur :"; table_counts urag | sed 's/^/  /'
  printf '%s %s\n' "$(date +%s)" "$DIR" > "$MARK"
  echo
  echo "Rien n'a été modifié. Pour remplacer les données actuelles par cette sauvegarde :"
  echo "  sudo $0 confirm $DIR"
  ;;
confirm)
  [[ -f "$MARK" ]] || fail "lancez d'abord : $0 prepare $DIR"
  read -r when prepared < "$MARK"
  [[ "$prepared" == "$DIR" ]] || fail "la préparation concerne un autre dossier : $prepared"
  (( $(date +%s) - when < 3600 )) || fail "préparation de plus d'une heure : relancez « prepare »"
  check
  START=$(date +%s)

  step "Arrêt des services applicatifs"
  "${COMPOSE[@]}" stop caddy api worker

  step "Base PostgreSQL"
  psql_q -d postgres -c "DROP DATABASE IF EXISTS urag WITH (FORCE)" >/dev/null
  psql_q -d postgres -c "CREATE DATABASE urag" >/dev/null
  "${COMPOSE[@]}" exec -T postgres pg_restore -U postgres -d urag --exit-on-error < "$DIR/urag.dump"
  table_counts urag > "$URAG_DATA_DIR/backups/.lignes-restaurees"
  diff -q "$DIR/lignes.txt" "$URAG_DATA_DIR/backups/.lignes-restaurees" >/dev/null \
    || fail "la base restaurée ne correspond pas à la sauvegarde"
  rm -f "$URAG_DATA_DIR/backups/.lignes-restaurees"
  export URAG_ADMIN_DATABASE_URL="postgresql+psycopg://postgres:${URAG_PG_SUPERUSER_PASSWORD}@postgres:5432/urag"
  export URAG_APP_PASSWORD_IN="$URAG_APP_DB_PASSWORD"
  "${COMPOSE[@]}" run --rm --no-deps -T -e URAG_ADMIN_DATABASE_URL api urag-admin migrate
  "${COMPOSE[@]}" run --rm --no-deps -T -e URAG_ADMIN_DATABASE_URL -e URAG_APP_PASSWORD_IN api \
    urag-admin app-password --password-env URAG_APP_PASSWORD_IN
  unset URAG_APP_PASSWORD_IN
  echo "base restaurée et à jour"

  step "Index Qdrant"
  "${COMPOSE[@]}" start api >/dev/null  # sert de relais vers Qdrant (réseau interne)
  wanted=$(python3 -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))['qdrant_collections']))" "$DIR/manifest.json")
  current=$(qdrant GET /collections | python3 -c "import json,sys; print(' '.join(c['name'] for c in json.load(sys.stdin)['result']['collections']))")
  for c in $current; do
    [[ " $wanted " == *" $c "* ]] || { qdrant DELETE "/collections/$c" >/dev/null; echo "collection retirée (absente de la sauvegarde) : $c"; }
  done
  for c in $wanted; do
    mkdir -p "$URAG_DATA_DIR/qdrant-snapshots/$c"
    cp "$DIR/qdrant/$c.snapshot" "$URAG_DATA_DIR/qdrant-snapshots/$c/restauration.snapshot"
    qdrant PUT "/collections/$c/snapshots/recover?wait=true" \
      "{\"location\": \"file:///qdrant/snapshots/$c/restauration.snapshot\", \"priority\": \"snapshot\"}" >/dev/null
    rm -f "$URAG_DATA_DIR/qdrant-snapshots/$c/restauration.snapshot"
    echo "collection restaurée : $c"
  done

  step "Redémarrage"
  "${COMPOSE[@]}" up -d
  for org in $(psql_q -d urag -c "SELECT id FROM organizations"); do
    psql_q -d urag -c "INSERT INTO audit_log (org_id, action, details) VALUES ('$org', 'backup.restored',
      jsonb_build_object('backup', '$(basename "$DIR")'))" >/dev/null
  done
  rm -f "$MARK"
  echo "restauration terminée en $(( $(date +%s) - START )) s ; vérifiez le service (verify-install.py)"
  ;;
*) fail "action inconnue : $ACTION" ;;
esac
