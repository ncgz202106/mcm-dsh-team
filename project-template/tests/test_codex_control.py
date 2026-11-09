"""Fault injection for cooperative control. All identities and data here are synthetic."""
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("codex_control_tested", ROOT / "scripts/codex_control.py")
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
m = c.mcm


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".mcm-project").mkdir()
        shutil.copytree(ROOT / "config", self.root / "config")
        for name in m.REGISTRIES:
            m.save_records(self.root, name, [])
        self.role = ".codex/agents/mcm-programmer.toml"
        self.put(self.role, 'name = "mcm-programmer"\ndescription = "Synthetic test role"\ndeveloper_instructions = "Use task contract"\n')
        self.role_hash = m.file_hash(self.root / self.role)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def config(self, **values):
        p = self.root / "config/runtime.json"
        data = m.read_json(p); data.update(values); m.atomic_json(p, data)

    def task(self, identity="T1", **values):
        row = {"task_id": identity, "owner_role": "mcm-programmer", "owner_agent_id": None,
               "status": "queued", "inputs": [], "allowed_write_paths": ["tasks/" + identity],
               "required_skills": [], "acceptance_criteria": ["Check synthetic arithmetic"],
               "assigned_verifier_agent_id": "synthetic-reviewer", "outputs": [], "synthetic": True}
        row.update(values)
        rows = m.records(self.root, "tasks"); rows.append(row); m.save_records(self.root, "tasks", rows)
        return row

    def start(self, **values):
        c.init_demo(self.root)
        self.task(**values)
        return c.claim(self.root, "T1", "synthetic-author", self.role, self.role_hash, True)

    def output_ref(self, path):
        return {"path": path, "sha256": m.file_hash(self.root / path)}

    def manifest(self, claimed, **values):
        self.put("tasks/T1/result.json", {"synthetic": True, "value": 4})
        data = {"task_id": "T1", "attempt_id": claimed["attempt_id"], "author_agent_id": "synthetic-author",
                "role_sha256": self.role_hash, "inputs": [], "synthetic": True, "skill_readback": [],
                "outputs": [dict(self.output_ref("tasks/T1/result.json"), artifact_id="RESULT-1", version=1,
                                 kind="result", generation="synthetic-run-1")]}
        data.update(values); self.put("tasks/T1/delivery.json", data)
        return data

    def review(self, data, **values):
        self.put("reviews/check.json", {"synthetic": True, "assertion": "2+2==4"})
        report = {"task_id": "T1", "attempt_id": data["attempt_id"], "verifier_agent_id": "synthetic-reviewer",
                  "manifest_sha256": m.file_hash(self.root / "tasks/T1/delivery.json"), "status": "passed",
                  "unresolved_blockers": [], "checks": [self.output_ref("reviews/check.json")],
                  "output_refs": [{k: r.get(k) for k in ("artifact_id", "path", "version", "sha256", "generation")} for r in data["outputs"]]}
        report.update(values); self.put("reviews/review.json", report)
        return report

    def handoff(self):
        claim = self.start(); data = self.manifest(claim)
        c.deliver(self.root, "T1", "tasks/T1/delivery.json")
        self.review(data)
        return claim, data

    def test_strict_default_does_not_accept_manual_true(self):
        self.put(".mcm/codex/observations.json", {"records": [{"capability": "native_role_binding", "status": "verified", "origin": "manual"}]})
        self.assertFalse(c.capabilities(self.root)["ok"])
        self.assertFalse(c.preflight(self.root)["ok"])

    def test_demo_requires_empty_registries(self):
        self.task()
        with self.assertRaisesRegex(ValueError, "empty registries"):
            c.init_demo(self.root)

    def test_demo_rejects_contest_or_real_data(self):
        self.config(run_mode="contest")
        with self.assertRaises(ValueError): c.init_demo(self.root)
        self.config(run_mode="preparation")
        self.put("data/raw/real.csv", "real data")
        with self.assertRaisesRegex(ValueError, "scientific data"):
            c.init_demo(self.root)

    def test_demo_marker_cannot_be_copied_to_different_root(self):
        c.init_demo(self.root)
        with tempfile.TemporaryDirectory() as other:
            shutil.copytree(self.root / "config", Path(other) / "config")
            shutil.copytree(self.root / ".mcm", Path(other) / ".mcm")
            self.assertFalse(c.preflight(Path(other), synthetic_demo=True)["ok"])

    def test_claim_without_native_proof_fails_even_with_valid_role_file(self):
        self.task()
        with self.assertRaisesRegex(ValueError, "Strict native execution blocked"):
            c.claim(self.root, "T1", "author", self.role, self.role_hash)

    def test_role_hash_and_name_checked(self):
        c.init_demo(self.root); self.task()
        with self.assertRaisesRegex(ValueError, "SHA256 changed"):
            c.claim(self.root, "T1", "author", self.role, "0" * 64, True)
        self.put(self.role, 'name="mcm-figure"\ndescription="wrong"\ndeveloper_instructions="wrong"')
        with self.assertRaisesRegex(ValueError, "requested role"):
            c.claim(self.root, "T1", "author", self.role, m.file_hash(self.root / self.role), True)

    def test_duplicate_claim_is_rejected(self):
        self.start()
        with self.assertRaises(ValueError): c.claim(self.root, "T1", "synthetic-author", self.role, self.role_hash, True)

    def test_task_private_scope_is_mandatory(self):
        c.init_demo(self.root); self.task(allowed_write_paths=["paper"])
        with self.assertRaisesRegex(ValueError, "task_id"):
            c.claim(self.root, "T1", "author", self.role, self.role_hash, True)

    def test_capacity_unknown_serializes_different_writers(self):
        self.start(); self.task("T2")
        with self.assertRaisesRegex(ValueError, "capacity unknown"):
            c.claim(self.root, "T2", "author2", self.role, self.role_hash, True)

    def test_overlapping_scope_rejected(self):
        self.start(); self.task("T2", allowed_write_paths=["tasks/T1"])
        with self.assertRaises(ValueError): c.claim(self.root, "T2", "other", self.role, self.role_hash, True)

    def test_output_requires_current_attempt(self):
        claim = self.start(); self.manifest(claim, attempt_id="previous")
        with self.assertRaisesRegex(ValueError, "attempt_id"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_output_hash_tamper_rejected(self):
        claim = self.start(); self.manifest(claim); self.put("tasks/T1/result.json", "changed")
        with self.assertRaisesRegex(ValueError, "SHA256 changed"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_path_escape_and_wrong_directory_rejected(self):
        claim = self.start(); data = self.manifest(claim)
        data["outputs"][0]["path"] = "../outside.json"; self.put("tasks/T1/delivery.json", data)
        with self.assertRaises(ValueError): c.deliver(self.root, "T1", "tasks/T1/delivery.json")
        self.put("tasks/T2/result.json", {"synthetic": True, "value": 4})
        data["outputs"][0].update(self.output_ref("tasks/T2/result.json")); self.put("tasks/T1/delivery.json", data)
        with self.assertRaisesRegex(ValueError, "outside allowed"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_role_changed_after_claim_is_detected(self):
        claim = self.start(); self.manifest(claim)
        self.put(self.role, 'name="mcm-programmer"\ndescription="changed"\ndeveloper_instructions="changed"')
        with self.assertRaisesRegex(ValueError, "protected changes"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_task_contract_changed_after_claim_is_detected(self):
        claim = self.start(); self.manifest(claim)
        rows = m.records(self.root, "tasks"); rows[0]["acceptance_criteria"] = ["changed"]; m.save_records(self.root, "tasks", rows)
        with self.assertRaisesRegex(ValueError, "contract changed"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_stale_input_is_refused(self):
        c.init_demo(self.root)
        self.put("models/input.json", {"synthetic": True})
        artifact = dict(self.output_ref("models/input.json"), artifact_id="INPUT", version=1, kind="model", inputs=[],
                        status="draft", approval_state="draft", verification_status="pending", synthetic=True)
        m.save_records(self.root, "artifacts", [artifact])
        ref = {k: artifact[k] for k in ("artifact_id", "path", "version", "sha256")}; ref["version"] = 2
        self.task(inputs=[ref])
        with self.assertRaisesRegex(ValueError, "stale input"):
            c.claim(self.root, "T1", "author", self.role, self.role_hash, True)

    def test_read_only_skill_cannot_claim_executed(self):
        c.init_demo(self.root); self.put("skill-inputs/figure/SKILL.md", "Synthetic figure instructions")
        skill = {"name": "test-figure", "source": "skill-inputs/figure/SKILL.md", "sha256": m.file_hash(self.root / "skill-inputs/figure/SKILL.md"), "required_state": "executed"}
        self.task(required_skills=[skill])
        claim = c.claim(self.root, "T1", "synthetic-author", self.role, self.role_hash, True)
        self.put("tasks/T1/read.json", {"read": True})
        report = dict(skill, status="read", read_evidence=self.output_ref("tasks/T1/read.json"))
        self.manifest(claim, skill_readback=[report])
        with self.assertRaisesRegex(ValueError, "falls short"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")
        report["status"] = "executed"; self.manifest(claim, skill_readback=[report])
        with self.assertRaisesRegex(ValueError, "execution evidence"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_extra_unpinned_skill_claim_rejected(self):
        claim = self.start(); self.manifest(claim, skill_readback=[{"name": "made-up", "status": "executed"}])
        with self.assertRaisesRegex(ValueError, "pinned skill set"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

    def test_pause_late_return_is_pending_without_writing(self):
        claim = self.start(); self.manifest(claim)
        self.config(pause_state={"paused": True, "user_message_ref": "SYNTHETIC_PAUSE"})
        before = m.file_hash(self.root / ".mcm/tasks.json")
        result = c.deliver(self.root, "T1", "tasks/T1/delivery.json")
        self.assertEqual(result["status"], "pending_paused")
        self.assertEqual(before, m.file_hash(self.root / ".mcm/tasks.json"))
        with self.assertRaisesRegex(ValueError, "pause"):
            c.claim(self.root, "T1", "author", self.role, self.role_hash, True)

    def test_self_review_cannot_accept(self):
        _, data = self.handoff(); self.review(data, verifier_agent_id="synthetic-author")
        with self.assertRaisesRegex(ValueError, "Non-author"):
            c.accept(self.root, "T1", "reviews/review.json")

    def test_nonassigned_review_cannot_accept(self):
        _, data = self.handoff(); self.review(data, verifier_agent_id="stranger")
        with self.assertRaisesRegex(ValueError, "captain-assigned"):
            c.accept(self.root, "T1", "reviews/review.json")

    def test_wrong_generation_review_is_rejected(self):
        _, data = self.handoff(); review = self.review(data)
        review["output_refs"][0]["generation"] = "different-run"; self.put("reviews/review.json", review)
        with self.assertRaisesRegex(ValueError, "generation"):
            c.accept(self.root, "T1", "reviews/review.json")

    def test_missing_review_check_is_rejected(self):
        _, data = self.handoff(); self.review(data, checks=[])
        with self.assertRaisesRegex(ValueError, "concrete checks"):
            c.accept(self.root, "T1", "reviews/review.json")

    def test_manifest_changed_after_handoff_is_rejected(self):
        _, data = self.handoff(); data["note"] = "changed"; self.put("tasks/T1/delivery.json", data)
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            c.accept(self.root, "T1", "reviews/review.json")

    def test_intake_creates_new_draft_and_preserves_human_gates(self):
        self.handoff(); gates = m.file_hash(self.root / "config/gates.json")
        report = c.accept(self.root, "T1", "reviews/review.json")
        self.assertTrue(report["ok"]); self.assertFalse(report["formal_pass"])
        row = m.records(self.root, "artifacts")[0]
        self.assertEqual(row["approval_state"], "draft"); self.assertEqual(row["verification_status"], "pending")
        self.assertTrue(row["path"].startswith(".mcm/codex/accepted/"))
        self.assertEqual(row["sha256"], m.file_hash(self.root / row["path"]))
        self.assertEqual(gates, m.file_hash(self.root / "config/gates.json"))
        self.assertTrue(c.recover(self.root)["ok"])

    def test_protect_does_not_rebaseline_tampering(self):
        self.put("paper/main.tex", "original"); c.protect(self.root)
        self.put("paper/main.tex", "unauthorized change")
        with self.assertRaisesRegex(ValueError, "protected changes"): c.protect(self.root)
        self.assertFalse(c.recover(self.root)["ok"])

    def test_partial_intake_is_diagnosed_and_blocks_new_work(self):
        self.handoff(); original = m.save_records
        def fail_tasks(root, name, rows):
            if name == "tasks": raise OSError("Synthetic power failure")
            return original(root, name, rows)
        with patch.object(m, "save_records", side_effect=fail_tasks):
            with self.assertRaisesRegex(OSError, "power failure"):
                c.accept(self.root, "T1", "reviews/review.json")
        report = c.recover(self.root)
        self.assertFalse(report["ok"]); self.assertEqual(len(report["unfinished_transactions"]), 1)
        self.assertFalse(report["registry_modified"])
        self.assertFalse(c.preflight(self.root, synthetic_demo=True)["ok"])

    def test_interrupted_does_not_release_capacity(self):
        claim = self.start()
        receipt = {"agent_id": "synthetic-author", "attempt_id": claim["attempt_id"], "origin": "simulated",
                   "observation_tool": "TEST_LIST_AGENTS", "state": "interrupted", "observed_at": m.utcnow()}
        self.put("runtime/observation.json", receipt)
        self.assertFalse(c.observe_agent(self.root, "T1", "runtime/observation.json")["local_capacity_released"])
        self.task("T2")
        with self.assertRaisesRegex(ValueError, "capacity unknown"):
            c.claim(self.root, "T2", "author2", self.role, self.role_hash, True)
        receipt["state"] = "completed"; self.put("runtime/observation.json", receipt)
        self.assertTrue(c.observe_agent(self.root, "T1", "runtime/observation.json")["local_capacity_released"])
        self.assertTrue(c.claim(self.root, "T2", "author2", self.role, self.role_hash, True)["ok"])

    def test_stale_runtime_observation_rejected(self):
        claim = self.start()
        self.put("runtime/observation.json", {"agent_id": "synthetic-author", "attempt_id": claim["attempt_id"],
                 "origin": "simulated", "observation_tool": "TEST", "state": "completed",
                 "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()})
        with self.assertRaisesRegex(ValueError, "recent timezone"):
            c.observe_agent(self.root, "T1", "runtime/observation.json")

    def test_cli_reports_blocked_without_exception(self):
        with redirect_stdout(io.StringIO()) as capture:
            result = c.main(["--root", str(self.root), "preflight"])
        self.assertEqual(result, 2)
        self.assertFalse(json.loads(capture.getvalue())["formal_pass"])


if __name__ == "__main__":
    unittest.main()
