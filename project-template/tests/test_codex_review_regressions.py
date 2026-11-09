"""Independent fault probes for the Codex control regression review."""

from pathlib import Path
import stat
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import test_codex_control as controls

c = controls.c
m = controls.m


class ControlReviewRegressions(TestCase):
    def setUp(self):
        self.fixture = controls.Controls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root

    def test_demo_rejects_scientific_file_at_scan_root(self):
        science = self.fixture.put("data", "unregistered scientific data")
        with self.assertRaisesRegex(ValueError, "real data, models and results directories"):
            c.init_demo(self.root)
        self.assertEqual(science.read_text(encoding="utf-8"), "unregistered scientific data")
        self.assertFalse((self.root / ".mcm/codex/synthetic-demo.json").exists())

    def test_demo_rejects_link_like_roots_and_nested_directories(self):
        nested = self.root / "models/nested"
        nested.mkdir(parents=True)
        lstat = Path.lstat
        for folder, message in ((nested.parent, "real data"), (nested, "scientific data")):
            for metadata in (
                SimpleNamespace(st_mode=stat.S_IFLNK),
                SimpleNamespace(st_mode=stat.S_IFDIR, st_reparse_tag=stat.IO_REPARSE_TAG_MOUNT_POINT),
            ):
                with self.subTest(folder=folder.name, metadata=metadata):
                    def simulated_lstat(path):
                        return metadata if path == folder else lstat(path)

                    with patch.object(Path, "lstat", simulated_lstat):
                        with self.assertRaisesRegex(ValueError, message):
                            c.init_demo(self.root)
                    self.assertFalse((self.root / ".mcm/codex/synthetic-demo.json").exists())

    def test_demo_rejects_unexpected_or_modified_scaffold_files(self):
        for relative, content in (
            ("data/processed/.gitkeep", "unregistered observations"),
            ("models/unexpected/.gitkeep", ""),
            ("data/raw/README.md", "a replacement with scientific data"),
        ):
            with self.subTest(relative=relative):
                fixture = controls.Controls()
                fixture.setUp()
                self.addCleanup(fixture.tearDown)
                fixture.put(relative, content)
                with self.assertRaisesRegex(ValueError, "scientific data"):
                    c.init_demo(fixture.root)
                self.assertFalse((fixture.root / ".mcm/codex/synthetic-demo.json").exists())

    def test_intake_copy_does_not_absorb_unrelated_protected_edit(self):
        paper = self.fixture.put("paper/main.tex", "original")
        self.fixture.handoff()
        baseline = self.root / ".mcm/codex/protected.json"
        baseline_before = baseline.read_bytes()
        tasks_before = (self.root / ".mcm/tasks.json").read_bytes()
        artifacts_before = (self.root / ".mcm/artifacts.json").read_bytes()
        copyfile = c.shutil.copyfile

        def copy_and_modify(source, target):
            result = copyfile(source, target)
            paper.write_text("unauthorized during intake", encoding="utf-8")
            return result

        with patch.object(c.shutil, "copyfile", side_effect=copy_and_modify):
            with self.assertRaisesRegex(ValueError, "Protected files changed"):
                c.accept(self.root, "T1", "reviews/review.json")

        report = c.recover(self.root)
        self.assertFalse(report["ok"])
        self.assertEqual([row["path"] for row in report["integrity"]["changes"]], ["paper/main.tex"])
        self.assertEqual(len(report["unfinished_transactions"]), 1)
        journal = self.root / report["unfinished_transactions"][0]
        self.assertEqual(m.read_json(journal)["state"], "prepared")
        self.assertEqual(baseline.read_bytes(), baseline_before)
        self.assertEqual((self.root / ".mcm/tasks.json").read_bytes(), tasks_before)
        self.assertEqual((self.root / ".mcm/artifacts.json").read_bytes(), artifacts_before)
        self.assertFalse((self.root / ".mcm/codex/accepted").exists())

    def test_intake_rejects_review_substituted_after_validation(self):
        self.fixture.handoff()
        validate_review = c._review

        def validate_then_replace(root, task, delivery, review_path, *args, **kwargs):
            review = validate_review(root, task, delivery, review_path, *args, **kwargs)
            failed_review = m.read_json(self.root / review_path)
            self.fixture.put(review_path, dict(failed_review, status="failed"))
            return review

        with patch.object(c, "_review", side_effect=validate_then_replace):
            with self.assertRaisesRegex(ValueError, "[Rr]eview"):
                c.accept(self.root, "T1", "reviews/review.json")

        self.assertEqual(m.records(self.root, "artifacts"), [])

    def test_intake_rejects_delivered_manifest_replaced_during_copy(self):
        _, delivery = self.fixture.handoff()
        copyfile = c.shutil.copyfile

        def copy_then_replace(source, target):
            result = copyfile(source, target)
            changed = dict(delivery, note="substituted after validated delivery")
            self.fixture.put("tasks/T1/delivery.json", changed)
            return result

        with patch.object(c.shutil, "copyfile", side_effect=copy_then_replace):
            with self.assertRaisesRegex(ValueError, "[Mm]anifest"):
                c.accept(self.root, "T1", "reviews/review.json")

        self.assertEqual(m.records(self.root, "artifacts"), [])

    def test_claim_pins_declared_output_contract(self):
        claim = self.fixture.start(outputs=[{"artifact_id": "DECLARED"}])
        self.fixture.manifest(claim)
        rows = m.records(self.root, "tasks")
        rows[0]["outputs"] = [{"artifact_id": "RESULT-1"}]
        m.save_records(self.root, "tasks", rows)
        before = (self.root / ".mcm/tasks.json").read_bytes()

        with self.assertRaisesRegex(ValueError, "contract changed"):
            c.deliver(self.root, "T1", "tasks/T1/delivery.json")

        self.assertEqual((self.root / ".mcm/tasks.json").read_bytes(), before)
        self.assertEqual(m.records(self.root, "tasks")[0]["codex"]["state"], "claimed")

    def test_delivery_respects_declared_output_properties(self):
        fields = {
            "kind": "model",
            "path": "tasks/T1/expected.json",
            "version": 2,
            "generation": "different-run",
            "owner_role": "mcm-figure",
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                self._check_declared_output_field(field, value)

    def test_delivery_accepts_matching_declared_output_properties(self):
        claim = self.fixture.start(outputs=[{
            "artifact_id": "RESULT-1",
            "kind": "result",
            "path": "tasks/T1/result.json",
            "version": 1,
            "generation": "synthetic-run-1",
            "owner_role": "mcm-programmer",
        }])
        self.fixture.manifest(claim)
        self.assertTrue(c.deliver(self.root, "T1", "tasks/T1/delivery.json")["ok"])

    def _check_declared_output_field(self, field, value):
        fixture = controls.Controls()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        claim = fixture.start(outputs=[{"artifact_id": "RESULT-1", field: value}])
        fixture.manifest(claim)
        with self.assertRaisesRegex(ValueError, "[Dd]eclared|contract"):
            c.deliver(fixture.root, "T1", "tasks/T1/delivery.json")

    def test_recover_and_preflight_report_residual_lock_without_removing_it(self):
        c.init_demo(self.root)
        self.fixture.task()
        lock = self.fixture.put(".mcm/write.lock", {
            "pid": 987654321, "actor": "captain", "started_at": "2026-01-01T00:00:00Z"
        })
        before = lock.read_bytes()

        report = c.recover(self.root)
        self.assertFalse(report["ok"])
        self.assertTrue(report["writer_lock"]["present"])
        self.assertEqual(report["writer_lock"]["pid"], 987654321)
        self.assertTrue(report["writer_lock"]["action"])
        self.assertFalse(report["registry_modified"])
        preflight = c.preflight(self.root, "T1", synthetic_demo=True)
        self.assertFalse(preflight["ok"])
        self.assertRegex(" ".join(preflight["errors"]), "writer lock")
        with self.assertRaisesRegex(ValueError, "writer already active"):
            c.claim(self.root, "T1", "synthetic-author", self.fixture.role, self.fixture.role_hash, True)
        self.assertEqual(lock.read_bytes(), before)

    def test_protect_rejects_change_between_initial_scan_and_refresh(self):
        paper = self.fixture.put("paper/main.tex", "original")
        c.protect(self.root)
        baseline = self.root / ".mcm/codex/protected.json"
        before = baseline.read_bytes()
        scan = c.protected_files
        scans = 0

        def scan_and_modify(root):
            nonlocal scans
            current = scan(root)
            scans += 1
            if scans == 1:
                paper.write_text("unauthorized after initial scan", encoding="utf-8")
            return current

        with patch.object(c, "protected_files", side_effect=scan_and_modify):
            with self.assertRaisesRegex(ValueError, "Protected files changed"):
                c.protect(self.root)

        self.assertEqual(baseline.read_bytes(), before)
        self.assertEqual([row["path"] for row in c.integrity(self.root)["changes"]], ["paper/main.tex"])

    def test_recover_classifies_malformed_writer_lock_and_leaves_it_untouched(self):
        c.init_demo(self.root)
        self.fixture.task()
        for content in ("", "{broken", [], {}, {"pid": True, "started_at": []}):
            with self.subTest(content=content):
                lock = self.fixture.put(".mcm/write.lock", content)
                before = lock.read_bytes()
                report = c.recover(self.root)
                self.assertFalse(report["ok"])
                self.assertTrue(report["writer_lock"]["present"])
                self.assertTrue(report["writer_lock"].get("malformed"))
                self.assertFalse(c.preflight(self.root, "T1", synthetic_demo=True)["ok"])
                self.assertEqual(lock.read_bytes(), before)

    def test_dangling_writer_lock_still_blocks_preflight(self):
        c.init_demo(self.root)
        self.fixture.task()
        lock = self.root / ".mcm/write.lock"
        is_symlink = Path.is_symlink

        def simulated_symlink(path):
            return path == lock or is_symlink(path)

        with patch.object(Path, "is_symlink", simulated_symlink):
            self.assertFalse(lock.exists())
            report = c.recover(self.root)
            self.assertFalse(report["ok"])
            self.assertTrue(report["writer_lock"]["present"])
            self.assertTrue(report["writer_lock"]["malformed"])
            self.assertFalse(c.preflight(self.root, "T1", synthetic_demo=True)["ok"])
