#!/usr/bin/env python3
"""Check v0.2.2 source and declared artifact bindings; never certify release."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path,PureWindowsPath
import re
import subprocess
import sys

VERSION='0.2.2'
ROLES={'mcm-captain','mcm-model-lead','mcm-modeler','mcm-evidence','mcm-programmer',
       'mcm-code-lead','mcm-verifier','mcm-paper-lead','mcm-writer','mcm-figure','mcm-typesetter','mcm-reviewer'}
HEX=re.compile(r'^[a-f0-9]{64}$')
IDENTIFIER=re.compile(r'^[a-z0-9][a-z0-9-]*$')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def relative_file(base,relative):
    if not isinstance(relative,str) or not relative.strip():raise ValueError('Missing relative file path')
    path=Path(relative)
    if path.is_absolute() or PureWindowsPath(relative).is_absolute() or '..' in path.parts or '..' in PureWindowsPath(relative).parts:
        raise ValueError('Reference must remain inside its declared root')
    target=(Path(base)/path).resolve()
    if not target.is_relative_to(Path(base).resolve()) or not target.is_file():
        raise ValueError('Referenced file is absent or escapes its declared root: '+relative)
    return target

def fixed_file(base,ref):
    if not isinstance(ref,dict):raise ValueError('Fixed reference must be an object')
    version=ref.get('version')
    if not isinstance(version,int) or isinstance(version,bool) or version<1:raise ValueError('Fixed reference needs a positive artifact version')
    if not isinstance(ref.get('sha256'),str) or not HEX.fullmatch(ref['sha256']):raise ValueError('Fixed reference needs SHA256')
    target=relative_file(base,ref.get('path'))
    if digest(target)!=ref['sha256']:raise ValueError('Changed reference bytes: '+ref['path'])
    return target

def nonempty_strings(value,label):
    if not isinstance(value,list) or not value or any(not isinstance(item,str) or not item.strip() for item in value):
        raise ValueError(label+' must be a nonempty string list')

def valid_digest(value,label):
    if not isinstance(value,str) or not HEX.fullmatch(value):raise ValueError(label+' must be SHA256')

def public_url(value,label):
    if not isinstance(value,str) or not re.match(r'^https?://[^/\s]+(?:/|$)',value):raise ValueError(label+' must be a public source URL')

def validate_case(case,case_id):
    if case.get('format_version')!=1 or case.get('id')!=case_id:raise ValueError('Source case identity mismatch: '+case_id)
    if case.get('problem') not in ('A','B','C'):raise ValueError('Source case is outside MCM A/B/C: '+case_id)
    if not isinstance(case.get('year'),int) or isinstance(case.get('year'),bool):raise ValueError('Source case needs its year: '+case_id)
    if not isinstance(case.get('team'),str) or not case['team'].isdigit():raise ValueError('Source case needs its public team control number: '+case_id)
    valid_digest(case.get('pdf_sha256'),'Source PDF digest')
    count=case.get('physical_page_count')
    if not isinstance(count,int) or isinstance(count,bool) or count<1:raise ValueError('Invalid physical page count: '+case_id)
    public_url(case.get('public_source',{}).get('url'),'Source copy URL')
    award=case.get('award_evidence',{})
    public_url(award.get('url'),'Award evidence URL');valid_digest(award.get('source_sha256'),'Award evidence digest')
    if not isinstance(award.get('physical_page'),int) or isinstance(award['physical_page'],bool) or award['physical_page']<1:
        raise ValueError('Award evidence needs a physical page: '+case_id)
    if award.get('status')!='official_result_row_checked' or award.get('designation')!='Outstanding Winner':
        raise ValueError('Case does not declare the checked official Outstanding result row: '+case_id)
    observed=case.get('observed_pages',{})
    for key in ('rendered_and_viewed','text_context_reviewed'):
        pages=observed.get(key)
        # An image-only paper can be visually read while its text extraction is empty.
        if not isinstance(pages,list) or (key=='rendered_and_viewed' and not pages) or any(not isinstance(page,int) or isinstance(page,bool) or not 1<=page<=count for page in pages):
            raise ValueError('Case has invalid actual observed pages: '+case_id+' / '+key)
    for key in ('answer_chain','good_practices','risks'):nonempty_strings(case.get(key),'Case '+key)
    validation=case.get('validation',{})
    if validation.get('official_award_identity_verified') is not True:raise ValueError('Case award identity is not recorded as checked: '+case_id)
    if not isinstance(validation.get('level'),str) or not validation['level'].strip():raise ValueError('Case needs its declared observation level: '+case_id)

def validate_library(root):
    base=Path(root)/'project-template/references/award-patterns'
    if not (base/'catalog.json').is_file():return {'status':'pending','reason':'Pattern catalog has not been produced; no reference acceptance inferred.'}
    catalog=read_json(base/'catalog.json')
    if catalog.get('format_version')!=1 or not isinstance(catalog.get('patterns'),list) or not catalog['patterns']:
        raise ValueError('Pattern catalog must contain versioned entries')
    ids=set();case_ids=set();categories=set();hashes={};awards={};declared_refs={}
    for row in catalog['patterns']:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not IDENTIFIER.fullmatch(row['id']):raise ValueError('Invalid pattern ID')
        if row['id'] in ids:raise ValueError('Duplicate pattern ID: '+row['id'])
        ids.add(row['id'])
        if not isinstance(row.get('category'),str) or not row['category'].strip():raise ValueError('Pattern needs an argument category')
        categories.add(row['category'])
        nonempty_strings(row.get('roles'),'Pattern roles');nonempty_strings(row.get('keywords'),'Pattern keywords')
        if not set(row['roles'])<=ROLES:raise ValueError('Unknown actual preset role in '+row['id'])
        if row.get('validation_status')!='observed_pattern_not_causal_award_rule':raise ValueError('Patterns must retain their observation-only status')
        target=relative_file(base,row.get('file'))
        if target.suffix!='.md' or not target.read_text(encoding='utf-8').strip():raise ValueError('Pattern must name a nonempty authored Markdown reference')
        hashes[row['file']]=digest(target)
        # Old catalogs pin references through task inputs and omit entry-level
        # metadata. Optional new pins must be complete and match real bytes;
        # a declared version is not a claim of behavioral effectiveness.
        if 'version' in row or 'sha256' in row:
            version=row.get('version')
            if not isinstance(version,int) or isinstance(version,bool) or version<1:
                raise ValueError('Pattern entry needs a positive integer version: '+row['id'])
            valid_digest(row.get('sha256'),'Pattern entry digest')
            if row['sha256']!=hashes[row['file']]:raise ValueError('Pattern entry digest mismatch: '+row['id'])
            declared_refs[row['id']]={'path':row['file'],'version':version,'sha256':row['sha256']}
        nonempty_strings(row.get('source_case_ids'),'Pattern source case IDs')
        for case_id in row['source_case_ids']:
            if not IDENTIFIER.fullmatch(case_id):raise ValueError('Unsafe source case ID')
            case_path=relative_file(base,'cases/'+case_id+'.json');case=read_json(case_path)
            validate_case(case,case_id);case_ids.add(case_id);hashes['cases/'+case_id+'.json']=digest(case_path)
            awards[case_id]=case['award_evidence']['status']
    return {'status':'passed','patterns':len(ids),'source_cases':len(case_ids),'categories':sorted(categories),
            'catalog_sha256':digest(base/'catalog.json'),'reference_sha256':hashes,'declared_award_statuses':awards,
            'versioned_patterns':len(declared_refs),'declared_pattern_refs':declared_refs,
            'limits':['Checked authored reference paths and source-observation metadata only; did not reauthenticate remote copies or reproduce paper results.',
                      'Award identity and an observed pattern do not establish causal award rules or the correctness of source modeling.']}

def validate_gallery(root):
    root=Path(root);base=root/'gallery'
    if not (base/'manifest.json').is_file():return {'status':'pending','reason':'Gallery manifest has not been produced; no mechanical or visual approval inferred.'}
    manifest=read_json(base/'manifest.json')
    if manifest.get('version')!=VERSION or manifest.get('synthetic') is not True or manifest.get('uses_heldout_answers') is not False:
        raise ValueError('Gallery must declare current synthetic, non-heldout examples')
    source=manifest.get('style_source',{})
    source_path=relative_file(root,source.get('path'))
    if source_path!=(root/'bundle/src/figure-style.json').resolve() or digest(source_path)!=source.get('sha256'):
        raise ValueError('Gallery style source differs from the maintained bundle source')
    snapshot=fixed_file(base,manifest.get('style_snapshot'))
    if snapshot.read_bytes()!=source_path.read_bytes():raise ValueError('Gallery style snapshot differs from its source')
    script=fixed_file(base,manifest.get('source_script'))
    if script.read_bytes()!=(root/'tools/figure-gallery.py').read_bytes():raise ValueError('Gallery drawing script snapshot is stale')
    spec=importlib.util.spec_from_file_location('v022_figure_check',root/'project-template/scripts/figure_check.py')
    figure=importlib.util.module_from_spec(spec);spec.loader.exec_module(figure)
    records=manifest.get('figures')
    if not isinstance(records,list) or not records:raise ValueError('Gallery has no figure contracts')
    seen=set();failed=[];declared_mismatch=[]
    for row in records:
        identity=row.get('id')
        if not isinstance(identity,str) or identity in seen:raise ValueError('Invalid or duplicate gallery figure ID')
        seen.add(identity);contract=read_json(fixed_file(base,row.get('contract')))
        if contract.get('figure_id')!=identity or contract.get('synthetic') is not True:raise ValueError('Figure identity/synthetic declaration mismatch')
        result=figure.check_contract(base,contract)
        if result['ok'] is not bool(row.get('passed_mechanical')):declared_mismatch.append(identity)
        if not result['ok']:failed.append({'id':identity,'errors':result['errors']})
    if declared_mismatch:raise ValueError('Gallery declared mechanical outcomes disagree with current checker: '+', '.join(declared_mismatch))
    pages=manifest.get('pages',{});pdf=fixed_file(base,pages.get('pdf'));build=read_json(fixed_file(base,pages.get('build_report')))
    from pypdf import PdfReader
    actual_count=len(PdfReader(pdf).pages)
    if pages.get('page_count')!=actual_count or build.get('page_count')!=actual_count or build.get('pdf_sha256')!=digest(pdf):
        raise ValueError('Gallery PDF page count/hash binding mismatch')
    if build.get('source_sha256')!=digest(base/'latex/page-examples.tex'):raise ValueError('Gallery page source hash is stale')
    page_rows=build.get('pages',[])
    if len(page_rows)!=actual_count or sorted(row.get('page') for row in page_rows)!=list(range(1,actual_count+1)):
        raise ValueError('Gallery page render coverage is incomplete')
    rendered={row['render']:digest(relative_file(base,row.get('render'))) for row in page_rows}
    commands=build.get('commands',[])
    if not commands or any(row.get('exit_code')!=0 for row in commands):raise ValueError('Gallery page compilation is absent or failed')
    if build.get('full_competition_paper') is not False:raise ValueError('Page samples must not be declared a full contest paper')
    preflight=manifest.get('source_preflight',{})
    preflight_path=relative_file(base,'checks/source-preflight.json');preflight_report=read_json(preflight_path)
    preflight_summary=preflight_report.get('summary',{})
    preflight_ok=preflight_summary.get('ready') is True and preflight_summary.get('counts',{}).get('FAIL')==0
    if preflight.get('status')=='passed' and (preflight.get('exit_code')!=0 or not preflight_ok):
        raise ValueError('Declared source preflight pass disagrees with its actual report')
    ready=not failed and preflight.get('status')=='passed' and preflight.get('exit_code')==0 and preflight_ok
    return {'status':'passed' if ready else 'pending','manifest_sha256':digest(base/'manifest.json'),
            'declared_status':manifest.get('status'),'figures':len(records),'page_count':actual_count,
            'failed_mechanical_figures':failed,'source_preflight':preflight,'source_preflight_report_sha256':digest(preflight_path),'render_sha256':rendered,
            'visual_acceptance':'not_assessed','limits':['This rechecks synthetic figure contracts, declared compiler results and current artifact hashes.',
            'It does not open rendered pages, create independent visual approval, authenticate human approval or certify a full contest paper.']}

def run_tests(root,command,kind):
    result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    output=result.stdout+'\n'+result.stderr
    count=None
    if kind=='python':
        found=re.search(r'Ran\s+(\d+)\s+tests?',output);count=int(found.group(1)) if found else None
    elif kind=='node':
        found=re.search(r'(?:#|ℹ)\s+tests\s+(\d+)',output);count=int(found.group(1)) if found else None
    else:
        start=result.stdout.find('{')
        if start>=0:
            try:
                parsed=json.loads(result.stdout[start:]);count=parsed.get('count')
                if parsed.get('passed') is not True:raise ValueError('Installer report did not declare pass')
            except (ValueError,TypeError):count=None
    return {'status':'passed' if result.returncode==0 and isinstance(count,int) and count>0 else 'failed',
            'exit_code':result.returncode,'tests':count,'count_observed_from_actual_output':count is not None,
            'scope':'Software tests; no original rehearsal, model provider or installation activation is certified.'}

def verify(root,include_tests=False):
    root=Path(root).resolve();checks={}
    def record(name,fn):
        try:checks[name]=fn()
        except (OSError,ValueError,AssertionError,TypeError,KeyError,ImportError,subprocess.SubprocessError) as exc:
            message=str(exc).replace(str(root),'<PACKAGE_ROOT>').replace(str(Path.home()),'<USER_HOME>')
            checks[name]={'status':'failed','error':message}
    def source():
        package=read_json(root/'bundle/package.json');manifest=read_json(root/'skill-overlays/manifest.json');routing=read_json(root/'project-template/config/skill-routing.json')
        if package['version']!=VERSION or manifest['overlay_version']!=VERSION or routing['bundle_version']!=VERSION:raise ValueError('Current version declarations disagree')
        if set(routing['roles'])!=ROLES:raise ValueError('Current routing no longer covers exactly the twelve preset IDs')
        if routing.get('reference_library',{}).get('maximum_patterns_per_task')!=2 or routing['reference_library'].get('minimum_patterns_per_task')!=0:
            raise ValueError('Pattern routing no longer permits zero matches and bounds selection to two')
        if (root/'bundle/src/figure-style.json').read_bytes()!=(root/'project-template/config/figure-style.json').read_bytes():raise ValueError('Default project style differs from the maintained source')
        if set(manifest['skills'])!={'nature-figure','nature-writing','nature-polishing','nature-reviewer','nature-statistics'}:raise ValueError('Unexpected specialist Skill set')
        for skill in manifest['skills']:
            text=(root/'skill-overlays'/skill/manifest['reference']).read_text(encoding='utf-8')
            if 'references/award-patterns/catalog.json' not in text or 'path/version/sha256' not in text:raise ValueError('Missing selective fixed-input guidance in '+skill)
        result=subprocess.run(['node','bundle/src/build.mjs','--check','--sync-project-style'],cwd=root,capture_output=True,text=True)
        if result.returncode:raise ValueError('Generated bundle/style is absent or stale')
        provenance=read_json(root/'bundle/provenance.json')
        if provenance.get('bundle_version')!=VERSION or provenance.get('role_count')!=12:raise ValueError('Generated preset provenance is stale')
        return {'status':'passed','version':VERSION,'role_count':12,'skill_count':len(manifest['skills']),'style_default_consistent':True}
    record('current_source',source);record('pattern_library',lambda:validate_library(root));record('gallery_snapshot',lambda:validate_gallery(root))
    if include_tests:
        commands={'overlay_and_design_regressions':([sys.executable,'-m','unittest','discover','-s','tests','-q'],'python'),
                  'project_regressions':([sys.executable,'-m','unittest','discover','-s','project-template/tests','-q'],'python'),
                  'bundle_regressions':(['node','--test',*map(str,sorted((root/'bundle/tests').glob('*.test.mjs')))],'node'),
                  'installer_faults':(['pwsh','-NoProfile','-File','tools/test-install.ps1'],'installer')}
        for name,(command,kind) in commands.items():record(name,lambda command=command,kind=kind:run_tests(root,command,kind))
    status='failed' if any(row['status']=='failed' for row in checks.values()) else 'pending' if any(row['status']=='pending' for row in checks.values()) else 'passed'
    source_files=[]
    for directory in ['bundle','skill-overlays','project-template','tools','tests','gallery']:
        source_files.extend(path for path in (root/directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.md','.json','.mjs','.py','.ps1','.tex','.yml'))
    return {'version':VERSION,'checked_at':datetime.now(timezone.utc).isoformat(),'status':status,
        'scope':'Current source, software regressions when requested, and declared reference/gallery byte bindings.',
        'checks':checks,'software_regressions_requested':include_tests,'release_ready':False,'independent_behavior_acceptance':'not_assessed','independent_visual_acceptance':'not_assessed','deployment':'not_assessed',
        'source_sha256':{path.relative_to(root).as_posix():digest(path) for path in sorted(source_files)},
        'limits':['This verifier does not invoke external model APIs, rerun the native Host, install software or create visual/scientific approval.',
                  'A passed source check does not establish autonomous team quality, source-paper correctness or an O-award probability.',
                  'Pending or failed gallery work remains explicit. Old version audit reports are not current attestations.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tests',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=verify(Path(__file__).resolve().parents[1],args.run_tests)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({key:value for key,value in report.items() if key!='source_sha256'},ensure_ascii=False))
    return 0 if report['status']=='passed' else 2 if report['status']=='pending' else 1

if __name__=='__main__':raise SystemExit(main())
