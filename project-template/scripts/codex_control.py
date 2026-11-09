#!/usr/bin/env python3
"""Cooperative Codex task admission and artifact intake; never a permissions sandbox.

Strict native execution remains blocked until a supported runtime observer exists.
The explicitly isolated synthetic mode exercises the same file/state checks without
pretending to authenticate native roles, hooks, people, or independent model calls.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tomllib
import uuid

_spec = importlib.util.spec_from_file_location("mcm_codex_registry", Path(__file__).with_name("mcm.py"))
mcm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcm)

VERSION = "1.0"
ACTIVE = {"claimed", "delivered"}
PROTECTED_ROOTS = ("src", "models", "paper", "figures", "results", "data", "scripts", "protocols", ".codex")
PROTECTED_FILES = (".mcm/artifacts.json", ".mcm/issues.json", ".mcm/decisions.json", "config/gates.json")
CONTROL = ".mcm/codex"
EMPTY_DEMO_MARKERS = {"data/processed/.gitkeep", "models/.gitkeep", "results/.gitkeep"}
RAW_README_SHA256 = "fcf50e45b1e2d65a7d57c71e0d1f2264b40b4284cfe56ef09e7b0212b881f2ea"


def inside(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Paths must be nonempty project-relative POSIX paths")
    parts = Path(relative).parts
    if relative.startswith("/") or any(part in {".", ".."} for part in parts) or relative == ".":
        raise ValueError("Unsafe relative path")
    return mcm.resolve_inside(root, relative)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def task_row(root, task_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", task_id or ""):
        raise ValueError("Unsafe task identifier")
    rows = mcm.records(root, "tasks")
    matches = [row for row in rows if row.get("task_id") == task_id]
    if len(matches) != 1:
        raise ValueError("Task must exist exactly once in the captain registry")
    return rows, matches[0]


def _role(root, relative, expected_hash, requested_role):
    path = inside(root, relative)
    if not path.is_file() or mcm.file_hash(path) != expected_hash:
        raise ValueError("Role configuration missing or SHA256 changed")
    if path.suffix != ".toml" or not path.is_relative_to(inside(root, ".codex/agents")):
        raise ValueError("Role must be a project .codex/agents TOML")
    data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("name") != requested_role or not data.get("description") or not data.get("developer_instructions"):
        raise ValueError("Role configuration does not match the requested role")
    return data


def _demo_marker(root):
    path = inside(root, CONTROL + "/synthetic-demo.json")
    if not path.is_file():
        return False
    marker = mcm.read_json(path)
    config = mcm.read_json(inside(root, "config/runtime.json"))
    return (marker.get("synthetic") is True and marker.get("formal_pass") is False
            and marker.get("project_root_hash") == fingerprint(str(Path(root).resolve()))
            and config.get("run_mode") != "contest")


def _no_approvals(root):
    gates = mcm.read_json(inside(root, "config/gates.json"))
    return not any(row.get("status") == "approved" for row in gates.get("records", []))


def is_link_like(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return (stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, "st_reparse_tag", None) == stat.IO_REPARSE_TAG_MOUNT_POINT)


def is_demo_scaffold(root, path):
    if is_link_like(path):
        return False
    relative = path.relative_to(root).as_posix()
    if relative in EMPTY_DEMO_MARKERS:
        return path.stat().st_size <= 2 and path.read_bytes() in (b"", b"\n", b"\r\n")
    return relative == "data/raw/README.md" and mcm.file_hash(path) == RAW_README_SHA256


def init_demo(root):
    root = Path(root).resolve()
    if not (root / ".mcm-project").exists():
        raise ValueError("Demo requires a fresh MCM project marker")
    with mcm.registry_lock(root):
        if any(mcm.records(root, name) for name in mcm.REGISTRIES) or not _no_approvals(root):
            raise ValueError("Demo initialization requires empty registries and no approved gates")
        if mcm.read_json(root / "config/runtime.json").get("run_mode") == "contest":
            raise ValueError("Contest projects cannot become synthetic demos")
        for relative in ("data", "models", "results"):
            folder = root / relative
            if is_link_like(folder) or (folder.exists() and not folder.is_dir()):
                raise ValueError("Demo initialization needs real data, models and results directories")
            if folder.exists() and any(
                (is_link_like(p) or p.is_file()) and not is_demo_scaffold(root, p)
                for p in folder.rglob("*")
            ):
                raise ValueError("Demo initialization refuses existing scientific data or results")
        path = inside(root, CONTROL + "/synthetic-demo.json")
        if path.exists():
            raise ValueError("Synthetic demo marker already exists")
        marker = {"format_version": 1, "synthetic": True, "formal_pass": False,
                  "project_root_hash": fingerprint(str(root)), "created_at": mcm.utcnow()}
        mcm.atomic_json(path, marker)
    return {"ok": True, "mode": "synthetic-demo", "formal_pass": False}


def capabilities(root):
    """Untrusted/manual observations are diagnostic only, never runtime authority.

    Add a reviewed, versioned native observer here when the host exposes binding
    and interception evidence. This entry deliberately executes no plugin supplied
    by a project and accepts no JSON boolean as a capability grant.
    """
    observation_path = inside(root, CONTROL + "/observations.json")
    observations = []
    if observation_path.is_file():
        data = mcm.read_json(observation_path)
        observations = [{key: row.get(key) for key in ("capability", "status", "origin", "evidence_ref")}
                        for row in data.get("records", []) if isinstance(row, dict)]
    return {"ok": False, "format_version": 1, "control_version": VERSION,
            "native_role_binding": "unverified", "tool_interception": "unverified",
            "supported_native_observers": [], "observations": observations,
            "operative_checks": ["input_hashes", "role_file_identity", "unique_attempt", "scope_conflicts",
                                 "protected_fingerprints", "intake_validation", "non_author_record",
                                 "pause", "recovery_diagnostics"],
            "blocked_reasons": ["No verified native role-binding observer for this host",
                                "No verified native hook coverage for this host"],
            "formal_pass": False,
            "limitations": ["These checks are cooperative and are not OS isolation",
                            "Agent/reviewer identities recorded by the captain are not cryptographic authentication",
                            "A manual or simulated capability report cannot enable strict execution"]}


def _transaction_pending(root):
    folder = inside(root, CONTROL + "/transactions")
    if not folder.exists():
        return []
    return [p.relative_to(Path(root)).as_posix() for p in sorted(folder.glob("*.json"))
            if mcm.read_json(p).get("state") != "committed"]


def _check_mode(root, synthetic_demo):
    if synthetic_demo:
        if not _demo_marker(root) or not _no_approvals(root):
            raise ValueError("Synthetic mode requires its root-bound marker and no approved human gates")
        if any(row.get("synthetic") is not True for row in mcm.records(root, "artifacts")):
            raise ValueError("Synthetic demo contains non-synthetic artifacts")
        return "synthetic-demo"
    report = capabilities(root)
    if not report["ok"]:
        raise ValueError("Strict native execution blocked: " + "; ".join(report["blocked_reasons"]))
    return "strict"


def _inputs(root, task):
    artifacts = {row["artifact_id"]: row for row in mcm.records(root, "artifacts")}
    refs = task.get("inputs", [])
    if not isinstance(refs, list):
        raise ValueError("Task inputs must be a list")
    errors = []
    for ref in refs:
        errors.extend(mcm.reference_errors(root, ref, artifacts))
    closure = mcm.dependency_closure(artifacts, {ref.get("artifact_id") for ref in refs})
    for identity in closure:
        row = artifacts.get(identity)
        if row is None:
            continue
        errors.extend(mcm.reference_errors(root, {key: row.get(key) for key in ("artifact_id", "path", "version", "sha256")}, artifacts))
        for ref in row.get("inputs", []):
            errors.extend(mcm.reference_errors(root, ref, artifacts))
    if errors:
        raise ValueError("; ".join(dict.fromkeys(errors)))


def _scopes(root, task):
    scopes = task.get("allowed_write_paths", [])
    if not scopes:
        raise ValueError("Codex workers must have a task-private output directory")
    private = inside(root, "tasks/" + task["task_id"])
    resolved = []
    for scope in scopes:
        path = inside(root, scope)
        if path != private and not path.is_relative_to(private):
            raise ValueError("Workers write only tasks/<task_id>/; captain accepts formal artifacts")
        resolved.append(path)
    return resolved


def _overlap(left, right):
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def protected_files(root):
    root = Path(root).resolve()
    paths = set()
    for relative in PROTECTED_ROOTS + (CONTROL + "/accepted",):
        folder = inside(root, relative)
        if folder.exists():
            for path in folder.rglob("*"):
                if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                canonical = inside(root, path.relative_to(root).as_posix())
                if canonical.is_file():
                    paths.add(canonical)
    for relative in PROTECTED_FILES:
        path = inside(root, relative)
        if path.exists():
            paths.add(path)
    return {path.relative_to(root).as_posix(): mcm.file_hash(path) for path in sorted(paths)}


def integrity(root):
    path = inside(root, CONTROL + "/protected.json")
    current = protected_files(root)
    if not path.exists():
        missing = any(row.get("codex") for row in mcm.records(root, "tasks"))
        return {"ok": not missing, "initialized": False, "changes": [{"path": CONTROL + "/protected.json", "reason": "missing active protection baseline"}] if missing else [], "current_files": current}
    snapshot = mcm.read_json(path)
    before = snapshot["files"]
    changes = [{"path": p, "before": before.get(p), "after": current.get(p)}
               for p in sorted(before.keys() | current.keys()) if before.get(p) != current.get(p)]
    return {"ok": not changes, "initialized": True, "changes": changes, "current_files": current}


def _assert_integrity(root):
    report = integrity(root)
    if not report["ok"]:
        raise ValueError("Unregistered protected changes: " + ", ".join(row["path"] for row in report["changes"]))
    return report["current_files"]


def _write_protection(root, expected=None):
    current = protected_files(root)
    if expected is not None and current != expected:
        raise ValueError("Protected files changed during intake/claim; baseline was not refreshed")
    mcm.atomic_json(inside(root, CONTROL + "/protected.json"),
                    {"format_version": 1, "at": mcm.utcnow(), "files": current if expected is None else expected})


def protect(root):
    with mcm.registry_lock(root):
        expected = _assert_integrity(root)
        _write_protection(root, expected)
    return {"ok": True, "files": len(protected_files(root)), "refresh_did_not_hide_changes": True}


def writer_lock_status(root):
    path = inside(root, ".mcm") / "write.lock"
    if path.is_symlink():
        return {"present": True, "malformed": True, "action": "Inspect symlink at registry lock path; no automatic deletion"}
    if not path.exists():
        return {"present": False}
    try:
        data = mcm.read_json(path)
        if not isinstance(data, dict):
            raise ValueError("Malformed writer lock")
        pid = data.get("pid")
        started_at = data.get("started_at")
        if type(pid) is not int or pid <= 0 or not isinstance(started_at, str):
            raise ValueError("Malformed writer lock")
        if datetime.fromisoformat(started_at).tzinfo is None:
            raise ValueError("Writer lock timestamp needs a time zone")
        return {"present": True, "pid": pid, "started_at": started_at,
                "process_liveness": "not_verified", "action": "Inspect the writer; never remove this lock automatically"}
    except (OSError, ValueError, TypeError):
        return {"present": True, "malformed": True, "action": "Inspect unreadable writer lock; no automatic deletion"}


def preflight(root, task_id=None, synthetic_demo=False, _lock_held=False):
    errors = []
    mode = "strict"
    try:
        mode = _check_mode(root, synthetic_demo)
        if not _lock_held and writer_lock_status(root)["present"]:
            raise ValueError("Unresolved registry writer lock; inspect recover before new work")
        if mcm.pause_state(root)["paused"]:
            raise ValueError("Project is paused")
        pending = _transaction_pending(root)
        if pending:
            raise ValueError("Unfinished intake transaction; inspect recover before new work")
        _assert_integrity(root)
        if task_id:
            _, task = task_row(root, task_id)
            _inputs(root, task)
            _scopes(root, task)
            if not task.get("acceptance_criteria"):
                raise ValueError("Task must have acceptance criteria")
            if task.get("status") not in {"queued", "rework"}:
                raise ValueError("Task is not queued or rework")
            if task.get("codex", {}).get("state") in ACTIVE:
                raise ValueError("Task already has an active attempt")
            if task.get("human_gate"):
                gate = mcm.check_gate(root, task["human_gate"], allow_synthetic=False)
                if not gate["ok"]:
                    raise ValueError("Required human gate has not passed")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"ok": not errors, "mode": mode, "errors": errors, "formal_pass": False,
            "native_assurance": "unverified", "registry_modified": False}


def task_contract(task):
    return {k: v for k, v in task.items() if k not in {"status", "updated_at", "codex"}}


def _assert_task_current(root, task):
    claim = task.get("codex", {})
    if claim.get("state") not in ACTIVE:
        raise ValueError("Task has no current active attempt")
    if claim.get("task_contract_sha256") != fingerprint(task_contract(task)):
        raise ValueError("Task contract changed after claim")
    _role(root, claim["role_config"], claim["role_sha256"], task["owner_role"])
    _inputs(root, task)
    return claim


def claim(root, task_id, agent_id, role_config, role_sha, synthetic_demo=False):
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 256:
        raise ValueError("Actual observed agent identifier is required")
    with mcm.registry_lock(root):
        check = preflight(root, task_id, synthetic_demo, _lock_held=True)
        if not check["ok"]:
            raise ValueError("; ".join(check["errors"]))
        rows, task = task_row(root, task_id)
        protected_before = _assert_integrity(root)
        _role(root, role_config, role_sha, task.get("owner_role"))
        if task.get("owner_agent_id") not in {None, agent_id}:
            raise ValueError("Task owner differs from observed agent")
        own_scopes = _scopes(root, task)
        active = [r for r in rows if r.get("codex", {}).get("state") in ACTIVE]
        for other in active:
            if any(_overlap(a, b) for a in own_scopes for b in _scopes(root, other)):
                raise ValueError("Active task owns overlapping paths")
        # No host-wide authenticated capacity observer yet: one outstanding task.
        # A configured slot count and a caller's count do not prove free host slots.
        occupied = [r for r in rows if r.get("codex") and r["codex"].get("runtime_state") not in {"completed", "cancelled", "failed"}]
        if occupied:
            raise ValueError("Host capacity unknown; queue until the active task is accepted")
        task["owner_agent_id"] = agent_id
        task["status"] = "running"
        task["synthetic"] = check["mode"] == "synthetic-demo"
        contract = task_contract(task)
        task["codex"] = {"state": "claimed", "attempt_id": uuid.uuid4().hex, "mode": check["mode"],
                         "role_config": role_config, "role_sha256": role_sha,
                         "task_contract_sha256": fingerprint(contract), "claimed_at": mcm.utcnow(),
                         "runtime_state": "running",
                         "identity_assurance": "captain-observed; native binding not authenticated",
                         "formal_pass": False}
        mcm.save_records(root, "tasks", rows)
        _write_protection(root, protected_before)
    return {"ok": True, "task_id": task_id, **task["codex"], "owner_agent_id": agent_id}


def _file_ref(root, ref, label, within=None):
    if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
        raise ValueError(label + " needs path and SHA256")
    path = inside(root, ref["path"])
    if within and not any(path == base or path.is_relative_to(base) for base in within):
        raise ValueError(label + " is outside allowed paths")
    if not path.is_file() or mcm.file_hash(path) != ref["sha256"]:
        raise ValueError(label + " file SHA256 changed or missing")
    return path


def _skill_checks(root, task, manifest):
    reports = manifest.get("skill_readback", [])
    if not isinstance(reports, list):
        raise ValueError("skill_readback must be a list")
    by_name = {row.get("name"): row for row in reports if isinstance(row, dict)}
    if len(by_name) != len(reports):
        raise ValueError("Duplicate or invalid skill report")
    if set(by_name) != {r.get("name") for r in task.get("required_skills", [])}:
        raise ValueError("Skill readback must match the task-pinned skill set")
    for required in task.get("required_skills", []):
        report = by_name.get(required.get("name"))
        if report is None:
            raise ValueError("Required skill was not reported")
        # Sources are task-pinned project copies, not arbitrary local profile paths.
        source = {"path": required.get("source"), "sha256": required.get("sha256")}
        _file_ref(root, source, "Required skill")
        if report.get("source") != source["path"] or report.get("sha256") != source["sha256"]:
            raise ValueError("Skill readback does not match pinned source")
        status = report.get("status")
        if status not in {"discovered", "read", "executed", "checked"}:
            raise ValueError("Unknown skill use state")
        expected = required.get("required_state", "read")
        order = ["discovered", "read", "executed", "checked"]
        if expected not in order or order.index(status) < order.index(expected):
            raise ValueError("Skill state falls short of task requirement")
        if status != "discovered":
            _file_ref(root, report.get("read_evidence"), "Skill read evidence", _scopes(root, task))
        if status in {"executed", "checked"}:
            evidence = mcm.read_json(_file_ref(root, report.get("execution_evidence"), "Skill execution evidence", _scopes(root, task)))
            if (evidence.get("status") != "succeeded" or evidence.get("exit_code") != 0
                    or evidence.get("skill_sha256") != source["sha256"] or not evidence.get("command")):
                raise ValueError("Skill execution evidence does not establish a successful run")
            if evidence.get("attempt_id") != task["codex"]["attempt_id"]:
                raise ValueError("Skill execution belongs to a different attempt")
            for output in evidence.get("outputs", []):
                _file_ref(root, output, "Skill execution output", _scopes(root, task))
            if not evidence.get("outputs"):
                raise ValueError("Skill execution has no output evidence")
        if status == "checked":
            _file_ref(root, report.get("check_evidence"), "Skill check evidence", _scopes(root, task))


def validate_delivery(root, task, manifest_path):
    current = _assert_task_current(root, task)
    scopes = _scopes(root, task)
    path = inside(root, manifest_path)
    if not any(path.is_relative_to(base) or path == base for base in scopes):
        raise ValueError("Delivery manifest must be inside its task directory")
    data = mcm.read_json(path)
    for field, expected in (("task_id", task["task_id"]), ("attempt_id", current["attempt_id"]),
                            ("author_agent_id", task["owner_agent_id"]), ("role_sha256", current["role_sha256"])):
        if data.get(field) != expected:
            raise ValueError("Delivery has wrong " + field)
    if data.get("inputs") != task.get("inputs", []):
        raise ValueError("Delivery inputs differ from the claimed versions")
    if data.get("synthetic") is not True and current["mode"] == "synthetic-demo":
        raise ValueError("Demo output must be explicitly synthetic")
    outputs = data.get("outputs", [])
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Delivery needs actual output files")
    seen_ids, seen_paths = set(), set()
    expected_outputs = {row.get("artifact_id"): row for row in task.get("outputs", []) if row.get("artifact_id")}
    for output in outputs:
        path = _file_ref(root, output, "Output", scopes)
        identity = output.get("artifact_id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", identity or ""):
            raise ValueError("Invalid output artifact identifier")
        if identity in seen_ids or str(path) in seen_paths:
            raise ValueError("Duplicate output artifact or file")
        seen_ids.add(identity); seen_paths.add(str(path))
        if not isinstance(output.get("version"), int) or isinstance(output.get("version"), bool) or output["version"] < 1:
            raise ValueError("Output needs a positive integer version")
        if not output.get("kind"):
            raise ValueError("Output needs its artifact kind")
        if expected_outputs and identity not in expected_outputs:
            raise ValueError("Undeclared output artifact")
        declared = expected_outputs.get(identity, {})
        for field in ("kind", "path", "version", "generation"):
            if declared.get(field) is not None and output.get(field) != declared[field]:
                raise ValueError("Delivery differs from declared output " + field + ": " + identity)
        if declared.get("owner_role") is not None and declared["owner_role"] != task["owner_role"]:
            raise ValueError("Declared output owner differs from the task owner: " + identity)
        if output.get("owner_role") is not None and output["owner_role"] != task["owner_role"]:
            raise ValueError("Delivery output owner differs from the task owner: " + identity)
        if output.get("kind") in {"result", "verification", "validation", "verification_report"} and not output.get("generation"):
            raise ValueError("Scientific output needs a generation identifier")
    if expected_outputs and set(expected_outputs) != seen_ids:
        raise ValueError("Delivery is missing declared artifacts")
    _skill_checks(root, task, data)
    return data


def deliver(root, task_id, manifest_path):
    # A paused late return is diagnosable without changing any registry or baseline.
    if mcm.pause_state(root)["paused"]:
        _, task = task_row(root, task_id)
        path = inside(root, manifest_path)
        if not any(path == base or path.is_relative_to(base) for base in _scopes(root, task)):
            raise ValueError("Late return must be inside its task directory")
        return {"ok": False, "status": "pending_paused", "task_id": task_id, "manifest": manifest_path,
                "sha256": mcm.file_hash(path), "registry_modified": False, "formal_pass": False}
    with mcm.registry_lock(root):
        _assert_integrity(root)
        if _transaction_pending(root):
            raise ValueError("Unfinished intake transaction")
        rows, task = task_row(root, task_id)
        manifest_sha = mcm.file_hash(inside(root, manifest_path))
        data = validate_delivery(root, task, manifest_path)
        if mcm.file_hash(inside(root, manifest_path)) != manifest_sha:
            raise ValueError("Delivery manifest changed during validation")
        if task["codex"]["state"] != "claimed":
            raise ValueError("Attempt already delivered; create an explicit rework task for changes")
        task["codex"].update(state="delivered", manifest=manifest_path,
                              manifest_sha256=manifest_sha, delivered_at=mcm.utcnow())
        task["status"] = "in_review"
        mcm.save_records(root, "tasks", rows)
    return {"ok": True, "status": "in_review", "task_id": task_id, "attempt_id": data["attempt_id"],
            "manifest_sha256": task["codex"]["manifest_sha256"], "formal_pass": False}


def observe_agent(root, task_id, receipt_path):
    """Record a captain's visible tool observation; this is not a native attestation."""
    with mcm.registry_lock(root):
        _assert_integrity(root)
        rows, task = task_row(root, task_id)
        current = task.get("codex", {})
        if not current.get("attempt_id"):
            raise ValueError("Task has no claimed attempt")
        path = inside(root, receipt_path)
        if path.is_relative_to(inside(root, "tasks/" + task_id)):
            raise ValueError("Runtime observation must be stored outside the author's task")
        receipt = mcm.read_json(path)
        if receipt.get("agent_id") != task.get("owner_agent_id") or receipt.get("attempt_id") != current["attempt_id"]:
            raise ValueError("Runtime observation identity/attempt mismatch")
        if receipt.get("origin") not in {"parent-tool-observation", "simulated"} or not receipt.get("observation_tool"):
            raise ValueError("Observation must identify the actual tool and evidence origin")
        if receipt["origin"] == "simulated" and current.get("mode") != "synthetic-demo":
            raise ValueError("Simulated capacity observations apply only to synthetic demos")
        state = receipt.get("state")
        if state not in {"running", "waiting", "interrupted", "completed", "cancelled", "failed"}:
            raise ValueError("Unknown observed agent state")
        try:
            at = datetime.fromisoformat(receipt.get("observed_at", ""))
            age = (datetime.now(timezone.utc) - at).total_seconds()
            if at.tzinfo is None or not -5 <= age <= 120:
                raise ValueError("Runtime observation is stale")
        except (TypeError, ValueError) as exc:
            raise ValueError("Runtime observation requires a recent timezone timestamp") from exc
        current.update(runtime_state=state, runtime_observation={"path": receipt_path, "sha256": mcm.file_hash(path),
                                                               "origin": receipt["origin"]})
        mcm.save_records(root, "tasks", rows)
    return {"ok": True, "state": state, "local_capacity_released": state in {"completed", "cancelled", "failed"},
            "native_identity_authenticated": False, "formal_pass": False}


