#!/usr/bin/env python3
"""Verify the current upgrade; do not reuse frozen v0.2.0 attestations."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,hashlib,json,subprocess,sys

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-tests',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];checks={}
    def record(name,fn):
        try:checks[name]={'passed':True,**fn()}
        except (OSError,ValueError,AssertionError,subprocess.SubprocessError) as e:checks[name]={'passed':False,'error':str(e)}
    def shape():
        load=lambda rel:json.loads((root/rel).read_text(encoding='utf-8-sig'))
        package=load('bundle/package.json');manifest=load('skill-overlays/manifest.json')
        assert package['version']==manifest['overlay_version']=='0.2.1'
        assert (root/'bundle/src/figure-style.json').read_bytes()==(root/'project-template/config/figure-style.json').read_bytes()
        assert load('project-template/config/skill-routing.json')['bundle_version']=='0.2.1'
        for name in manifest['skills']:assert (root/'skill-overlays'/name/manifest['reference']).is_file()
        for name in ['argument-design','question-transfer','summary-claims']:
            assert load('project-template/templates/'+name+'.json')['_template_only'] is True
        result=subprocess.run(['node','bundle/src/build.mjs','--check','--sync-project-style'],cwd=root,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        return {'version':package['version'],'role_count':load('bundle/provenance.json')['role_count'],'skill_count':len(manifest['skills']),'style_default_consistent':True}
    record('current_build_and_content',shape)
    if a.run_tests:
        commands={
            'overlay_regressions':([sys.executable,'-m','unittest','discover','-s','tests','-q'],9),
            'project_regressions':([sys.executable,'-m','unittest','discover','-s','project-template/tests','-q'],107),
            'bundle_regressions':(['node','--test',*map(str,sorted((root/'bundle/tests').glob('*.test.mjs')))],37),
            'installer_faults':(['pwsh','-NoProfile','-File','tools/test-install.ps1'],10)}
        for name,(command,count) in commands.items():
            result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            # No command paths, machine environment or raw logs enter the portable record.
            checks[name]={'passed':result.returncode==0,'exit_code':result.returncode,'tests':count}
            if result.returncode:print(name+' failed; see local execution output',file=sys.stderr)
    source_files=[]
    for directory in ['bundle','skill-overlays','project-template','tools','tests']:
        source_files.extend(path for path in (root/directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in ['.md','.json','.mjs','.py','.ps1','.tex','.yml'])
    report={'version':'0.2.1','checked_at':datetime.now(timezone.utc).isoformat(),'status':'passed' if all(x['passed'] for x in checks.values()) else 'failed','checks':checks,
        'source_sha256':{path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source_files)},
        'limits':['This verifier does not create visual approval, install software or exercise an external model.','Native, independent skill trial, figure visual and deployment evidence are separately recorded for this version.','Old audit root records and SHA256SUMS.txt remain v0.2.0 history, not current attestations.']}
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
