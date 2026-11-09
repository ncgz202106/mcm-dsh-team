"""Independent installer interruption probes using a synthetic skill payload."""

from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from test_bundle import installer


class InstallRecovery(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "skills/mcm-team"
        self.backups = self.root / "backups"
        source = self.root / "payload.md"
        source.write_text("synthetic skill payload", encoding="utf-8")
        payload = patch.object(installer, "payload", return_value={"SKILL.md": source})
        payload.start()
        self.addCleanup(payload.stop)

    def install(self):
        return installer.install(self.target, self.backups)

    def test_failed_prepared_journal_leaves_active_update_intact(self):
        self.install()
        prior = (self.target / installer.RECEIPT).read_bytes()
        write = installer.write

        def fail_prepared(path, record):
            if path.name == "receipt.json":
                self.assertEqual(record["state"], "prepared")
                raise OSError("injected preparation journal failure")
            return write(path, record)

        with patch.object(installer, "write", side_effect=fail_prepared):
            with self.assertRaisesRegex(OSError, "preparation journal failure"):
                self.install()

        self.assertEqual((self.target / installer.RECEIPT).read_bytes(), prior)
        self.assertEqual(len(list(self.backups.glob("*/previous"))), 0)

    def test_failed_final_journal_update_still_allows_exact_rollback(self):
        self.install()
        prior = (self.target / installer.RECEIPT).read_bytes()
        write = installer.write

        def fail_installed(path, record):
            if path.name == "receipt.json" and record["state"] == "installed":
                raise OSError("injected final journal failure")
            return write(path, record)

        with patch.object(installer, "write", side_effect=fail_installed):
            with self.assertRaisesRegex(OSError, "final journal failure"):
                self.install()

        self.assertNotEqual((self.target / installer.RECEIPT).read_bytes(), prior)
        active = installer.current_state(self.target)
        journal = Path(active["backup"]) / "receipt.json"
        self.assertEqual(installer.load(journal)["state"], "prepared")
        self.assertEqual((journal.parent / "previous" / installer.RECEIPT).read_bytes(), prior)
        rolled_back = installer.rollback(journal)
        self.assertTrue(rolled_back["restored_previous"])
        self.assertEqual(rolled_back["deleted_files"], 0)
        self.assertEqual((self.target / installer.RECEIPT).read_bytes(), prior)
        self.assertEqual(installer.load(journal)["state"], "rolled_back")

    def test_interrupted_promotion_after_moving_previous_has_recovery_entry(self):
        self.install()
        prior = (self.target / installer.RECEIPT).read_bytes()
        rename = Path.rename

        def interrupt_promotion(source, destination):
            if source.name.startswith("mcm-team.staging-"):
                raise KeyboardInterrupt("injected process interruption")
            return rename(source, destination)

        with patch.object(Path, "rename", interrupt_promotion):
            with self.assertRaisesRegex(KeyboardInterrupt, "process interruption"):
                self.install()

        self.assertFalse(self.target.exists())
        previous, = self.backups.glob("*/previous")
        journal = previous.parent / "receipt.json"
        self.assertEqual(installer.load(journal)["state"], "prepared")
        self.assertTrue(installer.rollback(journal)["restored_previous"])
        self.assertEqual((self.target / installer.RECEIPT).read_bytes(), prior)

    def test_rollback_rejects_a_different_managed_previous_receipt(self):
        self.install()
        update = self.install()
        active = (self.target / installer.RECEIPT).read_bytes()
        journal = Path(update["receipt"])
        previous = journal.parent / "previous"
        different = installer.load(previous / installer.RECEIPT)
        different["backup"] = str(self.backups / "unrelated-transaction")
        installer.write(previous / installer.RECEIPT, different)
        with self.assertRaisesRegex(ValueError, "Backup receipt changed"):
            installer.rollback(journal)
        self.assertEqual((self.target / installer.RECEIPT).read_bytes(), active)
        self.assertFalse((journal.parent / "rolled-back-installation").exists())
