#!/usr/bin/env bash
# Modèles ONNX d'encodage (BGE-M3, MIT) et de reclassement (bge-reranker-v2-m3, Apache-2.0).
# Révisions figées et empreintes SHA-256 vérifiées (ADR-0018, ADR-0021).
#   fetch-models.sh DESTINATION              téléchargement depuis huggingface.co
#   fetch-models.sh DESTINATION --from DIR   installation hors ligne depuis une copie
set -euo pipefail

DEST=${1:?usage : fetch-models.sh DESTINATION [--from DOSSIER]}
FROM=""
if [[ "${2:-}" == "--from" ]]; then FROM=${3:?dossier source manquant}; fi

# dossier|dépôt|révision|fichier distant|fichier local|sha256
MANIFEST="
bge-m3-onnx|Xenova/bge-m3|4de13258303883538bd53b696b452bf8099f0858|onnx/model_int8.onnx|model_int8.onnx|a206e10e995aa2a833924bcd725ba5dd6c3425cd34bac3cf2b5677cd2a1c51d6
bge-m3-onnx|Xenova/bge-m3|4de13258303883538bd53b696b452bf8099f0858|tokenizer.json|tokenizer.json|6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790
bge-m3-onnx|Xenova/bge-m3|4de13258303883538bd53b696b452bf8099f0858|tokenizer_config.json|tokenizer_config.json|7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4
bge-m3-onnx|Xenova/bge-m3|4de13258303883538bd53b696b452bf8099f0858|config.json|config.json|734a79bf12d388c1467a4e3ab625f45de7f6906cffcfb93a1eca1787504bed95
bge-reranker-v2-m3-onnx|onnx-community/bge-reranker-v2-m3-ONNX|6f5ff65298512715a1e669753bc754d2bc8f367b|onnx/model_int8.onnx|model_int8.onnx|912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d
bge-reranker-v2-m3-onnx|onnx-community/bge-reranker-v2-m3-ONNX|6f5ff65298512715a1e669753bc754d2bc8f367b|tokenizer.json|tokenizer.json|8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3
bge-reranker-v2-m3-onnx|onnx-community/bge-reranker-v2-m3-ONNX|6f5ff65298512715a1e669753bc754d2bc8f367b|config.json|config.json|122e922dcfed6503c8721e6fe1daf090340c3d95ca7f3aa3a72730b321a51cfd
"

while IFS='|' read -r dir repo rev remote local sum; do
  [[ -z "$dir" ]] && continue
  mkdir -p "$DEST/$dir"
  target="$DEST/$dir/$local"
  if [[ -f "$target" ]] && echo "$sum  $target" | sha256sum -c --status; then
    echo "déjà présent : $dir/$local"; continue
  fi
  if [[ -n "$FROM" ]]; then
    cp "$FROM/$dir/$local" "$target.part"
  else
    echo "téléchargement : $repo/$remote"
    curl -fL --retry 4 --retry-delay 5 -o "$target.part" "https://huggingface.co/$repo/resolve/$rev/$remote"
  fi
  if ! echo "$sum  $target.part" | sha256sum -c --status; then
    rm -f "$target.part"; echo "ERREUR : empreinte incorrecte pour $dir/$local" >&2; exit 1
  fi
  mv "$target.part" "$target"
  echo "vérifié : $dir/$local"
done <<< "$MANIFEST"
chmod -R a+rX "$DEST"
echo "modèles prêts dans $DEST"
