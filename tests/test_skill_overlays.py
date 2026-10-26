from pathlib import Path
import importlib.util,json,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('skill_overlays',ROOT/'tools/skill-overlays.py')
overlay=importlib.util.module_from_spec(spec);spec.loader.exec_module(overlay)
SOURCE=ROOT/'skill-overlays'

class SkillOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.skills=self.base/'skills';self.backups=self.base/'backups'
        self.manifest=json.loads((SOURCE/'manifest.json').read_text())
        self.originals={}
        for name in self.manifest['skills']:
            p=self.skills/name/'SKILL.md';p.parent.mkdir(parents=True)
            content=f'---\r\nname: {name}\r\ndescription: Original route\r\n---\r\n\r\n# {name}\r\nKeep this distinct upstream workflow.\r\n'.encode()
            p.write_bytes(content);self.originals[p.relative_to(self.skills).as_posix()]=content
    def snapshot(self):return {p.relative_to(self.skills).as_posix():p.read_bytes() for p in self.skills.rglob('*') if p.is_file()}
    def install(self):return overlay.apply(SOURCE,self.skills,self.backups,True)
    def test_dry_run_does_not_mutate_and_apply_preserves_upstream(self):
        before=self.snapshot();plan=overlay.apply(SOURCE,self.skills)
        self.assertEqual(plan['changed_files'],10);self.assertEqual(before,self.snapshot())
        self.install()
        for relative,original in before.items():
            current=(self.skills/relative).read_bytes()
            body=b''.join(original.splitlines(keepends=True)[4:])
            self.assertIn(b'name: ',current);self.assertTrue(current.endswith(body))
            self.assertLess(current.index(overlay.START.encode()),current.index(b'Keep this distinct upstream workflow.'))
    def test_idempotence_and_exact_restore_including_absent_files(self):
        before=self.snapshot();result=self.install()
        self.assertEqual(self.install()['changed_files'],0)
        self.assertEqual(overlay.restore(result['receipt'])['status'],'restore_preflight_passed')
        overlay.restore(result['receipt'],True);self.assertEqual(before,self.snapshot())
    def test_later_user_edit_blocks_restore_without_partial_changes(self):
        result=self.install();p=self.skills/'nature-reviewer/SKILL.md';p.write_bytes(p.read_bytes()+b'Later user work\n')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'later skill changes'):overlay.restore(result['receipt'],True)
        self.assertEqual(before,self.snapshot())
    def test_corrupt_saved_bytes_block_restore_before_any_write(self):
        result=self.install();path=Path(result['receipt']);(path.parent/'files/nature-figure/SKILL.md').write_bytes(b'bad backup')
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'integrity'):overlay.restore(path,True)
        self.assertEqual(before,self.snapshot())
    def test_partial_apply_failure_restores_the_whole_written_window(self):
        before=self.snapshot();original=overlay.save;state={'injected':False}
        def fail_once(path,data):
            if path==self.skills/'nature-writing/references/mcm-adaptation.md' and not state['injected']:
                state['injected']=True;raise OSError('Injected write failure')
            original(path,data)
        overlay.save=fail_once
        try:
            with self.assertRaisesRegex(OSError,'Injected'):self.install()
        finally:overlay.save=original
        self.assertEqual(before,self.snapshot())
        receipt=json.loads(next(self.backups.glob('*/receipt.json')).read_text())
        self.assertEqual(receipt['status'],'failed_rolled_back')
    def test_malformed_prior_hook_rejected_without_mutation(self):
        p=self.skills/'nature-writing/SKILL.md';p.write_bytes(p.read_bytes()+overlay.START.encode())
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'Malformed'):self.install()
        self.assertEqual(before,self.snapshot())
    def test_restore_failure_recovers_the_current_overlay_and_can_retry(self):
        result=self.install();after=self.snapshot();original=overlay.save;state={'injected':False}
        def fail_once(path,data):
            if path==self.skills/'nature-writing/SKILL.md' and not state['injected']:
                state['injected']=True;raise OSError('Injected restore failure')
            original(path,data)
        overlay.save=fail_once
        try:
            with self.assertRaisesRegex(OSError,'Injected'):overlay.restore(result['receipt'],True)
        finally:overlay.save=original
        self.assertEqual(after,self.snapshot())
        receipt=json.loads(Path(result['receipt']).read_text());self.assertEqual(receipt['status'],'applied_verified')
        self.assertEqual(receipt['restore_outcome'],'failed_current_overlay_recovered')
        overlay.restore(result['receipt'],True);self.assertEqual(self.originals,self.snapshot())
    def test_apply_recovery_preserves_concurrent_edit_and_reports_partial(self):
        original=overlay.save;state={'injected':False};target=self.skills/'nature-figure/SKILL.md'
        def fail_after_user_edit(path,data):
            if path==self.skills/'nature-writing/references/mcm-adaptation.md' and not state['injected']:
                state['injected']=True;target.write_bytes(target.read_bytes()+b'Concurrent user edit\n');raise OSError('Injected apply failure')
            original(path,data)
        overlay.save=fail_after_user_edit
        try:
            with self.assertRaisesRegex(OSError,'Injected'):self.install()
        finally:overlay.save=original
        self.assertTrue(target.read_bytes().endswith(b'Concurrent user edit\n'))
        receipt=json.loads(next(self.backups.glob('*/receipt.json')).read_text());self.assertEqual(receipt['status'],'failed_rollback_partial')
        self.assertTrue(receipt['recovery_errors'])
    def test_restore_recovery_never_clobbers_a_concurrent_edit(self):
        result=self.install();original=overlay.save;state={'injected':False};target=self.skills/'nature-figure/SKILL.md'
        def fail_after_user_edit(path,data):
            if path==self.skills/'nature-writing/SKILL.md' and not state['injected']:
                state['injected']=True;target.write_bytes(target.read_bytes()+b'Concurrent user edit\n');raise OSError('Injected restore failure')
            original(path,data)
        overlay.save=fail_after_user_edit
        try:
            with self.assertRaisesRegex(OSError,'Injected'):overlay.restore(result['receipt'],True)
        finally:overlay.save=original
        self.assertTrue(target.read_bytes().endswith(b'Concurrent user edit\n'))
        receipt=json.loads(Path(result['receipt']).read_text());self.assertEqual(receipt['status'],'restore_failed_recovery_partial')

if __name__=='__main__':unittest.main()
