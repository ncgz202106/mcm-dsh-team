"""Independent read-only checks of LIVE-ACCEPTANCE-001; writes this archive only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

archive = Path(__file__).resolve().parent
kit = archive.parent.parent
workspace = kit.parent.parent
project = workspace / 'work/dsh-v020-live-smoke'
template = kit / 'project-template'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def project_file(relative):
    result = (project / relative).resolve()
    if not result.is_relative_to(project.resolve()):
        raise ValueError(f'Unexpected path outside isolated project: {relative}')
    return result

def archive_copy(source, relative):
    target = archive / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == source.read_bytes(), relative
    else:
        shutil.copyfile(source, target)
    return {'path': relative, 'bytes': target.stat().st_size, 'sha256': digest(target)}

parent_path = project / 'audit/LIVE-ACCEPTANCE-001-result.json'
child_path = project / 'audit/live-figure/child-report.json'
parent = read(parent_path)
child = read(child_path)
assert digest(parent_path) == '33db0283dae15db4257a105ce3260499388b8662a806fb04972139ef92733e40'
assert digest(child_path) == '5718e26f2459007d36013c13433343e423a7940e12e2323fcf05779d8314412d'

artifacts = []
for entry in child['artifacts']:
    path = project_file(entry['path'])
    assert path.is_file(), entry['path']
    assert path.stat().st_size == entry['bytes'], entry['path']
    assert digest(path) == entry['sha256'], entry['path']
    artifacts.append({**entry, 'verified': True})
assert len(artifacts) == 40
declared = {entry['path'] for entry in artifacts}
actual = {p.relative_to(project).as_posix() for p in (project / 'figures/figure-demo').iterdir() if p.is_file()}
assert actual == declared, {'undeclared': sorted(actual-declared), 'missing': sorted(declared-actual)}

protected = []
for section in ['scripts', 'config', '.mcm', 'paper']:
    def relevant(directory):
        return {p.relative_to(directory).as_posix(): p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc', '.pyo']}
    before = relevant(template / section)
    after = relevant(project / section)
    assert set(before) == set(after), section
    for relative in sorted(before):
        assert before[relative].read_bytes() == after[relative].read_bytes(), f'{section}/{relative}'
        protected.append({'path': f'{section}/{relative}', 'sha256': digest(after[relative]), 'matches_template': True})
assert len(protected) == 40
gates = read(project / 'config/gates.json')
if isinstance(gates.get('records'), list):
    gate_rows = gates['records']
elif isinstance(gates.get('gates'), list):
    gate_rows = gates['gates']
else:
    gate_rows = [{'gate_id': key, **value} for key, value in gates['gates'].items()]
assert len(gate_rows) == 4 and all(row['status'] == 'pending' for row in gate_rows)

metadata_path = kit / 'audit/live-session-metadata.json'
metadata = read(metadata_path)
parent_meta = next(s for s in metadata['sessions'] if s['header']['id'] == 'session-5cb9f2f7-7399-4e8d-b3c6-b7db5d71316a')
child_meta = next(s for s in metadata['sessions'] if s['header']['id'] == '84c73a8b-23e1-4b59-a667-02273e066615')
assert parent_meta['effective_preset'] == 'mcm-paper-lead'
assert parent_meta['header']['delegationDepth'] == 0
assert child_meta['effective_preset'] == 'mcm-figure'
assert child_meta['header']['delegationDepth'] == 1
assert child_meta['header']['parentSession'] == parent_meta['header']['id']
assert any(c['seq'] == 187 and c['agent_preset'] == 'mcm-figure' for c in parent_meta['delegation_calls'])
assert any(c['seq'] == 47 and c['tool'] == 'read' and c['value'].endswith('SKILL.md') for c in child_meta['skill_read_calls'])
assert any(c['seq'] == 109 and c['contains_skill_root'] for c in child_meta['figure_execution_calls'])
role_readback = {
    'evidence_ref': '../live-session-metadata.json',
    'evidence_sha256': digest(metadata_path),
    'method': metadata['method'],
    'root': {'session_id': parent_meta['header']['id'], 'effective_preset': parent_meta['effective_preset'], 'actual_depth': 0, 'parent_session_id': None},
    'child': {'session_id': child_meta['header']['id'], 'effective_preset': child_meta['effective_preset'], 'actual_depth': 1, 'parent_session_id': child_meta['header']['parentSession']},
    'correction': 'Original parent report claimed its own depth=1 and child depth=2. Native header records show root=0 and child=1, because paper-lead was opened as a root for this isolated test. The intended competition captain->paper-lead->figure tree was not exercised by this particular live test.',
    'native_calls': {'explicit_mcm_figure_spawn_seq': 187, 'skill_md_read_seq': 47, 'figure_demo_with_skill_root_seq': 109},
    'tool_surface_boundary': 'The leaf has no native subagent binding, but the captured SDK still exposes globally installed subagent_codex/subagent_claude_code tools. This record does not prove leaf delegation was mechanically blocked in this tested installation.',
    'scope_boundary': 'Uses the parent-produced whitelist metadata snapshot; this verifier did not re-read raw native logs.',
}
(archive / 'native-role-readback.json').write_text(json.dumps(role_readback, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

archive_files = [
    archive_copy(parent_path, 'LIVE-ACCEPTANCE-001-result.json'),
    archive_copy(project / 'audit/LIVE-ACCEPTANCE-001-result.md', 'LIVE-ACCEPTANCE-001-result.md'),
    archive_copy(project / 'audit/LIVE-ACCEPTANCE-001.md', 'LIVE-ACCEPTANCE-001.md'),
    archive_copy(child_path, 'child-report.json'),
]
for artifact in artifacts:
    archive_files.append(archive_copy(project_file(artifact['path']), artifact['path']))

png_observations = {
    'method': 'White background; four aligned rounded rectangles; labels fit; arrows separate from boxes and text; no visible clipping or overlap.',
    'comparison': 'Axis labels and fractional units legible; blue solid, orange dashed and green marked dotted series distinguishable; upper-right legend clear and unobstructed; synthetic label visible.',
    'sensitivity': 'Three rate scenarios use distinct line styles and semantic colors; axis labels/legend clear; no visible clipping or overlap.',
    'uncertainty': 'Blue reference curve and translucent parameter envelope distinguishable; legend accurately says parameter envelope, not confidence interval; no visible clipping or overlap.',
}
visual = []
for name, observation in png_observations.items():
    png = project / f'figures/figure-demo/{name}.png'
    visual.append({'path': f'figures/figure-demo/{name}.png', 'sha256': digest(png), 'actually_viewed_with': 'tools.view_image', 'reviewer': '/root/live_evidence_finalize', 'independent_of_authors': True, 'status': 'passed_png_inspection', 'observation': observation})

report = {
    'format_version': 1,
    'report_id': 'LIVE-ACCEPTANCE-001-independent',
    'verified_at': datetime.now(timezone.utc).isoformat(),
    'reviewer': '/root/live_evidence_finalize',
    'independent_of_dsh_authors': True,
    'overall_status': 'partial_acceptance_with_preserved_process_failure',
    'project': str(project),
    'synthetic': True,
    'source_reports': archive_files[:4],
    'artifact_check': {'passed': True, 'verified_count': 40, 'unexpected_or_missing': [], 'artifacts': artifacts},
    'protected_source_check': {'passed': True, 'verified_count': 40, 'basis': 'Current isolated-project bytes compared to current clean release template; no earlier state was reconstructed or overwritten.', 'files': protected},
    'human_gates': {'pending_count': 4, 'file_sha256': digest(project / 'config/gates.json'), 'statuses': [{'gate_id': row.get('gate_id') or row.get('id'), 'status': row['status']} for row in gate_rows], 'modified_by_this_review': False},
    'native_role_check': role_readback,
    'skill_evidence': {
        'installed': 'SKILL.md existence/hash claimed in source reports and matched by the native read-call reference; no independent full installed-skill audit was performed by this reviewer.',
        'read': 'Native whitelist records actual read calls to SKILL.md and four additional nature-figure documents. Parent/child report partial coverage of stance tail and qa-contract body is preserved.',
        'executed': 'Native seq109 records the figure_demo invocation with --skill-root; all 40 current output bytes match the child declaration. The read call itself is not treated as execution.',
        'accepted': 'Artifact integrity and four PNG inspections passed. No human approval or final manuscript visual acceptance was created.',
    },
    'visual_inspection': {'pngs': visual, 'pdf_pages_actually_viewed': 0, 'final_manuscript_pages_actually_viewed': 0, 'contract_visual_status_modified': False, 'scope': 'Four full PNGs only. No certification of exported PDF glyph appearance or final insertion scale/placement.'},
    'unresolved': [
        {'id': 'DEV-01/GAP-01', 'severity': 'major', 'status': 'open_in_this_historical_test', 'finding': 'The parent reports admit_one_task=false and absent verified capacity snapshot yet performed one spawn. Output success does not satisfy the admission rule; a bounded-probe explanation does not waive it.'},
        {'id': 'DEV-03', 'severity': 'minor', 'status': 'retained', 'finding': 'Child self-reported audit/live-figure/build_report.py but that file is absent. It was not a numbered evidence input; do not treat the self-report as a current file.'},
        {'id': 'DEV-04', 'severity': 'minor', 'status': 'unverified', 'finding': 'A /tmp write was self-reported; this review did not inspect system temp or certify an OS write boundary.'},
        {'id': 'VISUAL-FINAL-PAGES', 'severity': 'minor', 'status': 'not_performed', 'finding': 'This live test produced figures but did not build an inserted manuscript; contracts remain visually pending.'},
        {'id': 'SKILL-PARTIAL-AND-WARNINGS', 'severity': 'minor', 'status': 'retained', 'finding': 'Partial skill reading, non-strict collision mode and three source-preflight WARN classes remain disclosed. Project 300dpi PNG/PDF/SVG requirements differ from the skill default TIFF/600dpi.'},
    ],
    'closed_or_corrected': [{'id': 'GAP-02', 'status': 'closed_by_external_native_metadata_snapshot', 'finding': 'Effective paper-lead/figure presets and parent relation confirmed by selected events/header. Depth corrected to root0/child1; no claim of a live captain->paper-lead->figure depth2 exercise.'}],
    'new_guard_fix_verified_here': False,
    'human_release_approved': False,
    'original_rehearsal_resumed': False,
    'no_original_project_or_profile_access_by_this_reviewer': True,
    'archive': {'directory': 'audit/live-model-acceptance', 'files': archive_files, 'raw_native_sessions_copied': False, 'hidden_reasoning_or_credentials_copied': False},
}
destination = kit / 'audit/live-model-verification.json'
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'report': str(destination), 'sha256': digest(destination), 'artifacts_verified': len(artifacts), 'protected_files_verified': len(protected), 'pngs_actually_viewed': len(visual), 'overall_status': report['overall_status']}, ensure_ascii=False))
