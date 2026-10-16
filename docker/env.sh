#!/usr/bin/env bash
set -euo pipefail
# Only creates files inside this project. No users, sudoers, sysctl or host pip.
mkdir -p /workspace/.cache/home /workspace/.cache/huggingface \
  /workspace/data /workspace/models /workspace/runs /workspace/logs
