#!/usr/bin/env python3
"""Apply narrow, reversible MCM references without replacing upstream skills."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, tempfile

START='<!-- mcm-team-adaptation:begin -->'
END='<!-- mcm-team-adaptation:end -->'

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.mcm-overlay-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def inside(root,relative):
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe overlay path')
    target=root/p
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):raise ValueError('Overlay target escapes root')
    return target

def render_hook(original,hook):
    text=original.decode('utf-8-sig')
    block=START+'\n## MCM A/B/C task branch\n\n'+hook+'\n'+END
    if START in text or END in text:
        if text.count(START)!=1 or text.count(END)!=1 or text.index(END)<text.index(START):raise ValueError('Malformed existing MCM hook')
        start=text.index(START);end=text.index(END)+len(END)
        return (text[:start]+block+text[end:]).encode('utf-8')
    # Insert after frontmatter, before every upstream default or routing rule.
    lines=text.splitlines(keepends=True)
    if not lines or lines[0].strip()!='---':raise ValueError('Skill has no YAML frontmatter')
    closing=next((i for i in range(1,len(lines)) if lines[i].strip()=='---'),None)
    if closing is None:raise ValueError('Unclosed skill frontmatter')
    prefix=''.join(lines[:closing+1]);suffix=''.join(lines[closing+1:])
    return (prefix+'\n\n'+block+'\n'+suffix).encode('utf-8')

def plan(source,skills_root):
    source=Path(source).resolve();root=Path(skills_root).resolve()
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    changes=[]
    for name in manifest['skills']:
        if not name.startswith('nature-') or '/' in name or '\\' in name:raise ValueError('Invalid skill name')
        entry=inside(root,name+'/SKILL.md')
        if not entry.is_file():raise ValueError('Required installed skill missing: '+name)
        original=entry.read_bytes()
        ref=source/name/manifest['reference']
        if not ref.is_file() or not ref.read_text(encoding='utf-8').strip():raise ValueError('Missing MCM reference: '+name)
        for relative,content in [(name+'/SKILL.md',render_hook(original,manifest['hook'])),(name+'/'+manifest['reference'],ref.read_bytes())]:
            target=inside(root,relative);before=target.read_bytes() if target.exists() else None
            if before!=content:changes.append({'relative':relative,'before':before,'after':content})
    return manifest,changes

def apply(source,skills_root,backup_root=None,write=False):
    root=Path(skills_root).resolve();manifest,changes=plan(source,root)
    result={'overlay_version':manifest['overlay_version'],'skills':manifest['skills'],'changed_files':len(changes),'applied':False}
    if not write or not changes:return result
    if not backup_root:raise ValueError('Applying requires an explicit local backup root')
    backup=Path(backup_root).resolve()/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if backup.is_relative_to(root) or root.is_relative_to(backup):raise ValueError('Backup and skills root must be disjoint')
    backup.mkdir(parents=True,exist_ok=False)
    records=[]
    for item in changes:
        before=item['before'];record={'path':item['relative'],'existed':before is not None,'before_sha256':sha(before) if before is not None else None,'after_sha256':sha(item['after'])}
        if before is not None:save(inside(backup/'files',item['relative']),before)
        records.append(record)
    receipt={'format_version':1,'overlay_version':manifest['overlay_version'],'skills_root':str(root),'status':'prepared','files':records}
    receipt_path=backup/'receipt.json';save(receipt_path,(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
    written=[]
    try:
        for item in changes:
            target=inside(root,item['relative'])
            now=target.read_bytes() if target.exists() else None
            if now!=item['before']:raise ValueError('Target changed after planning: '+item['relative'])
            save(target,item['after']);written.append(item)
        for item in written:
            if inside(root,item['relative']).read_bytes()!=item['after']:raise ValueError('Target changed during installation: '+item['relative'])
        receipt['status']='applied_verified'
    except Exception:
        recovery_errors=[]
        for item in reversed(written):
            target=inside(root,item['relative'])
            try:
                if not target.is_file() or target.read_bytes()!=item['after']:raise ValueError('Later change retained: '+item['relative'])
                if item['before'] is None:target.unlink()
                else:save(target,item['before'])
            except (OSError,ValueError) as error:recovery_errors.append(str(error))
        receipt['status']='failed_rollback_partial' if recovery_errors else 'failed_rolled_back'
        if recovery_errors:receipt['recovery_errors']=recovery_errors
        save(receipt_path,(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
        raise
    save(receipt_path,(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
    return {**result,'applied':True,'receipt':str(receipt_path),'status':receipt['status']}

def restore(receipt_path,write=False):
    path=Path(receipt_path).resolve();receipt=json.loads(path.read_text(encoding='utf-8'));root=Path(receipt['skills_root']).resolve()
    if receipt['status'] not in ('applied_verified','restored_verified'):raise ValueError('Receipt is not an applied overlay')
    if receipt['status']=='restored_verified':return {'status':'restored_verified','changed':False}
    # Verify the whole window before touching any current file.
    for record in receipt['files']:
        current=inside(root,record['path'])
        if not current.is_file() or sha(current.read_bytes())!=record['after_sha256']:raise ValueError('Refuse to overwrite later skill changes: '+record['path'])
        if record['existed']:
            saved=inside(path.parent/'files',record['path'])
            if not saved.is_file() or sha(saved.read_bytes())!=record['before_sha256']:raise ValueError('Backup integrity failure')
    if not write:return {'status':'restore_preflight_passed','changed':False}
    written=[]
    try:
        for record in receipt['files']:
            target=inside(root,record['path']);after=target.read_bytes()
            if sha(after)!=record['after_sha256']:raise ValueError('Target changed during restore: '+record['path'])
            before=inside(path.parent/'files',record['path']).read_bytes() if record['existed'] else None
            if before is not None:save(target,before)
            else:target.unlink()
            written.append((record,before,after))
        for record,before,after in written:
            target=inside(root,record['path'])
            current=target.read_bytes() if target.exists() else None
            if current!=before:raise ValueError('Restored bytes changed before verification: '+record['path'])
    except Exception:
        recovery_errors=[]
        for record,before,after in reversed(written):
            target=inside(root,record['path'])
            try:
                current=target.read_bytes() if target.exists() else None
                if current!=before:raise ValueError('Later change retained: '+record['path'])
                save(target,after)
            except (OSError,ValueError) as error:recovery_errors.append(str(error))
        receipt['status']='restore_failed_recovery_partial' if recovery_errors else 'applied_verified'
        receipt['restore_outcome']='failed_current_overlay_recovered' if not recovery_errors else 'failed_recovery_partial'
        if recovery_errors:receipt['recovery_errors']=recovery_errors
        save(path,(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
        raise
    receipt['status']='restored_verified';receipt['restore_outcome']='restored_verified'
    receipt.pop('recovery_errors',None)
    save(path,(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode())
    return {'status':'restored_verified','changed':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'skill-overlays')
    parser.add_argument('--skills-root',type=Path);parser.add_argument('--backup-root',type=Path)
    parser.add_argument('--restore',type=Path);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        if args.restore:result=restore(args.restore,args.apply)
        elif args.skills_root:result=apply(args.source,args.skills_root,args.backup_root,args.apply)
        else:parser.error('Choose --skills-root or --restore')
        print(json.dumps(result,ensure_ascii=False));return 0
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'status':'failed','error':str(error)},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())
