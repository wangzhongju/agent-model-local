#!/usr/bin/env bash
# Generic post-data pipeline. All paths are explicit to prevent cross-domain mixing.
set -euo pipefail
if [[ $# -lt 4 ]]; then
  echo 'Usage (inside container): bash scripts/train_and_evaluate.sh CONFIG DATA_ROOT REPORT_DIR EXPORT_DIR' >&2
  exit 2
fi
config="$1"; root="$2"; report="$3"; exported="$4"
mapfile -t fields < <(python - "$config" <<'PY'
import sys,yaml
c=yaml.safe_load(open(sys.argv[1]))
for key in ('model','output_dir','instruction','max_length','dataset_root'):print(c[key])
PY
)
model="${fields[0]}"; experiment="${fields[1]}"; instruction="${fields[2]}"; length="${fields[3]}"
[[ "$root" == "${fields[4]}" ]] || { echo 'DATA_ROOT must match config dataset_root' >&2; exit 2; }
[[ ! -e "$report" && ! -e "$exported" ]] || { echo 'Report/export directory already exists; choose a new experiment' >&2; exit 2; }
python -m aml.cli validate --root "$root"
python -m aml.cli evaluate --root "$root" --split dev --model "$model" --instruction "$instruction" --max-length "$length" --output "$report/base-dev.json"
python -m aml.cli train --config "$config"
python -m aml.cli evaluate --root "$root" --split dev --model "$model" --adapter "$experiment/adapter" --instruction "$instruction" --max-length "$length" --output "$report/lora-dev.json"
python -m aml.cli compare --baseline "$report/base-dev.json" --candidate "$report/lora-dev.json" --output "$report/dev-gate.json"
python -m aml.cli evaluate --root "$root" --model "$model" --instruction "$instruction" --max-length "$length" --output "$report/base-test.json"
python -m aml.cli evaluate --root "$root" --model "$model" --adapter "$experiment/adapter" --instruction "$instruction" --max-length "$length" --output "$report/lora-test.json"
python -m aml.cli compare --baseline "$report/base-test.json" --candidate "$report/lora-test.json" --output "$report/test-gate.json"
python -m aml.cli export --model "$model" --adapter "$experiment/adapter" --output "$exported"
python scripts/verify_export.py --base "$model" --adapter "$experiment/adapter" --merged "$exported" --output "$report/export-equivalence.json"
