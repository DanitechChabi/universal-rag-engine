#!/usr/bin/env bash
# Mise à jour du serveur (docs/DEPLOYMENT.md §2.3) : sauvegarde vérifiée obligatoire, nouvelles
# images, migrations, redémarrage, test de santé. En cas d'échec : restore.sh avec la sauvegarde
# faite au début (le nom est affiché), puis les images précédentes (URAG_APP_IMAGE dans .env).
#
#   sudo upgrade.sh [--images ARCHIVE.tar]   (archive « docker save » pour les sites hors ligne)
set -euo pipefail
source "$(dirname "$0")/lib.sh"
ARCHIVE=""
[[ "${1:-}" == "--images" ]] && ARCHIVE=${2:?archive manquante}
load_env

step "Sauvegarde préalable"
"$INFRA/scripts/backup.sh" --kind manual | grep "sauvegarde vérifiée"
echo "en cas de problème : $INFRA/scripts/restore.sh prepare $(ls -1d "$URAG_DATA_DIR"/backups/urag-* | tail -1)"

step "Images"
if [[ -n "$ARCHIVE" ]]; then docker load -i "$ARCHIVE"; else echo "images locales utilisées (docker load ou construction préalables)"; fi

step "Migrations"
export URAG_ADMIN_DATABASE_URL="postgresql+psycopg://postgres:${URAG_PG_SUPERUSER_PASSWORD}@postgres:5432/urag"
"${COMPOSE[@]}" run --rm --no-deps -T -e URAG_ADMIN_DATABASE_URL api urag-admin migrate

step "Redémarrage"
"${COMPOSE[@]}" up -d --remove-orphans
for _ in $(seq 1 60); do
  if curl -fsS -k --noproxy "*" --resolve "$URAG_SITE_ADDRESS:$URAG_HTTPS_PORT:127.0.0.1" \
      "https://$URAG_SITE_ADDRESS:$URAG_HTTPS_PORT/api/v1/admin/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "mise à jour terminée : service en bonne santé"; exit 0
  fi
  sleep 3
done
fail "le service ne répond pas après la mise à jour ; voir docker compose logs, puis restaurer si besoin"
