#!/usr/bin/env bash
set -euo pipefail
cd /workspace
export PYTHONPATH=/workspace/src
python scripts/make_demo.py
python -m aml.cli ingest --input data/domains/demo/raw --output data/domains/demo/staging/corpus.jsonl
python -m aml.cli queries --corpus data/domains/demo/staging/corpus.jsonl --output data/domains/demo/staging/queries.jsonl
python -m aml.cli prepare --corpus data/domains/demo/staging/corpus.jsonl --queries data/domains/demo/staging/queries.jsonl --domain demo --version v1 --allow-draft
root=data/domains/demo/versions/v1
for split in train dev; do
  python -m aml.cli mine --root "$root" --split "$split" --output "$root/embedding/bm25/$split.jsonl"
done
if [ ! -f models/base/Qwen3-Embedding-0.6B/download.json ]; then
  python -m aml.cli download-model
fi
python -m aml.cli evaluate --root "$root" --output runs/evaluation/demo/baseline.json
python -m aml.cli train --config configs/embedding/qwen3-0.6b-lora.yaml --max-steps 2
adapter=runs/embedding/demo/qwen3-0.6b/lora-v1/adapter
python -m aml.cli evaluate --root "$root" --adapter "$adapter" --output runs/evaluation/demo/candidate.json
python -m aml.cli export --adapter "$adapter" --output models/exports/embedding/demo/smoke-v1
python scripts/verify_export.py --adapter "$adapter" --merged models/exports/embedding/demo/smoke-v1 --output runs/evaluation/demo/export-equivalence.json
# Comparison may intentionally fail its quality gate: a smoke test is not an improvement claim.
python -m aml.cli compare --baseline runs/evaluation/demo/baseline.json --candidate runs/evaluation/demo/candidate.json --output runs/evaluation/demo/comparison.json || test "$?" -eq 2
python -m aml.cli search --root "$root" --model models/exports/embedding/demo/smoke-v1 --query 'What is the backup retention policy for service S00?' > runs/evaluation/demo/search.json
