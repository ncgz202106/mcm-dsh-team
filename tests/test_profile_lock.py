"""Synthetic pnpm 9 fixtures; never read or write an installed DSH profile."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check-profile-lock.py"
SPEC = importlib.util.spec_from_file_location("check_profile_lock", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)

LOCK = """\
lockfileVersion: '9.0'

settings:
  autoInstallPeers: true
  excludeLinksFromLockfile: false

importers:

  .:
    dependencies:
      '@synthetic/local-agent':
        specifier: link:./packages/local-agent
        version: link:packages/local-agent
      synthetic-core:
        specifier: ^1.2.3
        version: 1.2.4
    devDependencies:
      synthetic-test:
        specifier: ~2.0.0
        version: 2.0.1
    optionalDependencies:
      synthetic-platform:
        specifier: 3.0.0
        version: 3.0.0

packages:
  synthetic-core@1.2.4:
    resolution: {integrity: sha512-SYNTHETIC}

snapshots:
  synthetic-core@1.2.4: {}
"""

MANIFEST = {
    "name": "synthetic-profile",
    "dependencies": {"@synthetic/local-agent": "link:./packages/local-agent", "synthetic-core": "^1.2.3"},
    "devDependencies": {"synthetic-test": "~2.0.0"},
    "optionalDependencies": {"synthetic-platform": "3.0.0"},
}


class ProfileLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, manifest=None, lock=LOCK):
        if manifest is None:
            manifest = MANIFEST
        (self.root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.root / "pnpm-lock.yaml").write_text(lock, encoding="utf-8")

    def assess(self, manifest=None, lock=LOCK):
        self.write(manifest, lock)
        return CHECKER.check_profile(self.root)

    def assert_unknown(self, result, reason=None):
        self.assertEqual(result["status"], "unknown", result)
        self.assertEqual(result["differences"], [])
        self.assertTrue(result["reason_codes"])
        if reason:
            self.assertIn(reason, result["reason_codes"])

    def test_malformed_dependency_keys_do_not_disclose_urls(self):
        secret = "https://user:fixture-secret@example.invalid/private"
        result = self.assess({"dependencies": {secret: "1.0.0"}})
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn(secret, json.dumps(result))
        lock = LOCK.replace("synthetic-core:", "'" + secret + "':", 1)
        result = self.assess(lock=lock)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn(secret, json.dumps(result))

    def test_all_direct_sections_and_local_link_are_consistent(self):
        result = self.assess()
        self.assertEqual(result, {
            "schema_version": 1, "status": "consistent", "scope": "direct_specifiers_only",
            "pnpm_lockfile_major": 9, "differences": [], "reason_codes": [],
        })

    def test_three_manifest_only_links_are_reported_without_values(self):
        manifest = json.loads(json.dumps(MANIFEST))
        for name in ("synthetic-agent-a", "synthetic-agent-b", "synthetic-agent-c"):
            manifest["dependencies"][name] = "link:./private-local-path/" + name
        result = self.assess(manifest)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["differences"], [
            {"section": "dependencies", "dependency": name, "kind": "missing_in_lock"}
            for name in ("synthetic-agent-a", "synthetic-agent-b", "synthetic-agent-c")
        ])
        self.assertNotIn("private-local-path", json.dumps(result))
        self.assertNotIn("link:", json.dumps(result))

    def test_mismatch_extra_and_section_moves_are_not_resolved_versions(self):
        manifest = json.loads(json.dumps(MANIFEST))
        manifest["dependencies"]["synthetic-core"] = "^1.2.4"
        manifest["devDependencies"].pop("synthetic-test")
        manifest["optionalDependencies"]["synthetic-test"] = "~2.0.0"
        result = self.assess(manifest)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["differences"], [
            {"section": "dependencies", "dependency": "synthetic-core", "kind": "specifier_mismatch"},
            {"section": "devDependencies", "dependency": "synthetic-test", "kind": "extra_in_lock"},
            {"section": "optionalDependencies", "dependency": "synthetic-test", "kind": "missing_in_lock"},
        ])

    def test_exact_specifier_not_equivalence_or_resolved_version(self):
        for replacement in ("1.2.4", "^1.2.3 ", ">=1.2.3 <2"):
            with self.subTest(replacement=replacement):
                manifest = json.loads(json.dumps(MANIFEST))
                manifest["dependencies"]["synthetic-core"] = replacement
                result = self.assess(manifest)
                self.assertEqual(result["status"], "mismatch")
                self.assertEqual(result["differences"][0]["kind"], "specifier_mismatch")

    def test_both_quote_styles_escapes_comments_bom_and_crlf(self):
        manifest = {"dependencies": {
            "@synthetic/quoted": "file:./has'quote",
            "synthetic-double": "file:./space # retained",
            "synthetic-unicode": "file:./café",
        }}
        lock = "\ufeff" + textwrap.dedent('''\
            ---
            "lockfileVersion": "9.0" # pnpm 9
            'importers':
              '.':
                dependencies:
                  '@synthetic/quoted':
                    specifier: 'file:./has''quote' # comment
                    version: link:elsewhere
                  synthetic-double:
                    specifier: "file:./space # retained"
                    version: link:elsewhere
                  synthetic-unicode:
                    specifier: "file:./caf\\u00e9"
                    version: link:elsewhere
            ...
        ''').replace("\n", "\r\n")
        self.assertEqual(self.assess(manifest, lock)["status"], "consistent")

    def test_other_workspace_importer_is_not_compared_to_root(self):
        lock = LOCK.replace("packages:\n", "  packages/other:\n    dependencies:\n      synthetic-other:\n        specifier: ^99.0.0\n        version: 99.0.1\n\npackages:\n")
        self.assertEqual(self.assess(lock=lock)["status"], "consistent")

    def test_unrelated_sections_are_not_general_yaml_or_pnpm_validation(self):
        lock = LOCK + "\nsyntheticOpaqueSection:\n  - anything: [with, complex, flow]\n  ? complex YAML key\n  : &syntheticAnchor {value: tagged}\n"
        self.assertEqual(self.assess(lock=lock)["status"], "consistent")

    def test_empty_root_and_empty_sections(self):
        for root in ("  .: {}\n", "  .:\n    dependencies: {}\n    devDependencies: {}\n    optionalDependencies: {}\n"):
            with self.subTest(root=root):
                self.assertEqual(self.assess({}, "lockfileVersion: 9.0\nimporters:\n" + root)["status"], "consistent")

    def test_missing_input_files_and_unreadable_file_are_unknown(self):
        self.assert_unknown(CHECKER.check_profile(self.root), "manifest_missing")
        self.write()
        (self.root / "pnpm-lock.yaml").unlink()
        self.assert_unknown(CHECKER.check_profile(self.root), "lockfile_missing")
        (self.root / "pnpm-lock.yaml").mkdir()
        self.assert_unknown(CHECKER.check_profile(self.root), "lockfile_unreadable")

    def test_non_9_or_missing_lockfile_version_is_unknown(self):
        for value in ("'6.0'", "'8.0'", "'10.0'", "null", "true", "{}"):
            with self.subTest(value=value):
                self.assert_unknown(self.assess(lock=LOCK.replace("'9.0'", value, 1)), "unsupported_lockfile_version")
        self.assert_unknown(self.assess(lock=LOCK.replace("lockfileVersion: '9.0'\n", "")), "lockfile_version_missing")

    def test_missing_importers_or_root_is_unknown(self):
        for lock, reason in (
            ("lockfileVersion: '9.0'\npackages: {}\n", "importers_missing"),
            ("lockfileVersion: '9.0'\nimporters: {}\n", "root_importer_missing"),
            ("lockfileVersion: '9.0'\nimporters:\n  other: {}\n", "root_importer_missing"),
            ("lockfileVersion: '9.0'\nimporters:\n  .: null\n", "root_importer_not_mapping"),
        ):
            with self.subTest(reason=reason):
                self.assert_unknown(self.assess(lock=lock), reason)

    def test_presence_only_null_or_typed_specifier_never_consistent(self):
        for replacement in ("specifier:", "specifier: null", "specifier: ~", "specifier: true", "specifier: 1.2"):
            with self.subTest(replacement=replacement):
                lock = LOCK.replace("specifier: ^1.2.3", replacement)
                self.assert_unknown(self.assess(lock=lock), "lock_specifier_missing_or_not_string")
        self.assert_unknown(self.assess(lock=LOCK.replace("        specifier: ^1.2.3\n", "")), "lock_specifier_missing_or_not_string")
        lock = LOCK.replace("synthetic-core:\n        specifier: ^1.2.3\n        version: 1.2.4", "synthetic-core:")
        self.assert_unknown(self.assess(lock=lock), "lock_specifier_missing_or_not_string")

    def test_duplicate_keys_at_every_relevant_level_are_unknown(self):
        variants = (
            LOCK + "\nimporters: {}\n",
            LOCK.replace("  .:\n", "  .: {}\n  .:\n"),
            LOCK.replace("    dependencies:\n", "    dependencies: {}\n    dependencies:\n"),
            LOCK.replace("      synthetic-core:\n", "      synthetic-core: {}\n      synthetic-core:\n"),
            LOCK.replace("        specifier: ^1.2.3\n", "        specifier: ^0.1.0\n        specifier: ^1.2.3\n"),
        )
        for lock in variants:
            with self.subTest(lock=lock):
                self.assert_unknown(self.assess(lock=lock), "duplicate_yaml_key")

    def test_unsupported_importer_references_merge_tags_flow_and_tabs(self):
        variants = (
            (LOCK.replace("  .:\n", "  .: &root\n"), "unsupported_yaml_reference_or_tag"),
            (LOCK.replace("  .:\n", "  .: *root\n"), "unsupported_yaml_reference_or_tag"),
            (LOCK.replace("  .:\n", "  .: !!map\n"), "unsupported_yaml_reference_or_tag"),
            (LOCK.replace("  .:\n", "  .:\n    <<: *root\n"), "unsupported_yaml_merge"),
            (LOCK.replace("specifier: ^1.2.3", "specifier: {value: ^1.2.3}"), "unsupported_yaml_flow"),
            (LOCK.replace("specifier: ^1.2.3", "specifier: [^1.2.3]"), "unsupported_yaml_flow"),
            (LOCK.replace("  .:\n", "\t.:\n"), "unsupported_yaml_tab_indentation"),
            (LOCK.replace("specifier: ^1.2.3", "specifier: |"), "unsupported_yaml_scalar"),
        )
        for lock, reason in variants:
            with self.subTest(reason=reason):
                self.assert_unknown(self.assess(lock=lock), reason)

    def test_top_level_merge_and_multiple_documents_are_unknown(self):
        self.assert_unknown(self.assess(lock=LOCK + "\n<<: *root\n"), "unsupported_yaml_merge")
        self.assert_unknown(self.assess(lock=LOCK + "\n---\nimporters: {}\n"), "unsupported_yaml_multiple_documents")

    def test_colon_inside_comment_is_not_an_entry(self):
        lock = LOCK.replace("      synthetic-core:", "      synthetic-core # invalid key: ")
        self.assert_unknown(self.assess(lock=lock), "unsupported_yaml_mapping")

    def test_malformed_manifest_is_unknown_without_source_values(self):
        self.write()
        for manifest in ('{"dependencies":{"x":"private-secret","x":"again"}}', "[]", '{"dependencies":{"x":null}}', '{"dependencies":null}', "{"):
            with self.subTest(manifest=manifest):
                (self.root / "package.json").write_text(manifest, encoding="utf-8")
                result = CHECKER.check_profile(self.root)
                self.assert_unknown(result)
                self.assertNotIn("private-secret", json.dumps(result))

    def test_invalid_utf8_is_unknown(self):
        self.write()
        (self.root / "pnpm-lock.yaml").write_bytes(b"\xff\xfe")
        self.assert_unknown(CHECKER.check_profile(self.root), "lockfile_unreadable")

    def test_cli_single_json_no_stderr_exit_zero_and_read_only(self):
        self.write()
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        process = subprocess.run([sys.executable, str(SCRIPT), "--profile-root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stderr, "")
        self.assertEqual(len(process.stdout.splitlines()), 1)
        self.assertEqual(json.loads(process.stdout)["status"], "consistent")
        after = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.assertEqual(before, after)

    def test_cli_mismatch_unknown_and_invalid_arguments_always_zero_json(self):
        for args, expected in ((["--profile-root", str(self.root)], "unknown"), ([], "unknown"), (["--bad-argument"], "unknown")):
            with self.subTest(args=args):
                process = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(process.stderr, "")
                self.assertEqual(json.loads(process.stdout)["status"], expected)
        manifest = {"dependencies": {"synthetic-added": "https://private.invalid/synthetic-secret.tgz"}}
        self.write(manifest, "lockfileVersion: '9.0'\nimporters:\n  .: {}\n")
        process = subprocess.run([sys.executable, str(SCRIPT), "--profile-root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stderr, "")
        self.assertEqual(json.loads(process.stdout)["status"], "mismatch")
        self.assertNotIn("private.invalid", process.stdout)
        self.assertNotIn("synthetic-secret", process.stdout)
        self.assertNotIn(str(self.root), process.stdout)


if __name__ == "__main__":
    unittest.main()
