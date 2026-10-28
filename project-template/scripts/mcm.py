#!/usr/bin/env python3
"""Small, local MCM project registry. It does not spawn agents or grant approval."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
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

REGISTRIES = ("tasks", "artifacts", "issues", "decisions")
ID_KEYS = dict(tasks="task_id", artifacts="artifact_id", issues="issue_id", decisions="decision_id")
ARTIFACT_STATES = {"draft", "verified", "approved", "stale", "retracted"}
APPROVAL_STATES = {"draft", "verified", "approved", "invalidated"}
TASK_STATES = {"queued", "running", "in_review", "rework", "approved", "blocked", "cancelled"}
ISSUE_STATES = {"open", "assigned", "fixed_pending_review", "closed", "accepted_risk"}
ROLE_ALIASES = {
    "captain": "mcm-captain", "model_lead": "mcm-model-lead", "modeler": "mcm-modeler",
    "researcher": "mcm-evidence", "evidence": "mcm-evidence", "programmer": "mcm-programmer",
    "verifier": "mcm-verifier", "paper_lead": "mcm-paper-lead", "paper_writer": "mcm-writer",
    "figure_editor": "mcm-figure", "typesetter": "mcm-typesetter", "reviewer": "mcm-reviewer",
    "code_lead": "mcm-code-lead",
}


def canonical_role(role):
    return ROLE_ALIASES.get(role, role)


def timeline(project, at=None):
    config=read_json(Path(project)/'config/runtime.json')
    rules=read_json(resolve_inside(project,config.get('competition_file','config/contest-mcm-2027.json')))
    now=datetime.fromisoformat(at) if at else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Timeline timestamps must include a timezone offset')
    start=datetime.fromisoformat(rules['starts_at']);stop=datetime.fromisoformat(rules['stop_work_at'])
    offsets=config.get('freeze_hours_before_stop',{'model':18,'results':10,'paper':2})
    times={key:stop-timedelta(hours=value) for key,value in offsets.items()}
    state='pre_contest' if now<start else 'active'
    for key in ('model','results','paper'):
        if now>=times[key]:state=key+'_frozen'
    if now>=stop:state='stopped'
    return {'state':state,'at':now.astimezone(start.tzinfo).isoformat(),'run_mode':config.get('run_mode','preparation'),
            'freeze_at':{k:v.isoformat() for k,v in times.items()},'stop_work_at':stop.isoformat(),
            'submit_by':rules['submit_by'],'solution_changes_allowed':now<stop,
            'schedule_source':config.get('competition_file','config/contest-mcm-2027.json')}
GATE_ALIASES = {"H0": "H0_TOPIC", "H1": "H1_MODEL", "H2": "H2_RESULTS", "H3": "H3_RELEASE",
                "G0_TOPIC": "H0_TOPIC", "G1_MODEL": "H1_MODEL", "G2_RESULTS": "H2_RESULTS",
                "G3_PAPER": "H3_RELEASE", "G4_RELEASE": "H3_RELEASE"}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_inside(project, relative, protect_raw=False):
    project = Path(project).resolve()
    given = Path(relative)
    if given.is_absolute() or ".." in given.parts:
        raise ValueError(f"Only project-relative paths without '..' are allowed: {relative}")
    result = (project / given).resolve()
    if not result.is_relative_to(project):
        raise ValueError(f"Path escapes project: {relative}")
    raw = (project / "data" / "raw").resolve()
    if protect_raw and (result == raw or result.is_relative_to(raw)):
        raise ValueError("Original data/raw is read only")
    return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".mcm-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_registry(project, name):
    data = read_json(Path(project) / ".mcm" / f"{name}.json")
    if not isinstance(data, dict) or data.get("format_version") != 1 or not isinstance(data.get("records"), list):
        raise ValueError(f"Invalid {name} registry envelope")
    return data


def records(project, name):
    return load_registry(project, name)["records"]


def save_records(project, name, rows):
    atomic_json(Path(project) / ".mcm" / f"{name}.json", {"format_version": 1, "records": rows})


@contextmanager
def registry_lock(project, actor="captain"):
    if canonical_role(actor) != "mcm-captain":
        raise ValueError("Only captain may merge registry records; workers return proposals")
    if pause_state(project)["paused"]:
        raise ValueError("User pause is active; registry mutations require an actual user resume")
    path = Path(project) / ".mcm" / "write.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Registry writer already active; inspect .mcm/write.lock before recovery") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "actor": actor, "started_at": utcnow()}, stream)
        yield
    finally:
        path.unlink(missing_ok=True)


def descendants(rows, initial):
    affected = set(initial)
    changed = True
    while changed:
        changed = False
        for row in rows:
            identity = row["artifact_id"]
            if identity not in affected and any(i.get("artifact_id") in affected for i in row.get("inputs", [])):
                affected.add(identity)
                changed = True
    return affected


def dependency_closure(artifacts, initial):
    """Resolve upstream IDs; keep unknown IDs so a missing reference cannot disappear."""
    selected, pending = set(initial), list(initial)
    while pending:
        for ref in artifacts.get(pending.pop(), {}).get("inputs", []):
            if not isinstance(ref, dict):
                continue
            identity = ref.get("artifact_id")
            if identity not in selected:
                selected.add(identity)
                pending.append(identity)
    return selected


def reference_errors(project, ref, artifacts):
    """Check one complete reference; legacy refs may omit path, never mix old/new tuples."""
    if not isinstance(ref, dict):
        return ["artifact reference must be an object"]
    identity = ref.get("artifact_id")
    row = artifacts.get(identity)
    if row is None:
        return [f"unknown artifact {identity}"]
    errors = []
    if ref.get("version") != row.get("version") or ref.get("sha256") != row.get("sha256"):
        errors.append(f"stale input version/digest {identity}")
    if "path" in ref and ref["path"] != row.get("path"):
        errors.append(f"reference path does not match artifact {identity}")
    if ref.get("generation") is not None and row.get("generation") is not None and ref["generation"] != row["generation"]:
        errors.append(f"reference generation does not match artifact {identity}")
    try:
        path = resolve_inside(project, row.get("path", ""))
        if not path.is_file():
            errors.append(f"file missing for {identity}: {row.get('path')}")
        elif file_hash(path) != ref.get("sha256"):
            errors.append(f"reference file SHA256 changed for {identity}")
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"invalid reference path for {identity}: {exc}")
    if row.get("status") in {"stale", "retracted"} or row.get("approval_state") == "invalidated":
        errors.append(f"input {identity} is invalidated")
    return errors


def _nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def _complete_review_ref(ref):
    return (isinstance(ref, dict) and all(_nonempty_text(ref.get(k)) for k in ("artifact_id", "path"))
            and isinstance(ref.get("version"), int) and not isinstance(ref["version"], bool) and ref["version"] > 0
            and isinstance(ref.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", ref["sha256"]) is not None)


def _optional_version_matches(row, version):
    # JSON booleans are not artifact versions, even though True == 1 in Python.
    return "version" not in row or (not isinstance(row["version"], bool) and row["version"] == version)


def task_dependency_shape_errors(task):
    """Old strings and {task_id} remain execution dependencies; review must be explicit."""
    dependencies = task.get("depends_on", [])
    if not isinstance(dependencies, list):
        return ["Task dependencies must be a list"]
    errors, seen = [], set()
    for entry in dependencies:
        identity = entry if isinstance(entry, str) else entry.get("task_id") if isinstance(entry, dict) else None
        relation = entry.get("relation", "execution") if isinstance(entry, dict) else "execution"
        if not _nonempty_text(identity) or relation not in ("execution", "review"):
            errors.append("Invalid task dependency relation")
            continue
        if identity in seen or identity == task.get("task_id"):
            errors.append("Duplicate or self task dependency")
        seen.add(identity)
        if relation == "review":
            refs, handoff = entry.get("output_refs"), entry.get("handoff_ref")
            if (not isinstance(refs, list) or not refs or not all(_complete_review_ref(ref) for ref in refs)
                    or not isinstance(handoff, dict) or not _nonempty_text(handoff.get("path"))
                    or not isinstance(handoff.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", handoff["sha256"])):
                errors.append("Review dependency requires complete output refs and handoff SHA256")
            elif len({ref["artifact_id"] for ref in refs}) != len(refs):
                errors.append("Duplicate review output reference")
    return errors


def task_dependency_errors(project, task, tasks, artifacts):
    """Read-only delivery readiness. Context-pack separately checks the full input closure; this grants no Host admission."""
    errors = task_dependency_shape_errors(task)
    if errors:
        return errors
    if len({row.get("task_id") for row in tasks}) != len(tasks):
        return ["Duplicate task identity"]
    for entry in task.get("depends_on", []):
        identity = entry if isinstance(entry, str) else entry["task_id"]
        relation = entry.get("relation", "execution") if isinstance(entry, dict) else "execution"
        producer = next((row for row in tasks if row.get("task_id") == identity), None)
        if producer is None or producer.get("_template_only") is True:
            errors.append("Missing or template task dependency: " + identity)
            continue
        if relation == "execution":
            if producer.get("status") != "approved":
                errors.append("Task dependency is not approved: " + identity)
            continue
        if canonical_role(task.get("owner_role")) not in {"mcm-verifier", "mcm-reviewer"}:
            errors.append("Review dependency requires a review role")
        if producer.get("status") not in {"in_review", "approved"}:
            errors.append("Review producer has not delivered a candidate")
        author = producer.get("owner_agent_id")
        if not _nonempty_text(author) or author.startswith("pending:") or author == task.get("owner_agent_id"):
            errors.append("Review requires an actual non-self author identity")
        try:
            for row in (task, producer):
                value = row.get("project_root")
                if value is not None and (not _nonempty_text(value) or ".." in Path(value).parts
                                          or (Path(project) / value).resolve(strict=True) != Path(project).resolve()):
                    errors.append("Task belongs to another project")
            handoff = entry["handoff_ref"]
            if handoff["path"] != producer.get("completion_handoff_path"):
                errors.append("Review handoff path differs from producer delivery")
            handoff_path = resolve_inside(project, handoff["path"])
            if handoff_path.stat().st_size > 8 * 1024 * 1024 or file_hash(handoff_path) != handoff["sha256"]:
                errors.append("Review handoff SHA256 changed")
            protected = [handoff_path]
            inputs = task.get("inputs", [])
            for ref in entry["output_refs"]:
                if not any(isinstance(i, dict) and all(i.get(k) == ref[k] for k in ("artifact_id", "path", "version", "sha256")) for i in inputs):
                    errors.append("Review output is not a scoped task input")
                artifact = artifacts.get(ref["artifact_id"], {})
                errors.extend(reference_errors(project, ref, artifacts))
                if artifact.get("task_id") != identity or artifact.get("author_agent_id") != author or artifact.get("_template_only") is True:
                    errors.append("Review output author or producer mismatch")
                outputs = producer.get("outputs", [])
                if not isinstance(outputs, list) or not any(isinstance(i, dict) and i.get("artifact_id") == ref["artifact_id"] and i.get("path") == ref["path"] and _optional_version_matches(i, ref["version"]) and ("sha256" not in i or i["sha256"] == ref["sha256"]) for i in outputs):
                    errors.append("Review output was not declared by producer")
                readback = producer.get("output_readback", [])
                if not isinstance(readback, list) or not any(isinstance(i, dict) and all(i.get(k) == ref[k] for k in ("artifact_id", "path", "sha256")) and _optional_version_matches(i, ref["version"]) for i in readback):
                    errors.append("Review output lacks producer delivery readback")
            selected = dependency_closure(artifacts, {ref.get("artifact_id") for ref in inputs if isinstance(ref, dict)})
            protected.extend(resolve_inside(project, artifacts[i]["path"]) for i in selected if i in artifacts)
            for prefix in task.get("allowed_write_paths", []):
                writable = resolve_inside(project, prefix, protect_raw=True)
                if any(path.is_relative_to(writable) for path in protected):
                    errors.append("Review write scope overlaps source evidence")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(f"Invalid review delivery: {exc}")
    return errors


def pause_state(project):
    config = read_json(Path(project) / "config/runtime.json")
    state = config.get("pause_state", {})
    if not isinstance(state, dict):
        raise ValueError("pause_state must be an object")
    return {"paused": state.get("paused") is True or config.get("paused") is True,
            "reason": state.get("reason"), "user_message_ref": state.get("user_message_ref"),
            "recorded_at": state.get("recorded_at"),
            "priority": "actual user pause overrides queued work; only actual user resume releases it"}


def handover_errors(project, task, agent_id):
    handover = task.get("handover") or {}
    if not isinstance(handover, dict):
        return ["Handover must be an object"]
    if not (handover.get("from_agent_id") or handover.get("source_refs")):
        return []
    errors = []
    if handover.get("permission_granted") is not True or handover.get("reclaimed_at"):
        errors.append("Handover permission is missing or reclaimed; old grants do not authorize writing")
    if handover.get("to_agent_id") != agent_id:
        errors.append("Handover recipient does not match actual agent")
    try:
        expiry = datetime.fromisoformat(handover.get("permission_expires_at") or "")
        if expiry.tzinfo is None or datetime.now(timezone.utc) >= expiry:
            errors.append("Handover permission has expired or lacks a timezone")
    except (TypeError, ValueError):
        errors.append("Handover requires a valid explicit permission expiry with timezone")
    for source in handover.get("source_refs", []):
        try:
            path = resolve_inside(project, source["path"])
            if file_hash(path) != source.get("sha256"):
                errors.append("Handover source SHA256 changed; renew handover before writing")
        except (OSError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"Invalid handover source: {exc}")
    return errors


def invalidate_artifacts(project, artifact_ids, reason):
    rows = records(project, "artifacts")
    known = {r["artifact_id"] for r in rows}
    if set(artifact_ids) - known:
        raise ValueError(f"Unknown artifacts: {sorted(set(artifact_ids) - known)}")
    affected = descendants(rows, artifact_ids)
    for row in rows:
        if row["artifact_id"] in affected:
            row.update(status="stale", approval_state="invalidated", verification_status="pending",
                       reproduced=False, invalidated_at=utcnow(), invalidation_reason=reason)
    save_records(project, "artifacts", rows)
    gates_path = Path(project) / "config" / "gates.json"
    if gates_path.exists():
        data = read_json(gates_path)
        for gate in data.get("records", []):
            if any(ref.get("artifact_id") in affected for ref in gate.get("scope_refs", [])):
                gate.update(status="invalidated", invalidation_reason=reason)
        atomic_json(gates_path, data)
    return sorted(affected)


def _record_errors(name, rows):
    errors, seen = [], set()
    key = ID_KEYS[name]
    for row in rows:
        identity = row.get(key)
        if not isinstance(identity, str) or not identity:
            errors.append(f"{name}: missing {key}")
        elif identity in seen:
            errors.append(f"{name}: duplicate {identity}")
        seen.add(identity)
        if name == "tasks" and row.get("status") not in TASK_STATES:
            errors.append(f"{identity}: invalid task status")
        if name == "tasks":
            errors.extend(f"{identity}: {message}" for message in task_dependency_shape_errors(row))
            for field in ("required_skills", "skill_readback", "output_readback"):
                if field in row and not isinstance(row[field], list):
                    errors.append(f"{identity}: {field} must be a list when present")
        if name == "artifacts":
            if row.get("status") not in ARTIFACT_STATES:
                errors.append(f"{identity}: invalid artifact status")
            if row.get("approval_state") not in APPROVAL_STATES:
                errors.append(f"{identity}: missing/invalid approval_state")
            if not isinstance(row.get("version"), int) or isinstance(row.get("version"), bool) or row["version"] < 1:
                errors.append(f"{identity}: version must be a positive integer")
            if row.get("verification_status") not in {"pending", "passed", "failed"}:
                errors.append(f"{identity}: invalid verification_status")
            if not isinstance(row.get("inputs", []), list):
                errors.append(f"{identity}: inputs must be artifact references")
            elif any(not isinstance(ref, dict) for ref in row.get("inputs", [])):
                errors.append(f"{identity}: every input reference must be an object")
        if name == "issues":
            if row.get("status") not in ISSUE_STATES:
                errors.append(f"{identity}: invalid issue status")
            if row.get("severity") not in {"blocker", "major", "minor", "suggestion"}:
                errors.append(f"{identity}: invalid issue severity")
            if row.get("severity") == "blocker" and row.get("status") == "accepted_risk":
                errors.append(f"{identity}: blocker cannot be accepted as risk")
            if row.get("status") == "closed":
                if not row.get("closed_by") or row.get("closed_by") == row.get("author_agent_id"):
                    errors.append(f"{identity}: issue requires a non-author verifier")
                if not row.get("verification_evidence"):
                    errors.append(f"{identity}: closed issue missing verification evidence")
                if not row.get("reported_by") or row.get("closed_by") not in {row.get("reported_by"),row.get("assigned_verifier_agent_id")}:
                    errors.append(f"{identity}: closure must be by the original or captain-assigned reviewer")
    return errors


def validate_project(project, strict=False, allow_synthetic=False, artifact_scope=None):
    errors, warnings, registry = [], [], {}
    for name in REGISTRIES:
        try:
            registry[name] = records(project, name)
            errors += _record_errors(name, registry[name])
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{name}: {exc}")
            registry[name] = []
    artifacts = {r.get("artifact_id"): r for r in registry["artifacts"]}
    roots = (set(artifact_scope) if artifact_scope is not None else
             {identity for identity, row in artifacts.items() if row.get("status") not in {"stale", "retracted"}})
    if artifact_scope is None:
        gates_path = Path(project) / "config/gates.json"
        if gates_path.exists():
            for gate in read_json(gates_path).get("records", []):
                if not gate.get("retired") and gate.get("status") in {"pending", "approved", "invalidated"}:
                    roots.update(ref.get("artifact_id") for ref in gate.get("scope_refs", []) if isinstance(ref, dict))
    selected = dependency_closure(artifacts, roots)
    for identity in selected - artifacts.keys():
        errors.append(f"Unknown artifact in current dependency closure: {identity}")
    for identity, artifact in artifacts.items():
        if identity not in selected:
            if artifact.get("status") in {"stale", "retracted"}:
                warnings.append(f"{identity}: historical {artifact['status']} retained outside current dependency closure")
            continue
        try:
            path = resolve_inside(project, artifact.get("path", ""))
            if not path.is_file():
                errors.append(f"{identity}: file missing: {artifact.get('path')}")
            elif file_hash(path) != artifact.get("sha256"):
                errors.append(f"{identity}: file SHA256 changed; refresh/invalidate downstream")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{identity}: {exc}")
        for ref in artifact.get("inputs", []):
            errors.extend(f"{identity}: {message}" for message in reference_errors(project, ref, artifacts))
        if artifact.get("status") in {"stale", "retracted"} or artifact.get("approval_state") == "invalidated":
            errors.append(f"{identity}: artifact is {artifact['status']}")
        if strict:
            if artifact.get("synthetic") and not allow_synthetic:
                errors.append(f"{identity}: synthetic artifact cannot pass a real contest gate")
            if artifact.get("verification_status") != "passed":
                errors.append(f"{identity}: verification has not passed")
            if artifact.get("reproduction_required", artifact.get("kind") in {"result", "figure", "table", "paper"}) and not artifact.get("reproduced"):
                errors.append(f"{identity}: reproduction has not passed")
            if artifact.get("citations_required", artifact.get("kind") in {"evidence", "literature", "data", "model", "paper"}) and not artifact.get("citations_verified"):
                errors.append(f"{identity}: citations are unverified")
            if artifact.get("verification_status") == "passed" and artifact.get("verified_by") == artifact.get("author_agent_id"):
                errors.append(f"{identity}: author cannot provide independent verification")
            if artifact.get("verification_status") == "passed" and not artifact.get("verified_by"):
                errors.append(f"{identity}: independent verifier identity is missing")
            if artifact.get("kind") == "result":
                report_ref = artifact.get("verification_report")
                if not report_ref:
                    errors.append(f"{identity}: result missing independent verification report")
                else:
                    try:
                        report = read_json(resolve_inside(project, report_ref["path"]))
                        if file_hash(resolve_inside(project, report_ref["path"])) != report_ref.get("sha256"):
                            errors.append(f"{identity}: verification report digest changed")
                        if report.get("status") != "passed" or report.get("result_sha256") != artifact.get("sha256"):
                            errors.append(f"{identity}: verification report failed or applies to old results")
                        if artifact.get("generation") is not None and report.get("result_generation", report.get("generation")) != artifact["generation"]:
                            errors.append(f"{identity}: verification report applies to a different or missing result generation")
                        if report.get("reproduction_passed") is not True:
                            errors.append(f"{identity}: independent reproduction failed")
                        if report.get("verifier_agent_id") != artifact.get("verified_by") or report.get("verifier_agent_id") == artifact.get("author_agent_id"):
                            errors.append(f"{identity}: verification report does not name an independent matching verifier")
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        errors.append(f"{identity}: invalid verification report: {exc}")
    visiting, visited = set(), set()
    def visit(identity):
        if identity in visiting:
            errors.append(f"{identity}: cyclic artifact dependencies")
            return
        if identity in visited:
            return
        visiting.add(identity)
        for ref in artifacts.get(identity, {}).get("inputs", []):
            if ref.get("artifact_id") in artifacts:
                visit(ref["artifact_id"])
        visiting.remove(identity)
        visited.add(identity)
    for identity in selected:
        visit(identity)
    for issue in registry["issues"]:
        linked = {ref.get("artifact_id") for ref in issue.get("artifact_refs", [])}
        historical_issue = bool(linked) and not (linked & selected)
        if historical_issue:
            if issue.get("status") not in {"closed", "accepted_risk"}:
                warnings.append(f"{issue.get('issue_id')}: issue outside current dependency closure remains {issue.get('status')}")
            continue
        if issue.get("severity") == "blocker" and issue.get("status") != "closed":
            errors.append(f"{issue['issue_id']}: unclosed blocker")
        elif issue.get("status") not in {"closed", "accepted_risk"}:
            warnings.append(f"{issue.get('issue_id')}: unresolved {issue.get('severity')}")
        if issue.get("status") == "closed":
            for proof in issue.get("verification_evidence", []):
                try:
                    path = resolve_inside(project, proof["path"])
                    content = read_json(path)
                    if file_hash(path) != proof.get("sha256") or content.get("status") != "passed":
                        errors.append(f"{issue['issue_id']}: closure evidence changed or failed")
                    if content.get("verifier_agent_id") != issue.get("closed_by") or content.get("issue_id") != issue.get("issue_id"):
                        errors.append(f"{issue['issue_id']}: closure evidence identity mismatch")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    errors.append(f"{issue['issue_id']}: invalid closure evidence: {exc}")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "counts": {name: len(rows) for name, rows in registry.items()},
            "strict": strict, "synthetic_allowed": allow_synthetic,
            "artifact_scope": sorted(selected, key=str), "scope_mode": "explicit" if artifact_scope is not None else "current_dependency_closure"}


def check_gate(project, gate_id, allow_synthetic=False):
    gate_id = GATE_ALIASES.get(gate_id, gate_id)
    gates = read_json(Path(project) / "config" / "gates.json").get("records", [])
    gate = next((g for g in gates if g.get("gate_id") == gate_id), None)
    by_id = {r["artifact_id"]: r for r in records(project, "artifacts")}
    selected = dependency_closure(by_id, {ref.get("artifact_id") for ref in (gate or {}).get("scope_refs", [])})
    report = validate_project(project, strict=True, allow_synthetic=allow_synthetic, artifact_scope=selected)
    errors = report["errors"]
    if not gate:
        errors.append(f"Unknown gate {gate_id}")
    else:
        if gate.get("status") != "approved":
            errors.append(f"{gate_id}: human decision is {gate.get('status', 'missing')}")
        if not gate.get("approved_by") or not gate.get("approved_at"):
            errors.append(f"{gate_id}: missing recorded human approval")
        decisions = records(project, "decisions")
        decision = next((d for d in decisions if d.get("decision_id") == gate.get("decision_id")), None)
        if not decision or decision.get("decision_type") != "human_gate" or decision.get("decision") != "approve":
            errors.append(f"{gate_id}: missing human_gate approval decision")
        elif decision.get("synthetic") and not allow_synthetic:
            errors.append(f"{gate_id}: synthetic decision cannot approve real work")
        elif decision.get("scope_refs") != gate.get("scope_refs"):
            errors.append(f"{gate_id}: decision scope does not match gate scope")
        if decision:
            if not decision.get("user_message_ref") or not decision.get("user_confirmation_text"):
                errors.append(f"{gate_id}: missing actual human confirmation text/reference")
            if decision.get("approved_by") != gate.get("approved_by") or decision.get("approved_at") != gate.get("approved_at"):
                errors.append(f"{gate_id}: human approval identity/time differs from the decision")
        if not gate.get("scope_refs"):
            errors.append(f"{gate_id}: approval must bind exact artifact versions and digests")
        for ref in gate.get("scope_refs", []):
            row = by_id.get(ref.get("artifact_id"), {})
            ref_errors = reference_errors(project, ref, by_id)
            errors.extend(f"{gate_id}: approved scope is stale: {message}" for message in ref_errors)
            if row.get("approval_state") != "approved":
                errors.append(f"{gate_id}: artifact not approved: {ref.get('artifact_id')}")
            if gate_id == "H2_RESULTS" and (row.get("kind") not in {"model", "result", "verification", "validation", "verification_report", "contract"}
                                            or str(row.get("path", "")).lower().endswith(".pdf")):
                errors.append(f"{gate_id}: scope must bind model/results/verification, not the mutable paper/PDF: {ref.get('artifact_id')}")
    if gate_id == "H3_RELEASE":
        h2 = check_gate(project, "H2_RESULTS", allow_synthetic=allow_synthetic)
        errors.extend(f"{gate_id}: valid H2 required: {message}" for message in h2["errors"])
        report["h2_check"] = {"ok": h2["ok"], "artifact_scope": h2["artifact_scope"]}
        paper_ids = {ref.get("artifact_id") for ref in (gate or {}).get("scope_refs", [])
                     if by_id.get(ref.get("artifact_id"), {}).get("kind") == "paper"
                     and str(by_id.get(ref.get("artifact_id"), {}).get("path", "")).lower().endswith(".pdf")}
        if len(paper_ids) != 1:
            errors.append(f"{gate_id}: approved scope must directly bind exactly one final paper PDF artifact")
        paper_closure = dependency_closure(by_id, paper_ids)
        consumed_results = {identity for identity in paper_closure if by_id.get(identity, {}).get("kind") == "result"}
        if not consumed_results:
            errors.append(f"{gate_id}: final PDF must declare the results it consumes in its dependency closure")
        for identity in consumed_results - set(h2["artifact_scope"]):
            errors.append(f"{gate_id}: final PDF consumes result outside the current H2 scope: {identity}")
        consumed_science = {identity for identity in paper_closure
                            if by_id.get(identity, {}).get("kind") in {"model", "verification", "validation", "verification_report"}}
        for identity in consumed_science - set(h2["artifact_scope"]):
            errors.append(f"{gate_id}: final PDF consumes scientific artifact outside the current H2 scope: {identity}")
        report["paper_artifacts"] = sorted(paper_ids)
        report["consumed_result_artifacts"] = sorted(consumed_results)
    report.update(ok=not errors, gate_id=gate_id, action="check only; no approval created")
    return report


def refresh_artifact(project, identity, reason):
    rows = records(project, "artifacts")
    row = next((r for r in rows if r.get("artifact_id") == identity), None)
    if not row:
        raise ValueError(f"Unknown artifact {identity}")
    digest = file_hash(resolve_inside(project, row["path"]))
    if digest == row.get("sha256"):
        return {"changed": False, "artifact_id": identity, "invalidated": []}
    affected = invalidate_artifacts(project, [identity], reason)
    rows = records(project, "artifacts")
    row = next(r for r in rows if r["artifact_id"] == identity)
    row.update(version=row["version"] + 1, sha256=digest, status="draft", approval_state="draft",
               verification_status="pending", reproduced=False, citations_verified=False,
               verified_by=None, verification_report=None)
    save_records(project, "artifacts", rows)
    return {"changed": True, "artifact_id": identity, "version": row["version"], "invalidated": affected}


def write_output(project, relative, content, actor, task_id=None, agent_id=None):
    path = resolve_inside(project, relative, protect_raw=True)
    config = read_json(Path(project) / "config" / "runtime.json")
    if pause_state(project)["paused"]:
        raise ValueError("User pause is active; solution/output writes require an actual user resume")
    actor = canonical_role(actor)
    allowed = config.get("partition_ownership", {}).get(actor, [])
    rel = path.relative_to(Path(project).resolve()).as_posix()
    if config.get('run_mode')=='contest' and not timeline(project)['solution_changes_allowed']:
        if rel.split('/')[0] not in {'logs','reviews','audit','.mcm'}:
            raise ValueError('Official stop-work time has passed; solution writes are blocked')
    if not any(rel == prefix or rel.startswith(prefix.rstrip("/") + "/") for prefix in allowed):
        raise ValueError(f"{actor} does not own output partition {relative}")
    if actor != "mcm-captain":
        if not task_id or not agent_id:
            raise ValueError("Worker writes require task_id and agent_id from the actual dispatched task")
        task = next((t for t in records(project, "tasks") if t.get("task_id") == task_id), None)
        if not task or canonical_role(task.get("owner_role")) != actor or task.get("owner_agent_id") != agent_id:
            raise ValueError("Task owner role/agent does not match this writer")
        if task.get("status") not in {"running", "rework"}:
            raise ValueError("Worker may write only a running or rework task")
        handover_problems = handover_errors(project, task, agent_id)
        if handover_problems:
            raise ValueError("; ".join(handover_problems))
        scopes = task.get("allowed_write_paths", [])
        for prefix in scopes:
            resolve_inside(project, prefix, protect_raw=True)
        if not any(rel == p.rstrip("/") or rel.startswith(p.rstrip("/")+"/") for p in scopes):
            raise ValueError("Output is outside the task's allowed_write_paths")
        for other in records(project, "tasks"):
            if other.get("task_id") == task_id or other.get("status") not in {"running", "rework"}:
                continue
            if other.get("owner_agent_id") == agent_id:
                continue
            for prefix in other.get("allowed_write_paths", []):
                normalized = resolve_inside(project, prefix, protect_raw=True).relative_to(Path(project).resolve()).as_posix().rstrip("/")
                if rel == normalized or rel.startswith(normalized + "/"):
                    raise ValueError(f"Another active task owns this file range: {other.get('task_id')}; obtain an explicit handover")
        if rel.startswith("tasks/") and not rel.startswith(f"tasks/{task_id}/"):
            raise ValueError("Worker cannot write another task's private directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
    return {"path": rel, "sha256": file_hash(path), "owner_role": actor, "overwritten": False}


def close_issue(project, issue_id, verifier, evidence):
    rows = records(project, "issues")
    row = next((r for r in rows if r.get("issue_id") == issue_id), None)
    if not row:
        raise ValueError(f"Unknown issue {issue_id}")
    if verifier == row.get("author_agent_id"):
        raise ValueError("The author of the affected work cannot close the review issue")
    if not row.get("reported_by") or verifier not in {row.get("reported_by"),row.get("assigned_verifier_agent_id")}:
        raise ValueError("Closure requires the original or captain-assigned reviewer")
    if row.get("status") != "fixed_pending_review":
        raise ValueError("Issue must be fixed_pending_review before independent closure")
    path = resolve_inside(project, evidence)
    proof = read_json(path)
    if proof.get("status") != "passed" or proof.get("verifier_agent_id") != verifier or proof.get("issue_id") != issue_id:
        raise ValueError("Verification evidence must record matching issue, independent verifier and passed status")
    row.update(status="closed", closed_by=verifier, closed_at=utcnow(),
               verification_evidence=[{"path": evidence, "sha256": file_hash(path)}])
    save_records(project, "issues", rows)
    return row


def snapshot_project(project, label):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", label):
        raise ValueError("Snapshot label must contain 1-64 ASCII letters, digits, dots, underscores or dashes")
    report = validate_project(project)
    if not report["ok"]:
        raise ValueError("Cannot snapshot invalid project: " + "; ".join(report["errors"]))
    project = Path(project).resolve()
    target = project / ".mcm" / "snapshots" / label
    if target.exists():
        raise ValueError("Snapshot already exists; snapshots are immutable")
    candidates, raw_inputs = [], []
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(project)
        if any(p in {".venv", ".git", "__pycache__", "snapshots", "restored"} for p in rel.parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(project):
            raise ValueError(f"Snapshot refuses symlink/reparse traversal: {rel}")
        if rel.as_posix().startswith("data/raw/"):
            raw_inputs.append({"path": rel.relative_to(Path("data/raw")).as_posix(), "sha256": file_hash(path)})
            continue
        if rel.name in {"write.lock", "last-good.json"}:
            continue
        candidates.append((path, rel))
    target.mkdir(parents=True)
    manifest = {"format_version": 1, "label": label, "created_at": utcnow(), "integrity_validated": True,
                "scientific_approval_implied": False, "original_raw_root": str(project / "data" / "raw"),
                "raw_inputs": raw_inputs, "files": []}
    for source, rel in candidates:
        destination = target / "files" / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest["files"].append({"path": rel.as_posix(), "sha256": file_hash(destination)})
    atomic_json(target / "manifest.json", manifest)
    atomic_json(project / ".mcm" / "last-good.json", {"label": label, "manifest_sha256": file_hash(target / "manifest.json")})
    return {"snapshot": label, "files": len(candidates), "path": str(target), "raw_data_copied": False}


def restore_snapshot(project, label, destination=None):
    project = Path(project).resolve()
    expected_manifest_digest = None
    if label == "last-good":
        pointer = read_json(project / ".mcm" / "last-good.json")
        label, expected_manifest_digest = pointer["label"], pointer["manifest_sha256"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", label):
        raise ValueError("Invalid snapshot label")
    source = resolve_inside(project, f".mcm/snapshots/{label}")
    manifest_path = source / "manifest.json"
    if expected_manifest_digest and file_hash(manifest_path) != expected_manifest_digest:
        raise ValueError("Last-good manifest digest mismatch")
    manifest = read_json(manifest_path)
    dest_rel = destination or f".mcm/restored/{label}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
    target = resolve_inside(project, dest_rel, protect_raw=True)
    restore_root = (project / ".mcm" / "restored").resolve()
    if target == restore_root or not target.is_relative_to(restore_root):
        raise ValueError("Restore destination must be a NEW directory inside .mcm/restored")
    if target.exists():
        raise ValueError("Restore refuses to overwrite an existing directory")
    for item in manifest["files"]:
        original = resolve_inside(source / "files", item["path"])
        resolve_inside(target, item["path"], protect_raw=True)
        if file_hash(original) != item["sha256"]:
            raise ValueError(f"Snapshot file digest mismatch: {item['path']}")
    raw_root = Path(manifest.get("original_raw_root", project / "data/raw")).resolve()
    for item in manifest.get("raw_inputs", []):
        original = resolve_inside(raw_root, item["path"])
        if file_hash(original) != item["sha256"]:
            raise ValueError(f"Original raw data changed since snapshot; recover the immutable original first: {item['path']}")
        resolve_inside(target / "data/raw", item["path"])
    target.mkdir(parents=True)
    for item in manifest["files"]:
        original = source / "files" / item["path"]
        destination_path = target / item["path"]
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination_path)
    for item in manifest.get("raw_inputs", []):
        original = resolve_inside(raw_root, item["path"])
        destination_path = resolve_inside(target / "data/raw", item["path"])
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination_path)
        # New workspace gets a verified copy; original data is never written.
        destination_path.chmod(destination_path.stat().st_mode & ~0o222)
    atomic_json(target / ".mcm" / "resume.json", {"from_snapshot": label, "restored_at": utcnow(),
                "original_raw_root": manifest.get("original_raw_root"), "raw_data_not_overwritten": True,
                "raw_data_copied_to_new_workspace": True, "requires_raw_data_read_only_rebind": False})
    return {"restored_to": str(target), "snapshot": label, "overwrote_live_project": False,
            "raw_data_not_overwritten": True, "raw_inputs_verified_and_copied": len(manifest.get("raw_inputs", [])),
            "next": "Validate the recovered workspace, then explicitly choose it; live project and original raw inputs were not overwritten"}


def runtime_capacity(project, snapshot=None, reserve_task=False):
    config = read_json(Path(project) / "config" / "runtime.json")
    raw = read_json(snapshot) if snapshot else {"records": []}
    if raw.get("allocation_scope") == "root-activation-pool":
        return root_pool_advisory(project, config, raw, snapshot, reserve_task)
    rows = raw.get("records")
    if not isinstance(rows, list):
        raise ValueError("Normalize listRuntime into {records:[{agent_id,state,is_root,role}]} before import")
    allocated = []
    for row in rows:
        if not row.get("agent_id") or row.get("state") not in {"running", "waiting", "starting", "paused", "completed", "cancelled", "failed"}:
            raise ValueError("Runtime record needs agent_id and a known state")
        if not row.get("is_root", False) and row["state"] in {"running", "waiting", "starting", "paused"}:
            allocated.append(row)
    normal, reserve = config["normal_slots"], config["reserve_slots"]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (normal, reserve)):
        raise ValueError("Configured normal/reserve slots must be non-negative integers")
    host = raw.get("host_capacity", {})
    limit = host.get("max_active_descendants")
    host_verified = (host.get("verified") is True and isinstance(limit, int) and not isinstance(limit, bool)
                     and limit > 0 and bool(host.get("evidence_ref")))
    maximum_age = config.get("capacity_snapshot_max_age_seconds", 60)
    if not isinstance(maximum_age, (int, float)) or isinstance(maximum_age, bool) or maximum_age <= 0:
        raise ValueError("capacity_snapshot_max_age_seconds must be positive")
    snapshot_age = None
    try:
        captured_at = datetime.fromisoformat(raw.get("captured_at") or "")
        if captured_at.tzinfo is not None:
            snapshot_age = (datetime.now(timezone.utc) - captured_at).total_seconds()
    except (TypeError, ValueError):
        pass
    fresh = snapshot_age is not None and -5 <= snapshot_age <= maximum_age
    effective_limit = min(normal + reserve, limit) if host_verified else None
    # Reserve survives a smaller Host limit; do not let configured normal slots
    # consume the emergency allocation when project and Host totals differ.
    effective_normal = min(normal, max(0, effective_limit - reserve)) if host_verified else None
    used = len(allocated)
    paused = pause_state(project)["paused"]
    global_count_known = snapshot is not None and raw.get("allocation_scope") == "host"
    known = host_verified and global_count_known and fresh
    return {"allocated": used, "normal_slots": normal, "reserve_slots": reserve,
            "normal_available": max(0, effective_normal - used) if known else None,
            "reserve_available": max(0, effective_limit - max(effective_normal, used)) if known else None,
            "configured_normal_available": max(0, normal - used),
            "admit_one_task": (known and not paused and
                               used < (effective_limit if reserve_task else effective_normal)),
            "capacity_known": known, "host_allocation_count_known": global_count_known,
            "allocation_count_known": snapshot is not None,
            "host_capacity_verified": host_verified, "host_max_active_descendants": limit if host_verified else None,
            "snapshot_fresh": fresh, "snapshot_age_seconds": snapshot_age,
            "snapshot_max_age_seconds": maximum_age,
            "configured_total": normal + reserve, "effective_total": effective_limit,
            "effective_normal_slots": effective_normal,
            "team_member_limit": raw.get("team_member_limit"),
            "team_limit_is_host_capacity": False, "user_paused": paused,
            "reserve_requested": reserve_task, "over_capacity": used > (effective_limit if host_verified else normal + reserve),
            "waiting_supervisors_counted": True, "root_excluded": True,
            "source": str(snapshot) if snapshot else "no runtime snapshot supplied; capacity calculation only",
            "does_not_spawn_or_control_dsh": True, "allocated_agents": [r["agent_id"] for r in allocated]}


def root_pool_advisory(project, config, raw, snapshot, reserve_task=False):
    """Parse a scoped capture without pretending to verify its native ledger.

    This CLI runs outside the loaded plugin process. Even perfectly formed JSON
    cannot prove the exact live caller/service/pool or a process-local capture.
    Only the mounted native preflight can make an actual admission decision.
    """
    def integer(value, minimum=0):
        return isinstance(value, int) and not isinstance(value, bool) and value >= minimum

    def identity(value):
        return isinstance(value, str) and 0 < len(value) <= 256 and bool(value.strip())

    if raw.get("schema_version") != 1 or isinstance(raw.get("schema_version"), bool):
        raise ValueError("Root pool snapshot requires schema_version=1")
    for key in ("root_agent_id", "caller_agent_id", "allocation_domain_id", "capture_id"):
        if not identity(raw.get(key)):
            raise ValueError("Root pool snapshot requires bounded " + key)
    rows, pool, gaps = raw.get("records"), raw.get("pool_capacity"), raw.get("coverage_gaps")
    if not isinstance(rows, list) or len(rows) > 1024 or not isinstance(pool, dict):
        raise ValueError("Root pool records/capacity have unsupported structure")
    if not isinstance(gaps, list) or len(gaps) > 32 or any(not isinstance(gap, str) or len(gap) > 200 for gap in gaps):
        raise ValueError("Root pool coverage_gaps must be a bounded string list")
    for row in rows:
        if (not isinstance(row, dict) or not identity(row.get("agent_id")) or
                not isinstance(row.get("kind"), str) or row.get("kind") not in {"local", "external"} or
                not isinstance(row.get("closing"), bool)):
            raise ValueError("Root pool record requires agent_id, local/external kind and boolean closing")
    ids = [row["agent_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Root pool records contain duplicate agent identity")
    if raw["root_agent_id"] in ids:
        raise ValueError("Root pool records must exclude the root")
    limit, reserved, pending = (pool.get(key) for key in ("max_active_descendants", "reserved_slots", "pending_materializations"))
    if not integer(limit, 1) or not integer(reserved) or not integer(pending) or not isinstance(pool.get("verified"), bool):
        raise ValueError("Root pool capacity needs integer limit/counts and boolean verified")
    normal, reserve = config["normal_slots"], config["reserve_slots"]
    if not integer(normal) or not integer(reserve):
        raise ValueError("Configured normal/reserve slots must be non-negative integers")
    maximum_age = config.get("capacity_snapshot_max_age_seconds", 60)
    if not isinstance(maximum_age, (int, float)) or isinstance(maximum_age, bool) or maximum_age <= 0:
        raise ValueError("capacity_snapshot_max_age_seconds must be positive")
    age = None
    try:
        captured = datetime.fromisoformat(raw.get("captured_at") or "")
        if captured.tzinfo is not None:
            age = (datetime.now(timezone.utc) - captured).total_seconds()
    except (TypeError, ValueError):
        pass
    fresh = age is not None and -5 <= age <= maximum_age
    reconciled = reserved == len(rows) and pending == 0 and not gaps
    structurally_complete = reconciled and pool["verified"] is True
    total = min(normal + reserve, limit)
    normal_limit = min(normal, max(0, total - reserve))
    advisory_known = structurally_complete and fresh
    paused = pause_state(project)["paused"]
    selected_limit = total if reserve_task else normal_limit
    return {"allocation_scope": "root-activation-pool", "root_agent_id": raw["root_agent_id"],
            "caller_agent_id": raw["caller_agent_id"], "allocation_domain_id": raw["allocation_domain_id"],
            "allocated": len(rows), "reserved_slots_declared": reserved, "pending_materializations_declared": pending,
            "records_reconciled": reconciled, "coverage_gaps": gaps,
            "normal_slots": normal, "reserve_slots": reserve, "configured_total": normal + reserve,
            "normal_available": None, "reserve_available": None,
            "advisory_effective_total": total, "advisory_effective_normal_slots": normal_limit,
            "advisory_available": max(0, selected_limit - reserved) if advisory_known else None,
            "advisory_normal_available": max(0, normal_limit - reserved) if advisory_known else None,
            "advisory_reserve_available": max(0, total - max(normal_limit, reserved)) if advisory_known else None,
            "advisory_can_admit": (advisory_known and not paused and raw.get("admit_one_task") is not False and reserved < selected_limit),
            "capacity_known": False, "admit_one_task": False, "native_validation_required": True,
            "native_capture_ledger_verified": False, "pool_capacity_verified": False,
            "pool_capacity_declared_verified": pool["verified"], "pool_max_active_descendants_declared": limit,
            "host_allocation_count_known": False, "host_capacity_verified": False,
            "host_max_active_descendants": None, "allocation_count_known": reconciled,
            "effective_total": None, "effective_normal_slots": None,
            "snapshot_fresh": fresh, "snapshot_age_seconds": age, "snapshot_max_age_seconds": maximum_age,
            "team_limit_is_host_capacity": False, "user_paused": paused, "reserve_requested": reserve_task,
            "waiting_supervisors_counted": True, "closing_residents_counted": True, "root_excluded": True,
            "source": str(snapshot), "does_not_spawn_or_control_dsh": True, "allocated_agents": ids,
            "next": "Obtain a fresh capture for this exact manager in the mounted plugin process, then call mcm_dispatch_preflight; this offline JSON report never grants admission."}


def context_pack(project, task_id):
    """Return bounded task context, not a copy of session history or all registries."""
    tasks = records(project, "tasks")
    task = next((r for r in tasks if r.get("task_id") == task_id), None)
    if task is None:
        raise ValueError(f"Unknown task {task_id}")
    config = read_json(Path(project) / "config/runtime.json")
    limit = config.get("context_pack_max_items", 40)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("context_pack_max_items must be a positive integer")
    artifact_rows = records(project, "artifacts")
    artifacts = {r["artifact_id"]: r for r in artifact_rows}
    inputs = task.get("inputs", [])
    if not isinstance(inputs, list):
        raise ValueError("Task inputs must be artifact references")
    selected = dependency_closure(artifacts, {ref.get("artifact_id") for ref in inputs if isinstance(ref, dict)})
    errors, warnings = task_dependency_errors(project, task, tasks, artifacts), []
    if len(artifacts) != len(artifact_rows):
        errors.append("Duplicate task input artifact")
    if canonical_role(task.get("owner_role")) not in config.get("partition_ownership", {}):
        errors.append("Task requires a configured owner_role")
    if not task.get("owner_agent_id"):
        errors.append("Task requires actual owner_agent_id")
    if not task.get("allowed_write_paths") and task.get("read_only") is not True:
        errors.append("Task requires explicit allowed_write_paths or read_only=true")
    if not task.get("acceptance_criteria"):
        errors.append("Task requires acceptance_criteria")
    skills = task.get("required_skills", [])
    if not isinstance(skills, list):
        errors.append("Task required_skills must be a list")
        skills = []
    elif any(not isinstance(s, dict) or not s.get("name") or not s.get("source") for s in skills):
        errors.append("Every required skill must name its SKILL.md source and skill name")
    errors.extend(handover_errors(project, task, task.get("owner_agent_id")))
    for ref in inputs:
        errors.extend(reference_errors(project, ref, artifacts))
    metadata = []
    for identity in sorted(selected, key=str):
        row = artifacts.get(identity)
        if row is None:
            errors.append(f"Unknown dependency {identity}")
            continue
        ref = {k: row.get(k) for k in ("artifact_id", "path", "version", "sha256")}
        errors.extend(reference_errors(project, ref, artifacts))
        for upstream in row.get("inputs", []):
            errors.extend(f"{identity}: {message}" for message in reference_errors(project, upstream, artifacts))
        metadata.append(dict(ref, kind=row.get("kind"), status=row.get("status"), approval_state=row.get("approval_state")))
    requested_decisions = {d.get("decision_id") if isinstance(d, dict) else d for d in task.get("decision_refs", [])}
    related_decisions = []
    for decision in records(project, "decisions"):
        refs = {ref.get("artifact_id") for ref in decision.get("scope_refs", []) if isinstance(ref, dict)}
        if (decision.get("decision_id") in requested_decisions or decision.get("task_id") == task_id or refs & selected):
            related_decisions.append({key: decision[key] for key in
                                      ("decision_id", "decision_type", "decision", "summary", "scope_refs", "user_message_ref", "created_at", "registry_recorded_at")
                                      if key in decision})
    issues = []
    for issue in records(project, "issues"):
        refs = {ref.get("artifact_id") for ref in issue.get("artifact_refs", []) if isinstance(ref, dict)}
        if issue.get("status") not in {"closed", "accepted_risk"} and (issue.get("task_id") == task_id or refs & selected):
            issues.append({key: issue[key] for key in
                           ("issue_id", "severity", "status", "artifact_refs", "location", "description", "acceptance_criteria", "owner_agent_id")
                           if key in issue})
    for prefix in task.get("allowed_write_paths", []):
        try:
            resolve_inside(project, prefix, protect_raw=True)
        except (ValueError, TypeError) as exc:
            errors.append(f"Invalid write scope: {exc}")
    def trim(value):
        if isinstance(value, str):
            return value if len(value) <= 1200 else value[:1200] + " [truncated; read referenced source]"
        if isinstance(value, list):
            return [trim(v) for v in value[:limit]]
        if isinstance(value, dict):
            return {k: trim(v) for k, v in value.items()}
        return value
    sections = {"inputs": inputs, "dependency_refs": metadata, "related_decisions": related_decisions,
                "task_dependencies": task.get("depends_on", []) if isinstance(task.get("depends_on", []), list) else [],
                "open_issues": issues, "required_skills": skills,
                "acceptance_criteria": task.get("acceptance_criteria", [])}
    omitted = {name: max(0, len(items) - limit) for name, items in sections.items()}
    if any(omitted.values()):
        errors.append("Context item budget exceeded; split this task before dispatch (omitted_counts records gaps)")
    for identity in requested_decisions - {row.get("decision_id") for row in related_decisions}:
        errors.append(f"Missing requested decision {identity}")
    pause = pause_state(project)
    pack = {"format_version": 1, "generated_at": utcnow(), "clock_source": "tool_utc_clock",
            "task_id": task_id, "project_root": str(Path(project).resolve()),
            "objective": trim(task.get("objective") or task.get("title")),
            "owner_role": canonical_role(task.get("owner_role")), "owner_agent_id": task.get("owner_agent_id"),
            "parent_task_id": task.get("parent_task_id"), "specialty": task.get("specialty"),
            "handover": trim(task.get("handover") or {}), "read_only": task.get("read_only") is True,
            "skill_readback": trim(task.get("skill_readback", [])),
            "status": task.get("status"), "allowed_write_paths": task.get("allowed_write_paths", []),
            "deadline": task.get("deadline"), "budget": task.get("budget", {}),
            "human_gate": task.get("human_gate"), "pause": pause,
            "ready_to_start": not errors and not pause["paused"] and task.get("status") in {"queued", "running", "rework"},
            "omitted_counts": omitted, "errors": list(dict.fromkeys(errors)), "warnings": warnings,
            "contains_full_session_history": False, "registry_modified": False,
            "skill_readback_required": True, "ok": not errors}
    pack.update({name: trim(items) for name, items in sections.items()})
    return pack


def doctor(project):
    found = {name: shutil.which(name) for name in ("python", "latexmk", "pdflatex", "xelatex", "perl", "git")}
    git_perl = Path("C:/Program Files/Git/usr/bin/perl.exe")
    return {"ok": sys.version_info >= (3, 12), "python": sys.version, "python_executable": sys.executable,
            "default_runtime": "Python 3.12 (.venv)", "project_marker": (Path(project) / ".mcm-project").is_dir(),
            "matplotlib_available": importlib.util.find_spec("matplotlib") is not None,
            "tools": found, "git_perl_fallback": str(git_perl) if git_perl.exists() else None,
            "latex_note": "paper.py may prepend Git/usr/bin only in its child-process environment when perl is absent",
            "dsh_connection_tested": False, "no_credentials_read": True}


def run_demo(project, force=False):
    script = Path(project) / "example" / "run_demo.py"
    command = [sys.executable, str(script), "--project", str(project)]
    if force:
        command.append("--force")
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or completed.stdout.strip() or "Demo failed")
    return json.loads(completed.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", "--project", dest="project", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    schedule = sub.add_parser("timeline")
    schedule.add_argument("--at", help="Read-only simulation timestamp with timezone offset")
    validate = sub.add_parser("validate")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--allow-synthetic", action="store_true")
    gate = sub.add_parser("gate")
    gate.add_argument("gate_id")
    gate.add_argument("--allow-synthetic", action="store_true")
    for name in ("refresh", "invalidate"):
        item = sub.add_parser(name)
        item.add_argument("artifact_id", nargs="?" if name == "refresh" else None)
        item.add_argument("--reason", required=name == "invalidate", default="source digest changed")
    item = sub.add_parser("import", help="captain merges one proposed record; no human approval is inferred")
    item.add_argument("registry", choices=REGISTRIES)
    item.add_argument("record_file", type=Path)
    item.add_argument("--replace", action="store_true")
    item.add_argument("--actor", default="captain")
    item = sub.add_parser("write-output")
    item.add_argument("path")
    item.add_argument("source", type=Path)
    item.add_argument("--actor", required=True)
    item.add_argument("--task-id")
    item.add_argument("--agent-id")
    item = sub.add_parser("close-issue")
    item.add_argument("issue_id")
    item.add_argument("--verifier", required=True)
    item.add_argument("--evidence", required=True)
    item = sub.add_parser("snapshot")
    item.add_argument("label")
    item = sub.add_parser("restore")
    item.add_argument("snapshot", nargs="?", default="last-good")
    item.add_argument("--destination")
    item = sub.add_parser("runtime")
    item.add_argument("--snapshot", type=Path)
    item.add_argument("--reserve-task", action="store_true")
    item = sub.add_parser("context-pack", help="Read-only bounded context for one task; no chat history export")
    item.add_argument("task_id")
    item = sub.add_parser("demo")
    item.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    try:
        if not (project / ".mcm-project").is_dir():
            raise ValueError("Project marker .mcm-project directory missing")
        command = args.command
        if command == "doctor":
            result = doctor(project)
        elif command == "timeline":
            result = timeline(project,args.at)
        elif command == "validate":
            result = validate_project(project, args.strict, args.allow_synthetic)
        elif command == "gate":
            result = check_gate(project, args.gate_id, args.allow_synthetic)
        elif command == "runtime":
            result = runtime_capacity(project, args.snapshot, args.reserve_task)
        elif command == "context-pack":
            result = context_pack(project, args.task_id)
        elif command == "write-output":
            result = write_output(project, args.path, args.source.read_bytes(), args.actor, args.task_id, args.agent_id)
        elif command == "demo":
            result = run_demo(project, args.force)
        elif command == "restore":
            result = restore_snapshot(project, args.snapshot, args.destination)
        else:
            actor = getattr(args, "actor", "captain")
            with registry_lock(project, actor):
                if command == "refresh":
                    if args.artifact_id:
                        result = refresh_artifact(project, args.artifact_id, args.reason)
                    else:
                        changed=[]
                        for row in records(project,"artifacts"):
                            source=resolve_inside(project,row["path"])
                            if not source.is_file():
                                changed.append({"artifact_id":row["artifact_id"],"missing":True,
                                    "invalidated":invalidate_artifacts(project,[row["artifact_id"]],"source file missing")})
                            elif file_hash(source)!=row.get("sha256"):
                                changed.append(refresh_artifact(project,row["artifact_id"],args.reason))
                        result={"changed_artifacts":changed,"approval_created":False}
                elif command == "invalidate":
                    result = {"invalidated": invalidate_artifacts(project, [args.artifact_id], args.reason)}
                elif command == "snapshot":
                    result = snapshot_project(project, args.label)
                elif command == "close-issue":
                    result = close_issue(project, args.issue_id, args.verifier, args.evidence)
                elif command == "import":
                    record = read_json(args.record_file)
                    if record.get("_template_only"):
                        raise ValueError("Instantiate the record and remove _template_only before merging a template")
                    if record.get("owner_role"):
                        record["owner_role"] = canonical_role(record["owner_role"])
                    record["registry_recorded_at"] = utcnow()
                    key = ID_KEYS[args.registry]
                    if _record_errors(args.registry, [record]):
                        raise ValueError("; ".join(_record_errors(args.registry, [record])))
                    rows = records(project, args.registry)
                    existing = next((i for i, r in enumerate(rows) if r.get(key) == record.get(key)), None)
                    if existing is not None and not args.replace:
                        raise ValueError("Record exists; inspect proposal and use --replace explicitly")
                    if existing is None:
                        rows.append(record)
                    else:
                        rows[existing] = record
                    save_records(project, args.registry, rows)
                    result = {"merged": record[key], "registry": args.registry, "approval_inferred": False}
                else:
                    raise ValueError("Unknown command")
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result.get("ok", True) else 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
