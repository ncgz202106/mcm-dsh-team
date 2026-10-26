#!/usr/bin/env python3
"""Build an isolated XeLaTeX copy, audit the PDF and render pages for review."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def sources(project):
    result = {}
    for folder in ('paper', 'figures'):
        base = project / folder
        if base.exists():
            for p in sorted(base.rglob('*')):
                if p.is_file() and p.suffix.lower() in {'.tex','.bib','.sty','.cls','.bst','.pdf','.png','.jpg','.jpeg','.svg','.json'}:
                    result[p.relative_to(project).as_posix()] = digest(p)
    return result

def tex_environment():
    env = os.environ.copy()
    if os.name == 'nt' and not shutil.which('perl'):
        candidates = [Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/usr/bin',
                      Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Git/usr/bin']
        git = shutil.which('git')
        if git:
            candidates.append(Path(git).resolve().parents[1]/'usr/bin')
        for p in candidates:
            if (p/'perl.exe').exists():
                env['PATH'] = str(p)+os.pathsep+env.get('PATH','')
                break
    env['MIKTEX_ENABLE_INSTALLER'] = '0'
    env['SOURCE_DATE_EPOCH'] = '1792800000'
    return env

def project_rules(project):
    runtime=Path(project)/'config/runtime.json'
    config=json.loads(runtime.read_text(encoding='utf-8')) if runtime.exists() else {}
    relative=Path(config.get('competition_file','config/contest-mcm-2027.json'))
    path=(Path(project)/relative).resolve()
    if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(Path(project).resolve()):
        raise ValueError('Competition rule file must stay within the project')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

def main_report_pages(aux, fallback):
    if not Path(aux).exists():
        raise ValueError('Missing aux file: cannot establish the main report / AI report boundary')
    match = re.search(r'\\newlabel\{main-report-end\}\{\{[^}]*\}\{(\d+)\}', Path(aux).read_text(encoding='utf-8',errors='replace'))
    if not match:
        raise ValueError('Missing main-report-end label: AI pages cannot be excluded by guessing')
    page = int(match.group(1))
    if not 1 <= page <= fallback:
        raise ValueError('Invalid main-report-end page number')
    return page

def audit_pdf(pdf, main_pages=None, release=False, rules=None):
    from pypdf import PdfReader
    pdf = Path(pdf)
    reader = PdfReader(pdf)
    errors, review = [], []
    text = ''
    rules=rules or {}
    max_bytes=rules.get('submission_size_exclusive_max_bytes',25_000_000)
    max_pages=rules.get('main_report_max_pages',25)
    if pdf.stat().st_size >= max_bytes:
        errors.append(f'PDF must be smaller than {max_bytes} bytes')
    if main_pages is None:
        main_pages = len(reader.pages)
        review.append('No confirmed main/AI boundary supplied; all pages counted conservatively')
    if main_pages > max_pages:
        errors.append(f'Main report has {main_pages} pages; maximum is {max_pages}')
    for number, page in enumerate(reader.pages, 1):
        crop = page.cropbox
        xmin,ymin,xmax,ymax = map(float,(crop.left,crop.bottom,crop.right,crop.top))
        outside = []
        def visit(chunk,cm,tm,font,size):
            if not chunk.strip():
                return
            # Text origin transformed into page coordinates. Exact glyph clipping
            # and source-image clipping still require the rendered-page review.
            x = tm[4]*cm[0] + tm[5]*cm[2] + cm[4]
            y = tm[4]*cm[1] + tm[5]*cm[3] + cm[5]
            if x < xmin-3 or x > xmax+3 or y < ymin-5 or y > ymax+3:
                outside.append(chunk.strip()[:60])
        page_text = page.extract_text(visitor_text=visit) or ''
        text += page_text+'\n'
        if outside:
            errors.append(f'Page {number}: text origin outside CropBox: {outside[0]}')
        if not page_text.strip() and not page.get('/Resources',{}).get('/XObject'):
            errors.append(f'Page {number}: apparently blank page')
        if number <= main_pages and not re.search(r'Team\s+\d+',page_text):
            errors.append(f'Page {number}: no extractable team header')
    if 'Summary Sheet' not in (reader.pages[0].extract_text() or ''):
        errors.append('First page does not contain Summary Sheet')
    if release:
        for token in ('DRAFT','0000000','Demonstration only','Synthetic Workflow Rehearsal','DRAFT INSTRUCTION','RESULT PENDING','no_run_yet'):
            if token in text:
                errors.append(f'Template/demo marker remains: {token}')
        if re.search(r'\b(?:TODO|TBD|REPLACE_[A-Z_]+)\b|RESULT\s+PENDING|no[_\s]run[_\s]yet',text,re.I):
            errors.append('Unfinished content marker remains in PDF')
        if re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text):
            errors.append('Email-like identifying text requires anonymity review')
    review.extend(['Inspect every rendered page for clipping, overlap and readable figures',
                   'Check anonymity in text, acknowledgments, images and PDF metadata',
                   'Verify citations against sources and AI disclosure against visible records'])
    return {'mechanical_passed':not errors,'main_report_pages':main_pages,
            'total_pdf_pages':len(reader.pages),'pdf_bytes':pdf.stat().st_size,
            'errors':errors,'requires_visual_review':True,'review_items':review,
            'human_release_approved':False}

def result_snapshot(project):
    """Capture the author's declared result inputs without inventing approval."""
    path=Path(project)/'paper/paper-plan.json'
    plan=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return {'result_generation':plan.get('result_generation'),
            'consumed_result_refs':plan.get('consumed_result_refs',[]),
            'verification_refs':plan.get('verification_refs',[]),
            'figure_refs':plan.get('figures',[]),
            'paper_author_agent_ids':plan.get('authors',[])}


