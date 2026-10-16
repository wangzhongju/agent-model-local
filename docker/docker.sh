#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_PATH="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yaml"

export WORKSPACE_PATH
export DOCKER_USERS="${DOCKER_USERS:-${USER:-$(id -un)}}"
export USER_ID="${USER_ID:-$(id -u)}"
export GROUP_ID="${GROUP_ID:-$(id -g)}"
export CONTAINER_NAME="${CONTAINER_NAME:-agent-model-local-${DOCKER_USERS}}"
export DOCKER_IMAGE="${DOCKER_IMAGE:-agent-model-local:0.1.0}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-agent_model_local_${DOCKER_USERS}}"

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

is_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || true)" == "true" ]]
}

init_container() {
  docker cp "${SCRIPT_DIR}/env.sh" "${CONTAINER_NAME}:/tmp/agent_model_env.sh"
  docker exec -u root "$CONTAINER_NAME" bash /tmp/agent_model_env.sh
}

build_image() {
  compose build "$@"
}

start_container() {
  compose up -d trainer
  init_container
  echo "Started ${CONTAINER_NAME}"
  enter_container
}

stop_container() {
  compose down
}

restart_container() {
  stop_container
  start_container
}

show_logs() {
  compose logs -f --tail="${LOG_TAIL:-200}" trainer
}

enter_container() {
  if ! is_running; then
    start_container
  fi
  docker exec -it -u "$DOCKER_USERS" "$CONTAINER_NAME" bash
}

exec_container() {
  if [[ $# -eq 0 ]]; then
    enter_container
    return
  fi
  if ! is_running; then
    start_container
  fi
  docker exec -u "$DOCKER_USERS" "$CONTAINER_NAME" "$@"
}

show_status() {
  compose ps
}

help() {
  cat <<EOF
Usage: docker/docker.sh <command> [args]

Commands:
  build [args]     Build ${DOCKER_IMAGE}. Extra args pass to docker compose build.
  start            Start trainer container and initialize the host user.
  stop             Stop and remove the compose container.
  restart          Restart trainer container.
  logs             Follow trainer logs.
  status           Show compose container status.
  into | shell     Open an interactive shell as ${DOCKER_USERS}.
  exec <cmd...>    Run a command as ${DOCKER_USERS} inside the container.
  init             Re-run lightweight user initialization.
  help             Show this message.

Useful environment variables:
  DOCKER_IMAGE=${DOCKER_IMAGE}
  BASE_IMAGE=pytorch/pytorch:2.7.1-cuda12.6-cudnn9-runtime
  GPU_ID=0
  CONTAINER_NAME=${CONTAINER_NAME}
EOF
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    build) build_image "$@" ;;
    start) start_container ;;
    stop) stop_container ;;
    restart) restart_container ;;
    logs) show_logs ;;
    status|ps) show_status ;;
    into|shell) enter_container ;;
    exec) exec_container "$@" ;;
    init) init_container ;;
    -h|--help|help) help ;;
    *)
      echo "Unknown command: $cmd" >&2
      help
      exit 2
      ;;
  esac
}

main "$@"
