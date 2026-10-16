#!/usr/bin/env bash
# A short-lived, CPU-only download container. Optional proxy affects this process only.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "${1:-}" in
  download-model|download-dataset) ;;
  *) echo 'Usage: bash docker/download.sh {download-model|download-dataset} [CLI options]' >&2; exit 2 ;;
esac
docker run --rm --network "${DOWNLOAD_NETWORK:-bridge}" \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges:true \
  -e HTTPS_PROXY="${HTTPS_PROXY:-}" -e HTTP_PROXY="${HTTP_PROXY:-}" \
  -e HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}" -e HF_TOKEN="${HF_TOKEN:-}" \
  -e HF_HUB_DISABLE_XET=1 -v "$ROOT:/workspace" -w /workspace \
  "${DOCKER_IMAGE:-agent-model-local:0.1.0}" python -m aml.cli "$@"
