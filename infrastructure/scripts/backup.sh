#!/usr/bin/env bash
# Sauvegarde complète et vérifiée (docs/DEPLOYMENT.md §4, ADR-0025).
#
#   sudo infrastructure/scripts/backup.sh [--dest DOSSIER] [--keep N] [--kind manual|scheduled]
#
# Contenu : base PostgreSQL (pg_dump, format personnalisé), instantanés des collections Qdrant,
# réglages non secrets, manifeste avec empreintes SHA-256 et nombres de lignes.
# NON inclus : la clé maîtresse (à sauvegarder à part : export-master-key.sh) et les mots de passe
# du .env (régénérables). La sauvegarde est restaurée dans une base temporaire et comparée :
# elle n'est marquée « vérifiée » qu'après ce contrôle.
set -euo pipefail
source "$(dirname "$0")/lib.sh"

DEST="" KEEP=14 KIND=manual
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST=$2; shift 2 ;;
    --keep) KEEP=$2; shift 2 ;;
    --kind) KIND=$2; shift 2 ;;
    *) fail "option inconnue : $1" ;;
  esac
done
load_env
DEST=${DEST:-$URAG_DATA_DIR/backups}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DEST/urag-$STAMP"
umask 077
mkdir -p "$OUT/qdrant"
START=$(date +%s)
ORGS=$(psql_q -d urag -c "SELECT id FROM organizations")
record() {  # journal des sauvegardes, par organisation
  local status=$1 err=${2:-}
  for org in $ORGS; do
    psql_q -d urag -c "INSERT INTO backups (org_id, kind, status, location, size_bytes, finished_at, error)
      VALUES ('$org', '$KIND', '$status', '$OUT', $(du -sb "$OUT" | cut -f1), now(), NULLIF('$err', ''))" >/dev/null
  done
}
trap 'record failed "interrompue ou en erreur (voir la sortie du script)" || true' ERR

step "Base PostgreSQL"
REVISION=$(psql_q -d urag -c "SELECT version_num FROM alembic_version")
table_counts urag > "$OUT/lignes.txt"
"${COMPOSE[@]}" exec -T postgres pg_dump -U postgres -d urag -Fc -Z 6 > "$OUT/urag.dump"
echo "export : $(du -h "$OUT/urag.dump" | cut -f1) (schéma $REVISION)"

step "Index Qdrant (instantanés)"
COLLECTIONS=$(qdrant GET /collections | python3 -c "import json,sys; print(' '.join(c['name'] for c in json.load(sys.stdin)['result']['collections']))")
for c in $COLLECTIONS; do
  name=$(qdrant POST "/collections/$c/snapshots?wait=true" | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['name'])")
  cp "$URAG_DATA_DIR/qdrant-snapshots/$c/$name" "$OUT/qdrant/$c.snapshot"
  qdrant DELETE "/collections/$c/snapshots/$name?wait=true" >/dev/null
  echo "collection $c : $(du -h "$OUT/qdrant/$c.snapshot" | cut -f1)"
done

step "Réglages (sans secrets)"
grep -vE '_PASSWORD=|_API_KEY=' "$ENV_FILE" > "$OUT/env.sans-secrets"
cp "$INFRA/urag.env" "$OUT/urag.env"

step "Vérification par restauration dans une base temporaire"
VERIFY_DB="urag_verification_$STAMP"
VERIFY_DB=${VERIFY_DB,,}
psql_q -d postgres -c "CREATE DATABASE \"$VERIFY_DB\"" >/dev/null
cleanup_verify() { psql_q -d postgres -c "DROP DATABASE IF EXISTS \"$VERIFY_DB\" WITH (FORCE)" >/dev/null || true; }
"${COMPOSE[@]}" exec -T postgres pg_restore -U postgres -d "$VERIFY_DB" --exit-on-error < "$OUT/urag.dump"
table_counts "$VERIFY_DB" > "$OUT/lignes-verification.txt"
cleanup_verify
if ! diff -q "$OUT/lignes.txt" "$OUT/lignes-verification.txt" >/dev/null; then
  diff "$OUT/lignes.txt" "$OUT/lignes-verification.txt" >&2 || true
  fail "la copie restaurée ne correspond pas à l'original"
fi
rm "$OUT/lignes-verification.txt"
echo "copie restaurée identique (lignes de $(echo "$TABLES" | wc -w) tables comparées)"

step "Manifeste"
(cd "$OUT" && find . -type f ! -name manifest.json ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
python3 - "$OUT" "$STAMP" "$REVISION" "$(key_fingerprint)" "$KIND" "$COLLECTIONS" <<'PY'
import json, sys
out, stamp, revision, key, kind, collections = sys.argv[1:7]
json.dump({
    "format": 1, "date": stamp, "kind": kind, "schema_revision": revision,
    "master_key_fingerprint": key, "qdrant_collections": collections.split(),
    "verified": True, "contains_master_key": False,
}, open(f"{out}/manifest.json", "w"), indent=1)
PY
trap - ERR
record verified
echo "sauvegarde vérifiée : $OUT ($(du -sh "$OUT" | cut -f1), $(( $(date +%s) - START )) s)"

step "Rétention ($KEEP sauvegardes)"
mapfile -t old < <(ls -1d "$DEST"/urag-* 2>/dev/null | sort -r | tail -n +$((KEEP + 1)))
for d in "${old[@]}"; do rm -rf -- "$d"; echo "supprimée : $d"; done
