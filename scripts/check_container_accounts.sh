#!/usr/bin/env bash
# Run on the server with existing Docker; uses disposable containers, no GPU.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="aml-account-check-$$"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" --user 1000:1000 --cap-drop ALL \
  --cap-add AUDIT_WRITE --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
  --cap-add SETGID --cap-add SETUID \
  "${DOCKER_IMAGE:-agent-model-local:0.1.0}" sleep infinity >/dev/null
docker cp "$root/docker/env.sh" "$name:/tmp/env.sh" >/dev/null
initialize() {
  docker exec -u 0:0 -e DOCKER_USER=amlcheck -e DOCKER_USER_ID=22001 \
    -e DOCKER_GRP=amlcheck -e DOCKER_GRP_ID=22001 "$name" bash /tmp/env.sh
}
initialize
before="$(docker exec -u 0:0 "$name" sha256sum /etc/passwd /etc/group /etc/sudoers.d/nopasswd /home/amlcheck/.bashrc /home/amlcheck/.profile /home/amlcheck/.vimrc /home/amlcheck/.pip/pip.conf)"
initialize
after="$(docker exec -u 0:0 "$name" sha256sum /etc/passwd /etc/group /etc/sudoers.d/nopasswd /home/amlcheck/.bashrc /home/amlcheck/.profile /home/amlcheck/.vimrc /home/amlcheck/.pip/pip.conf)"
[[ "$before" == "$after" ]]
docker exec -u amlcheck "$name" bash -euc '
  test "$(whoami)" = amlcheck
  test "$(id -g -n)" = amlcheck
  test "$HOME" = /home/amlcheck
  id -nG | tr " " "\n" | grep -Fxq sudo
  id -nG | tr " " "\n" | grep -Fxq video
  test "$(awk "/CapEff/ {print \$2}" /proc/self/status)" = 0000000000000000
  touch /home/amlcheck/ownership-probe
  test "$(stat -c %u:%g /home/amlcheck/ownership-probe)" = 22001:22001
  test -w /home/amlcheck/.bashrc
  test "$(wc -l < /home/amlcheck/.bashrc)" -gt 20
  test -s /home/amlcheck/.profile
  grep -q "alias ls=.*--color=auto" /home/amlcheck/.bashrc
  test "$(sudo -n id -u)" = 0
  command -v vim >/dev/null
  grep -q "pypi.tuna.tsinghua.edu.cn" /home/amlcheck/.pip/pip.conf
  id; groups
'
# Conflicting user/group names must fail without altering existing accounts.
if docker exec -u 0:0 -e DOCKER_USER=amlother -e DOCKER_USER_ID=22001 \
    -e DOCKER_GRP=amlcheck -e DOCKER_GRP_ID=22001 "$name" bash /tmp/env.sh; then
  echo 'Expected UID collision rejection' >&2; exit 1
fi
if docker exec -u 0:0 -e DOCKER_USER=amlother -e DOCKER_USER_ID=22002 \
    -e DOCKER_GRP=amlcheck -e DOCKER_GRP_ID=22002 "$name" bash /tmp/env.sh; then
  echo 'Expected group collision rejection' >&2; exit 1
fi
[[ "$after" == "$(docker exec -u 0:0 "$name" sha256sum /etc/passwd /etc/group /etc/sudoers.d/nopasswd /home/amlcheck/.bashrc /home/amlcheck/.profile /home/amlcheck/.vimrc /home/amlcheck/.pip/pip.conf)" ]]
# Reuse an existing GID even if its existing group name differs.
docker exec -u 0:0 -e DOCKER_USER=amlcheck -e DOCKER_USER_ID=22001 \
  -e DOCKER_GRP=aliasgroup -e DOCKER_GRP_ID=22001 "$name" bash /tmp/env.sh
[[ "$after" == "$(docker exec -u 0:0 "$name" sha256sum /etc/passwd /etc/group /etc/sudoers.d/nopasswd /home/amlcheck/.bashrc /home/amlcheck/.profile /home/amlcheck/.vimrc /home/amlcheck/.pip/pip.conf)" ]]
echo 'PASS: reference-style account setup, standard home, shell defaults, sudo/vim, ownership, non-root capabilities, idempotency, collisions, GID reuse'
