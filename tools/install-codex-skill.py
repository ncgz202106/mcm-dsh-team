#!/usr/bin/env python3
"""Install only the namespaced mcm-team entry; preserve user edits and exact rollback."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
RECEIPT='.mcm-skill-install.json'
spec=importlib.util.spec_from_file_location('mcm_codex_project',Path(__file__).with_name('codex-project.py'))
project=importlib.util.module_from_spec(spec);spec.loader.exec_module(project)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,obj):
    path=Path(path)
    tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(tmp,path)

def payload(root=ROOT):
    manifest=project.verify_bundle(root)
    base=Path(root)/'adapters/codex/generated/skill'
    return {rel.removeprefix('skill/'):base/rel.removeprefix('skill/') for rel in manifest['files'] if rel.startswith('skill/')}

def current_state(target):
    if not target.exists():return None
    if target.is_symlink() or not target.is_dir():raise ValueError('Skill target must be a normal directory')
    receipt=target/RECEIPT
    if not receipt.is_file():raise ValueError('Existing skill has no managed receipt; refusing to overwrite it')
    prior=load(receipt)
    if prior.get('skill')!='mcm-team':raise ValueError('Unexpected installed skill identity')
    actual=dict(project.files_under(target)); actual.pop(RECEIPT,None)
    if set(actual)!=set(prior['files']):raise ValueError('Installed skill file set changed; preserve user changes')
    for rel,expected in prior['files'].items():
        if sha(actual[rel])!=expected:raise ValueError('User-modified installed file: '+rel)
    return prior

def inspect(target, root=ROOT):
    target=Path(target).absolute()
    if target.name!='mcm-team':raise ValueError('Only a directory named mcm-team may be installed')
    files=payload(root); prior=current_state(target)
    expected={rel:sha(p) for rel,p in files.items()}
    return {'action':'update' if prior else 'install','changed':False,'target':str(target),
            'files':expected,'same_payload':bool(prior and prior['files']==expected),
            'prior_receipt_sha256':sha(target/RECEIPT) if prior else None,
            'candidate':True,'native_runtime_verified':False}

def install(target, backup_root, root=ROOT):
    target=Path(target).absolute(); backup_root=Path(backup_root).absolute(); root=Path(root).resolve()
    plan=inspect(target,root)
    if backup_root.resolve().is_relative_to(root) or backup_root.resolve().is_relative_to(target.resolve()):
        raise ValueError('Backups must be outside the source repository and installed skill')
    tag=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    backup=backup_root/tag
    backup.mkdir(parents=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    stage=target.parent/(target.name+'.staging-'+uuid.uuid4().hex)
    stage.mkdir()
    for rel,source in payload(root).items():
        p=stage/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p)
    record={'format_version':1,'skill':'mcm-team','source_root':str(root),'files':plan['files'],
            'backup':str(backup),'native_runtime_verified':False,'candidate':True}
    write(stage/RECEIPT,record)
    # Recheck immediately before moving an existing installation.
    current_state(target)
    if (sha(target/RECEIPT) if target.exists() else None)!=plan['prior_receipt_sha256']:
        raise ValueError('Another installation changed the target during preparation')
    previous=backup/'previous'
    had_previous=target.exists()
    transaction={'format_version':1,'skill':'mcm-team','state':'prepared','target':str(target),
                 'had_previous':had_previous,'installed_files':plan['files'],
                 'installed_receipt_sha256':sha(stage/RECEIPT),'source_root':str(root),
                 'previous_receipt_sha256':plan['prior_receipt_sha256'],'stage':str(stage)}
    # The recovery entry exists before either installation is moved.
    write(backup/'receipt.json',transaction)
    if had_previous:target.rename(previous)
    try:stage.rename(target)
    except Exception:
        if had_previous and not target.exists():previous.rename(target)
        raise
    transaction['state']='installed'
    write(backup/'receipt.json',transaction)
    return {'installed':str(target),'receipt':str(backup/'receipt.json'),'files':len(plan['files']),
            'native_runtime_verified':False,'candidate':True}

def rollback(receipt):
    receipt=Path(receipt).resolve(); txn=load(receipt)
    if txn.get('skill')!='mcm-team' or txn.get('state') not in {'prepared','installed'}:raise ValueError('Not an active mcm-team installation receipt')
    target=Path(txn['target']).absolute(); backup=receipt.parent
    if target.name!='mcm-team' or backup.is_relative_to(target.resolve()):raise ValueError('Unsafe rollback target')
    previous=backup/'previous'
    if txn['state']=='prepared' and not target.exists():
        if txn['had_previous']:
            current_state(previous)
            if sha(previous/RECEIPT)!=txn['previous_receipt_sha256']:raise ValueError('Backup receipt changed')
            previous.rename(target)
        txn['state']='rolled_back';write(receipt,txn)
        return {'rolled_back':True,'restored_previous':txn['had_previous'],'staging_retained':txn.get('stage'),'deleted_files':0}
    if (txn['state']=='prepared' and txn['had_previous'] and not previous.exists()
            and target.exists() and sha(target/RECEIPT)==txn.get('previous_receipt_sha256')):
        current_state(target)
        txn['state']='rolled_back';write(receipt,txn)
        return {'rolled_back':True,'restored_previous':True,'switch_never_completed':True,'deleted_files':0}
    current_state(target)
    if sha(target/RECEIPT)!=txn['installed_receipt_sha256']:raise ValueError('Installation receipt changed; refusing rollback')
    if load(target/RECEIPT)['files']!=txn['installed_files']:raise ValueError('Receipt does not match this installation')
    if txn['had_previous']:
        if not previous.is_dir() or previous.is_symlink():raise ValueError('Previous installation missing')
        current_state(previous)
        if sha(previous/RECEIPT)!=txn.get('previous_receipt_sha256'):raise ValueError('Backup receipt changed')
    archived=backup/'rolled-back-installation'
    if archived.exists():raise ValueError('Rollback archive already exists')
    target.rename(archived)
    try:
        if txn['had_previous']:previous.rename(target)
    except Exception:
        archived.rename(target);raise
    txn['state']='rolled_back';write(receipt,txn)
    return {'rolled_back':True,'restored_previous':txn['had_previous'],'archived':str(archived),
            'deleted_files':0}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    for name in ['preview','install']:
        q=sub.add_parser(name);q.add_argument('--target',type=Path,default=Path.home()/'.codex/skills/mcm-team')
        if name=='install':q.add_argument('--backup-root',type=Path,default=Path.home()/'.codex/skill-backups/mcm-team')
    q=sub.add_parser('rollback');q.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args(argv)
    try:
        result=rollback(a.receipt) if a.command=='rollback' else inspect(a.target) if a.command=='preview' else install(a.target,a.backup_root)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
