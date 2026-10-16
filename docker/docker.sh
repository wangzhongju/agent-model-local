#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WORKSPACE_PATH="$(cd "$SCRIPT_DIR/.." && pwd)"
export USER_ID="$(id -u)" GROUP_ID="$(id -g)"
export CONTAINER_NAME="${CONTAINER_NAME:-agent-model-local-$(id -un)}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-agent_model_local_$(id -un)}"
compose() { docker compose -f "$SCRIPT_DIR/docker-compose.yaml" "$@"; }
start() { compose up -d trainer; compose exec -T trainer bash docker/env.sh; }
cmd="${1:-help}"; shift || true
case "$cmd" in
  build) compose build "$@" ;;
  start) start ;;
  stop) compose down ;;
  restart) compose down; start ;;
  status|ps) compose ps ;;
  logs) compose logs --tail=100 "$@" ;;
  into|shell) compose exec trainer bash ;;
  exec) compose exec -T trainer "$@" ;;
  config) compose config ;;
  init) compose exec -T trainer bash docker/env.sh ;;
  *) printf 'Usage: bash docker/docker.sh {build|start|stop|restart|status|shell|exec CMD|logs|config}\n' ;;
esac
