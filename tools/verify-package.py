"""Verify the portable package without installing into the running DSH profile."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_ROLES={'mcm-captain','mcm-model-lead','mcm-modeler','mcm-evidence','mcm-programmer','mcm-code-lead',
                'mcm-verifier','mcm-paper-lead','mcm-writer','mcm-figure','mcm-typesetter','mcm-reviewer'}
REQUIRED_SOURCE_FILES={f'project-template/scripts/{name}.py' for name in ('mcm','paper','figure_check','figure_demo')} | {
    'project-template/config/runtime.json','project-template/config/skill-routing.json',
    'project-template/config/figure-style.json','project-template/paper/main.tex','project-template/paper/paper-plan.json',
    'tools/update-dsh.ps1','tools/restore-dsh.ps1','tools/dsh-install-common.ps1','tools/test-install.ps1'}
REQUIRED_BUNDLE_FILES={'package.json','cordis.patch.yml','provenance.json','src/presets.mjs','src/build.mjs',
    'src/native-plan.mjs','src/skill-routing.mjs','src/archive-core.mjs','src/archive-tool.mjs','src/archive-plugin.mjs',
    'src/runtime-guard-core.mjs','src/runtime-guard-plugin.mjs'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inside(root,relative):
    root=Path(root).resolve();p=Path(relative);target=(root/p).resolve()
    if p.is_absolute() or '..' in p.parts or not target.is_relative_to(root):
        raise ValueError('Evidence path escapes its root: '+str(relative))
    return target

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def run(command,cwd=None):
    result=subprocess.run(command,cwd=cwd,text=True,encoding='utf-8',errors='replace',capture_output=True)
    text=result.stdout+'\n'+result.stderr
    return {'passed':result.returncode==0,'exit_code':result.returncode,'output':text.strip()}

def verify_native_guard():
    """Require current-source evidence from the real nested PTC execution path."""
    path=ROOT/'audit/guard-native-runtime.json'
    errors=[]
    if not path.is_file():return {'passed':False,'errors':['Missing real PTC dispatch-guard report']}
    try:
        report=read_json(path)
        if report.get('status')!='passed':errors.append('Dispatch guard did not pass')
        tests=report.get('checks',[])
        if len(tests)<6 or any(c.get('passed') is not True for c in tests):errors.append('Incomplete or failed real guard checks')
        fingerprints=report.get('bundle_file_sha256',{})
        missing=REQUIRED_BUNDLE_FILES-set(fingerprints)
        errors.extend('Missing guarded source fingerprint: '+x for x in sorted(missing))
        for relative,digest in fingerprints.items():
            p=inside(ROOT/'bundle',relative)
            if not p.is_file() or sha(p)!=digest:errors.append('Guard report has stale source: '+relative)
        for key,relative in [('fixture_sha256','audit/guard-native-fixture.mjs'),('launcher_sha256','audit/run-native-smoke.mjs')]:
            if report.get(key)!=sha(ROOT/relative):errors.append('Guard report has stale '+key)
        native=read_json(ROOT/'audit/native-runtime-smoke.json')
        if native.get('guard_report',{}).get('sha256')!=sha(path):errors.append('Main native report does not bind the current guard run')
        return {'passed':not errors,'errors':errors,'checks':len(tests),'runtime':report.get('runtime_version'),
                'executed_at':report.get('executed_at'),'replayed_now':False,
                'scope':'real agent turn → run_code → nested PTC → tool pre-execute/monotonic guard; scripted LLM'}
    except (OSError,ValueError,TypeError,KeyError) as exc:
        return {'passed':False,'errors':[str(exc)]}

def verify_release_evidence():
    """Read actual current files; never manufacture visual or human approval."""
    errors=[];details={};visual_expected=set()
    path=ROOT/'audit/release-evidence.json'
    if not path.is_file():return {'passed':False,'errors':['Missing current audit/release-evidence.json']}
    try:
        evidence=read_json(path)
        if evidence.get('bundle_version')!='0.2.0':errors.append('Release evidence is not v0.2.0')
        sources=evidence.get('source_sha256',{})
        missing=REQUIRED_SOURCE_FILES-set(sources)
        errors.extend('Missing release source fingerprint: '+x for x in sorted(missing))
        for relative,digest in sources.items():
            p=inside(ROOT,relative)
            if not p.is_file() or sha(p)!=digest:errors.append('Changed/missing release source: '+relative)
        native=ROOT/'audit/native-runtime-smoke.json'
        if not native.is_file() or evidence.get('native_report_sha256')!=sha(native):
            errors.append('Release evidence does not bind the current native-runtime report')
        artifacts=evidence.get('artifacts',[])
        artifact_paths={ref.get('path') for ref in artifacts}
        expected_artifacts=set()
        if not artifacts:errors.append('Release evidence has no output artifacts')
        for ref in artifacts:
            p=inside(ROOT,ref.get('path',''))
            if not p.is_file() or sha(p)!=ref.get('sha256'):errors.append('Changed/missing delivery artifact: '+str(ref.get('path')))
            if not ref.get('purpose'):errors.append('Delivery artifact lacks purpose: '+str(ref.get('path')))
        contracts=evidence.get('figure_contracts',[])
        if len(contracts)<4:errors.append('Rehearsal requires method, comparison, sensitivity and uncertainty figure contracts')
        figures=[];names=set()
        for ref in contracts:
            project=inside(ROOT,ref.get('project_root',''))
            for name in ('mcm','paper','figure_check','figure_demo'):
                local=project/'scripts'/f'{name}.py'
                current=ROOT/'project-template/scripts'/f'{name}.py'
                if not local.is_file() or sha(local)!=sha(current):
                    errors.append('Rehearsal script differs from the current project template: '+name)
            contract_path=inside(project,ref.get('path',''))
            if not contract_path.is_file() or sha(contract_path)!=ref.get('sha256'):
                errors.append('Changed/missing rehearsal figure contract: '+str(ref.get('path')));continue
            contract=read_json(contract_path);names.add(contract_path.name.split('.')[0])
            for out in contract.get('outputs',[]):
                expected_artifacts.add(inside(project,out['path']).relative_to(ROOT).as_posix())
                if str(out.get('path','')).lower().endswith('.png'):
                    visual_expected.add(inside(project,out['path']).relative_to(ROOT).as_posix())
            result=run([sys.executable,str(ROOT/'project-template/scripts/figure_check.py'),'--root',str(project),str(ref['path'])])
            figures.append({'contract':str(ref['path']),**result})
            if not result['passed']:errors.append('Current rehearsal figure contract failed: '+str(ref['path']))
        if not {'method','comparison','sensitivity','uncertainty'}.issubset(names):
            errors.append('Four required rehearsal figure types are not represented')
        details['figure_checks']=figures
        paper=evidence.get('paper_build',{})
        project=inside(ROOT,paper.get('project_root',''))
        pdf=inside(project,paper.get('pdf',''))
        manifest=pdf.with_suffix('.build.json')
        if not pdf.is_file() or sha(pdf)!=paper.get('pdf_sha256'):errors.append('Changed/missing rehearsal PDF')
        if not manifest.is_file() or sha(manifest)!=paper.get('manifest_sha256'):errors.append('Changed/missing rehearsal build manifest')
        if pdf.is_file() and manifest.is_file():
            from pypdf import PdfReader
            build=read_json(manifest)
            actual_pages=len(PdfReader(pdf).pages)
            if not build.get('total_pdf_pages') or build.get('total_pdf_pages')!=actual_pages:
                errors.append('Rehearsal manifest does not record the actual PDF page count')
            expected_artifacts.update((pdf.relative_to(ROOT).as_posix(),manifest.relative_to(ROOT).as_posix()))
            for relative in build.get('rendered_pages',[]):
                visual_expected.add(inside(project,relative).relative_to(ROOT).as_posix())
                p=inside(project,relative)
                if not p.is_file() or sha(p)!=build.get('rendered_page_sha256',{}).get(relative):
                    errors.append('Changed/missing rehearsal page render: '+relative)
            if len(build.get('rendered_pages',[]))!=build.get('total_pdf_pages'):
                errors.append('Rehearsal renders do not cover all PDF pages')
            result=run([sys.executable,str(ROOT/'project-template/scripts/paper.py'),'--root',str(project),'check',str(pdf)])
            details['paper_check']=result
            if not result['passed']:errors.append('Current rehearsal PDF/source mechanical check failed')
        for name in ('01-role-architecture','02-runtime-communication','03-workflow-review'):
            visual_expected.add(f'diagrams/{name}.png')
            expected_artifacts.update(f'diagrams/{name}.{ext}' for ext in ('svg','png','json'))
        errors.extend('Release artifact index omits current deliverable: '+x for x in sorted(expected_artifacts-artifact_paths))
        review_ref=evidence.get('visual_review_ref',{})
        review_path=inside(ROOT,review_ref.get('path',''))
        if not review_path.is_file() or sha(review_path)!=review_ref.get('sha256'):
            errors.append('Missing/changed current visual review record')
        else:
            review=read_json(review_path)
            if review.get('bundle_version')!='0.2.0' or review.get('passed') is not True or not review.get('reviewer') or not review.get('checked_at'):
                errors.append('Visual record must identify v0.2.0, actual reviewer/time and passed status')
            images={ref.get('path'):ref for ref in review.get('images',[])}
            errors.extend('Visual review omitted current output: '+x for x in sorted(visual_expected-set(images)))
            for relative,ref in images.items():
                p=inside(ROOT,relative)
                if not p.is_file() or sha(p)!=ref.get('sha256') or not ref.get('checked'):
                    errors.append('Visual review reference changed or has no checks: '+str(relative))
                if not ref.get('checked_by') or not ref.get('author_agent_ids'):
                    errors.append('Visual output lacks actual reviewer or author identities: '+str(relative))
                elif ref['checked_by'] in ref['author_agent_ids']:
                    errors.append('Visual output cannot be independently accepted by its author: '+str(relative))
        details.update(source_files=len(sources),artifacts=len(artifacts),visual_outputs_required=len(visual_expected))
    except (OSError,ValueError,TypeError,KeyError,ImportError) as exc:errors.append(str(exc))
    return {'passed':not errors,'errors':errors,**details,'note':'Recorded AI visual review is checked for current-file binding; this tool does not see images or create a human approval.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    checks={}
    python=run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'project-template/tests'),'-q'])
    match=re.search(r'Ran (\d+) tests?',python['output']);python['tests']=int(match.group(1)) if match else None
    checks['python_regressions']=python
    node=shutil.which('node')
    if node:
        checks['preset_build']=run([node,str(ROOT/'bundle/src/build.mjs'),'--check'])
        tests=sorted((ROOT/'bundle/tests').glob('*.test.mjs'))
        result=run([node,'--test',*[str(p) for p in tests]])
        match=re.search(r'(?:ℹ|#) tests (\d+)',result['output']);result['tests']=int(match.group(1)) if match else None
        checks['bundle_regressions']=result
        inspection=run([node,'--input-type=module','-e',
            "import {ROLES} from './src/presets.mjs'; import {SKILL_ROUTING,OPTIONAL_ROLES} from './src/skill-routing.mjs'; import {createHash} from 'node:crypto'; console.log(JSON.stringify({roles:ROLES.map(x=>x.id),routing:SKILL_ROUTING,optional:OPTIONAL_ROLES,routing_sha256:createHash('sha256').update(JSON.stringify(SKILL_ROUTING)).digest('hex')}));"],cwd=ROOT/'bundle')
        errors=[]
        try:
            exported=json.loads(inspection['output']) if inspection['passed'] else {}
            package=read_json(ROOT/'bundle/package.json');provenance=read_json(ROOT/'bundle/provenance.json')
            project_routes=read_json(ROOT/'project-template/config/skill-routing.json')
            runtime=read_json(ROOT/'project-template/config/runtime.json')
            if package.get('name')!='dsh-mcm-team' or package.get('version')!='0.2.0':errors.append('Wrong package identity/version')
            if set(exported.get('roles',[]))!=EXPECTED_ROLES or len(exported.get('roles',[]))!=12:errors.append('Preset IDs differ from the compatible twelve-role contract')
            if provenance.get('bundle_version')!='0.2.0' or provenance.get('role_count')!=12:errors.append('Wrong provenance version/role count')
            if exported.get('optional',{}).get('mcm-code-lead',{}).get('enabled_by_default') is not False:errors.append('Optional code lead is not off by default')
            if runtime.get('code_lead_enabled_by_default') is not False:errors.append('Project enables optional code lead by default')
            if exported.get('routing')!=project_routes:errors.append('Project skill routing differs from embedded preset routing')
            if provenance.get('skill_routing_sha256')!=exported.get('routing_sha256'):errors.append('Embedded routing digest differs from provenance')
            if provenance.get('routing_source_sha256')!=sha(ROOT/'bundle/src/skill-routing.mjs'):errors.append('Routing source digest differs from provenance')
            if project_routes.get('defaults',{}).get('excluded_orchestrators_apply_to_indirect_routes') is not True:errors.append('Indirect orchestrator routing exclusion is missing')
        except (OSError,ValueError,TypeError,KeyError) as exc:errors.append(str(exc))
        if not inspection['passed']:errors.append('Cannot import actual bundle definitions: '+inspection['output'])
        checks['v020_role_and_skill_contract']={'passed':not errors,'errors':errors}
    else:checks['node']={'passed':False,'reason':'Node.js not available'}
    native_path=ROOT/'audit/native-runtime-smoke.json'
    if native_path.exists():
        native=json.loads(native_path.read_text(encoding='utf-8-sig'))
        drift=[p for p,h in native.get('bundle_file_sha256',{}).items() if not (ROOT/'bundle'/p).is_file() or sha(ROOT/'bundle'/p)!=h]
        # build.mjs fingerprints the normalized text that is actually embedded,
        # whereas bundle_file_sha256 records exact bytes for generated/runtime files.
        drift += [p for p,h in native.get('prompt_sha256',{}).items() if not (ROOT/'bundle'/p).is_file()
                  or hashlib.sha256((ROOT/'bundle'/p).read_text(encoding='utf-8').strip().encode()).hexdigest()!=h]
        missing=REQUIRED_BUNDLE_FILES-set(native.get('bundle_file_sha256',{}))
        expected_prompts={'prompts/shared.md'}|{f'prompts/{role}.md' for role in EXPECTED_ROLES}
        missing_prompts=expected_prompts-set(native.get('prompt_sha256',{}))
        registry_covered=any(set(c.get('presets',[]))==EXPECTED_ROLES for c in native.get('checks',[]))
        checks_pass=bool(native.get('checks')) and all(c.get('passed') is True for c in native.get('checks',[]))
        checks['native_runtime_record']={'passed':native.get('status')=='passed' and checks_pass and not drift and not missing and not missing_prompts and registry_covered,
            'checks':len(native.get('checks',[])),'runtime':native.get('runtime_version'),'source_drift':drift,
            'executed_at':native.get('executed_at'),'replayed_now':False,
            'missing_source_fingerprints':sorted(missing),'missing_prompt_fingerprints':sorted(missing_prompts),'all_twelve_registry_roles_covered':registry_covered,
            'prompt_digest_policy':'CRLF normalized to LF; surrounding whitespace trimmed as in build.mjs',
            'live_desktop_installation_checked':False,'installed_into_live_desktop_by_this_tool':False,
            'llm_output':'scripted fixture; no external model calls'}
    else:checks['native_runtime_record']={'passed':False,'reason':'No actual-runtime record'}
    checks['native_dispatch_guard_record']=verify_native_guard()
    templates=[]
    for p in sorted((ROOT/'project-template/templates').glob('*.json')):
        value=json.loads(p.read_text(encoding='utf-8'));templates.append(p.name)
        if value.get('_template_only') is not True:raise ValueError('Template lacks _template_only: '+p.name)
    card=json.loads((ROOT/'project-template/templates/scorecard.json').read_text(encoding='utf-8'))
    checks['templates']={'passed':sum(d['maximum'] for d in card['dimensions'])==100,
        'count':len(templates),'internal_score_total':sum(d['maximum'] for d in card['dimensions'])}
    integrity={'passed':True,'records':{}}
    for name in ('tasks','artifacts','issues','decisions'):
        registry=json.loads((ROOT/'project-template/.mcm'/f'{name}.json').read_text(encoding='utf-8'))
        integrity['records'][name]=len(registry['records'])
        if registry['records']:integrity['passed']=False
    gates=json.loads((ROOT/'project-template/config/gates.json').read_text(encoding='utf-8'))['records']
    integrity['human_gates_pending']=all(g['status']=='pending' for g in gates)
    integrity['passed'] &= integrity['human_gates_pending']
    checks['clean_template']=integrity
    pwsh=shutil.which('pwsh')
    if pwsh:
        parse=run([pwsh,'-NoProfile','-Command',
            "$bad=@(); Get-ChildItem -LiteralPath 'tools' -Filter '*.ps1' | ForEach-Object {$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$tokens,[ref]$errors) | Out-Null;$bad+=@($errors)}; if($bad.Count){$bad | Format-List;exit 1}; 'PowerShell scripts parsed successfully'"],cwd=ROOT)
        checks['installer_script_syntax']=parse
        fixture=run([pwsh,'-NoProfile','-File',str(ROOT/'tools/test-install.ps1')])
        try:
            value=json.loads(fixture['output']);fixture['tests']=value.get('count')
            fixture['passed'] &= value.get('passed') is True and value.get('actual_user_plugin_modified') is False and value.get('official_cli_mocked') is True
        except ValueError:fixture['passed']=False
        checks['isolated_installer_fault_injection']=fixture
    else:checks['isolated_installer_fault_injection']={'passed':False,'reason':'PowerShell 7 (pwsh) required for installer verification'}
    checks['current_delivery_evidence']=verify_release_evidence()
    report={'format_version':1,'checked_at':datetime.now(timezone.utc).isoformat(),'python':sys.version,
        'python_executable':sys.executable,'passed':all(x['passed'] for x in checks.values()),'checks':checks,
        'limitations':['Native record uses the real DSH runtime with a scripted LLM; it does not test scientific quality.',
          'No package installation was made into the user running desktop profile.',
          'Human gates remain pending. Example results are synthetic and cannot be submitted as a contest paper.']}
    if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
