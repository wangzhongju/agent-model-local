import argparse
import json
from pathlib import Path
from .common import dataset_root


def main():
    p=argparse.ArgumentParser(description='容器内运行的 RAG 模型微调工具链')
    s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('download-model'); a.add_argument('--repo',default='Qwen/Qwen3-Embedding-0.6B'); a.add_argument('--output',default='models/base/Qwen3-Embedding-0.6B'); a.add_argument('--revision',default='main')
    a=s.add_parser('download-dataset'); a.add_argument('--output',default='data/external/scifact')
    a=s.add_parser('ingest'); a.add_argument('--input',required=True); a.add_argument('--output',required=True); a.add_argument('--chunk-size',type=int,default=700); a.add_argument('--overlap',type=int,default=100); a.add_argument('--ocr',action='store_true')
    a=s.add_parser('queries'); a.add_argument('--corpus',required=True); a.add_argument('--output',required=True); a.add_argument('--generator',help='已下载到本地的指令模型目录；省略则使用待审核模板')
    a=s.add_parser('prepare'); a.add_argument('--corpus',required=True); a.add_argument('--queries',required=True); a.add_argument('--domain',required=True); a.add_argument('--version',required=True); a.add_argument('--seed',type=int,default=42); a.add_argument('--allow-draft',action='store_true')
    a=s.add_parser('validate'); a.add_argument('--root',required=True)
    a=s.add_parser('mine'); a.add_argument('--root',required=True); a.add_argument('--output',required=True); a.add_argument('--method',choices=['bm25','dense'],default='bm25'); a.add_argument('--model',default='models/base/Qwen3-Embedding-0.6B'); a.add_argument('--negatives',type=int,default=4); a.add_argument('--split',choices=['train','dev'],default='train'); a.add_argument('--max-length',type=int,default=512); a.add_argument('--margin',type=float,default=.05); a.add_argument('--instruction')
    a=s.add_parser('train'); a.add_argument('--config',required=True); a.add_argument('--resume'); a.add_argument('--max-steps',type=int)
    a=s.add_parser('evaluate'); a.add_argument('--root',required=True); a.add_argument('--model',default='models/base/Qwen3-Embedding-0.6B'); a.add_argument('--adapter'); a.add_argument('--output',required=True); a.add_argument('--split',choices=['dev','test'],default='test'); a.add_argument('--max-length',type=int); a.add_argument('--instruction')
    a=s.add_parser('compare'); a.add_argument('--baseline',required=True); a.add_argument('--candidate',required=True); a.add_argument('--output',required=True); a.add_argument('--tolerance',type=float,default=0.)
    a=s.add_parser('export'); a.add_argument('--model',default='models/base/Qwen3-Embedding-0.6B'); a.add_argument('--adapter',required=True); a.add_argument('--output',required=True)
    a=s.add_parser('search'); a.add_argument('--root',required=True); a.add_argument('--model',required=True); a.add_argument('--adapter'); a.add_argument('--query',required=True); a.add_argument('--top-k',type=int,default=5); a.add_argument('--instruction'); a.add_argument('--max-length',type=int)
    a=s.add_parser('convert'); a.add_argument('--input',required=True); a.add_argument('--output',required=True); a.add_argument('--task',choices=['reranker','llm'],required=True)
    s.add_parser('doctor')
    args=vars(p.parse_args()); command=args.pop('command'); result=None
    if command=='download-model':
        from .data import download_model
        download_model(**args)
    elif command=='download-dataset':
        from .data import download_scifact
        download_scifact(**args)
    elif command=='ingest':
        from .documents import ingest
        args['input_dir']=args.pop('input'); ingest(**args)
    elif command=='queries':
        from .data import generate_queries
        generate_queries(**args)
    elif command=='prepare':
        from .data import prepare
        root=dataset_root(args.pop('domain'),args.pop('version'))
        result=prepare(args.pop('corpus'),args.pop('queries'),root,**args)
    elif command=='validate':
        from .data import validate
        result=validate(**args)
    elif command=='mine':
        from .retrieval import mine
        mine(**args)
    elif command=='train':
        from .training import train
        result=train(**args)
    elif command=='evaluate':
        from .retrieval import evaluate
        result=evaluate(**args)
    elif command=='compare':
        from .retrieval import compare
        result=compare(args['baseline'],args['candidate'],args['output'],args['tolerance'])
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if not result['passed']: raise SystemExit(2)
        return
    elif command=='export':
        from .embedding import export_model
        export_model(**args)
    elif command=='search':
        import numpy as np
        from .common import read_jsonl
        from .embedding import Encoder,DEFAULT_INSTRUCTION
        enc=Encoder(args['model'],args['adapter'],max_length=args['max_length'],instruction=args['instruction'])
        docs=read_jsonl(Path(args['root'])/'corpus.jsonl')
        scores=enc.encode([d['text'] for d in docs]) @ enc.encode([args['query']],query=True)[0]
        result=[dict(docs[int(i)],score=float(scores[i])) for i in np.argsort(-scores)[:args['top_k']]]
    elif command=='convert':
        from .common import read_jsonl,write_jsonl
        rows=read_jsonl(args['input']); output=[]
        for r in rows:
            if args['task']=='reranker':
                for passage,label in [(r['positive'],1)]+[(n,0) for n in r['negatives']]:
                    output.append({'query':r['query'],'document':passage,'label':label,'split':r['split'],'source_query_id':r['id']})
            else:
                # Retrieval positives are context, never fabricate a supervised answer.
                output.append({'id':r['id'],'question':r['query'],'context':r['positive'],
                               'answer':None,'status':'needs_answer_annotation','split':r['split']})
        write_jsonl(args['output'],output)
    elif command=='doctor':
        import torch,transformers,peft
        result={'torch':torch.__version__,'transformers':transformers.__version__,'peft':peft.__version__,
                'cuda_available':torch.cuda.is_available(),'cuda_runtime':torch.version.cuda}
        if torch.cuda.is_available():
            free,total=torch.cuda.mem_get_info()
            result.update(gpu=torch.cuda.get_device_name(),free_gb=free/1024**3,total_gb=total/1024**3,bf16=torch.cuda.is_bf16_supported())
        else: raise RuntimeError('容器未检测到 GPU')
    if result is not None: print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
