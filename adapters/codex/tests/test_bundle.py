import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT=Path(__file__).resolve().parents[3]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

project=module('codex_project_test',ROOT/'tools/codex-project.py')
installer=module('codex_install_test',ROOT/'tools/install-codex-skill.py')

class BundleTests(unittest.TestCase):
    def test_generated_bundle_is_current(self):
        result=subprocess.run(['node','adapters/codex/build.mjs','--check'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(project.verify_bundle()['role_count'],12)

    def test_native_role_schema_and_inherited_settings(self):
        paths=list((ROOT/'adapters/codex/generated/project/.codex/agents').glob('*.toml'))
        self.assertEqual(len(paths),12)
        for path in paths:
            obj=tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(set(obj),{'name','description','developer_instructions'})
            self.assertEqual(path.stem,obj['name'])
            text=obj['developer_instructions']
            for forbidden in ['DSH','agent_preset','mcm_dispatch_preflight','mcm_archive_audit','run_code','深度 2','深度2']:
                self.assertNotIn(forbidden,text)
            self.assertIn('物理深度1',text)
            self.assertIn('H0_TOPIC/H1_MODEL/H2_RESULTS/H3_RELEASE',text)

    def test_figure_knowledge_and_science_preserved(self):
        base=ROOT/'adapters/codex/generated/project/.codex/agents'
        figure=tomllib.loads((base/'mcm-figure.toml').read_text(encoding='utf-8'))['developer_instructions']
        for term in ['mcm-visual-recipes','12pt','真实结果','SHA','PDF']:
            self.assertIn(term,figure)
        model=tomllib.loads((base/'mcm-model-lead.toml').read_text(encoding='utf-8'))['developer_instructions']
        self.assertIn('公式到函数映射',model)
        self.assertIn('独立盲写',model)
        paper=tomllib.loads((base/'mcm-paper-lead.toml').read_text(encoding='utf-8'))['developer_instructions']
        self.assertIn('之后为独立AI使用报告',paper)
        self.assertIn('正文篇幅不含附录',paper)

    def test_projection_fails_on_missing_source_anchor(self):
        script="import { paragraph, exact } from './adapters/codex/build.mjs'; let n=0; for (const f of [()=>paragraph('new text','old','x'),()=>exact('new text','old','x')]) { try { f(); } catch { n++; } } if(n!==2) process.exit(1);"
        result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_generated_config_is_pending_and_flat(self):
        base=ROOT/'adapters/codex/generated/project/config'
        runtime=json.loads((base/'runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(runtime['max_nested_depth'],1)
        self.assertEqual(runtime['default_mode'],'strict')
        self.assertFalse(runtime['capabilities']['native_role_selection']['verified'])
        roles=json.loads((base/'codex-roles.json').read_text(encoding='utf-8'))['roles']
        self.assertEqual([r['id'] for r in roles if r['may_spawn']],['mcm-captain'])

    def test_generated_project_readme_and_provenance_are_portable(self):
        base=ROOT/'adapters/codex/generated/project'
        readme=(base/'README-example.md').read_text(encoding='utf-8')
        self.assertIn('codex preflight',readme)
        self.assertNotIn('listRuntime',readme)
        self.assertNotIn('DSH',readme)
        provenance=json.loads((base/'paper/provenance/latex-project.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['template']['path'],'paper/provenance')
        self.assertTrue((ROOT/'project-template'/provenance['template']['path']/provenance['main_tex']).is_file())

    def test_shared_references_and_public_case_index(self):
        generated=ROOT/'adapters/codex/generated'
        for name in ('o-award-framework.md','chart-reference.md'):
            shared=(ROOT/'project-template/resources/mcm-skills'/name).read_text(encoding='utf-8')
            self.assertEqual((generated/'project/resources/mcm-skills'/name).read_text(encoding='utf-8'),shared)
            self.assertEqual((generated/'skill/references'/name).read_text(encoding='utf-8'),shared)
        index=(generated/'skill/references/chart-gallery.html').read_text(encoding='utf-8')
        self.assertEqual(index.count('<article class="card"'),34)
        self.assertNotIn('data:image/',index)
        self.assertNotIn('selected_papers/',index)

    def test_fresh_generated_project_can_enter_synthetic_rehearsal(self):
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'project'
            project.create(target)
            def invoke(*args):
                return subprocess.run([sys.executable, 'scripts/mcm.py', 'codex', *args],
                                      cwd=target, capture_output=True, text=True)
            self.assertEqual(invoke('preflight').returncode,2)
            prepared=invoke('init-demo')
            self.assertEqual(prepared.returncode,0,prepared.stdout+prepared.stderr)
            rehearsal=invoke('preflight','--synthetic-demo')
            self.assertEqual(rehearsal.returncode,0,rehearsal.stdout+rehearsal.stderr)
            self.assertFalse(json.loads(rehearsal.stdout)['formal_pass'])

    def test_new_project_and_preview_preserve_existing_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'project'
            result=project.create(target)
            self.assertFalse(result['native_runtime_verified'])
            self.assertEqual(len(list((target/'.codex/agents').glob('*.toml'))),12)
            self.assertTrue((target/'.mcm-project').is_dir())
            marker=target/'AGENTS.md';marker.write_text('USER CONTENT',encoding='utf-8')
            with self.assertRaises(ValueError):project.create(target)
            report=project.preview(target)
            self.assertFalse(report['changed'])
            self.assertEqual(marker.read_text(encoding='utf-8'),'USER CONTENT')
            self.assertEqual(next(x['state'] for x in report['files'] if x['path']=='AGENTS.md'),'different_preserve_existing')

    def test_installer_preview_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'mcm-team'
            report=installer.inspect(target)
            self.assertFalse(report['changed']);self.assertFalse(target.exists())

    def test_install_and_rollback_new_entry_without_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'skills/mcm-team'
            result=installer.install(target,Path(tmp)/'backups')
            self.assertTrue((target/'SKILL.md').is_file())
            self.assertFalse(result['native_runtime_verified'])
            back=installer.rollback(result['receipt'])
            self.assertFalse(target.exists())
            self.assertEqual(back['deleted_files'],0)
            self.assertTrue((Path(back['archived'])/'SKILL.md').is_file())

    def test_update_rollback_restores_exact_previous_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'skills/mcm-team'
            installer.install(target,Path(tmp)/'backups')
            old=(target/installer.RECEIPT).read_bytes()
            update=installer.install(target,Path(tmp)/'backups')
            installer.rollback(update['receipt'])
            self.assertEqual((target/installer.RECEIPT).read_bytes(),old)

    def test_refuse_overwrite_and_rollback_of_user_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'skills/mcm-team'
            result=installer.install(target,Path(tmp)/'backups')
            (target/'SKILL.md').write_text('User modified',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'User-modified'):installer.install(target,Path(tmp)/'backups')
            with self.assertRaisesRegex(ValueError,'User-modified'):installer.rollback(result['receipt'])
            self.assertEqual((target/'SKILL.md').read_text(encoding='utf-8'),'User modified')

    def test_unmanaged_existing_skill_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'mcm-team';target.mkdir();(target/'SKILL.md').write_text('mine')
            with self.assertRaisesRegex(ValueError,'no managed receipt'):installer.inspect(target)

    def test_backup_inside_repo_or_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'mcm-team'
            for backup in [ROOT/'backups',target/'backups']:
                with self.assertRaisesRegex(ValueError,'Backups must'):installer.install(target,backup)

if __name__=='__main__':unittest.main()
