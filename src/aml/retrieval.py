import json
import math
import re
from pathlib import Path
import numpy as np
from .common import read_jsonl, write_jsonl, write_json, digest, file_digest, normalize
from .data import validate


def tokens(text):
    return re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]',text.lower())


def mine(root, output, method='bm25', model=None, negatives=4, split='train',
         max_length=512, margin=.05, instruction=None):
    validate(root)
    if negatives < 1: raise ValueError('negatives 必须为正数')
    root=Path(root); corpus=[d for d in read_jsonl(root/'corpus.jsonl') if d['split']==split]
    qs=read_jsonl(root/f'{split}.queries.jsonl'); docs={d['id']:d for d in corpus}
    indexes={d['id']:i for i,d in enumerate(corpus)}
    if method == 'bm25':
        from rank_bm25 import BM25Okapi
        bm25=BM25Okapi([tokens(d['text']) for d in corpus])
    else:
        from .embedding import Encoder, DEFAULT_INSTRUCTION
        instruction=instruction or DEFAULT_INSTRUCTION
        enc=Encoder(model,max_length=max_length,instruction=instruction)
        vectors=enc.encode([d['text'] for d in corpus])
        query_vectors=enc.encode([q['query'] for q in qs],query=True)
    results=[]; skipped=[]
    for i,q in enumerate(qs):
        scores=bm25.get_scores(tokens(q['query'])) if method=='bm25' else vectors @ query_vectors[i]
        positives=set(q['positive_ids']); sources={docs[p]['source_id'] for p in positives}
        pos_texts={normalize(docs[p]['text']) for p in positives}
        positive_score=max(float(scores[indexes[p]]) for p in positives)
        chosen=[]; audit=[]
        for j in np.argsort(-scores,kind='stable'):
            d=corpus[int(j)]
            if d['id'] in positives or d['source_id'] in sources or normalize(d['text']) in pos_texts: continue
            # Dense scores too close to a positive may be unlabelled positives.
            if method=='dense' and float(scores[j]) >= positive_score-margin: continue
            chosen.append(d['id']); audit.append({'id':d['id'],'score':float(scores[j])})
            if len(chosen)==negatives: break
        if len(chosen)<negatives:
            skipped.append({'id':q['id'],'reason':'insufficient safe negatives','available':len(chosen)}); continue
        # Keep all known positives in metadata, rotate positive choice across queries upstream if needed.
        results.append({'id':q['id'],'query':q['query'],'positive_ids':q['positive_ids'],
                        'positive':docs[q['positive_ids'][0]]['text'],
                        'negatives':[docs[p]['text'] for p in chosen],'negative_ids':chosen,
                        'split':split,'mining':{'method':method,'positive_score':positive_score,'candidates':audit}})
    write_jsonl(output,results)
    write_json(str(output)+'.report.json',{'kept':len(results),'skipped':skipped,'method':method,'margin':margin,
               'model':model,'instruction':instruction,'max_length':max_length,
               'dataset_manifest_sha256':digest((root/'manifest.json').read_bytes()),'output_sha256':digest(Path(output).read_bytes())})
    if not results: raise ValueError('没有有效三元组，请检查正样本质量、分区大小、negative 数或 dense margin')


def metrics_for(ranked, relevant, ks=(1,5,10)):
    relevant=set(relevant); result={}
    for k in ks:
        hits=[int(p in relevant) for p in ranked[:k]]
        result[f'recall@{k}']=sum(hits)/len(relevant)
        result[f'mrr@{k}']=next((1/(i+1) for i,h in enumerate(hits) if h),0.)
        dcg=sum(h/math.log2(i+2) for i,h in enumerate(hits))
        ideal=sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
        result[f'ndcg@{k}']=dcg/ideal
    return result


def evaluate(root, model, output, adapter=None, split='test', max_length=None, instruction=None):
    from .embedding import Encoder, DEFAULT_INSTRUCTION
    validate(root); root=Path(root)
    corpus=read_jsonl(root/'corpus.jsonl'); qs=read_jsonl(root/f'{split}.queries.jsonl')
    # Evaluation retrieves against the complete corpus, including distractors from other partitions.
    enc=Encoder(model,adapter,max_length=max_length,instruction=instruction)
    vectors=enc.encode([d['text'] for d in corpus]); qv=enc.encode([q['query'] for q in qs],query=True)
    totals={}; details=[]
    for q,v in zip(qs,qv):
        scores=vectors @ v; top=np.argsort(-scores,kind='stable')[:10]
        ranked=[corpus[int(i)]['id'] for i in top]
        m=metrics_for(ranked,q['positive_ids']); details.append({'id':q['id'],'ranked':ranked,'metrics':m})
        for key,value in m.items(): totals[key]=totals.get(key,0)+value
    report={'model':str(model),'adapter':str(adapter) if adapter else None,'split':split,
            'instruction':enc.instruction,'max_length':enc.max_length,
            'queries':len(qs),'corpus':len(corpus),'dataset_manifest_sha256':digest((root/'manifest.json').read_bytes()),
            'metrics':{k:v/len(qs) for k,v in totals.items()}}
    if adapter:
        report['adapter_sha256']={p.name:file_digest(p) for p in Path(adapter).glob('*.safetensors')}
    provenance=Path(model)/'download.json'
    if provenance.exists():report['model_provenance']=json.loads(provenance.read_text())
    write_json(output,report); write_jsonl(str(output)+'.queries.jsonl',details)
    return report


def compare(before, after, output, tolerance=0.):
    a=json.loads(Path(before).read_text()); b=json.loads(Path(after).read_text())
    for key in ('dataset_manifest_sha256','split','instruction','max_length','queries','corpus'):
        if a[key]!=b[key]: raise ValueError(f'评估条件不一致: {key}')
    delta={k:b['metrics'][k]-v for k,v in a['metrics'].items()}
    report={'baseline':a['metrics'],'candidate':b['metrics'],'delta':delta,
            'passed':delta['ndcg@10']>=-tolerance and delta['recall@10']>=-tolerance,'tolerance':tolerance}
    write_json(output,report)
    return report
