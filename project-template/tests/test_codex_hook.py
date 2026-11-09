import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('codex_hook', Path(__file__).parents[1] / 'scripts/codex_hook.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / '.mcm-project').mkdir()
        (self.root / 'config').mkdir()
        self.runtime(False)

    def runtime(self, pause):
        (self.root / 'config/runtime.json').write_text(json.dumps({'runtime_provider': 'codex', 'pause_state': {'paused': pause}}), encoding='utf-8')

    def call(self, tool='apply_patch', command='*** Add File: tasks/T1/draft.md\n+draft'):
        return hook.evaluate({'hook_event_name': 'PreToolUse', 'cwd': str(self.root), 'tool_name': tool, 'tool_input': {'command': command}})

    def blocked(self, result):
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_scoped_task_edit(self):
        self.assertEqual(self.call(), {})

    def test_protected_registry(self):
        self.blocked(self.call(command='*** Update File: .mcm/tasks.json\n+forged'))

    def test_absolute_escape(self):
        self.blocked(self.call(command='*** Add File: ' + str(self.root.parent / 'escape.txt')))

    def test_relative_escape(self):
        self.blocked(self.call(command='*** Add File: ../escape.txt'))

    def test_pause_blocks_shell_and_spawn(self):
        self.runtime(True)
        for name in ('Bash', 'exec_command', 'spawn_agent', 'apply_patch', 'followup_task'):
            self.blocked(self.call(name))

    def test_reads_are_not_marked_mutation(self):
        self.runtime(True)
        self.assertEqual(self.call('read_file'), {})

    def test_native_dispatch_not_faked(self):
        self.blocked(self.call('spawn_agent'))

    def test_unknown_edit_shape(self):
        self.blocked(self.call(command='not inspectable'))

    def test_delete_not_auto_allowed(self):
        self.blocked(self.call(command='*** Delete File: tasks/T1/draft.md'))

    def test_corrupt_runtime_blocks(self):
        (self.root / 'config/runtime.json').write_text('{broken', encoding='utf-8')
        self.blocked(self.call())

    def test_unrelated_project_untouched(self):
        result = hook.evaluate({'hook_event_name': 'PreToolUse', 'cwd': str(self.root.parent), 'tool_name': 'Bash'})
        self.assertEqual(result, {})

    def test_cannot_create_approval(self):
        self.assertEqual(hook.evaluate({'hook_event_name': 'PostToolUse', 'status': 'approved'}), {})


if __name__ == '__main__':
    unittest.main()