def _review(root, task, data, review_path):
    review_file = inside(root, review_path)
    if review_file.is_relative_to(inside(root, "tasks/" + task["task_id"])):
        raise ValueError("Independent review cannot be stored in the author's task directory")
    review = mcm.read_json(review_file)
    reviewer = review.get("verifier_agent_id")
    if not reviewer or reviewer == task["owner_agent_id"]:
        raise ValueError("Non-author reviewer identity is required")
    assigned = task.get("assigned_verifier_agent_id")
    if not assigned or reviewer != assigned:
        raise ValueError("Reviewer must match the captain-assigned verifier")
    if (review.get("task_id") != task["task_id"] or review.get("attempt_id") != data["attempt_id"]
            or review.get("manifest_sha256") != task["codex"]["manifest_sha256"]):
        raise ValueError("Review does not bind this fixed delivery")
    if review.get("status") != "passed" or review.get("unresolved_blockers") != []:
        raise ValueError("Review is not passed or has unresolved blockers")
    expected = [{key: row.get(key) for key in ("artifact_id", "path", "version", "sha256", "generation")} for row in data["outputs"]]
    if review.get("output_refs") != expected:
        raise ValueError("Review is from a different output generation/version")
    if not review.get("checks") or not isinstance(review["checks"], list):
        raise ValueError("Review must provide concrete checks")
    for proof in review["checks"]:
        _file_ref(root, proof, "Review check")
    return review


