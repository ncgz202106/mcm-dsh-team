"""Visible archive/report integration: synthetic fixtures never approve real work."""
from contextlib import redirect_stdout, redirect_stderr
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_report_under_test", ROOT / "scripts/ai_report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class AIReport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / ".mcm-project").mkdir()
        self.archive = self.project / "logs/ai-audit/test"
        self.archive.mkdir(parents=True)
        self.query = r"Check $x_1 & 50% \end{quote}" + "\n    indented"
        self.response = "Visible answer\nSecond text block\n\nComplete tail"
        self.events = [
            {"seq": 0, "type": "request/context", "data": {"provider": "native-provider", "model": "native-model-id"}},
            {"seq": 1, "type": "system/message", "data": {"message": {"content": [{"type": "text", "text": "SYSTEM_ONLY_MARKER"}]}}},
            {"seq": 2, "type": "user/message", "data": {"role": "user", "content": [{"type": "text", "text": self.query}]}},
            {"seq": 3, "type": "tool/result", "data": {"message": {"content": [{"type": "text", "text": "TOOL_ONLY_MARKER"}]}}},
            {"seq": 4, "type": "assistant/message", "data": {"message": {"source": {"provider": "native-provider", "model": "native-model-id"}, "content": [
                {"type": "reasoning", "text": "HIDDEN_REASONING_MARKER"},
                {"type": "text", "text": "Visible answer"}, {"type": "text", "text": "Second text block"}]}}},
            {"seq": 5, "type": "assistant/message", "data": {"message": {"source": {"provider": "native-provider", "model": "native-model-id"}, "content": [{"type": "text", "text": "Complete tail"}]}}},
        ]
        self.attachment_references = []
        self.make_archive()

    def tearDown(self):
        self.temp.cleanup()

    def make_archive(self, complete=True, models=None):
        models = [{"provider": "native-provider", "model": "native-model-id"}] if models is None else models
        lines = [{"type": "mcm-visible-session", "schema_version": 1,
                  "header": {"id": "session-one", "agentPreset": "mcm-captain"}}, *self.events]
        transcript = self.archive / "sessions/captain.visible.jsonl"
        write_jsonl(transcript, lines)
        index = {"session_id": "session-one", "role_preset": "mcm-captain", "actual_models": models,
                 "checkpoint": "H3", "checkpoint_purpose": "Final use review",
                 "prompt_event_seqs": [1, 2, 3],
                 "visible_output_event_seqs": [event["seq"] for event in self.events if event["type"] == "assistant/message"],
                 "human_verification": {"status": "pending"}}
        write_jsonl(self.archive / "ai-use-index.jsonl", [index])
        write_json(self.archive / "attachments.json", {"schema_version": 1, "archived_bytes": False,
                   "references": self.attachment_references})
        manifest = {"schema_version": 1, "root_session_id": "session-one", "checkpoint": "H3",
            "purpose": "Final use review", "captured_at": "2026-10-24T08:00:00Z",
            "transcripts_complete": complete, "archived_sessions": 1,
            "discovered_sessions": 1 if complete else 2,
            "sessions": [{"session_id": "session-one", "role_preset": "mcm-captain",
                "path": "sessions/captain.visible.jsonl", "sha256": file_hash(transcript),
                "source_event_count": len(self.events), "visible_event_count": len(self.events),
                "exported_through_seq": max(event["seq"] for event in self.events)}],
            "warnings": [], "attachment_count": len(self.attachment_references),
            "attachment_bytes_included": False, "human_verification_complete": False}
        write_json(self.archive / "manifest.json", manifest)

    def human_record(self, adopted=True):
        # Tests use an isolated synthetic fixture with simulated human evidence.
        # It is never written to the shipped project or presented as real approval.
        state = "adopted" if adopted else "not_adopted"
        proof = {"source": "human", "synthetic": False, "record_id": "USE-ONE",
            "checked_by": "fixture-human", "checked_at": "2026-10-24T08:10:00Z",
            "query_sha256": report.text_hash(self.query), "response_sha256": report.text_hash(self.response),
            "adoption_status": state, "purpose": "Check the calculation", "purpose_confirmed": True,
            "citations_verified": True}
        proof_path = self.project / "reviews/use-one.json"
        write_json(proof_path, proof)
        citations = self.project / "evidence/source-check.txt"
        citations.parent.mkdir(parents=True, exist_ok=True)
        citations.write_text("Fixture citation review; no source-dependent empirical claim adopted.\n", encoding="utf-8")
        row = {"record_id": "USE-ONE", "session_id": "session-one", "query_event_seq": 2,
            "assistant_event_seqs": [4, 5], "purpose": "Check the calculation", "adoption_status": state,
            "synthetic": False, "citations_verified": True,
            "citation_evidence": [{"path": "evidence/source-check.txt", "sha256": file_hash(citations)}],
            "human_check": {"status": "verified", "source": "human", "checked_by": "fixture-human",
                "checked_at": proof["checked_at"], "evidence_ref": {"path": "reviews/use-one.json", "sha256": file_hash(proof_path)}}}
        self.uses_path = self.project / ".mcm/ai-usage.json"
        write_json(self.uses_path, {"format_version": 1, "records": [row]})
        return row

    def save_uses(self, row):
        write_json(self.uses_path, {"format_version": 1, "records": [row]})

    def test_draft_keeps_complete_visible_text_and_never_copies_hidden_or_tools(self):
        text, metadata = report.build_report(self.project, [self.archive])
        self.assertIn("DRAFT", text)
        self.assertIn("Complete", text)
        self.assertIn("tail", text)
        self.assertIn(r"\$x\_1", text)
        self.assertIn(r"\textbackslash{}end\{quote\}", text)
        for excluded in ("SYSTEM_ONLY_MARKER", "TOOL_ONLY_MARKER", "HIDDEN_REASONING_MARKER", "minted"):
            self.assertNotIn(excluded, text)
        self.assertEqual(metadata["interactions"][0]["query_sha256"], report.text_hash(self.query))
        self.assertEqual(metadata["interactions"][0]["response_sha256"], report.text_hash(self.response))
        self.assertEqual(metadata["interactions"][0]["review_state"], "pending")
        self.assertFalse(metadata["official_submission_approved"])

    def test_final_requires_human_records(self):
        with self.assertRaisesRegex(ValueError, "human-use record"):
            report.build_report(self.project, [self.archive], final=True)

    def test_final_with_bound_human_evidence_retains_native_model_id(self):
        self.human_record()
        text, metadata = report.build_report(self.project, [self.archive], self.uses_path, final=True)
        self.assertNotIn("DRAFT", text)
        self.assertIn("native-model-id", text)
        self.assertEqual(metadata["status"], "final_from_supplied_human_records")
        self.assertFalse(metadata["human_identity_authenticated"])

    def test_synthetic_or_template_human_record_cannot_finalize(self):
        row = self.human_record()
        for key in ("synthetic", "_template_only"):
            altered = copy.deepcopy(row)
            altered[key] = True
            self.save_uses(altered)
            with self.assertRaisesRegex(ValueError, "real, instantiated"):
                report.build_report(self.project, [self.archive], self.uses_path, final=True)

    def test_partial_archive_is_draft_only(self):
        self.make_archive(complete=False)
        _, metadata = report.build_report(self.project, [self.archive])
        self.assertTrue(any("Partial" in warning for warning in metadata["warnings"]))
        with self.assertRaisesRegex(ValueError, "Partial"):
            report.build_report(self.project, [self.archive], final=True)

    def test_missing_session_is_not_silently_omitted(self):
        (self.archive / "sessions/captain.visible.jsonl").unlink()
        with self.assertRaisesRegex(ValueError, "Missing evidence file"):
            report.build_report(self.project, [self.archive])

    def test_transcript_digest_mismatch_is_rejected(self):
        with (self.archive / "sessions/captain.visible.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            report.build_report(self.project, [self.archive])

    def test_index_cannot_invent_a_model_or_skip_output(self):
        self.make_archive(models=[{"provider": "invented", "model": "marketing-name"}])
        with self.assertRaisesRegex(ValueError, "model index disagrees"):
            report.build_report(self.project, [self.archive])
        self.make_archive()
        index = report.json_lines(self.archive / "ai-use-index.jsonl")[0]
        index["visible_output_event_seqs"] = [4]
        write_jsonl(self.archive / "ai-use-index.jsonl", [index])
        with self.assertRaisesRegex(ValueError, "output references"):
            report.build_report(self.project, [self.archive])

    def test_unknown_actual_model_prevents_final_even_if_index_has_a_guess(self):
        self.events = [event for event in self.events if event["type"] != "request/context"]
        for event in self.events:
            if event["type"] == "assistant/message":
                event["data"]["message"].pop("source")
        self.make_archive()
        text, _ = report.build_report(self.project, [self.archive])
        self.assertIn("UNKNOWN", text)
        with self.assertRaisesRegex(ValueError, "Missing actual model"):
            report.build_report(self.project, [self.archive], final=True)

    def test_human_review_cannot_omit_the_tail_or_change_purpose(self):
        row = self.human_record()
        row["assistant_event_seqs"] = [4]
        self.save_uses(row)
        with self.assertRaisesRegex(ValueError, "every corresponding"):
            report.build_report(self.project, [self.archive], self.uses_path, final=True)
        row["assistant_event_seqs"] = [4, 5]
        row["purpose"] = "Different unreviewed purpose"
        self.save_uses(row)
        with self.assertRaisesRegex(ValueError, "bind the reviewed"):
            report.build_report(self.project, [self.archive], self.uses_path, final=True)

    def test_citation_evidence_is_required_for_adopted_text(self):
        row = self.human_record()
        row["citation_evidence"] = []
        self.save_uses(row)
        with self.assertRaisesRegex(ValueError, "citation evidence"):
            report.build_report(self.project, [self.archive], self.uses_path, final=True)

    def test_changed_human_evidence_digest_is_rejected(self):
        self.human_record()
        (self.project / "reviews/use-one.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            report.build_report(self.project, [self.archive], self.uses_path, final=True)

    def test_attachment_manifest_is_not_a_preserved_original(self):
        self.events[2]["data"]["content"].append({"type": "image", "attachmentId": "image-one"})
        self.attachment_references = [{"attachmentId": "image-one", "mediaType": "image/png", "archived_bytes": False}]
        self.make_archive()
        row = self.human_record()
        with self.assertRaisesRegex(ValueError, "preserved original"):
            report.build_report(self.project, [self.archive], self.uses_path, final=True)
        original = self.project / "input/attachments/original.png"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"fixture original image bytes")
        row["attachment_checks"] = [{"attachment_id": "image-one", "path": "input/attachments/original.png",
            "sha256": file_hash(original), "checked_by": "fixture-human"}]
        self.save_uses(row)
        text, _ = report.build_report(self.project, [self.archive], self.uses_path, final=True)
        self.assertIn("Bytes are not part", text)

    def test_multiple_checkpoints_deduplicate_immutable_events(self):
        duplicate = self.project / "logs/ai-audit/second"
        shutil.copytree(self.archive, duplicate)
        _, metadata = report.build_report(self.project, [self.archive, duplicate])
        self.assertEqual(len(metadata["interactions"]), 1)
        self.assertEqual(len(metadata["archives"]), 2)

    def test_conflicting_events_between_snapshots_are_rejected(self):
        duplicate = self.project / "logs/ai-audit/second"
        shutil.copytree(self.archive, duplicate)
        path = duplicate / "sessions/captain.visible.jsonl"
        lines = report.json_lines(path)
        lines[-1]["data"]["message"]["content"][0]["text"] = "Changed immutable event"
        write_jsonl(path, lines)
        manifest = report.read_json(duplicate / "manifest.json")
        manifest["sessions"][0]["sha256"] = file_hash(path)
        write_json(duplicate / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "immutable session event"):
            report.build_report(self.project, [self.archive, duplicate])

    def test_reviewed_unadopted_interaction_is_in_coverage_not_formal_body(self):
        self.human_record(adopted=False)
        text, metadata = report.build_report(self.project, [self.archive], self.uses_path, final=True)
        self.assertEqual(metadata["included_interactions"], 0)
        self.assertEqual(metadata["interactions"][0]["review_state"], "not_adopted")
        self.assertNotIn("exact archived text", text)

    def test_tool_event_cannot_be_declared_a_query(self):
        row = self.human_record()
        row["query_event_seq"] = 3
        self.save_uses(row)
        with self.assertRaisesRegex(ValueError, "unarchived query"):
            report.build_report(self.project, [self.archive], self.uses_path, final=True)

    def test_no_overwrite_and_no_output_path_escape(self):
        text, metadata = report.build_report(self.project, [self.archive])
        saved = report.save_report(self.project, "paper/ai-use/report.tex", text, metadata)
        before = Path(saved["report"]).read_bytes()
        with self.assertRaisesRegex(ValueError, "already exist"):
            report.save_report(self.project, "paper/ai-use/report.tex", "changed", metadata)
        self.assertEqual(Path(saved["report"]).read_bytes(), before)
        with self.assertRaises(ValueError):
            report.save_report(self.project, "../escape.tex", text, metadata)

    def test_cli_resolves_relative_inputs_against_explicit_project_root(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = report.main(["--root", str(self.project), "--archive", "logs/ai-audit/test"])
        self.assertEqual(code, 0, errors.getvalue())
        self.assertTrue((self.project / "paper/ai-use/report-v1.tex").is_file())
        metadata = report.read_json(self.project / "paper/ai-use/report-v1.coverage.json")
        self.assertEqual(metadata["status"], "draft")
        self.assertFalse(metadata["official_submission_approved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