def check_paper_figures(project,manifest):
    """Audit only the figure contracts declared by this paper's fixed plan."""
    project=Path(project).resolve();errors=[];checked=[]
    checker=project/'scripts/figure_check.py'
    refs=manifest.get('figure_refs',[])
    if refs!=result_snapshot(project).get('figure_refs',[]):
        errors.append('Paper figure inputs changed after the recorded build')
    if not refs:
        return {'ok':not errors,'errors':errors,'checked':checked,
                'note':'No figure contracts declared; the content reviewer must check question/evidence coverage.'}
    if not checker.is_file():return {'ok':False,'errors':['Missing figure contract checker'],'checked':[]}
    spec=importlib.util.spec_from_file_location('paper_figure_guard',checker)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for ref in refs:
        contract_ref=ref.get('contract_ref',{}) if isinstance(ref,dict) else {}
        try:
            path=module.inside(project,contract_ref.get('path',''))
            if not path.is_file() or digest(path)!=contract_ref.get('sha256'):
                errors.append('Paper figure contract missing or changed: '+str(contract_ref.get('path')));continue
            contract=json.loads(path.read_text(encoding='utf-8'))
            if ref.get('figure_id')!=contract.get('figure_id'):
                errors.append('Paper figure ID differs from its fixed contract')
            result=module.check_contract(project,contract,release=True)
            checked.append({'figure_id':contract.get('figure_id'),**result})
            errors.extend(result['errors'])
        except (OSError,ValueError,TypeError) as exc:errors.append(str(exc))
    return {'ok':not errors,'errors':errors,'checked':checked}

def check_paper_results(project,manifest):
    """Match the build's result generation to real files, registry and valid H2."""
    project=Path(project).resolve();errors=[]
    checker=project/'scripts/mcm.py'
    if not checker.exists():return {'ok':False,'errors':['Missing registry checker for H2_RESULTS']}
    spec=importlib.util.spec_from_file_location('paper_results_registry',checker)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    h2=module.check_gate(project,'H2_RESULTS')
    errors.extend(h2.get('errors',[]))
    if not h2.get('ok') and not h2.get('errors'):errors.append('H2_RESULTS is not valid')
    plan=project/'paper/paper-plan.json'
    plan_data=json.loads(plan.read_text(encoding='utf-8')) if plan.exists() else {}
    if plan_data.get('_template_only'):errors.append('Paper plan is still a template')
    if result_snapshot(project)!={k:manifest.get(k,[] if k!='result_generation' else None) for k in result_snapshot(project)}:
        errors.append('Paper result inputs changed after the recorded build')
    generation=manifest.get('result_generation')
    if not generation:errors.append('Paper has no fixed result_generation')
    refs=manifest.get('consumed_result_refs',[]);verification=manifest.get('verification_refs',[])
    if not refs:errors.append('Paper has no consumed result references')
    if not verification:errors.append('Paper has no same-generation verification references')
    gates=module.read_json(project/'config/gates.json').get('records',[])
    gate=next((g for g in gates if g.get('gate_id')=='H2_RESULTS'),{})
    approved={(x.get('artifact_id'),x.get('version'),x.get('sha256')) for x in gate.get('scope_refs',[])}
    artifacts={x.get('artifact_id'):x for x in module.records(project,'artifacts')}
    for ref in refs+verification:
        identifier=ref.get('artifact_id');artifact=artifacts.get(identifier,{})
        triple=(identifier,ref.get('version'),ref.get('sha256'))
        if triple not in approved:errors.append('Paper input is outside effective H2 scope: '+str(identifier))
        if not artifact or any(ref.get(k)!=artifact.get(k) for k in ('version','sha256','path')):
            errors.append('Paper input differs from current artifact record: '+str(identifier))
            continue
        if ref.get('generation')!=generation:errors.append('Paper input generation differs: '+str(identifier))
        if artifact.get('generation') is not None and artifact.get('generation')!=generation:
            errors.append('Registry generation differs: '+str(identifier))
        try:
            path=module.resolve_inside(project,ref.get('path',''))
            if not path.is_file() or digest(path)!=ref.get('sha256'):errors.append('Paper input bytes changed: '+str(identifier))
        except (OSError,ValueError) as exc:errors.append(str(exc))
    return {'ok':not errors,'errors':errors,'gate_id':'H2_RESULTS','result_generation':generation}

