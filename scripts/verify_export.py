"""Compare loaded adapter vs merged deployment model on identical queries/documents."""
import argparse
import gc
import json
import numpy as np
import torch
from pathlib import Path
from aml.embedding import Encoder
from aml.common import write_json
p=argparse.ArgumentParser()
p.add_argument('--base',default='models/base/Qwen3-Embedding-0.6B')
p.add_argument('--adapter',required=True)
p.add_argument('--merged',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
cfg=json.loads((Path(a.adapter)/'embedding_config.json').read_text())
texts=['How long are backup files retained?','备份文件保留多长时间？','Backup retention is 30 days.']
def encode(model,adapter=None):
    enc=Encoder(model,adapter,instruction=cfg['instruction'],max_length=cfg['max_length'])
    result=np.concatenate([enc.encode(texts[:2],query=True),enc.encode(texts[2:])])
    del enc;gc.collect();torch.cuda.empty_cache()
    return result
before=encode(a.base,a.adapter);after=encode(a.merged)
from sentence_transformers import SentenceTransformer
st=SentenceTransformer(a.merged,device='cuda',model_kwargs={'torch_dtype':torch.bfloat16})
st_vectors=np.concatenate([st.encode(texts[:2],prompt_name='query'),st.encode(texts[2:])])
cos=(before*after).sum(axis=1)
report={'shape':list(after.shape),'max_absolute_error':float(np.abs(before-after).max()),
        'minimum_cosine':float(cos.min()),'norms':np.linalg.norm(after,axis=1).tolist(),
        'sentence_transformers_max_error':float(np.abs(st_vectors-after).max())}
report['passed']=report['max_absolute_error']<.01 and report['minimum_cosine']>.999 and report['sentence_transformers_max_error']<.01
write_json(a.output,report);print(json.dumps(report,indent=2))
if not report['passed']:raise SystemExit(2)
