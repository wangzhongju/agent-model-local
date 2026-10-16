import hashlib
import json
import random
import re
from pathlib import Path


def digest(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def file_digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def read_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    tmp.replace(path)


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def dataset_root(domain, version):
    for name in (domain, version):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
            raise ValueError('domain/version 仅支持字母、数字、点、下划线、短横线')
    return Path('data/domains') / domain / 'versions' / version


def partition(groups, seed=42):
    groups = sorted(set(groups)); random.Random(seed).shuffle(groups)
    if len(groups) < 3:
        raise ValueError('至少需要 3 个独立文档/查询连通组，才能隔离 train/dev/test')
    n = max(1, round(len(groups) * .1))
    return {g: ('test' if i < n else 'dev' if i < 2*n else 'train') for i, g in enumerate(groups)}


def manifest(root, **extra):
    root = Path(root)
    files = {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(root.rglob('*.jsonl'))}
    write_json(root / 'manifest.json', {'schema_version': 1, 'files': files, **extra})
