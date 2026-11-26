#!/usr/bin/env bash
# Clé maîtresse : export chiffré par une phrase de passe, et réimport (docs/DEPLOYMENT.md §4).
# Sans elle, les secrets en base (clés d'API, identifiants des sources) sont illisibles : elle se
# sauvegarde À PART des sauvegardes de la base (autre support, coffre, papier sous scellé).
#
#   sudo master-key.sh export FICHIER     (phrase de passe demandée deux fois)
#   sudo master-key.sh import FICHIER     (remplace la clé du serveur ; à faire avant une restauration)
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env
ACTION=${1:?usage : master-key.sh export|import FICHIER}
FILE=${2:?fichier manquant}
KEY="$URAG_DATA_DIR/master.key"
# La phrase de passe vient du terminal, ou de URAG_KEY_PASSPHRASE_FILE pour une procédure automatisée.
pass_args=(-pass stdin)
read_pass() {
  if [[ -n "${URAG_KEY_PASSPHRASE_FILE:-}" ]]; then cat "$URAG_KEY_PASSPHRASE_FILE"; return; fi
  local a b
  read -rsp "Phrase de passe (12 caractères au moins) : " a; echo >&2
  [[ ${#a} -ge 12 ]] || fail "phrase de passe trop courte"
  if [[ "$ACTION" == export ]]; then read -rsp "Confirmation : " b; echo >&2; [[ "$a" == "$b" ]] || fail "phrases différentes"; fi
  printf '%s' "$a"
}
case "$ACTION" in
  export)
    umask 077
    read_pass | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -in "$KEY" -out "$FILE" "${pass_args[@]}"
    echo "clé exportée chiffrée : $FILE (empreinte $(key_fingerprint))"
    ;;
  import)
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    read_pass | openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in "$FILE" -out "$tmp" "${pass_args[@]}" \
      || fail "phrase de passe incorrecte ou fichier abîmé"
    [[ $(tr -d '\n' < "$tmp" | wc -c) -eq 64 ]] || fail "contenu inattendu : ce n'est pas une clé maîtresse"
    [[ -f "$KEY" ]] && cp -p "$KEY" "$KEY.avant-import-$(date +%Y%m%d%H%M%S)"
    install -m 400 -o 10001 -g 10001 "$tmp" "$KEY"
    echo "clé importée (empreinte $(key_fingerprint)) ; redémarrez l'API et le worker"
    ;;
  *) fail "action inconnue : $ACTION" ;;
esac
