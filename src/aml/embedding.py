import json
from pathlib import Path
import torch
from torch.nn import functional as F

DEFAULT_INSTRUCTION = 'Given a search query, retrieve relevant passages that answer the query'


def query_text(text, instruction=DEFAULT_INSTRUCTION):
    return f'Instruct: {instruction}\nQuery:{text}'


def pool(hidden, mask):
    # Works with both left and right padding, including mixed-length batches.
    positions = torch.arange(mask.shape[1],device=mask.device).expand_as(mask)
    last = positions.masked_fill(mask == 0, -1).max(dim=1).values
    return F.normalize(hidden[torch.arange(len(hidden),device=hidden.device),last].float(),p=2,dim=-1)


def load_model(path, adapter=None, training=False):
    from transformers import AutoTokenizer, AutoModel
    tok = AutoTokenizer.from_pretrained(path, padding_side='left', local_files_only=True)
    model = AutoModel.from_pretrained(path, torch_dtype=torch.float32 if training else torch.bfloat16,
                                     attn_implementation='sdpa', local_files_only=True)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter, is_trainable=training)
    model.config.use_cache = False
    return tok, model


class Encoder:
    def __init__(self, model, adapter=None, max_length=None, batch_size=8, instruction=None):
        if not torch.cuda.is_available(): raise RuntimeError('需要可用 CUDA GPU；请检查容器 GPU 配置')
        metadata=Path(adapter or model)/'embedding_config.json'
        cfg=json.loads(metadata.read_text()) if metadata.exists() else {}
        self.tokenizer, self.model = load_model(model,adapter)
        self.model.cuda().eval(); self.max_length=max_length or cfg.get('max_length',512)
        self.batch_size=batch_size; self.instruction=instruction or cfg.get('instruction',DEFAULT_INSTRUCTION)

    def encode(self, texts, query=False):
        result=[]
        for start in range(0,len(texts),self.batch_size):
            batch=texts[start:start+self.batch_size]
            if query: batch=[query_text(t,self.instruction) for t in batch]
            inputs=self.tokenizer(batch,padding=True,truncation=True,max_length=self.max_length,return_tensors='pt').to('cuda')
            with torch.inference_mode():
                result.append(pool(self.model(**inputs).last_hidden_state,inputs['attention_mask']).cpu())
        return torch.cat(result).numpy()


def export_model(model, adapter, output):
    output=Path(output)
    if output.exists() and any(output.iterdir()): raise ValueError('导出目录非空')
    tok, base=load_model(model,adapter)
    merged=base.merge_and_unload(safe_merge=True)
    merged.save_pretrained(output,safe_serialization=True); tok.save_pretrained(output)
    (output/'1_Pooling').mkdir()
    (output/'2_Normalize').mkdir()
    (output/'modules.json').write_text(json.dumps([
        {'idx':0,'name':'0','path':'','type':'sentence_transformers.models.Transformer'},
        {'idx':1,'name':'1','path':'1_Pooling','type':'sentence_transformers.models.Pooling'},
        {'idx':2,'name':'2','path':'2_Normalize','type':'sentence_transformers.models.Normalize'}]))
    (output/'1_Pooling/config.json').write_text(json.dumps({'word_embedding_dimension':merged.config.hidden_size,
        'pooling_mode_cls_token':False,'pooling_mode_mean_tokens':False,'pooling_mode_max_tokens':False,
        'pooling_mode_lasttoken':True}))
    metadata=Path(adapter)/'embedding_config.json'
    cfg=json.loads(metadata.read_text()) if metadata.exists() else {'instruction':DEFAULT_INSTRUCTION,'max_length':512}
    (output/'sentence_bert_config.json').write_text(json.dumps({'max_seq_length':cfg['max_length'],'do_lower_case':False}))
    (output/'config_sentence_transformers.json').write_text(json.dumps({'prompts':{'query':query_text('',cfg['instruction'])},'default_prompt_name':None}))
    (output/'embedding_config.json').write_text(json.dumps(cfg))
