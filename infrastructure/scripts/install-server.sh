#!/usr/bin/env bash
# Installation du mode Server (docs/DEPLOYMENT.md §2.3, ADR-0025).
#
#   sudo infrastructure/scripts/install-server.sh --site rag.cabinet.local \
#        --org-name "Cabinet Exemple" --org-slug cabinet --admin-login admin
#
# Étapes : vérifications, secrets (clé maîtresse, mots de passe), .env, modèles, base, migrations,
# organisation et premier administrateur, démarrage, test de santé en HTTPS.
# Relancer le script est sans danger : les secrets et l'organisation existants sont conservés.
set -euo pipefail

INFRA=$(cd "$(dirname "$0")/.." && pwd)
SITE="" ORG_NAME="" ORG_SLUG="" ADMIN_LOGIN="admin"
DATA_DIR=/var/lib/urag DOCUMENTS_DIR=/srv/documents HTTPS_PORT=443
TLS=internal MODELS_FROM="" CHAT_MODEL="qwen2.5:14b" PULL_LLM=1 GPU=auto BEHIND_PROXY=0

usage() {
  cat <<'TXT'
Options :
  --site ADRESSE          nom ou adresse IP du serveur (obligatoire)
  --org-name NOM          nom de l'organisation (obligatoire)
  --org-slug CODE         identifiant court de l'organisation (obligatoire)
  --admin-login LOGIN     identifiant du premier administrateur (défaut : admin)
  --data-dir DOSSIER      données du serveur (défaut : /var/lib/urag)
  --documents-dir DOSSIER dossiers de documents à indexer, en lecture seule (défaut : /srv/documents)
  --https-port PORT       port HTTPS publié (défaut : 443)
  --tls-cert CERT --tls-key CLE   certificat de l'entreprise (sinon autorité interne du serveur)
  --models-from DOSSIER   installation hors ligne des modèles d'encodage
  --chat-model NOM        modèle de génération local (défaut : qwen2.5:14b, ADR-0024)
  --no-llm                ne pas télécharger le modèle de génération
  --gpu oui|non|auto      génération sur GPU NVIDIA (défaut : détection)
  --behind-proxy          derrière un relais HTTPS existant (ex. GitHub Codespaces, relais de
                          l'entreprise) : HTTP simple, publié sur 127.0.0.1 seulement
TXT
}

TLS_CERT="" TLS_KEY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --site) SITE=$2; shift 2 ;;
    --org-name) ORG_NAME=$2; shift 2 ;;
    --org-slug) ORG_SLUG=$2; shift 2 ;;
    --admin-login) ADMIN_LOGIN=$2; shift 2 ;;
    --data-dir) DATA_DIR=$2; shift 2 ;;
    --documents-dir) DOCUMENTS_DIR=$2; shift 2 ;;
    --https-port) HTTPS_PORT=$2; shift 2 ;;
    --tls-cert) TLS_CERT=$2; shift 2 ;;
    --tls-key) TLS_KEY=$2; shift 2 ;;
    --models-from) MODELS_FROM=$2; shift 2 ;;
    --chat-model) CHAT_MODEL=$2; shift 2 ;;
    --no-llm) PULL_LLM=0; shift ;;
    --gpu) GPU=$2; shift 2 ;;
    --behind-proxy) BEHIND_PROXY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "option inconnue : $1" >&2; usage; exit 2 ;;
  esac
done
[[ -n "$SITE" && -n "$ORG_NAME" && -n "$ORG_SLUG" ]] || { usage; exit 2; }

step() { printf '\n== %s\n' "$*"; }
fail() { echo "ERREUR : $*" >&2; exit 1; }
secret() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40; }

step "Vérifications"
[[ $EUID -eq 0 ]] || fail "à lancer en administrateur (sudo)"
command -v docker >/dev/null || fail "Docker est requis"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 est requis"
command -v openssl >/dev/null || fail "openssl est requis"
mem_gb=$(awk '/MemTotal/ {print int($2/1048576)}' /proc/meminfo)
mkdir -p "$DATA_DIR"
free_gb=$(df -Pk "$DATA_DIR" | awk 'NR==2 {print int($4/1048576)}')
echo "mémoire : ${mem_gb} Go ; espace libre dans $DATA_DIR : ${free_gb} Go"
(( mem_gb >= 15 )) || echo "ATTENTION : 16 Go de mémoire au moins sont recommandés"
# Processus de l'API : chacun charge l'encodeur et le reclassement (≈ 2,5 Go) ; le reste de la
# mémoire va à PostgreSQL, Qdrant, au worker et à Ollama (docs/DEPLOYMENT.md §2.4).
api_workers=$(( (mem_gb - 9) / 3 ))  # 16 Go (15 visibles) : 2 ; 32 Go : 4
if (( api_workers < 1 )); then api_workers=1; fi
if (( api_workers > 4 )); then api_workers=4; fi
echo "processus de l'API : $api_workers"
(( free_gb >= 40 )) || echo "ATTENTION : 40 Go d'espace libre au moins sont recommandés (modèles, index, sauvegardes)"
if [[ "$GPU" == auto ]]; then
  if command -v nvidia-smi >/dev/null && docker info 2>/dev/null | grep -qi nvidia; then GPU=oui; else GPU=non; fi