def accept(root, task_id, review_path):
    with mcm.registry_lock(root):
        protected_before = _assert_integrity(root)
        if _transaction_pending(root):
            raise ValueError("Unfinished intake transaction; inspect recover")
        tasks, task = task_row(root, task_id)
        claim_data = task.get("codex", {})
        if claim_data.get("state") != "delivered":
            raise ValueError("Only a delivered current attempt can be accepted")
        _check_mode(root, claim_data.get("mode") == "synthetic-demo")
        manifest_path = claim_data["manifest"]
        if mcm.file_hash(inside(root, manifest_path)) != claim_data["manifest_sha256"]:
            raise ValueError("Delivered manifest changed after handoff")
        data = validate_delivery(root, task, manifest_path)
        review_sha = mcm.file_hash(inside(root, review_path))
        review = _review(root, task, data, review_path)
        if mcm.file_hash(inside(root, review_path)) != review_sha:
            raise ValueError("Review changed during validation")
        artifacts = mcm.records(root, "artifacts")
        known = {row["artifact_id"] for row in artifacts}
        if any(row["artifact_id"] in known for row in data["outputs"]):
            raise ValueError("Artifact ID already exists; use a new versioned ID instead of overwriting")
        attempt = claim_data["attempt_id"]
        destination = inside(root, CONTROL + "/accepted/" + task_id + "/" + attempt)
        if destination.exists():
            raise ValueError("Intake destination already exists; inspect recovery")
        tx_id = uuid.uuid4().hex
        journal = {"format_version": 1, "state": "prepared", "transaction_id": tx_id,
                   "task_id": task_id, "attempt_id": attempt, "started_at": mcm.utcnow(),
                   "before": {name: mcm.file_hash(inside(root, ".mcm/" + name + ".json")) for name in ("tasks", "artifacts")},
                   "destination": destination.relative_to(Path(root).resolve()).as_posix(),
                   "manifest": {"path": manifest_path, "sha256": claim_data["manifest_sha256"]},
                   "review": {"path": review_path, "sha256": review_sha},
                   "formal_pass": False, "recovery": "inspect-only; never resume or approve automatically"}
        journal_path = inside(root, CONTROL + "/transactions/" + tx_id + ".json")
        mcm.atomic_json(journal_path, journal)
        stage = inside(root, CONTROL + "/staging/" + tx_id)
        stage.mkdir(parents=True, exist_ok=False)
        accepted = []
        for index, output in enumerate(data["outputs"]):
            source = inside(root, output["path"])
            filename = f"{index:03d}-{source.name}"
            target = stage / filename
            shutil.copyfile(source, target)
            if mcm.file_hash(target) != output["sha256"]:
                raise ValueError("Input changed during artifact intake")
            relative = (destination / filename).relative_to(Path(root).resolve()).as_posix()
            row = dict(output, path=relative, original_task_path=output["path"], inputs=deepcopy(task.get("inputs", [])),
                       author_agent_id=task["owner_agent_id"], owner_role=task["owner_role"],
                       status="draft", approval_state="draft", verification_status="pending", verified_by=None,
                       synthetic=claim_data["mode"] == "synthetic-demo", accepted_at=mcm.utcnow(),
                       intake_review={"path": review_path, "sha256": journal["review"]["sha256"],
                                      "verifier_agent_id": review["verifier_agent_id"]},
                       assurance="cooperative intake only; not scientific or human approval")
            artifacts.append(row); accepted.append(row)
        # A copying task must not silently absorb unrelated concurrent writes.
        if protected_files(root) != protected_before:
            raise ValueError("Protected files changed during intake; nothing was accepted")
        for name, expected in journal["before"].items():
            if mcm.file_hash(inside(root, ".mcm/" + name + ".json")) != expected:
                raise ValueError("Registry changed during intake")
        validate_delivery(root, task_row(root, task_id)[1], manifest_path)
        if mcm.file_hash(inside(root, manifest_path)) != claim_data["manifest_sha256"]:
            raise ValueError("Delivered manifest changed during intake")
        if mcm.file_hash(inside(root, review_path)) != journal["review"]["sha256"]:
            raise ValueError("Review changed during intake")
        if mcm.pause_state(root)["paused"]:
            raise ValueError("User paused during intake")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, destination)
        journal["state"] = "files_promoted"
        mcm.atomic_json(journal_path, journal)
        mcm.save_records(root, "artifacts", artifacts)
        task["codex"].update(state="accepted", accepted_at=mcm.utcnow(), intake_transaction=tx_id,
                              accepted_artifact_ids=[row["artifact_id"] for row in accepted])
        # Existing task vocabulary is preserved; scientific review remains separate.
        task["status"] = "in_review"
        mcm.save_records(root, "tasks", tasks)
        expected_protected = dict(protected_before)
        for row in accepted:
            expected_protected[row["path"]] = row["sha256"]
        artifact_bytes = (json.dumps({"format_version": 1, "records": artifacts}, ensure_ascii=False,
                                    indent=2, allow_nan=False) + "\n").encode("utf-8")
        expected_protected[".mcm/artifacts.json"] = hashlib.sha256(artifact_bytes).hexdigest()
        _write_protection(root, expected_protected)
        journal["state"] = "committed"
        journal["after"] = {name: mcm.file_hash(inside(root, ".mcm/" + name + ".json")) for name in ("tasks", "artifacts")}
        mcm.atomic_json(journal_path, journal)
    return {"ok": True, "status": "accepted_for_review", "task_id": task_id,
            "artifact_refs": [{k: row.get(k) for k in ("artifact_id", "path", "version", "sha256", "generation")} for row in accepted],
            "approval_created": False, "formal_pass": False, "independent_review_recorded": True,
            "independent_runtime_identity_authenticated": False}


