"""Collect measured acceptance evidence; run only after all server checks finish."""
import json
import re
from datetime import datetime,timezone
from pathlib import Path
import torch
from safetensors.torch import load_file
from aml.common import write_json

def read(path):return json.loads(Path(path).read_text())
checks={name:int(Path(f'logs/{name}.exit').read_text()) for name in
        ('build-mirror','acceptance','scifact-data','scifact-training','scifact-evaluation','download-wrapper')}
if any(checks.values()):raise RuntimeError(f'Acceptance has failed steps: {checks}')
state=read('runs/embedding/scifact/qwen3-0.6b/lora-v1/trainer_state.json')
checkpoint=Path('runs/embedding/scifact/qwen3-0.6b/lora-v1')/f"checkpoint-{state['global_step']}"
weights=load_file(checkpoint/'adapter_model.safetensors')
max_b=max(v.abs().max().item() for k,v in weights.items() if 'lora_B' in k)
if max_b==0:raise RuntimeError('No learned LoRA B update in final training checkpoint')
tests=re.findall(r'(\d+) passed',Path('logs/acceptance.log').read_text())
report={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'checks_exit_codes':checks,
        'tests_passed':int(tests[-1]),'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,
        'cuda_runtime':torch.version.cuda,'base_image':read('.cache/official-image/provenance.json'),
        'model_revision':read('models/base/Qwen3-Embedding-0.6B/download.json')['revision'],
        'demo_dataset':read('data/domains/demo/versions/v1/validation.json'),
        'scifact_dataset':read('data/domains/scifact/versions/v1/validation.json'),
        'dense_mining':read('data/domains/demo/versions/v1/embedding/dense/train.jsonl.report.json'),
        'demo_gpu_memory':read('runs/embedding/demo/qwen3-0.6b/lora-v1/gpu-memory.json'),
        'scifact_gpu_memory':read('runs/embedding/scifact/qwen3-0.6b/lora-v1/gpu-memory.json'),
        'resume_global_step':state['global_step'],'best_checkpoint':state['best_model_checkpoint'],
        'final_training_checkpoint_max_abs_lora_B':max_b,
        'export_equivalence':read('runs/evaluation/demo/export-equivalence.json'),
        'scifact_comparison':read('runs/evaluation/scifact/comparison.json'),
        'limitations':['仅验证短程工程闭环，未完成业务领域效果优化','演示查询为模板弱标签',
                       '本地 LLM 生成接口未在本次下载生成模型实测','ReRank/LLM 专用训练器为后续扩展项']}
write_json('docs/验收报告.json',report)
print(json.dumps(report,ensure_ascii=False,indent=2))