fi
echo "GPU NVIDIA pour la génération : $GPU"
if [[ -n "$TLS_CERT" ]]; then
  [[ -f "$TLS_CERT" && -f "$TLS_KEY" ]] || fail "certificat ou clé introuvable"
fi

step "Dossiers et secrets"
umask 077
mkdir -p "$DATA_DIR"/{postgres,qdrant,qdrant-snapshots,ollama,caddy,certs,models,backups}
# Dossier des documents : lu (jamais modifié) par le compte de l'application, uid 10001.
if [[ ! -d "$DOCUMENTS_DIR" ]]; then mkdir -p "$DOCUMENTS_DIR" && chmod 755 "$DOCUMENTS_DIR"; fi
# Vérifié dans un conteneur, comme le verra le worker (les dossiers parents de l'hôte n'interviennent pas).
if ! docker run --rm --network none -v "$DOCUMENTS_DIR:/documents:ro" "${URAG_APP_IMAGE:-urag-app:latest}" \
     sh -c 'test -r /documents -a -x /documents' 2>/dev/null; then
  echo "ATTENTION : $DOCUMENTS_DIR n'est pas lisible par le compte de l'application (uid 10001) ;"
  echo "            accordez-lui la lecture (ex. setfacl -R -m u:10001:rX $DOCUMENTS_DIR)"
fi
if [[ ! -f "$DATA_DIR/master.key" ]]; then
  openssl rand -hex 32 > "$DATA_DIR/master.key"
  echo "clé maîtresse créée : $DATA_DIR/master.key (à sauvegarder À PART, voir la documentation)"
else
  echo "clé maîtresse existante conservée"
fi
# Lisible par le seul compte de l'application dans les conteneurs (uid 10001).
chown 10001:10001 "$DATA_DIR/master.key" && chmod 400 "$DATA_DIR/master.key"

ENV_FILE="$INFRA/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "fichier .env existant conservé (secrets inchangés)"
else
  if [[ -n "$TLS_CERT" ]]; then
    install -m 444 "$TLS_CERT" "$DATA_DIR/certs/cert.pem"
    install -m 440 -g 0 "$TLS_KEY" "$DATA_DIR/certs/key.pem"
    tls_value="/certs/cert.pem /certs/key.pem"
  else
    tls_value="$TLS"
  fi
  site_value=$SITE bind_value=0.0.0.0 container_port=443
  if [[ $BEHIND_PROXY == 1 ]]; then
    # Le relais fournit le HTTPS : Caddy sert en HTTP (port 8080 du conteneur), joignable depuis
    # cette machine seulement.
    site_value="http://:8080" bind_value=127.0.0.1 container_port=8080
  fi
  cat > "$ENV_FILE" <<ENV
# Généré par install-server.sh le $(date -Iseconds). Contient des secrets : ne pas copier, ne pas committer.
URAG_DATA_DIR=$DATA_DIR
URAG_DOCUMENTS_DIR=$DOCUMENTS_DIR
URAG_SITE_ADDRESS=$site_value
URAG_BIND_ADDRESS=$bind_value
URAG_WEB_CONTAINER_PORT=$container_port
URAG_TLS=$tls_value
URAG_HTTPS_PORT=$HTTPS_PORT
URAG_API_WORKERS=$api_workers
URAG_PG_SUPERUSER_PASSWORD=$(secret)
URAG_APP_DB_PASSWORD=$(secret)
URAG_QDRANT_API_KEY=$(secret)
ENV
  # Images choisies à l'installation (miroir, version figée) : mémorisées pour les scripts suivants.
  for v in URAG_APP_IMAGE URAG_WEB_IMAGE URAG_POSTGRES_IMAGE URAG_QDRANT_IMAGE URAG_OLLAMA_IMAGE URAG_TIKA_IMAGE; do
    [[ -n "${!v:-}" ]] && echo "$v=${!v}" >> "$ENV_FILE"
  done
  chmod 600 "$ENV_FILE"
  echo "secrets générés dans $ENV_FILE (droits 600)"
fi
[[ -f "$INFRA/urag.env" ]] || { sed "s/^URAG_CHAT_MODEL=.*/URAG_CHAT_MODEL=$CHAT_MODEL/" "$INFRA/urag.env.example" > "$INFRA/urag.env"; chmod 644 "$INFRA/urag.env"; }
set -a; source "$ENV_FILE"; set +a

COMPOSE=(docker compose --project-directory "$INFRA" -f "$INFRA/compose.yml")
[[ "$GPU" == oui ]] && COMPOSE+=(-f "$INFRA/compose.gpu.yml")

step "Modèles d'encodage et de reclassement"
if [[ -n "$MODELS_FROM" ]]; then
  "$INFRA/scripts/fetch-models.sh" "$DATA_DIR/models" --from "$MODELS_FROM"
else
  "$INFRA/scripts/fetch-models.sh" "$DATA_DIR/models"
fi

