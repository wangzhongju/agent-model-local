"""Fallback: download verified official Docker Hub layers using a container-only proxy.

Run in an existing Python container, never install anything on the host.
Produces Docker save format for `docker load`. No third-party model/image mirror.
"""
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import urllib.request

REPO='pytorch/pytorch'
TAG='2.7.1-cuda12.6-cudnn9-runtime'
root=Path('/workspace/.cache/official-image');root.mkdir(parents=True,exist_ok=True)
token=json.load(urllib.request.urlopen(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{REPO}:pull',timeout=60))['token']
headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'}


def request(path):
    return urllib.request.urlopen(urllib.request.Request(f'https://registry-1.docker.io/v2/{REPO}/{path}',headers=headers),timeout=120)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


with request('manifests/'+TAG) as response:
    raw=response.read(); manifest_digest=response.headers.get('Docker-Content-Digest')
if manifest_digest:
    assert hashlib.sha256(raw).hexdigest()==manifest_digest.split(':')[1]
m=json.loads(raw)
if 'manifests' in m:
    child=next(x for x in m['manifests'] if x['platform']['os']=='linux' and x['platform']['architecture']=='amd64')
    with request('manifests/'+child['digest']) as response: raw=response.read()
    assert hashlib.sha256(raw).hexdigest()==child['digest'].split(':')[1]
    m=json.loads(raw)
(root/'registry-manifest.json').write_bytes(raw)


def fetch(desc):
    digest=desc['digest'].split(':')[1]; path=root/digest
    if path.exists() and sha(path)==digest:return path
    print('Downloading',digest,desc['size'],flush=True)
    with request('blobs/'+desc['digest']) as response, path.with_suffix('.part').open('wb') as out:
        shutil.copyfileobj(response,out,4*1024*1024)
    assert sha(path.with_suffix('.part'))==digest,'layer checksum mismatch'
    path.with_suffix('.part').replace(path)
    print('Verified',digest,flush=True)
    return path


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    paths=list(pool.map(fetch,[m['config']]+m['layers']))
config_path=paths[0]; layer_names=[]
with tarfile.open(root/'pytorch.tar','w') as tar:
    tar.add(config_path,arcname=config_path.name+'.json')
    for p in paths[1:]:
        expanded=p.with_suffix('.tar')
        with gzip.open(p,'rb') as src, expanded.open('wb') as dest:shutil.copyfileobj(src,dest,4*1024*1024)
        name=p.name+'/layer.tar';tar.add(expanded,arcname=name);layer_names.append(name)
        expanded.unlink()
    save=[{'Config':config_path.name+'.json','RepoTags':[REPO+':'+TAG],'Layers':layer_names}]
    (root/'manifest.json').write_text(json.dumps(save));tar.add(root/'manifest.json',arcname='manifest.json')
(root/'provenance.json').write_text(json.dumps({'repository':REPO,'tag':TAG,'registry_digest':manifest_digest,'config':m['config']['digest']},indent=2))
print('READY',root/'pytorch.tar',flush=True)
