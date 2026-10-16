#!/usr/bin/env bash
set -euo pipefail

user_name="${DOCKER_USER:?DOCKER_USER is required}"
uid="${DOCKER_USER_ID:?DOCKER_USER_ID is required}"
group_name="${DOCKER_GRP:-$user_name}"
gid="${DOCKER_GRP_ID:-$uid}"

ensure_group() {
  if getent group "$group_name" >/dev/null; then
    return
  fi
  if getent group "$gid" >/dev/null; then
    group_name="$(getent group "$gid" | cut -d: -f1)"
    return
  fi
  groupadd --gid "$gid" "$group_name"
}

ensure_user() {
  if id "$user_name" >/dev/null 2>&1; then
    return
  fi
  ensure_group
  useradd "$user_name" --uid "$uid" --gid "$gid" --create-home --shell /bin/bash
  usermod -aG sudo,video "$user_name" || true
}

append_once() {
  local line="$1"
  local file="$2"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  grep -Fqx "$line" "$file" || echo "$line" >> "$file"
}

write_pip_conf() {
  local home_dir="$1"
  mkdir -p "$home_dir/.pip"
  cat > "$home_dir/.pip/pip.conf" <<'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
EOF
}

setup_core_pattern() {
  if [[ -w /proc/sys/kernel/core_pattern ]]; then
    mkdir -p /workspace/data/core
    echo "/workspace/data/core/core_%e.%p" > /proc/sys/kernel/core_pattern
  fi
}

ensure_user
setup_core_pattern
primary_gid="$(id -g "$user_name")"
group_name="$(getent group "$primary_gid" | cut -d: -f1)"

echo "%sudo ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/nopasswd
chmod 0440 /etc/sudoers.d/nopasswd

user_home="$(getent passwd "$user_name" | cut -d: -f6)"
append_once "PS1='\\[\\033[01;32m\\]\\u@\\[\\033[01;35m\\]\\h\\[\\033[00m\\]:\\[\\033[01;36m\\]\\w\\[\\033[00m\\]$ '" "$user_home/.bashrc"
append_once 'export XDG_RUNTIME_DIR=/run/user/$(id -u)' "$user_home/.bashrc"
append_once "set encoding=utf-8" "$user_home/.vimrc"
append_once "set fileencodings=utf-8" "$user_home/.vimrc"
write_pip_conf "$user_home"
chown -R "$user_name:$group_name" "$user_home"

append_once "PS1='\\[\\033[01;32m\\]\\u@\\[\\033[01;35m\\]\\h\\[\\033[00m\\]:\\[\\033[01;36m\\]\\w\\[\\033[00m\\]$ '" /root/.bashrc
write_pip_conf /root

echo "Container user is ready: $user_name($uid):$group_name($gid)"
