#!/usr/bin/env bash
# Essai complet du mode Server dans GitHub Codespaces (docs/ESSAI-CODESPACES.md), en une commande :
#
#   bash infrastructure/scripts/essai-codespaces.sh
#
# Construit les images, télécharge 6 documents publics (BCEAO, FSB), installe le serveur derrière
# le relais HTTPS de Codespaces, indexe les documents et vérifie une recherche. Le modèle de
# génération est petit (CPU seulement) : réponses lentes et moins fiables qu'avec un GPU.
# Relancer le script est sans danger : l'installation existante est conservée.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DATA=${URAG_ESSAI_DATA:-$HOME/urag-essai}
DOCS=$DATA/documents
PORT=8443
MODEL=${URAG_ESSAI_MODELE:-qwen2.5:1.5b}
DOC_IDS="bceao-037,bceao-061,bceao-047,fsb-088,bceao-036,bceao-045"

step() { printf '\n== %s\n' "$*"; }

step "Outils"
missing=()
for tool in python3 openssl curl; do command -v "$tool" >/dev/null || missing+=("$tool"); done
if (( ${#missing[@]} )); then
  sudo apt-get update -q && sudo apt-get install -y -q "${missing[@]}"
fi
# Au premier démarrage du codespace, Docker peut mettre quelques secondes à répondre.
for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker info >/dev/null 2>&1 || { echo "Docker ne répond pas : relancez ce script dans un instant." >&2; exit 1; }

step "Images (≈ 10 minutes la première fois)"
# URAG_BUILD_ARGS : options supplémentaires (proxy d'entreprise, miroir d'images), facultatives.
# shellcheck disable=SC2086
docker build -q ${URAG_BUILD_ARGS:-} -f "$ROOT/infrastructure/docker/app.Dockerfile" -t urag-app:latest "$ROOT"
# shellcheck disable=SC2086
docker build -q ${URAG_BUILD_ARGS:-} ${URAG_WEB_BUILD_ARGS:-} -f "$ROOT/infrastructure/docker/web.Dockerfile" \
  -t urag-web:latest "$ROOT"

step "Documents d'essai (corpus public, empreintes vérifiées)"
mkdir -p "$DOCS/corpus"
python3 "$ROOT/eval/download_corpus.py" --dest "$DOCS/corpus" --only "$DOC_IDS"
chmod -R a+rX "$DOCS"

step "Installation (derrière le relais HTTPS de Codespaces)"
sudo "$ROOT/infrastructure/scripts/install-server.sh" --behind-proxy --site localhost \
  --org-name "Organisation d'essai" --org-slug essai --admin-login admin \
  --data-dir "$DATA/server" --documents-dir "$DOCS" --https-port "$PORT" \
  --chat-model "$MODEL" --gpu non

step "Indexation des documents et vérification d'une recherche"
if [[ -f "$DATA/.essai-indexe" ]]; then
  echo "déjà fait lors d'un lancement précédent"
else
  # Mot de passe lu par l'entrée standard, jamais en argument ; script exécuté dans l'image de
  # l'application (bibliothèques déjà présentes).
  sudo cat "$DATA/server/premier-administrateur.txt" | docker run --rm -i --network host \
    -v "$ROOT/infrastructure/scripts/verify-install.py:/tmp/verify-install.py:ro" \
    --entrypoint python urag-app:latest /tmp/verify-install.py \
    --url "http://127.0.0.1:$PORT" --login admin --password-file /dev/stdin --folder corpus
  touch "$DATA/.essai-indexe"
fi

# Copie lisible par l'utilisateur du codespace (privé), pour l'ouvrir dans l'éditeur.
ACCES="$HOME/ACCES-ESSAI.txt"
sudo cat "$DATA/server/premier-administrateur.txt" > "$ACCES"
chmod 600 "$ACCES"

cat <<TXT

Essai prêt.
  1. Onglet « PORTS » de Codespaces : ouvrez l'adresse du port $PORT (icône du globe).
  2. Identifiant et mot de passe provisoire : fichier $ACCES
  3. Questions d'essai : docs/ESSAI-CODESPACES.md.
Arrêtez le codespace après l'essai (le temps gratuit est compté pendant qu'il tourne).
TXT
