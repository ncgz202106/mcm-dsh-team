"""Fault injection for the local protocol guard; no real contest approval is created."""
import importlib.util
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mcm_test_subject", ROOT / "scripts/mcm.py")
mcm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mcm)
VSPEC = importlib.util.spec_from_file_location("independent_test_verifier", ROOT / "example/verify.py")
verifier_module = importlib.util.module_from_spec(VSPEC)
VSPEC.loader.exec_module(verifier_module)
SSPEC = importlib.util.spec_from_file_location("test_solver", ROOT / "example/solve.py")
solver_module = importlib.util.module_from_spec(SSPEC)
SSPEC.loader.exec_module(solver_module)


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        (self.project / ".mcm-project").mkdir()
        (self.project / ".mcm").mkdir()
        shutil.copytree(ROOT / "config", self.project / "config")
        for name in mcm.REGISTRIES:
            mcm.save_records(self.project, name, [])
        (self.project / "results").mkdir()
        (self.project / "data/raw").mkdir(parents=True)
        (self.project / "data/raw/original.csv").write_text("original,immutable\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def artifact(self, identity, inputs=(), kind="model", **updates):
        path = self.project / "results" / f"{identity}.txt"
        path.write_text(f"payload for {identity}\n", encoding="utf-8")
        row = {"artifact_id": identity, "kind": kind, "path": path.relative_to(self.project).as_posix(),
               "version": 1, "status": "verified", "approval_state": "verified", "owner_role": "programmer",
               "task_id": "TASK", "inputs": list(inputs), "sha256": mcm.file_hash(path),
               "verification_status": "passed", "verified_by": "independent", "author_agent_id": "author",
               "reproduced": True, "citations_verified": True, "synthetic": True}
        row.update(updates)
        return row

    @staticmethod
    def ref(row):
        return {key: row[key] for key in ("artifact_id", "version", "sha256")}

    def release_pair(self):
        result = self.artifact("READY", kind="result", status="approved", approval_state="approved")
        proof = self.project / "results/ready-verification.json"
        mcm.atomic_json(proof, {"status": "passed", "result_sha256": result["sha256"],
                               "reproduction_passed": True, "verifier_agent_id": "independent"})
        result["verification_report"] = {"path": "results/ready-verification.json", "sha256": mcm.file_hash(proof)}
        paper = self.artifact("PDF", [self.ref(result)], kind="paper", status="approved", approval_state="approved")
        old = self.project / paper["path"]
        new = old.with_suffix(".pdf")
        old.rename(new)
        paper["path"] = new.relative_to(self.project).as_posix()
        return result, paper

    def scope_gate(self, row, gate_id="H3_RELEASE", approve=False):
        gates = mcm.read_json(self.project / "config/gates.json")
        gate = next(g for g in gates["records"] if g["gate_id"] == gate_id)
        gate["scope_refs"] = [self.ref(row)]
        if approve:
            gate.update(status="approved", approved_by="SYNTHETIC_TEST_OPERATOR", approved_at="2026-10-24T00:00:00Z", decision_id="SYNTHETIC_"+gate_id)
            decisions = [d for d in mcm.records(self.project, "decisions") if d.get("decision_id") != gate["decision_id"]]
            decisions.append({"decision_id": gate["decision_id"], "decision_type": "human_gate", "decision": "approve",
                             "synthetic": True, "scope_refs": gate["scope_refs"],
                             "approved_by": gate["approved_by"], "approved_at": gate["approved_at"],
                             "user_message_ref": "SYNTHETIC_TEST_MESSAGE", "user_confirmation_text": "Synthetic fixture approval only"})
            mcm.save_records(self.project, "decisions", decisions)
        mcm.atomic_json(self.project / "config/gates.json", gates)

    def test_empty_project_is_integrity_valid_but_gate_is_pending(self):
        self.assertTrue(mcm.validate_project(self.project)["ok"])
        gate = mcm.check_gate(self.project, "G2_RESULTS", allow_synthetic=True)
        self.assertFalse(gate["ok"])
        self.assertTrue(any("human decision" in item for item in gate["errors"]))

    def test_old_hash_recursively_invalidates_descendants_and_gate(self):
        a = self.artifact("INPUT")
        b = self.artifact("RESULT", [self.ref(a)])
        c = self.artifact("FIGURE", [self.ref(b)], kind="figure")
        d = self.artifact("PAPER", [self.ref(c)], kind="paper")
        mcm.save_records(self.project, "artifacts", [a, b, c, d])
        gates = mcm.read_json(self.project / "config/gates.json")
        gates["records"][2].update(status="approved", scope_refs=[self.ref(d)])
        mcm.atomic_json(self.project / "config/gates.json", gates)
        (self.project / a["path"]).write_text("changed input", encoding="utf-8")
        self.assertFalse(mcm.validate_project(self.project)["ok"])
        with mcm.registry_lock(self.project):
            refreshed = mcm.refresh_artifact(self.project, "INPUT", "fault injection: input changed")
        self.assertEqual(set(refreshed["invalidated"]), {"INPUT", "RESULT", "FIGURE", "PAPER"})
        by_id = {r["artifact_id"]: r for r in mcm.records(self.project, "artifacts")}
        self.assertEqual(by_id["INPUT"]["version"], 2)
        for identity in ("RESULT", "FIGURE", "PAPER"):
            self.assertEqual(by_id[identity]["status"], "stale")
            self.assertEqual(by_id[identity]["approval_state"], "invalidated")
        self.assertEqual(mcm.read_json(self.project / "config/gates.json")["records"][2]["status"], "invalidated")

    def test_input_version_mismatch_is_detected_without_file_change(self):
        a = self.artifact("A")
        b = self.artifact("B", [dict(self.ref(a), version=2)])
        mcm.save_records(self.project, "artifacts", [a, b])
        self.assertTrue(any("stale input" in e for e in mcm.validate_project(self.project)["errors"]))

    def test_unverified_citation_blocks_strict_validation(self):
        row = self.artifact("MODEL", citations_verified=False)
        mcm.save_records(self.project, "artifacts", [row])
        report = mcm.validate_project(self.project, strict=True, allow_synthetic=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("citations are unverified" in e for e in report["errors"]))

    def test_reproduction_failure_blocks_gate_even_with_approved_flags(self):
        row = self.artifact("PAPER", kind="paper", reproduced=False, status="approved", approval_state="approved")
        mcm.save_records(self.project, "artifacts", [row])
        self.scope_gate(row)
        report = mcm.check_gate(self.project, "G3_PAPER", allow_synthetic=True)
        self.assertFalse(report["ok"])
        self.assertTrue(any("reproduction has not passed" in e for e in report["errors"]))

    def test_independent_result_report_failure_cannot_be_hidden_by_flags(self):
        row = self.artifact("RESULT", kind="result")
        evidence = self.project / "results/verification.json"
        mcm.atomic_json(evidence, {"status": "failed", "result_sha256": row["sha256"], "reproduction_passed": False})
        row["verification_report"] = {"path": "results/verification.json", "sha256": mcm.file_hash(evidence)}
        mcm.save_records(self.project, "artifacts", [row])
        report = mcm.validate_project(self.project, strict=True, allow_synthetic=True)
        self.assertTrue(any("independent reproduction failed" in e for e in report["errors"]))

    def test_blocker_requires_independent_closure(self):
        issue = {"issue_id": "I1", "severity": "blocker", "status": "fixed_pending_review", "author_agent_id": "author", "reported_by":"independent"}
        mcm.save_records(self.project, "issues", [issue])
        evidence = self.project / "results/proof.json"
        mcm.atomic_json(evidence, {"issue_id": "I1", "status": "passed", "verifier_agent_id": "author"})
        with self.assertRaisesRegex(ValueError, "author"):
            mcm.close_issue(self.project, "I1", "author", "results/proof.json")
        self.assertFalse(mcm.validate_project(self.project)["ok"])
        mcm.atomic_json(evidence, {"issue_id": "I1", "status": "passed", "verifier_agent_id": "independent"})
        result = mcm.close_issue(self.project, "I1", "independent", "results/proof.json")
        self.assertEqual(result["status"], "closed")
        self.assertTrue(mcm.validate_project(self.project)["ok"])

    def test_blocker_cannot_be_accepted_as_risk(self):
        mcm.save_records(self.project, "issues", [{"issue_id": "I2", "severity": "blocker", "status": "accepted_risk"}])
        self.assertTrue(any("cannot be accepted" in e for e in mcm.validate_project(self.project)["errors"]))

    def test_closed_issue_evidence_tamper_reopens_blocking_validation(self):
        issue = {"issue_id": "I3", "severity": "blocker", "status": "fixed_pending_review", "author_agent_id": "author", "reported_by":"independent"}
        mcm.save_records(self.project, "issues", [issue])
        evidence = self.project / "results/proof.json"
        mcm.atomic_json(evidence, {"issue_id": "I3", "status": "passed", "verifier_agent_id": "independent"})
        mcm.close_issue(self.project, "I3", "independent", "results/proof.json")
        mcm.atomic_json(evidence, {"issue_id": "I3", "status": "failed", "verifier_agent_id": "independent"})
        self.assertTrue(any("closure evidence changed" in e for e in mcm.validate_project(self.project)["errors"]))

    def test_uninstantiated_template_cannot_enter_registry(self):
        row = self.artifact("PLACEHOLDER", _template_only=True)
        proposal = self.project / "proposal.json"
        mcm.atomic_json(proposal, row)
        output = io.StringIO()
        with redirect_stderr(output):
            exit_code = mcm.main(["--root", str(self.project), "import", "artifacts", str(proposal)])
        self.assertEqual(exit_code, 2)
        self.assertIn("_template_only", output.getvalue())
        self.assertEqual(mcm.records(self.project, "artifacts"), [])

    def test_partition_writer_cannot_overwrite_or_write_other_partition(self):
        mcm.save_records(self.project,"tasks",[{"task_id":"WRITE1","owner_role":"mcm-writer",
            "owner_agent_id":"writer-instance-1","status":"running","allowed_write_paths":["tasks/WRITE1/draft"]}])
        output="tasks/WRITE1/draft/q1.tex"
        mcm.write_output(self.project, output, b"first", "paper_writer", "WRITE1", "writer-instance-1")
        with self.assertRaises(FileExistsError):
            mcm.write_output(self.project, output, b"overwrite", "paper_writer", "WRITE1", "writer-instance-1")
        with self.assertRaisesRegex(ValueError, "does not own"):
            mcm.write_output(self.project, "src/solver.py", b"wrong partition", "paper_writer", "WRITE1", "writer-instance-1")
        with self.assertRaisesRegex(ValueError, "does not own"):
            mcm.write_output(self.project, "paper/sections/q1.tex", b"wrong master", "mcm-writer", "WRITE1", "writer-instance-1")
        self.assertEqual((self.project / output).read_bytes(), b"first")

    def test_raw_data_and_path_traversal_are_rejected(self):
        with self.assertRaises(ValueError):
            mcm.write_output(self.project, "../escape.txt", b"bad", "captain")
        with self.assertRaisesRegex(ValueError, "read only"):
            mcm.write_output(self.project, "data/raw/new.csv", b"bad", "researcher")

    def test_only_one_registry_writer_and_workers_propose(self):
        with self.assertRaisesRegex(ValueError, "Only captain"):
            with mcm.registry_lock(self.project, "paper_writer"):
                pass
        with mcm.registry_lock(self.project):
            with self.assertRaisesRegex(ValueError, "already active"):
                with mcm.registry_lock(self.project):
                    pass

    def test_snapshot_resume_preserves_raw_and_live_state(self):
        row = self.artifact("A")
        mcm.save_records(self.project, "artifacts", [row])
        raw = (self.project / "data/raw/original.csv").read_bytes()
        saved = mcm.snapshot_project(self.project, "good-1")
        self.assertFalse(saved["raw_data_copied"])
        (self.project / row["path"]).write_text("broken live state", encoding="utf-8")
        restored = mcm.restore_snapshot(self.project, "last-good")
        recovered = Path(restored["restored_to"])
        self.assertTrue(mcm.validate_project(recovered)["ok"])
        self.assertEqual((recovered / row["path"]).read_text(encoding="utf-8"), "payload for A\n")
        self.assertEqual((self.project / row["path"]).read_text(encoding="utf-8"), "broken live state")
        self.assertEqual((self.project / "data/raw/original.csv").read_bytes(), raw)
        self.assertEqual((recovered / "data/raw/original.csv").read_bytes(), raw)

    def test_snapshot_destination_cannot_overwrite_project_or_escape(self):
        mcm.snapshot_project(self.project, "safe")
        for destination in (".", "../outside", "data/raw/restore", ".mcm/restored"):
            with self.assertRaises(ValueError):
                mcm.restore_snapshot(self.project, "safe", destination)

    def test_snapshot_tampering_is_detected(self):
        row = self.artifact("A")
        mcm.save_records(self.project, "artifacts", [row])
        mcm.snapshot_project(self.project, "safe")
        (self.project / ".mcm/snapshots/safe/files/results/A.txt").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            mcm.restore_snapshot(self.project, "last-good")

    def test_changed_original_raw_data_refuses_restore(self):
        mcm.snapshot_project(self.project, "raw-safe")
        (self.project / "data/raw/original.csv").write_text("unexpected mutation", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "raw data changed"):
            mcm.restore_snapshot(self.project, "last-good")

    def test_capacity_counts_waiting_supervisor_and_protects_reserve(self):
        payload = {"captured_at": datetime.now(timezone.utc).isoformat(), "allocation_scope": "host", "host_capacity": {"verified": True, "max_active_descendants": 8, "evidence_ref": "SYNTHETIC_HOST_PROBE"},
                   "records": [{"agent_id": "root", "state": "running", "is_root": True}] +
                   [{"agent_id": f"worker-{i}", "state": "waiting" if i == 0 else "running", "role": "model_lead" if i == 0 else "worker"} for i in range(7)]}
        snapshot = self.project / "runtime-snapshot.json"
        mcm.atomic_json(snapshot, payload)
        normal = mcm.runtime_capacity(self.project, snapshot)
        reserve = mcm.runtime_capacity(self.project, snapshot, reserve_task=True)
        self.assertEqual(normal["allocated"], 7)
        self.assertFalse(normal["admit_one_task"])
        self.assertTrue(reserve["admit_one_task"])
        self.assertTrue(normal["does_not_spawn_or_control_dsh"])

    def test_synthetic_records_never_pass_real_gate(self):
        mcm.save_records(self.project, "artifacts", [self.artifact("SYNTHETIC")])
        report = mcm.validate_project(self.project, strict=True)
        self.assertTrue(any("synthetic artifact" in e for e in report["errors"]))

    def test_synthetic_positive_gate_requires_exact_scope_and_real_mode_rejects_it(self):
        row, paper = self.release_pair()
        mcm.save_records(self.project, "artifacts", [row, paper])
        self.scope_gate(row, gate_id="H2_RESULTS", approve=True)
        self.scope_gate(paper, approve=True)
        self.assertTrue(mcm.check_gate(self.project, "H3", allow_synthetic=True)["ok"])
        self.assertFalse(mcm.check_gate(self.project, "H3")["ok"])
        decisions = mcm.records(self.project, "decisions")
        decisions[0]["scope_refs"][0]["version"] = 999
        mcm.save_records(self.project, "decisions", decisions)
        report = mcm.check_gate(self.project, "H3", allow_synthetic=True)
        self.assertTrue(any("decision scope" in e for e in report["errors"]))

    def test_gate_scopes_do_not_promote_unrelated_draft_artifacts(self):
        ready, paper = self.release_pair()
        unrelated = self.artifact("UNRELATED", status="draft", approval_state="draft", verification_status="pending")
        mcm.save_records(self.project, "artifacts", [ready, paper, unrelated])
        self.scope_gate(ready, gate_id="H2_RESULTS", approve=True)
        self.scope_gate(paper, approve=True)
        report = mcm.check_gate(self.project, "H3", allow_synthetic=True)
        self.assertTrue(report["ok"])
        self.assertEqual(report["artifact_scope"], ["PDF", "READY"])

    def test_cyclic_dependencies_are_rejected(self):
        a, b = self.artifact("A"), self.artifact("B")
        a["inputs"], b["inputs"] = [self.ref(b)], [self.ref(a)]
        mcm.save_records(self.project, "artifacts", [a, b])
        self.assertTrue(any("cyclic" in e for e in mcm.validate_project(self.project)["errors"]))


class IndependentVerification(unittest.TestCase):
    def test_real_wrong_value_fault_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = Path(temporary) / "result.json"
            solver_module.solve(ROOT / "example/synthetic_input.json", result)
            self.assertEqual(verifier_module.verify(ROOT / "example/synthetic_input.json", result)["status"], "passed")
            payload = mcm.read_json(result)
            payload["solution"]["cost"] += 1.0
            mcm.atomic_json(result, payload)
            verification = verifier_module.verify(ROOT / "example/synthetic_input.json", result)
            self.assertEqual(verification["status"], "failed")
            self.assertFalse(verification["reproduction_passed"])

    def test_invalid_solver_input_rejected(self):
        for values in ((0, 1, 2), (12, -1, 2), (float("nan"), 1, 2)):
            with self.assertRaises(ValueError):
                solver_module.solve_case(*values)


if __name__ == "__main__":
    unittest.main(verbosity=2)
