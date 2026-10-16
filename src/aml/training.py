import json
import os
import platform
import subprocess
from pathlib import Path
import yaml
import torch
from torch.nn import functional as F
from .common import read_jsonl, write_json, digest, file_digest
from .embedding import load_model, pool, query_text, DEFAULT_INSTRUCTION


def train(config, resume=None, max_steps=None):
    from transformers import Trainer, TrainingArguments, set_seed
    from peft import LoraConfig, get_peft_model, TaskType
    cfg=yaml.safe_load(Path(config).read_text(encoding='utf-8'))
    if not torch.cuda.is_available(): raise RuntimeError('CUDA 不可用')
    if not torch.cuda.is_bf16_supported(): raise RuntimeError('当前配置要求支持 BF16 的 GPU')
    out=Path(cfg['output_dir'])
    if out.exists() and any(out.iterdir()) and not resume:
        raise ValueError('实验目录非空；请使用新实验名或 --resume 指定 checkpoint')
    if resume:
        checkpoint=Path(resume).resolve()
        if checkpoint.parent != out.resolve() or not (checkpoint/'trainer_state.json').exists():
            raise ValueError('resume 必须是当前实验目录下包含 trainer_state.json 的 checkpoint')
        previous=json.loads((out/'run.json').read_text())
        if previous['config']!=cfg:
            raise ValueError('续训配置发生变化；请恢复原配置，新的配方必须新建实验')
    out.mkdir(parents=True,exist_ok=True)
    set_seed(cfg.get('seed',42))
    train_rows=read_jsonl(cfg['train_file']); dev_rows=read_jsonl(cfg['dev_file'])
    if not train_rows or not dev_rows: raise ValueError('训练或验证集为空')
    if any(r['split']!='train' for r in train_rows) or any(r['split']!='dev' for r in dev_rows):
        raise ValueError('训练/验证 split 错误')
    # Require mining provenance and unchanged files, then revalidate the frozen upstream dataset.
    from .data import validate
    validate(cfg['dataset_root'])
    dataset_manifest=json.loads((Path(cfg['dataset_root'])/'manifest.json').read_text())
    if dataset_manifest.get('allow_draft') and not cfg.get('allow_draft_data',False):
        raise ValueError('该数据版本含演示草稿，正式训练默认拒绝；仅演示配置允许 allow_draft_data')
    manifest_hash=digest((Path(cfg['dataset_root'])/'manifest.json').read_bytes())
    for key in ('train_file','dev_file'):
        report=json.loads(Path(cfg[key]+'.report.json').read_text())
        if report['dataset_manifest_sha256']!=manifest_hash or report['output_sha256']!=digest(Path(cfg[key]).read_bytes()):
            raise ValueError('挖掘数据已变更或来自其他数据版本')
    tok,model=load_model(cfg['model'],training=True)
    model=get_peft_model(model,LoraConfig(task_type=TaskType.FEATURE_EXTRACTION,
          r=cfg['lora']['r'],lora_alpha=cfg['lora']['alpha'],lora_dropout=cfg['lora']['dropout'],
          target_modules=cfg['lora']['target_modules'],bias='none'))
    trainable=[name for name,param in model.named_parameters() if param.requires_grad]
    if not trainable or any('lora_' not in name for name in trainable):
        raise RuntimeError('LoRA 冻结检查失败：出现非适配器训练参数')
    model.enable_input_require_grads(); model.print_trainable_parameters()
    instruction=cfg.get('instruction',DEFAULT_INSTRUCTION); length=cfg.get('max_length',512)
    nneg=cfg.get('negatives',4)
    lengths=[]
    for row in train_rows:
        texts=[query_text(row['query'],instruction),row['positive']]+row['negatives'][:nneg]
        lengths.extend(len(ids) for ids in tok(texts,truncation=False)['input_ids'])
    write_json(out/'token-lengths.json',{'texts':len(lengths),'max_tokens':max(lengths),
        'truncated_texts':sum(n>length for n in lengths),'max_length':length,
        'truncation_fraction':sum(n>length for n in lengths)/len(lengths)})
    def collate(rows):
        queries=[query_text(r['query'],instruction) for r in rows]
        documents=[]
        for r in rows:
            if len(r['negatives'])<nneg: raise ValueError('负样本数量不足')
            documents += [r['positive']]+r['negatives'][:nneg]
        encode=lambda texts:tok(texts,padding=True,truncation=True,max_length=length,return_tensors='pt')
        return {'queries':encode(queries),'documents':encode(documents), 'labels':torch.zeros(len(rows),dtype=torch.long)}
    class ContrastiveTrainer(Trainer):
        def compute_loss(self,model,inputs,return_outputs=False,num_items_in_batch=None):
            q,d=inputs['queries'],inputs['documents']
            qv=pool(model(**q).last_hidden_state,q['attention_mask'])
            dv=pool(model(**d).last_hidden_state,d['attention_mask']).reshape(len(qv),nneg+1,-1)
            logits=torch.einsum('bd,bnd->bn',qv,dv)/cfg.get('temperature',.05)
            loss=F.cross_entropy(logits,inputs['labels'])
            return (loss,{'logits':logits}) if return_outputs else loss
    steps=max_steps if max_steps is not None else cfg.get('max_steps',-1)
    args=TrainingArguments(output_dir=str(out),num_train_epochs=cfg.get('epochs',3),max_steps=steps,
        learning_rate=cfg.get('learning_rate',2e-4),per_device_train_batch_size=cfg.get('batch_size',4),
        per_device_eval_batch_size=cfg.get('batch_size',4),gradient_accumulation_steps=cfg.get('gradient_accumulation',8),
        warmup_ratio=.1,weight_decay=.01,lr_scheduler_type='cosine',bf16=True,tf32=True,
        gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},
        eval_strategy='steps' if steps>0 else 'epoch',save_strategy='steps' if steps>0 else 'epoch',
        eval_steps=1 if steps>0 else None,save_steps=1 if steps>0 else 500,
        load_best_model_at_end=True,metric_for_best_model='eval_loss',greater_is_better=False,
        save_total_limit=2,logging_steps=1,report_to='none',remove_unused_columns=False,
        label_names=['labels'],seed=cfg.get('seed',42),dataloader_num_workers=0,
        optim='adamw_torch',max_grad_norm=1.0)
    environment={'python':platform.python_version(),'torch':torch.__version__,'cuda':torch.version.cuda,
                 'gpu':torch.cuda.get_device_name(),'config':cfg,'max_steps_override':max_steps,
                 'dataset_manifest_sha256':manifest_hash,
                 'train_sha256':digest(Path(cfg['train_file']).read_bytes()),
                 'dev_sha256':digest(Path(cfg['dev_file']).read_bytes())}
    model_record=Path(cfg['model'])/'download.json'
    if model_record.exists():
        environment['base_model_revision']=json.loads(model_record.read_text())
        for name,expected in environment['base_model_revision'].get('files',{}).items():
            if file_digest(Path(cfg['model'])/name)!=expected:raise ValueError(f'基础模型文件被修改: {name}')
    environment['source_sha256']={str(p):file_digest(p) for p in Path('src/aml').rglob('*.py')}
    if resume:
        for key in ('train_sha256','dev_sha256','dataset_manifest_sha256','base_model_revision'):
            if previous.get(key)!=environment.get(key):raise ValueError(f'续训来源变化: {key}')
    write_json(out/'run.json',environment)
    (out/'pip-freeze.txt').write_text(subprocess.check_output(['python','-m','pip','freeze'],text=True))
    trainer=ContrastiveTrainer(model=model,args=args,train_dataset=train_rows,eval_dataset=dev_rows,data_collator=collate)
    # compute_loss returns a per-microbatch mean; Trainer must apply accumulation scaling.
    # PEFT accepts **kwargs, but this loss does not consume num_items_in_batch.
    trainer.model_accepts_loss_kwargs=False
    result=trainer.train(resume_from_checkpoint=resume)
    trainer.save_model(str(out/'adapter')); tok.save_pretrained(out/'adapter')
    write_json(out/'adapter/embedding_config.json',{'instruction':instruction,'max_length':length,'base_model':cfg['model'],
                                                 'base_model_revision':environment.get('base_model_revision')})
    trainer.save_state(); trainer.save_metrics('train',result.metrics)
    write_json(out/'gpu-memory.json',{'max_allocated_gb':torch.cuda.max_memory_allocated()/1024**3,
                                      'max_reserved_gb':torch.cuda.max_memory_reserved()/1024**3})
    return result.metrics
