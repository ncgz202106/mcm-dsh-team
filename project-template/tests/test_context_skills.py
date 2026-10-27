"""Regression probes for current dependency scope, bounded context and actual dispatch limits."""
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("context_cli", ROOT / "scripts/mcm.py")
mcm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mcm)


class CurrentContext(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".mcm-project").mkdir()
        shutil.copytree(ROOT / "config", self.root / "config")
        for name in mcm.REGISTRIES:
            mcm.save_records(self.root, name, [])

    def tearDown(self):
        self.temp.cleanup()

    def artifact(self, identity, **updates):
        path = self.root / "models" / (identity + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"identity": identity}), encoding="utf-8")
        row = {"artifact_id": identity, "path": path.relative_to(self.root).as_posix(), "version": 1,
               "sha256": mcm.file_hash(path), "kind": "model", "status": "approved", "approval_state": "approved",
               "verification_status": "passed", "verified_by": "verifier", "author_agent_id": "author",
               "reproduced": True, "citations_verified": True, "inputs": [], "synthetic": True}
        row.update(updates)
        return row

    @staticmethod
    def ref(row, path=True):
        return {key: row[key] for key in (("artifact_id", "path", "version", "sha256") if path else ("artifact_id", "version", "sha256"))}

    def task(self, **updates):
        task = {"task_id": "P1", "owner_role": "mcm-programmer", "owner_agent_id": "programmer-one",
                "status": "running", "objective": "Implement only the declared solver", "inputs": [],
                "allowed_write_paths": ["src/solver"], "acceptance_criteria": ["independent small-case agreement"]}
        task.update(updates)
        mcm.save_records(self.root, "tasks", [task])
        return task

    def config(self, **updates):
        path = self.root / "config/runtime.json"
        config = mcm.read_json(path)
        config.update(updates)
        mcm.atomic_json(path, config)

    def approve_gate(self, gate_id, row):
        gates = mcm.read_json(self.root / "config/gates.json")
        gate = next(g for g in gates["records"] if g["gate_id"] == gate_id)
        gate.update(status="approved", decision_id="TEST_" + gate_id, approved_by="SYNTHETIC_USER",
                    approved_at="2026-01-01T00:00:00Z", scope_refs=[self.ref(row)])
        decisions = mcm.records(self.root, "decisions")
        decisions.append({"decision_id": gate["decision_id"], "decision_type": "human_gate", "decision": "approve",
                          "synthetic": True, "scope_refs": gate["scope_refs"], "approved_by": gate["approved_by"],
                          "approved_at": gate["approved_at"], "user_message_ref": "SYNTHETIC_MESSAGE",
                          "user_confirmation_text": "SYNTHETIC fixture only"})
        mcm.save_records(self.root, "decisions", decisions)
        mcm.atomic_json(self.root / "config/gates.json", gates)

    def snapshot(self, limit=None, used=0):
        payload = {"captured_at": datetime.now(timezone.utc).isoformat(), "allocation_scope": "host", "records": [{"agent_id": f"worker-{i}", "state": "waiting" if i == 0 else "running"}
                               for i in range(used)], "team_member_limit": 8}
        if limit is not None:
            payload["host_capacity"] = {"verified": True, "max_active_descendants": limit, "evidence_ref": "SYNTHETIC_PROBE"}
        path = self.root / "host-snapshot.json"
        mcm.atomic_json(path, payload)
        return path

    def test_unreferenced_retracted_file_may_be_missing_without_blocking_current(self):
        current = self.artifact("CURRENT")
        history = self.artifact("OLD", status="retracted", approval_state="invalidated")
        (self.root / history["path"]).unlink()
        mcm.save_records(self.root, "artifacts", [current, history])
        report = mcm.validate_project(self.root, strict=True, allow_synthetic=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["artifact_scope"], ["CURRENT"])
        self.assertIn("historical retracted", " ".join(report["warnings"]))

    def test_explicitly_checking_retired_artifact_still_blocks(self):
        history = self.artifact("OLD", status="stale", approval_state="invalidated")
        mcm.save_records(self.root, "artifacts", [history])
        report = mcm.validate_project(self.root, artifact_scope={"OLD"})
        self.assertFalse(report["ok"])

    def test_current_input_recursively_reactivates_stale_failure(self):
        old = self.artifact("OLD", status="stale", approval_state="invalidated")
        current = self.artifact("CURRENT", inputs=[self.ref(old)])
        mcm.save_records(self.root, "artifacts", [old, current])
        report = mcm.validate_project(self.root, artifact_scope={"CURRENT"})
        self.assertFalse(report["ok"])
        self.assertEqual(report["artifact_scope"], ["CURRENT", "OLD"])
        self.assertIn("invalidated", " ".join(report["errors"]))

    def test_wrong_path_new_digest_tuple_is_rejected(self):
        row = self.artifact("CURRENT")
        child = self.artifact("CHILD", inputs=[dict(self.ref(row), path="models/OLD.json")])
        mcm.save_records(self.root, "artifacts", [row, child])
        self.assertIn("reference path", " ".join(mcm.validate_project(self.root)["errors"]))

    def test_legacy_reference_without_path_is_compatible(self):
        row = self.artifact("CURRENT")
        child = self.artifact("CHILD", inputs=[self.ref(row, path=False)])
        mcm.save_records(self.root, "artifacts", [row, child])
        self.assertTrue(mcm.validate_project(self.root)["ok"])

    def test_explicit_reference_generation_cannot_disagree_with_current_artifact(self):
        row = self.artifact("CURRENT", generation="run-2")
        child = self.artifact("CHILD", inputs=[dict(self.ref(row), generation="run-1")])
        mcm.save_records(self.root, "artifacts", [row, child])
        self.assertIn("reference generation", " ".join(mcm.validate_project(self.root)["errors"]))

    def test_result_report_cannot_claim_another_generation_with_matching_bytes(self):
        row = self.artifact("RESULT", kind="result", generation="run-2")
        proof_path = self.root / "models" / "proof.json"
        proof = {"status": "passed", "result_sha256": row["sha256"], "result_generation": "run-1",
                 "reproduction_passed": True, "verifier_agent_id": "verifier"}
        mcm.atomic_json(proof_path, proof)
        row["verification_report"] = {"path": "models/proof.json", "sha256": mcm.file_hash(proof_path)}
        mcm.save_records(self.root, "artifacts", [row])
        report = mcm.validate_project(self.root, strict=True, allow_synthetic=True)
        self.assertIn("result generation", " ".join(report["errors"]))
        proof["result_generation"] = "run-2"
        mcm.atomic_json(proof_path, proof)
        row["verification_report"]["sha256"] = mcm.file_hash(proof_path)
        mcm.save_records(self.root, "artifacts", [row])
        self.assertTrue(mcm.validate_project(self.root, strict=True, allow_synthetic=True)["ok"])

    def test_gate_direct_path_mismatch_is_not_hidden_by_matching_digest(self):
        row = self.artifact("CURRENT")
        mcm.save_records(self.root, "artifacts", [row])
        self.approve_gate("H2_RESULTS", row)
        gates = mcm.read_json(self.root / "config/gates.json")
        next(g for g in gates["records"] if g["gate_id"] == "H2_RESULTS")["scope_refs"][0]["path"] = "models/OLD.json"
        mcm.atomic_json(self.root / "config/gates.json", gates)
        self.assertIn("reference path", " ".join(mcm.check_gate(self.root, "H2", True)["errors"]))

    def test_h2_does_not_bind_live_paper_or_pdf(self):
        row = self.artifact("PAPER", kind="paper")
        mcm.save_records(self.root, "artifacts", [row])
        self.approve_gate("H2_RESULTS", row)
        self.assertIn("mutable paper/PDF", " ".join(mcm.check_gate(self.root, "H2", True)["errors"]))

    def test_h3_requires_still_valid_h2(self):
        row = self.ready_result("RESULT")
        pdf = self.paper_artifact("PDF", [self.ref(row)])
        mcm.save_records(self.root, "artifacts", [row, pdf])
        self.approve_gate("H3_RELEASE", pdf)
        self.assertFalse(mcm.check_gate(self.root, "H3", True)["ok"])
        self.approve_gate("H2_RESULTS", row)
        self.assertTrue(mcm.check_gate(self.root, "H3", True)["ok"])
        gates = mcm.read_json(self.root / "config/gates.json")
        next(g for g in gates["records"] if g["gate_id"] == "H2_RESULTS")["status"] = "invalidated"
        mcm.atomic_json(self.root / "config/gates.json", gates)
        self.assertIn("valid H2 required", " ".join(mcm.check_gate(self.root, "H3", True)["errors"]))

    def ready_result(self, identity):
        row = self.artifact(identity, kind="result")
        proof = self.root / "models" / (identity + "-verification.json")
        mcm.atomic_json(proof, {"status": "passed", "result_sha256": row["sha256"],
                               "reproduction_passed": True, "verifier_agent_id": "verifier"})
        row["verification_report"] = {"path": proof.relative_to(self.root).as_posix(), "sha256": mcm.file_hash(proof)}
        return row

    def paper_artifact(self, identity, inputs):
        row = self.artifact(identity, kind="paper", inputs=inputs)
        old = self.root / row["path"]
        pdf = old.with_suffix(".pdf")
        old.rename(pdf)
        row["path"] = pdf.relative_to(self.root).as_posix()
        return row

    def test_h3_model_only_approval_cannot_stand_for_final_pdf(self):
        row = self.artifact("MODEL")
        mcm.save_records(self.root, "artifacts", [row])
        self.approve_gate("H2_RESULTS", row)
        self.approve_gate("H3_RELEASE", row)
        self.assertIn("final paper PDF", " ".join(mcm.check_gate(self.root, "H3", True)["errors"]))

    def test_h3_pdf_cannot_omit_results_or_consume_results_outside_h2(self):
        approved = self.ready_result("APPROVED")
        other = self.ready_result("OTHER")
        pdf = self.paper_artifact("PDF", [])
        mcm.save_records(self.root, "artifacts", [approved, other, pdf])
        self.approve_gate("H2_RESULTS", approved)
        self.approve_gate("H3_RELEASE", pdf)
        self.assertIn("must declare the results", " ".join(mcm.check_gate(self.root, "H3", True)["errors"]))
        pdf["inputs"] = [self.ref(other)]
        mcm.save_records(self.root, "artifacts", [approved, other, pdf])
        self.assertIn("outside the current H2 scope", " ".join(mcm.check_gate(self.root, "H3", True)["errors"]))

    def test_h3_pdf_cannot_swap_model_while_keeping_approved_result(self):
        approved = self.ready_result("APPROVED")
        unapproved_model = self.artifact("NEW_MODEL")
        pdf = self.paper_artifact("PDF", [self.ref(approved), self.ref(unapproved_model)])
        mcm.save_records(self.root, "artifacts", [approved, unapproved_model, pdf])
        self.approve_gate("H2_RESULTS", approved)
        self.approve_gate("H3_RELEASE", pdf)
        self.assertIn("scientific artifact outside", " ".join(mcm.check_gate(self.root, "H3", True)["errors"]))

    def test_history_blocker_not_in_current_closure_is_warning(self):
        old = self.artifact("OLD", status="retracted", approval_state="invalidated")
        current = self.artifact("CURRENT")
        mcm.save_records(self.root, "artifacts", [old, current])
        mcm.save_records(self.root, "issues", [{"issue_id": "OLD-FAILURE", "severity": "blocker", "status": "open", "artifact_refs": [self.ref(old)]}])
        report = mcm.validate_project(self.root)
        self.assertTrue(report["ok"])
        self.assertIn("outside current", " ".join(report["warnings"]))

    def test_unlinked_blocker_is_not_silently_retired(self):
        mcm.save_records(self.root, "issues", [{"issue_id": "GLOBAL", "severity": "blocker", "status": "open"}])
        self.assertFalse(mcm.validate_project(self.root)["ok"])

    def test_context_is_relevant_bounded_and_read_only(self):
        row, other = self.artifact("INPUT"), self.artifact("UNRELATED")
        mcm.save_records(self.root, "artifacts", [row, other])
        self.task(inputs=[self.ref(row)], required_skills=[{"name": "LaTeX工具", "source": "skills/latex/SKILL.md", "purpose": "inspect formula interface"}])
        mcm.save_records(self.root, "decisions", [
            {"decision_id": "RELATED", "task_id": "P1", "decision": "use declared tolerance"},
            {"decision_id": "UNRELATED", "decision": "NEVER_COPY_UNRELATED_HISTORY"}])
        mcm.save_records(self.root, "issues", [
            {"issue_id": "OPEN", "task_id": "P1", "status": "open", "severity": "minor"},
            {"issue_id": "CLOSED", "task_id": "P1", "status": "closed", "severity": "minor"},
            {"issue_id": "OTHER", "task_id": "P2", "status": "open", "severity": "minor"}])
        before = {p.name: p.read_bytes() for p in (self.root / ".mcm").glob("*.json")}
        pack = mcm.context_pack(self.root, "P1")
        self.assertTrue(pack["ok"], pack)
        self.assertTrue(pack["ready_to_start"])
        self.assertEqual([r["artifact_id"] for r in pack["dependency_refs"]], ["INPUT"])
        self.assertEqual([r["issue_id"] for r in pack["open_issues"]], ["OPEN"])
        self.assertEqual([r["decision_id"] for r in pack["related_decisions"]], ["RELATED"])
        self.assertEqual(pack["required_skills"][0]["name"], "LaTeX工具")
        self.assertNotIn("NEVER_COPY_UNRELATED_HISTORY", json.dumps(pack))
        self.assertFalse(pack["contains_full_session_history"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / ".mcm").glob("*.json")})
        self.assertIsNotNone(datetime.fromisoformat(pack["generated_at"]).tzinfo)

    def test_context_catches_changed_input_bytes_and_old_version(self):
        row = self.artifact("INPUT")
        mcm.save_records(self.root, "artifacts", [row])
        self.task(inputs=[dict(self.ref(row), version=99)])
        (self.root / row["path"]).write_text("changed", encoding="utf-8")
        pack = mcm.context_pack(self.root, "P1")
        self.assertFalse(pack["ready_to_start"])
        self.assertIn("stale input", " ".join(pack["errors"]))
        self.assertIn("SHA256 changed", " ".join(pack["errors"]))

    def test_context_budget_omission_blocks_dispatch(self):
        rows = [self.artifact(f"INPUT{i}") for i in range(3)]
        mcm.save_records(self.root, "artifacts", rows)
        self.task(inputs=[self.ref(row) for row in rows])
        self.config(context_pack_max_items=2)
        pack = mcm.context_pack(self.root, "P1")
        self.assertFalse(pack["ready_to_start"])
        self.assertEqual(len(pack["inputs"]), 2)
        self.assertEqual(pack["omitted_counts"]["inputs"], 1)

    def test_missing_decision_reference_blocks_context(self):
        self.task(decision_refs=["MISSING"])
        self.assertIn("Missing requested decision", " ".join(mcm.context_pack(self.root, "P1")["errors"]))

    def test_old_task_without_skills_remains_readable(self):
        self.task()
        self.assertTrue(mcm.context_pack(self.root, "P1")["ok"])
        self.assertEqual(mcm.context_pack(self.root, "P1")["required_skills"], [])

    def review_task(self):
        source = self.artifact("SOURCE")
        candidate = self.artifact("CANDIDATE", task_id="AUTHOR", author_agent_id="actual-author",
                                  status="draft", approval_state="draft", verification_status="failed", inputs=[self.ref(source)])
        handoff_path = self.root / "tasks/author/handoff.json"
        mcm.atomic_json(handoff_path, {"delivered": True, "accepted": False})
        handoff = {"path": "tasks/author/handoff.json", "sha256": mcm.file_hash(handoff_path)}
        producer = {"task_id": "AUTHOR", "owner_agent_id": "actual-author", "status": "in_review", "project_root": ".",
                    "outputs": [self.ref(candidate)], "output_readback": [self.ref(candidate)], "completion_handoff_path": handoff["path"]}
        task = self.task(owner_role="mcm-verifier", owner_agent_id="pending:reviewer", allowed_write_paths=["reviews/task"],
                         inputs=[self.ref(candidate)], depends_on=[{"task_id": "AUTHOR", "relation": "review",
                         "output_refs": [self.ref(candidate)], "handoff_ref": handoff}])
        mcm.save_records(self.root, "tasks", [task, producer])
        mcm.save_records(self.root, "artifacts", [candidate, source])
        return task, producer, candidate, source

    def test_explicit_review_context_binds_delivery_without_granting_approval_or_host_admission(self):
        task, producer, candidate, _ = self.review_task()
        before = {p: p.read_bytes() for p in self.root.rglob("*.json")}
        pack = mcm.context_pack(self.root, "P1")
        self.assertTrue(pack["ready_to_start"], pack)
        self.assertEqual(pack["task_dependencies"], task["depends_on"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.json")})
        self.assertEqual(producer["status"], "in_review")
        self.assertEqual(candidate["approval_state"], "draft")
        self.assertFalse(mcm.runtime_capacity(self.root)["admit_one_task"])
        self.assertTrue(mcm.validate_project(self.root)["ok"])
        producer["output_readback"] = [{k: candidate[k] for k in ("artifact_id", "path", "sha256")}]
        mcm.save_records(self.root, "tasks", [task, producer])
        self.assertTrue(mcm.context_pack(self.root, "P1")["ready_to_start"])

    def test_optional_delivery_versions_reject_booleans_for_version_one(self):
        task, producer, candidate, _ = self.review_task()
        self.assertEqual(candidate["version"], 1)
        for field in ("outputs", "output_readback"):
            for version in (True, False, "1", None):
                with self.subTest(field=field, version=version):
                    producer[field] = [dict(self.ref(candidate), version=version)]
                    mcm.save_records(self.root, "tasks", [task, producer])
                    self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])
            producer[field] = [self.ref(candidate)]
            mcm.save_records(self.root, "tasks", [task, producer])
            self.assertTrue(mcm.context_pack(self.root, "P1")["ready_to_start"])

    def test_legacy_execution_dependencies_still_require_approved_work(self):
        task, producer, _, _ = self.review_task()
        for entry in ("AUTHOR", {"task_id": "AUTHOR"}, {"task_id": "AUTHOR", "relation": "execution"}):
            with self.subTest(entry=entry):
                task["depends_on"] = [entry]
                producer["status"] = "in_review"
                mcm.save_records(self.root, "tasks", [task, producer])
                self.assertIn("not approved", " ".join(mcm.context_pack(self.root, "P1")["errors"]))
                producer["status"] = "approved"
                mcm.save_records(self.root, "tasks", [task, producer])
                self.assertTrue(mcm.context_pack(self.root, "P1")["ready_to_start"])

    def test_dependency_shapes_reject_typos_missing_pins_duplicates_and_self_reference(self):
        task, producer, _, _ = self.review_task()
        good = json.loads(json.dumps(task["depends_on"][0]))
        for dependencies in (None, {}, [None], [{}], [{"task_id": "AUTHOR", "relation": "reveiw"}],
                             [dict(good, output_refs=[])], [dict(good, handoff_ref={"path": "tasks/author/handoff.json"})],
                             [good, good], ["P1"]):
            with self.subTest(dependencies=dependencies):
                task["depends_on"] = dependencies
                mcm.save_records(self.root, "tasks", [task, producer])
                self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])
                self.assertTrue(mcm._record_errors("tasks", [task]))

    def test_review_context_rejects_undelivered_misattributed_unread_or_writable_source(self):
        task, producer, candidate, source = self.review_task()
        originals = json.loads(json.dumps([task, producer, candidate, source]))
        changes = [lambda: producer.update(status="running"), lambda: producer.update(status="rework"),
                   lambda: producer.update(output_readback=[]), lambda: producer.update(outputs=[]),
                   lambda: producer.update(outputs=[dict(self.ref(candidate), version=99)]),
                   lambda: producer.update(outputs=[dict(self.ref(candidate), sha256="0" * 64)]),
                   lambda: candidate.update(_template_only=True),
                   lambda: producer.update(owner_agent_id="pending:author"),
                   lambda: task.update(owner_agent_id=producer["owner_agent_id"]),
                   lambda: candidate.update(author_agent_id="someone-else"), lambda: candidate.update(task_id="OTHER"),
                   lambda: task.update(owner_role="mcm-programmer"), lambda: task.update(allowed_write_paths=["."]),
                   lambda: task.update(allowed_write_paths=[source["path"]]), lambda: task.update(inputs=[]),
                   lambda: task["depends_on"][0]["output_refs"][0].update(version=99),
                   lambda: producer.update(completion_handoff_path="tasks/wrong.json")]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                task, producer, candidate, source = json.loads(json.dumps(originals))
                change()
                mcm.save_records(self.root, "tasks", [task, producer])
                mcm.save_records(self.root, "artifacts", [candidate, source])
                self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])

    def test_review_context_does_not_hide_duplicate_registry_evidence(self):
        task, producer, candidate, source = self.review_task()
        mcm.save_records(self.root, "artifacts", [candidate, candidate, source])
        self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])
        mcm.save_records(self.root, "artifacts", [candidate, source])
        mcm.save_records(self.root, "tasks", [task, producer, producer])
        self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])

    def test_review_context_checks_actual_handoff_and_transitive_bytes(self):
        for target in ("handoff", "upstream", "candidate"):
            with self.subTest(target=target):
                task, producer, candidate, source = self.review_task()
                relative = producer["completion_handoff_path"] if target == "handoff" else source["path"] if target == "upstream" else candidate["path"]
                (self.root / relative).write_text("changed", encoding="utf-8")
                self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])

    def test_review_does_not_override_an_unapproved_execution_dependency(self):
        task, producer, _, _ = self.review_task()
        task["depends_on"].append("EXECUTE")
        mcm.save_records(self.root, "tasks", [task, producer, {"task_id": "EXECUTE", "status": "in_review"}])
        self.assertIn("not approved", " ".join(mcm.context_pack(self.root, "P1")["errors"]))

    def test_pause_overrides_context_writes_registry_and_capacity(self):
        self.task()
        self.config(pause_state={"paused": True, "reason": "actual user stop", "user_message_ref": "USER-PAUSE"})
        self.assertFalse(mcm.context_pack(self.root, "P1")["ready_to_start"])
        with self.assertRaisesRegex(ValueError, "User pause"):
            mcm.write_output(self.root, "src/solver/a.py", b"pass", "programmer", "P1", "programmer-one")
        with self.assertRaisesRegex(ValueError, "User pause"):
            with mcm.registry_lock(self.root):
                pass
        self.assertFalse(mcm.runtime_capacity(self.root, self.snapshot(8))["admit_one_task"])

    def test_project_config_and_team_limit_do_not_prove_host_capacity(self):
        self.config(normal_slots=15, reserve_slots=1)
        report = mcm.runtime_capacity(self.root, self.snapshot())
        self.assertTrue(report["allocation_count_known"])
        self.assertFalse(report["capacity_known"])
        self.assertFalse(report["admit_one_task"])
        self.assertFalse(report["team_limit_is_host_capacity"])

    def test_stale_missing_or_future_snapshot_cannot_admit_tasks(self):
        path = self.snapshot(8)
        payload = mcm.read_json(path)
        for captured in (None, (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                         (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), "2026-01-01T00:00:00"):
            payload["captured_at"] = captured
            mcm.atomic_json(path, payload)
            report = mcm.runtime_capacity(self.root, path)
            self.assertFalse(report["snapshot_fresh"])
            self.assertFalse(report["capacity_known"])
            self.assertFalse(report["admit_one_task"])

    def test_verified_host_8_caps_project_16(self):
        self.config(normal_slots=15, reserve_slots=1)
        report = mcm.runtime_capacity(self.root, self.snapshot(8, 8))
        self.assertEqual(report["effective_total"], 8)
        self.assertFalse(report["admit_one_task"])

    def test_smaller_host_keeps_emergency_slot_out_of_normal_admission(self):
        self.config(normal_slots=15, reserve_slots=1)
        path = self.snapshot(8, 7)
        normal, emergency = mcm.runtime_capacity(self.root, path), mcm.runtime_capacity(self.root, path, True)
        self.assertEqual(normal["effective_normal_slots"], 7)
        self.assertEqual(normal["normal_available"], 0)
        self.assertEqual(normal["reserve_available"], 1)
        self.assertFalse(normal["admit_one_task"])
        self.assertTrue(emergency["admit_one_task"])

    def test_reserve_larger_than_host_cannot_create_normal_capacity(self):
        self.config(normal_slots=7, reserve_slots=3)
        path = self.snapshot(2)
        normal, emergency = mcm.runtime_capacity(self.root, path), mcm.runtime_capacity(self.root, path, True)
        self.assertEqual(normal["normal_available"], 0)
        self.assertEqual(normal["reserve_available"], 2)
        self.assertFalse(normal["admit_one_task"])
        self.assertTrue(emergency["admit_one_task"])

    def test_verified_host_16_separates_team_8_and_preserves_reserve(self):
        self.config(normal_slots=15, reserve_slots=1)
        path = self.snapshot(16, 15)
        normal, reserve = mcm.runtime_capacity(self.root, path), mcm.runtime_capacity(self.root, path, True)
        self.assertEqual(normal["allocated"], 15)
        self.assertEqual(normal["team_member_limit"], 8)
        self.assertFalse(normal["admit_one_task"])
        self.assertTrue(reserve["admit_one_task"])

    def test_parallel_programmers_write_disjoint_files_and_overlap_is_rejected(self):
        first = self.task()
        second = dict(first, task_id="P2", owner_agent_id="programmer-two", allowed_write_paths=["src/pipeline"])
        mcm.save_records(self.root, "tasks", [first, second])
        mcm.write_output(self.root, "src/solver/a.py", b"solver", "programmer", "P1", "programmer-one")
        mcm.write_output(self.root, "src/pipeline/a.py", b"pipeline", "programmer", "P2", "programmer-two")
        second["allowed_write_paths"] = ["src/solver"]
        mcm.save_records(self.root, "tasks", [first, second])
        with self.assertRaisesRegex(ValueError, "Another active task"):
            mcm.write_output(self.root, "src/solver/b.py", b"conflict", "programmer", "P1", "programmer-one")

    def test_optional_code_lead_is_owned_but_not_given_child_file_privileges(self):
        self.task(owner_role="mcm-code-lead", owner_agent_id="integrator", allowed_write_paths=["src/integration"])
        mcm.write_output(self.root, "src/integration/entry.py", b"pass", "code_lead", "P1", "integrator")
        with self.assertRaisesRegex(ValueError, "allowed_write_paths"):
            mcm.write_output(self.root, "src/solver/core.py", b"bad", "code_lead", "P1", "integrator")

    def test_reclaimed_or_expired_handover_beats_old_true_grant(self):
        handover = {"from_agent_id": "old-author", "to_agent_id": "programmer-one", "permission_granted": True,
                    "permission_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "reclaimed_at": mcm.utcnow()}
        self.task(handover=handover)
        with self.assertRaisesRegex(ValueError, "reclaimed"):
            mcm.write_output(self.root, "src/solver/a.py", b"bad", "programmer", "P1", "programmer-one")
        handover.update(reclaimed_at=None, permission_expires_at="2000-01-01T00:00:00Z")
        self.task(handover=handover)
        with self.assertRaisesRegex(ValueError, "expired"):
            mcm.write_output(self.root, "src/solver/a.py", b"bad", "programmer", "P1", "programmer-one")

    def test_handover_checks_source_bytes_before_writing(self):
        row = self.artifact("SOURCE")
        handover = {"from_agent_id": "old-author", "to_agent_id": "programmer-one", "permission_granted": True,
                    "permission_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "source_refs": [{"path": row["path"], "sha256": row["sha256"]}]}
        self.task(handover=handover)
        (self.root / row["path"]).write_text("unexpected author edit", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source SHA256"):
            mcm.write_output(self.root, "src/solver/a.py", b"bad", "programmer", "P1", "programmer-one")

    def test_cli_context_pack_does_not_mutate_registry(self):
        self.task()
        output = io.StringIO()
        with redirect_stdout(output):
            code = mcm.main(["--root", str(self.root), "context-pack", "P1"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["registry_modified"])

    def test_import_records_tool_clock_separately_from_author_clock(self):
        row = self.artifact("MODEL")
        row["created_at"] = "2099-01-01T00:00:00Z"
        path = self.root / "proposal.json"
        mcm.atomic_json(path, row)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(mcm.main(["--root", str(self.root), "import", "artifacts", str(path)]), 0)
        actual = mcm.records(self.root, "artifacts")[0]
        self.assertEqual(actual["created_at"], row["created_at"])
        self.assertLess(datetime.fromisoformat(actual["registry_recorded_at"]).year, 2099)


if __name__ == "__main__":
    unittest.main(verbosity=2)
