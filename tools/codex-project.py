#!/usr/bin/env python3
"""Create a new Codex MCM project or show a read-only preview for an existing one."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.venv', '__pycache__', 'node_modules', '.git', '.pytest_cache'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_bundle(root=ROOT):
    root = Path(root).resolve()
    base = root/'adapters/codex/generated'
    manifest = json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    for collection, parent in [('sources', root), ('files', base)]:
        for rel, expected in manifest[collection].items():
            p = parent/rel
            if Path(rel).is_absolute() or '..' in Path(rel).parts or p.is_symlink() or not p.resolve().is_relative_to(parent):
                raise ValueError('Unsafe bundle path: '+rel)
            if not p.is_file() or sha(p) != expected:
                raise ValueError('Stale or changed bundle input: '+rel+'; rebuild the adapter first')
    return manifest

def files_under(base):
    base=Path(base).resolve()
    for folder, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for d in dirs:
            if (Path(folder)/d).is_symlink():
                raise ValueError('Symlinked template directories are unsupported')
        for name in files:
            p=Path(folder)/name
            if p.is_symlink() or not p.resolve().is_relative_to(base):
                raise ValueError('Symlinked or escaping template file')
            yield p.relative_to(base).as_posix(), p

def project_files(root=ROOT):
    manifest=verify_bundle(root)
    result=dict(files_under(Path(root)/'project-template'))
    for rel in manifest['files']:
        if rel.startswith('project/'):
            result[rel.removeprefix('project/')]=Path(root)/'adapters/codex/generated'/rel
    return result,manifest

def preview(destination, root=ROOT):
    target=Path(destination).resolve()
    expected,manifest=project_files(root)
    changes=[]
    for rel,source in expected.items():
        p=target/rel
        if p.is_symlink() or (p.exists() and not p.resolve().is_relative_to(target)):
            state='unsafe_existing_path'
        elif not p.exists(): state='missing'
        elif not p.is_file(): state='type_conflict'
        elif sha(p)==sha(source): state='same'
        else: state='different_preserve_existing'
        changes.append({'path':rel,'state':state})
    return {'mode':'preview','changed':False,'native_runtime_verified':False,
            'adapter_version':manifest['adapter_version'],'files':changes,
            'note':'No files or approval records were changed. Existing projects are never upgraded automatically.'}

def create(destination, root=ROOT):
    target=Path(destination).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError('Destination already exists; use preview or choose a new directory')
    expected,manifest=project_files(root)
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=target.parent/(target.name+'.staging-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        for rel,source in expected.items():
            p=stage/rel
            p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,p)
        (stage/'.mcm-project').mkdir(exist_ok=True)
        for rel in ('input/problem','input/attachments','data/raw','data/processed','models','tasks','drafts','audit','logs'):
            (stage/rel).mkdir(parents=True,exist_ok=True)
        receipt={'format_version':1,'adapter_version':manifest['adapter_version'],
                 'status':'candidate_native_runtime_pending','native_runtime_verified':False,
                 'files':{rel:sha(stage/rel) for rel in expected}}
        (stage/'config/codex-install.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # rename is non-replacing on Windows; explicit recheck also protects POSIX.
        if target.exists(): raise ValueError('Destination appeared during creation; staged files retained')
        stage.rename(target)
    except Exception as exc:
        raise ValueError(f'Creation failed; inspect retained stage {stage}: {exc}') from exc
    return {'created':str(target),'files':len(expected),'native_runtime_verified':False,
            'next':'Open this project in Codex; read AGENTS.md and run codex_control capabilities/preflight.'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['new','preview'])
    p.add_argument('--destination',required=True)
    args=p.parse_args(argv)
    try:
        result=create(args.destination) if args.command=='new' else preview(args.destination)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__': raise SystemExit(main())
