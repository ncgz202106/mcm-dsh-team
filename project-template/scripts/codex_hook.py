#!/usr/bin/env python3
"""Optional, project-scoped Codex tool guard. Not an OS or identity boundary.

Do not enable until the actual host has passed the callback smoke test.
The JSON input protocol alone cannot authenticate the caller or an agent role.
"""
import json
from pathlib import Path
import re
import sys

MUTATING = {'Bash', 'exec_command', 'apply_patch', 'Edit', 'Write', 'Agent',
            'spawn_agent', 'resume_agent', 'followup_task'}
PROTECTED = ('data/raw', '.mcm', 'config/gates.json', 'config/runtime.json',
             '.codex', 'scripts/codex_control.py', 'scripts/codex_hook.py')


def deny(reason):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny', 'permissionDecisionReason': reason}}


def project_from(cwd):
    p = Path(cwd).resolve()
    for candidate in (p, *p.parents):
        if (candidate / '.mcm-project').is_dir():
            return candidate
    return None


def evaluate(event):
    """Return an official hook response, never an approval or native-role proof."""
    if not isinstance(event, dict) or event.get('hook_event_name') != 'PreToolUse':
        return {}
    if not isinstance(event.get('cwd'), str):
        return deny('Missing working directory; cannot establish MCM project scope.')
    project = project_from(event['cwd'])
    if project is None:
        return {}
    try:
        runtime = json.loads((project / 'config/runtime.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return deny('MCM runtime configuration is unreadable; recover it before tool execution.')
    if runtime.get('runtime_provider') != 'codex':
        return {}
    tool = event.get('tool_name', '')
    # Names are matched as supplied by the host, not inferred from user text.
    short = tool.rsplit('.', 1)[-1]
    paused = runtime.get('paused') is True or runtime.get('pause_state', {}).get('paused') is True
    if paused and short in MUTATING:
        return deny('User pause is active. Stop new work and reconcile running tasks; no implicit resume.')
    if short in {'Agent', 'spawn_agent', 'resume_agent', 'followup_task'}:
        return deny('Strict native dispatch requires verified role/host evidence. This adapter has no authenticated native observer yet; use the documented capability probe, not a renamed generic role.')
    if short not in {'apply_patch', 'Edit', 'Write'}:
        return {}
    args = event.get('tool_input', {})
    if not isinstance(args, dict):
        return deny('Malformed file-edit arguments.')
    command = args.get('command', args.get('patch', ''))
    paths = re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$', command, re.M) if isinstance(command, str) else []
    if isinstance(args.get('file_path'), str):
        paths.append(args['file_path'])
    if not paths:
        return deny('File-edit paths cannot be inspected; use a supported project write interface.')
    if isinstance(command, str) and re.search(r'^\*\*\* (Delete File|Move to):', command, re.M):
        return deny('Deletion/move requires a separately reviewed explicit operation; automatic task edits cannot perform it.')
    for raw in paths:
        raw_path = Path(raw)
        target = (raw_path if raw_path.is_absolute() else Path(event['cwd']) / raw_path).resolve()
        if not target.is_relative_to(project):
            return deny('File edit escapes the active MCM project.')
        relative = target.relative_to(project).as_posix().casefold()
        if any(relative == p.casefold() or relative.startswith(p.casefold() + '/') for p in PROTECTED):
            return deny('Protected MCM data, control or approval file: use the checked registry/acceptance workflow.')
    return {}


def main():
    try:
        event = json.load(sys.stdin)
        response = evaluate(event)
        print(json.dumps(response, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        # Exit 2 blocks supported PreToolUse paths. No raw event/credentials logged.
        print('MCM hook failed to inspect this event: ' + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