def recover(root):
    tasks = mcm.records(root, "tasks")
    lock = writer_lock_status(root)
    input_errors = []
    for task in tasks:
        if task.get("codex", {}).get("state") in ACTIVE:
            try:
                _assert_task_current(root, task)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                input_errors.append({"task_id": task["task_id"], "error": str(exc)})
    return {"ok": not lock["present"] and not _transaction_pending(root) and integrity(root)["ok"] and not input_errors,
            "writer_lock": lock,
            "pause": mcm.pause_state(root), "integrity": integrity(root),
            "input_errors": input_errors,
            "unfinished_transactions": _transaction_pending(root),
            "tasks": [{"task_id": row["task_id"], "state": row.get("codex", {}).get("state"),
                       "attempt_id": row.get("codex", {}).get("attempt_id"), "owner_agent_id": row.get("owner_agent_id"),
                       "manifest": row.get("codex", {}).get("manifest"), "inputs": row.get("inputs", [])}
                      for row in tasks if row.get("codex")],
            "next_action": "Recheck inputs and actual agents; inspect pending intake before any explicit repair. No automatic restart.",
            "registry_modified": False, "approval_created": False, "formal_pass": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init-demo", "capabilities", "protect", "recover", "status"):
        commands.add_parser(name)
    item = commands.add_parser("preflight")
    item.add_argument("task", nargs="?"); item.add_argument("--synthetic-demo", action="store_true")
    item = commands.add_parser("claim")
    item.add_argument("task"); item.add_argument("--agent", required=True)
    item.add_argument("--role-config", required=True); item.add_argument("--role-sha", required=True)
    item.add_argument("--synthetic-demo", action="store_true")
    item = commands.add_parser("deliver")
    item.add_argument("task"); item.add_argument("--manifest", required=True)
    item = commands.add_parser("accept")
    item.add_argument("task"); item.add_argument("--review", required=True)
    item = commands.add_parser("observe-agent")
    item.add_argument("task"); item.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "init-demo": result = init_demo(root)
        elif args.command == "capabilities": result = capabilities(root)
        elif args.command == "preflight": result = preflight(root, args.task, args.synthetic_demo)
        elif args.command == "claim": result = claim(root, args.task, args.agent, args.role_config, args.role_sha, args.synthetic_demo)
        elif args.command == "deliver": result = deliver(root, args.task, args.manifest)
        elif args.command == "accept": result = accept(root, args.task, args.review)
        elif args.command == "observe-agent": result = observe_agent(root, args.task, args.receipt)
        elif args.command == "protect": result = protect(root)
        else: result = recover(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "formal_pass": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
