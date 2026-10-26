"""Cross-component regressions: role IDs, file ownership and human evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('roles_cli',ROOT/'scripts/mcm.py')
mcm=importlib.util.module_from_spec(spec);spec.loader.exec_module(mcm)

class RoleInterfaces(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        shutil.copytree(ROOT/'config',self.root/'config')
        (self.root/'.mcm-project').mkdir()
        for name in mcm.REGISTRIES:mcm.save_records(self.root,name,[])
        mcm.save_records(self.root,'tasks',[{'task_id':'W1','owner_role':'mcm-writer',
            'owner_agent_id':'writer-one','status':'running','allowed_write_paths':['tasks/W1/draft']}])
    def tearDown(self):self.temp.cleanup()
    def test_config_covers_base_roles_and_optional_code_lead(self):
        owners=mcm.read_json(self.root/'config/runtime.json')['partition_ownership']
        self.assertEqual(set(owners),{'mcm-captain','mcm-model-lead','mcm-modeler','mcm-evidence',
            'mcm-programmer','mcm-code-lead','mcm-verifier','mcm-paper-lead','mcm-writer','mcm-figure','mcm-typesetter','mcm-reviewer'})
    def test_alias_and_canonical_captain_have_same_registry_authority(self):
        for role in ('captain','mcm-captain'):
            with mcm.registry_lock(self.root,role):pass
        with self.assertRaises(ValueError):
            with mcm.registry_lock(self.root,'mcm-paper-lead'):pass
    def test_two_writers_cannot_claim_each_others_task(self):
        mcm.write_output(self.root,'tasks/W1/draft/section.tex',b'first','mcm-writer','W1','writer-one')
        with self.assertRaisesRegex(ValueError,'owner'):
            mcm.write_output(self.root,'tasks/W1/draft/other.tex',b'bad','mcm-writer','W1','writer-two')
        with self.assertRaisesRegex(ValueError,'does not own'):
            mcm.write_output(self.root,'paper/main.tex',b'bad','paper_writer','W1','writer-one')
    def test_missing_task_or_scope_is_not_a_write_permission(self):
        with self.assertRaisesRegex(ValueError,'require'):
            mcm.write_output(self.root,'tasks/W1/draft/x.tex',b'bad','mcm-writer')
        with self.assertRaisesRegex(ValueError,'allowed_write_paths'):
            mcm.write_output(self.root,'tasks/W1/unassigned.tex',b'bad','mcm-writer','W1','writer-one')
    def test_pending_or_finished_task_cannot_keep_writing(self):
        rows=mcm.records(self.root,'tasks');rows[0]['status']='approved';mcm.save_records(self.root,'tasks',rows)
        with self.assertRaisesRegex(ValueError,'running or rework'):
            mcm.write_output(self.root,'tasks/W1/draft/x.tex',b'bad','mcm-writer','W1','writer-one')
    def test_verifier_has_own_partition(self):
        mcm.save_records(self.root,'tasks',[{'task_id':'V1','owner_role':'mcm-verifier',
            'owner_agent_id':'verify-one','status':'running','allowed_write_paths':['audit/verification/V1']}])
        result=mcm.write_output(self.root,'audit/verification/V1/report.json',b'{}','verifier','V1','verify-one')
        self.assertEqual(result['owner_role'],'mcm-verifier')
    def test_shared_prompt_rule_entry_exists(self):
        shared=ROOT.parent/'bundle/prompts/shared.md'
        if not shared.exists():self.skipTest('Standalone project has no preset source beside it')
        self.assertNotIn('config/competition.json',shared.read_text(encoding='utf-8'))
        self.assertTrue((ROOT/'config/contest-mcm-2027.json').is_file())
    def test_schedule_has_exact_freezes_and_official_stop(self):
        for at,state in [('2027-02-01T15:00:00+08:00','model_frozen'),
                         ('2027-02-01T23:00:00+08:00','results_frozen'),
                         ('2027-02-02T07:00:00+08:00','paper_frozen'),
                         ('2027-02-02T09:00:00+08:00','stopped')]:
            self.assertEqual(mcm.timeline(self.root,at)['state'],state)
        with self.assertRaisesRegex(ValueError,'timezone'):
            mcm.timeline(self.root,'2027-02-01T15:00:00')
    def test_unknown_runtime_capacity_does_not_admit_a_task(self):
        report=mcm.runtime_capacity(self.root)
        self.assertFalse(report['capacity_known']);self.assertFalse(report['admit_one_task'])
    def test_contest_mode_blocks_solution_writes_after_stop(self):
        config=mcm.read_json(self.root/'config/runtime.json');config['run_mode']='contest'
        mcm.atomic_json(self.root/'config/runtime.json',config)
        rules=mcm.read_json(self.root/'config/contest-mcm-2027.json')
        rules.update(starts_at='2000-01-01T00:00:00+08:00',stop_work_at='2000-01-05T03:00:00+08:00')
        mcm.atomic_json(self.root/'config/contest-mcm-2027.json',rules)
        with self.assertRaisesRegex(ValueError,'stop-work'):
            mcm.write_output(self.root,'tasks/W1/draft/x.tex',b'bad','mcm-writer','W1','writer-one')

if __name__=='__main__':unittest.main()
