import json
from pathlib import Path
import pytest
from aml.common import write_jsonl,partition
from aml.data import prepare,validate
from aml.documents import ingest


def fixtures(tmp_path):
    corpus=[{'id':str(i),'source_id':str(i),'text':f'Independent document {i} about policy {i} with sufficient detail to be useful.'} for i in range(60)]
    queries=[{'id':str(i),'query':f'What is policy {i}?','positive_ids':[str(i)],'status':'approved'} for i in range(60)]
    write_jsonl(tmp_path/'c.jsonl',corpus); write_jsonl(tmp_path/'q.jsonl',queries)
    return corpus,queries


def test_group_isolation_and_manifest(tmp_path):
    c,q=fixtures(tmp_path); c[1]['source_id']='0'; c[2]['text']=c[0]['text']
    write_jsonl(tmp_path/'c.jsonl',c)
    root=tmp_path/'v1';prepare(tmp_path/'c.jsonl',tmp_path/'q.jsonl',root)
    rows=[json.loads(s) for s in (root/'corpus.jsonl').read_text().splitlines()]
    assert len({rows[i]['split'] for i in range(3)})==1
    with pytest.raises(ValueError,match='已存在'): prepare(tmp_path/'c.jsonl',tmp_path/'q.jsonl',root)
    with (root/'train.queries.jsonl').open('a') as f:f.write('\n')
    with pytest.raises(ValueError,match='冻结文件'):validate(root)


def test_approval_and_duplicate_queries(tmp_path):
    c,q=fixtures(tmp_path);q[0]['query']=q[1]['query'];q[2]['status']='draft'
    write_jsonl(tmp_path/'q.jsonl',q);root=tmp_path/'v1'
    prepare(tmp_path/'c.jsonl',tmp_path/'q.jsonl',root)
    qs=[json.loads(s) for p in root.glob('*.queries.jsonl') for s in p.read_text().splitlines()]
    assert len(qs)==58
    assert any(set(x['positive_ids'])=={'0','1'} for x in qs)


def test_mining_excludes_positive_sources(tmp_path):
    from aml.retrieval import mine
    c,q=fixtures(tmp_path);c[1]['source_id']='0';write_jsonl(tmp_path/'c.jsonl',c)
    root=tmp_path/'v1';prepare(tmp_path/'c.jsonl',tmp_path/'q.jsonl',root)
    mine(root,tmp_path/'mined.jsonl',negatives=2)
    rows=[json.loads(s) for s in (tmp_path/'mined.jsonl').read_text().splitlines()]
    docs={d['id']:d for d in c}
    for r in rows:
        pos_sources={docs[p]['source_id'] for p in r['positive_ids']}
        assert not pos_sources & {docs[p]['source_id'] for p in r['negative_ids']}


def test_ingest_and_failure(tmp_path):
    raw=tmp_path/'raw';raw.mkdir();(raw/'a.md').write_text('# Policy\n'+'This is a long enough policy sentence. '*5)
    ingest(raw,tmp_path/'c.jsonl',chunk_size=80,overlap=10)
    assert (tmp_path/'c.jsonl').read_text()
    with pytest.raises(ValueError):ingest(raw,tmp_path/'c.jsonl',chunk_size=80,overlap=80)
    (raw/'bad.pdf').write_bytes(b'broken pdf')
    with pytest.raises(ValueError,match='解析失败'):ingest(raw,tmp_path/'c.jsonl')


def test_pool_and_metrics():
    import torch
    from aml.embedding import pool
    from aml.retrieval import metrics_for
    h=torch.tensor([[[1.,0.],[0.,2.],[9.,9.]],[[0.,0.],[1.,0.],[0.,3.]]])
    p=pool(h,torch.tensor([[1,1,0],[0,1,1]]))
    assert torch.allclose(p,torch.tensor([[0.,1.],[0.,1.]]))
    m=metrics_for(['x','a','b'],{'a','b'})
    assert m['recall@1']==0 and m['recall@5']==1 and m['mrr@5']==.5
    assert 0<m['ndcg@5']<1


def test_compare_rejects_mismatched_conditions(tmp_path):
    from aml.retrieval import compare
    from aml.common import write_json
    base={'dataset_manifest_sha256':'abc','split':'test','instruction':'a','max_length':512,
          'queries':2,'corpus':10,'metrics':{'ndcg@10':.5,'recall@10':.7}}
    write_json(tmp_path/'a.json',base)
    changed=dict(base,metrics={'ndcg@10':.4,'recall@10':.7})
    write_json(tmp_path/'b.json',changed)
    assert not compare(tmp_path/'a.json',tmp_path/'b.json',tmp_path/'out.json')['passed']
    changed['instruction']='different';write_json(tmp_path/'b.json',changed)
    with pytest.raises(ValueError,match='评估条件'):compare(tmp_path/'a.json',tmp_path/'b.json',tmp_path/'out.json')