step "Base de données et index"
"${COMPOSE[@]}" up -d postgres qdrant
for _ in $(seq 1 60); do
  "${COMPOSE[@]}" exec -T postgres pg_isready -U postgres -d urag >/dev/null 2>&1 && break
  sleep 2
done
"${COMPOSE[@]}" exec -T postgres pg_isready -U postgres -d urag >/dev/null || fail "PostgreSQL ne répond pas"

# URL d'administration transmise par l'environnement, jamais sur la ligne de commande.
export URAG_ADMIN_DATABASE_URL="postgresql+psycopg://postgres:${URAG_PG_SUPERUSER_PASSWORD}@postgres:5432/urag"
admin() { "${COMPOSE[@]}" run --rm --no-deps -T -e URAG_ADMIN_DATABASE_URL api urag-admin "$@"; }
admin migrate
export URAG_APP_PASSWORD_IN="$URAG_APP_DB_PASSWORD"
"${COMPOSE[@]}" run --rm --no-deps -T -e URAG_ADMIN_DATABASE_URL -e URAG_APP_PASSWORD_IN api \
  urag-admin app-password --password-env URAG_APP_PASSWORD_IN
unset URAG_APP_PASSWORD_IN

step "Organisation et premier administrateur"
ADMIN_SECRET_FILE="$DATA_DIR/premier-administrateur.txt"
if "${COMPOSE[@]}" exec -T postgres psql -U postgres -d urag -tAc "SELECT 1 FROM organizations LIMIT 1" | grep -q 1; then
  echo "organisation existante conservée"
else
  admin_password=$(secret | head -c 20)
  export URAG_ADMIN_PASSWORD_IN="$admin_password"
  "${COMPOSE[@]}" run --rm --no-deps -T -e URAG_ADMIN_DATABASE_URL -e URAG_ADMIN_PASSWORD_IN api \
    urag-admin bootstrap --org-name "$ORG_NAME" --org-slug "$ORG_SLUG" --admin-login "$ADMIN_LOGIN" \
    --admin-password-env URAG_ADMIN_PASSWORD_IN
  unset URAG_ADMIN_PASSWORD_IN
  printf 'identifiant : %s\nmot de passe provisoire : %s\n' "$ADMIN_LOGIN" "$admin_password" > "$ADMIN_SECRET_FILE"
  chmod 600 "$ADMIN_SECRET_FILE"
fi

step "Démarrage"
"${COMPOSE[@]}" up -d
if [[ "$PULL_LLM" == 1 ]]; then
  echo "téléchargement du modèle de génération $CHAT_MODEL (plusieurs Go)…"
  "${COMPOSE[@]}" exec -T ollama ollama pull "$CHAT_MODEL" || echo "ATTENTION : téléchargement du modèle échoué, à relancer"
fi

step "Sauvegarde quotidienne"
if [[ -d /etc/cron.d ]]; then
  cat > /etc/cron.d/urag-backup <<CRON
# Universal RAG Engine : sauvegarde vérifiée chaque nuit (14 conservées). Journal : /var/log/urag-backup.log
SHELL=/bin/bash
17 2 * * * root $INFRA/scripts/backup.sh --kind scheduled >> /var/log/urag-backup.log 2>&1
CRON
  chmod 644 /etc/cron.d/urag-backup
  echo "planifiée à 2 h 17 (/etc/cron.d/urag-backup) ; copiez aussi les sauvegardes hors du serveur (--dest)"
else
  echo "ATTENTION : cron absent ; planifiez $INFRA/scripts/backup.sh --kind scheduled chaque jour"
fi

step "Test de santé"
if [[ $BEHIND_PROXY == 1 ]]; then health_url="http://127.0.0.1:$HTTPS_PORT/api/v1/admin/health"
else health_url="https://$SITE:$HTTPS_PORT/api/v1/admin/health"; fi
ok=0
for _ in $(seq 1 60); do
  if curl -fsS -k --noproxy "*" --resolve "$SITE:$HTTPS_PORT:127.0.0.1" "$health_url" 2>/dev/null \
      | grep -q '"status":"ok"'; then ok=1; break; fi
  sleep 3
done
[[ $ok == 1 ]] || fail "le service ne répond pas ; voir : docker compose logs"
echo "service en bonne santé"

cat <<TXT

Installation terminée.
  Adresse        : $( if [[ $BEHIND_PROXY == 1 ]]; then echo "celle du relais HTTPS (port local $HTTPS_PORT)"; else echo "https://$SITE$( [[ "$HTTPS_PORT" == 443 ]] || echo ":$HTTPS_PORT" )"; fi )
  Administrateur : voir $ADMIN_SECRET_FILE (mot de passe provisoire, à changer puis supprimer le fichier)
  Clé maîtresse  : $DATA_DIR/master.key — à sauvegarder À PART des sauvegardes de la base
  Sauvegarde     : chaque nuit (backup.sh) ; exportez la clé : master-key.sh export FICHIER
$( [[ "$TLS" == internal && -z "$TLS_CERT" && $BEHIND_PROXY == 0 ]] && echo "  Certificat     : autorité interne du serveur ; à installer sur les postes : $DATA_DIR/caddy/caddy/pki/authorities/local/root.crt" )
TXT