def build(project, demo=False, render=True):
    project = Path(project).resolve()
    stem = 'demo' if demo else 'main'
    env = tex_environment()
    latexmk = shutil.which('latexmk',path=env.get('PATH'))
    if not latexmk:
        raise ValueError('latexmk is required; install it with the chosen TeX distribution')
    probe = subprocess.run([latexmk,'-version'],env=env,text=True,capture_output=True,timeout=20)
    if probe.returncode:
        raise ValueError('latexmk failed its runtime check: '+(probe.stdout+probe.stderr)[-1500:])
    before = sources(project)
    consumed = result_snapshot(project)
    output = project/'build/paper'
    if not output.resolve().is_relative_to(project):
        raise ValueError('Build output escapes project through a symlink/reparse point')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mcm-paper-') as temp:
        scratch = Path(temp)
        shutil.copytree(project/'paper',scratch/'paper')
        if (project/'figures').exists():
            shutil.copytree(project/'figures',scratch/'figures')
        working = scratch/'paper'
        (working/'out').mkdir()
        # Native MiKTeX must receive Windows paths even when latexmk is run by
        # Git's MSYS Perl, whose getcwd() can return /tmp/... aliases. Also make
        # each project .bib directly visible from BibTeX's out/ working folder.
        env['BIBINPUTS'] = working.as_posix()+os.pathsep+env.get('BIBINPUTS','')
        env['BSTINPUTS'] = working.as_posix()+os.pathsep+env.get('BSTINPUTS','')
        for bibliography in working.rglob('*.bib'):
            if 'out' not in bibliography.relative_to(working).parts:
                destination = working/'out'/bibliography.relative_to(working)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(bibliography,destination)
        command = [latexmk,'-xelatex','-bibtex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',
                   '-file-line-error','-outdir=out',f'{stem}.tex']
        compiled = subprocess.run(command,cwd=working,env=env,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=240)
        (output/f'{stem}.console.log').write_text(compiled.stdout+'\n'+compiled.stderr,encoding='utf-8')
        logpath = working/'out'/f'{stem}.log'
        log = logpath.read_text(encoding='utf-8',errors='replace') if logpath.exists() else ''
        warnings = [line for line in log.splitlines() if re.search(r'Overfull \\[hv]box|Underfull \\[hv]box|undefined|LaTeX Warning:|Package .+ Warning:|Missing character:',line)]
        blgpath=working/'out'/f'{stem}.blg'
        if blgpath.exists():
            warnings += ['BibTeX: '+line for line in blgpath.read_text(encoding='utf-8',errors='replace').splitlines()
                         if re.search(r'Warning--|I found no|I couldn.t open|error message',line)]
        if compiled.returncode or not (working/'out'/f'{stem}.pdf').exists():
            raise ValueError(f'LaTeX build failed; see {output / (stem+".console.log")}')
        if before != sources(project):
            raise ValueError('Source changed during build; output not published')
        for suffix in ('.pdf','.log','.aux','.bbl','.blg'):
            src=working/'out'/f'{stem}{suffix}'
            if src.exists():shutil.copy2(src,output/src.name)
    pdf=output/f'{stem}.pdf'
    from pypdf import PdfReader
    pages=main_report_pages(output/f'{stem}.aux',len(PdfReader(pdf).pages))
    report=audit_pdf(pdf,pages,rules=project_rules(project))
    report.update({'format_version':1,'built_at':datetime.now(timezone.utc).isoformat(),
                   'entry':f'paper/{stem}.tex','synthetic':demo,'source_hashes':before,
                   'pdf_sha256':digest(pdf),'warnings':warnings,'source_unchanged':True,
                   'compile_passed':True,'visual_review_status':'pending','human_release_approved':False})
    report.update(consumed)
    content=audit_pdf(pdf,pages,release=True,rules=project_rules(project))
    report['content_status']='ready_for_review' if content['mechanical_passed'] and not demo else 'draft_or_incomplete'
    report['content_errors']=content['errors']
    report['shell_escape_enabled']=False
    # No warning is silently waived. Drafts remain inspectable but fail readiness.
    report['mechanical_passed']=report['mechanical_passed'] and not warnings
    report['rendered_pages']=[]
    report['rendered_page_sha256']={}
    if render:
        renderer=shutil.which('pdftoppm')
        if not renderer:raise ValueError('pdftoppm required for page rendering')
        renders=output/f'{stem}-pages'
        if not renders.resolve().is_relative_to(project):
            raise ValueError('Page render output escapes project')
        renders.mkdir(exist_ok=True)
        for old in renders.glob('page-*.png'):
            if not old.resolve().is_relative_to(renders.resolve()):
                raise ValueError('Page render path traverses a symlink/reparse point')
            old.unlink()
        done=subprocess.run([renderer,'-r','110','-png',str(pdf),str(renders/'page')],capture_output=True,text=True,timeout=120)
        if done.returncode:raise ValueError('PDF page rendering failed: '+done.stderr[-800:])
        report['rendered_pages']=[p.relative_to(project).as_posix() for p in sorted(renders.glob('page-*.png'))]
        if len(report['rendered_pages'])!=report['total_pdf_pages']:
            raise ValueError('Rendered page count differs from PDF page count')
        report['rendered_page_sha256']={relative:digest(project/relative) for relative in report['rendered_pages']}
    (output/f'{stem}.build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'pdf':str(pdf),'manifest':str(output/f'{stem}.build.json'),**report}

def release_gate_report(project,pdf):
    """Read recorded H3 approval, then bind its scope to this exact PDF."""
    path=Path(project)/'scripts/mcm.py'
    if not path.exists():
        return {'ok':False,'errors':['Missing local registry checker for H3_RELEASE']}
    spec=importlib.util.spec_from_file_location('paper_registry_guard',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.check_gate(project,'H3_RELEASE')
    errors=list(report.get('errors',[]))
    artifacts=module.records(project,'artifacts')
    gates=module.read_json(Path(project)/'config/gates.json').get('records',[])
    gate=next((g for g in gates if g.get('gate_id')=='H3_RELEASE'),{})
    matches=[]
    for ref in gate.get('scope_refs',[]):
        artifact=next((a for a in artifacts if a.get('artifact_id')==ref.get('artifact_id')),None)
        if artifact and artifact.get('kind')=='paper':
            artifact_path=module.resolve_inside(project,artifact.get('path',''))
            if artifact_path==Path(pdf).resolve() and artifact.get('sha256')==digest(pdf):
                matches.append(artifact)
    if not matches:
        errors.append('H3_RELEASE scope does not approve this exact PDF artifact and digest')
    decisions=module.records(project,'decisions')
    decision=next((d for d in decisions if d.get('decision_id')==gate.get('decision_id')),{})
    if not decision.get('user_message_ref') or not decision.get('user_confirmation_text'):
        errors.append('H3_RELEASE decision lacks the actual human confirmation reference and text')
    if decision.get('approved_by')!=gate.get('approved_by') or decision.get('approved_at')!=gate.get('approved_at'):
        errors.append('H3_RELEASE human approval identity/time differs from its decision record')
    return {'ok':not errors,'errors':errors,'gate_id':'H3_RELEASE',
            'paper_artifact_ids':[a['artifact_id'] for a in matches],
            'paper_author_agent_ids':[a.get('author_agent_id') for a in matches]}

def visual_review_report(project,pdf,manifest,attestation_path=None):
    """Validate an existing independent visual attestation; never create one."""
    project=Path(project).resolve()
    path=Path(attestation_path) if attestation_path else project/'reviews/paper-visual-review.json'
    if not path.is_absolute():path=project/path
    errors=[]
    if not path.resolve().is_relative_to(project):
        return {'ok':False,'errors':['Visual review attestation must be inside this project']}
    if not path.exists():
        return {'ok':False,'errors':['Missing reviews/paper-visual-review.json visual attestation']}
    attestation=json.loads(path.read_text(encoding='utf-8'))
    if attestation.get('_template_only') or attestation.get('synthetic'):
        errors.append('Visual attestation is a template or synthetic rehearsal')
    if attestation.get('status')!='passed' or not attestation.get('reviewer_agent_id') or not attestation.get('reviewed_at'):
        errors.append('Visual review must name an actual independent reviewer, review time and passed status')
    if attestation.get('pdf_sha256')!=digest(pdf):
        errors.append('Visual attestation applies to a different PDF digest')
    manifest_path=Path(pdf).with_suffix('.build.json')
    if not manifest_path.is_file() or attestation.get('build_manifest_sha256')!=digest(manifest_path):
        errors.append('Visual attestation applies to a different build manifest')
    authors=set(manifest.get('paper_author_agent_ids',[]))|set(attestation.get('paper_author_agent_ids',[]))
    if not manifest.get('paper_author_agent_ids'):
        errors.append('Build manifest must identify the paper authors before independent review')
    if attestation.get('reviewer_agent_id') in authors:
        errors.append('Paper author cannot provide its independent visual review')
    expected=manifest.get('rendered_pages',[])
    pages=attestation.get('pages',[])
    if not expected or [p.get('path') for p in pages]!=expected:
        errors.append('Visual review must cover every rendered page in the recorded order')
    for page in pages:
        relative=Path(page.get('path',''))
        resolved=(project/relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not resolved.is_relative_to(project):
            errors.append('Visual page reference escapes project');continue
        if not resolved.is_file() or page.get('sha256')!=digest(resolved):
            errors.append(f'Visual page digest missing or changed: {relative.as_posix()}')
        if manifest.get('rendered_page_sha256',{}).get(relative.as_posix())!=page.get('sha256'):
            errors.append(f'Visual page differs from the recorded build render: {relative.as_posix()}')
        checks=page.get('checks',{})
        for check_name in ('no_clipping','no_overlap','readable_text','readable_figures','consistent_headers','readable_equations','figure_font_at_final_size'):
            if checks.get(check_name) is not True:
                errors.append(f'Visual page check not passed: {relative.as_posix()} / {check_name}')
    return {'ok':not errors,'errors':errors,'reviewer_agent_id':attestation.get('reviewer_agent_id'),
            'attestation':path.relative_to(project).as_posix()}

def check(project,pdf,release=False,visual_review=None):
    project=Path(project).resolve();pdf=Path(pdf)
    if not pdf.is_absolute():pdf=project/pdf
    manifest=pdf.with_suffix('.build.json')
    errors=[]
    data=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    report=audit_pdf(pdf,data.get('main_report_pages'),release,rules=project_rules(project))
    if not data:errors.append('Missing build manifest; cannot prove source/PDF correspondence')
    if data.get('pdf_sha256') != digest(pdf):errors.append('PDF changed after the recorded build')
    if data.get('source_hashes') != sources(project):errors.append('Paper/figure sources changed after build')
    if data.get('warnings'):errors.append('Unresolved LaTeX warnings remain')
    report['errors'].extend(errors)
    report['mechanical_passed']=not report['errors']
    report['release_requested']=release
    report['release_ready']=False
    content=audit_pdf(pdf,data.get('main_report_pages'),release=True,rules=project_rules(project))
    report['content_status']='ready_for_review' if content['mechanical_passed'] and not data.get('synthetic') else 'draft_or_incomplete'
    report['content_errors']=content['errors']
    if release:
        gate=release_gate_report(project,pdf)
        results=check_paper_results(project,data)
        figures=check_paper_figures(project,data)
        visual=visual_review_report(project,pdf,data,visual_review)
        if visual.get('reviewer_agent_id') in gate.get('paper_author_agent_ids',[]):
            visual['errors'].append('Paper author cannot provide its independent visual release review')
            visual['ok']=False
        report['human_release_approved']=gate['ok']
        report['visual_review_status']='passed' if visual['ok'] else 'pending_or_failed'
        report['release_errors']=gate['errors']+results['errors']+figures['errors']+visual['errors']+report['content_errors']
        report['release_ready']=report['mechanical_passed'] and gate['ok'] and results['ok'] and figures['ok'] and visual['ok'] and report['content_status']=='ready_for_review'
        report['release_checks']={'gate':gate,'results':results,'figures':figures,'visual':visual}
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    sub=parser.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--demo',action='store_true');b.add_argument('--no-render',action='store_true')
    c=sub.add_parser('check');c.add_argument('pdf');c.add_argument('--release',action='store_true');c.add_argument('--visual-review',type=Path)
    args=parser.parse_args()
    try:
        result=build(args.root,args.demo,not args.no_render) if args.action=='build' else check(args.root,args.pdf,args.release,args.visual_review)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if (result.get('release_ready') if result.get('release_requested') else result['mechanical_passed']) else 1
    except (OSError,ValueError,subprocess.SubprocessError,ImportError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
