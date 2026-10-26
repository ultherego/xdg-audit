"""Access diagnostics regression tests: no root, no automatic PURGE."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
from xdg_access import authority_context, diagnose_access, repair_owner_directory, needs_access_recovery
from xdg_quarantine_lifecycle import capture_inventory


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="xdg-access-test-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.roots = audit.xdg_roots(self.home)
        for path in self.roots.values():
            path.mkdir(parents=True, exist_ok=True)
        self.run_id = "20261026-103000-120000"
        self.base = audit.quarantine_dir(self.home, self.roots)
        self.run = self.base / self.run_id
        self.tree = self.run / "cache" / "Shelly"
        self.pkg = self.tree / "lib32-gstreamer" / "pkg"
        self.pkg.mkdir(parents=True)
        self.original = self.roots["cache"] / "Shelly"
        initial = self.tree.lstat()
        self.row = {
            "scope": "cache", "source": str(self.original),
            "destination": str(self.tree),
            "identity": [initial.st_dev, initial.st_ino, stat.S_IFDIR],
            "move_status": "moving",
        }
        self.payload = {"format": "intent-journal-v3", "created": self.run_id,
                        "items": [self.row]}
        self.manifest = self.run / "manifest.json"
        self.write_manifest()
        os.chmod(self.pkg, 0o111)
        self.addCleanup(lambda: os.chmod(self.pkg, 0o700) if self.pkg.exists() else None)

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.payload), encoding="utf-8")

    def test_access_denied_pkg_has_exact_path_and_user_identity(self):
        report = diagnose_access(self.home, self.roots, self.run_id)
        self.assertEqual(len(report["issues"]), 1)
        issue = report["issues"][0]
        self.assertEqual(issue["code"], "DIRECTORY_UNREADABLE")
        self.assertEqual(issue["path"], str(self.pkg))
        self.assertEqual(issue["relative"], "cache/Shelly/lib32-gstreamer/pkg")
        self.assertEqual(issue["mode"], "111")
        self.assertEqual(issue["suggested_mode"], "511")
        self.assertTrue(issue["repairable"])
        self.assertEqual(report["identity"]["uid"], os.getuid())
        self.assertTrue(report["unsealed"])
        self.assertEqual(stat.S_IMODE(self.pkg.lstat().st_mode), 0o111)

    def test_explicit_owner_repair_only_adds_read_bit(self):
        issue = diagnose_access(self.home, self.roots, self.run_id)["issues"][0]
        result = repair_owner_directory(self.home, self.roots, self.run_id,
                                        issue["relative"])
        self.assertEqual((result["old_mode"], result["new_mode"]), ("111","511"))
        self.assertFalse(result["purge_authorized"])
        self.assertEqual(stat.S_IMODE(self.pkg.lstat().st_mode), 0o511)
        self.assertEqual(diagnose_access(self.home, self.roots, self.run_id)["issues"], [])
        self.assertEqual(self.row["move_status"], "moving")
        self.assertNotIn("tree_inventory", json.loads(self.manifest.read_text())["items"][0])

    def test_full_recovery_keeps_adopt_and_purge_as_separate_operations(self):
        self.assertTrue(diagnose_access(self.home, self.roots, self.run_id)["unsealed"])
        relative="cache/Shelly/lib32-gstreamer/pkg"
        repair_owner_directory(self.home, self.roots, self.run_id, relative)
        # ACCESS alone does not invent SHA256 inventory or delete anything.
        self.assertTrue(self.pkg.exists())
        self.assertNotIn("tree_inventory", json.loads(self.manifest.read_text())["items"][0])
        # ADOPT is a separate action gated by its own user confirmation in CLI/GUI.
        result = audit.adopt_quarantine_inventory(self.home, self.roots, self.run_id)
        self.assertEqual(result["adopted"], 1)
        self.assertTrue(self.tree.exists())
        # PURGE remains a third distinct action with the original preflight.
        preview = audit.purge_quarantine_run(
            self.home, self.roots, self.run_id, dry_run=True, emit=lambda *_:None)
        self.assertTrue(preview["dry_run"])
        self.assertTrue(self.tree.exists())
        deleted = audit.purge_quarantine_run(
            self.home, self.roots, self.run_id, dry_run=False, emit=lambda *_:None)
        self.assertEqual(deleted["objects"], 1)
        self.assertFalse(self.tree.exists())
        self.assertTrue(self.manifest.exists())

    def test_regular_unreadable_file_and_nonwritable_parent_block_purge_preflight(self):
        # Simulates a real cache directory containing a mode-000 file.
        self.pkg.chmod(0o700)
        protected = self.pkg / "userdata.txt"
        protected.write_bytes(b"sample protected user data")
        protected.chmod(0o000)
        self.addCleanup(lambda: protected.chmod(0o600) if protected.is_file() else None)
        self.pkg.chmod(0o111)

        def next_issue():
            return diagnose_access(self.home, self.roots, self.run_id)["issues"][0]

        first = next_issue()
        self.assertEqual(first["code"], "DIRECTORY_UNREADABLE")
        repair_owner_directory(self.home, self.roots, self.run_id, first["relative"])
        self.assertEqual(stat.S_IMODE(self.pkg.stat().st_mode), 0o511)

        report = diagnose_access(self.home, self.roots, self.run_id)
        self.assertEqual([i["code"] for i in report["issues"]],
                         ["DIRECTORY_NOT_WRITABLE", "FILE_UNREADABLE"])
        # Single interactive step adds only the directory owner-write bit.
        repair_owner_directory(self.home, self.roots, self.run_id,
                               report["issues"][0]["relative"])
        self.assertEqual(stat.S_IMODE(self.pkg.stat().st_mode), 0o711)
        pending = next_issue()
        self.assertEqual(pending["code"], "FILE_UNREADABLE")
        self.assertEqual(pending["mode"], "000")
        self.assertEqual(pending["suggested_mode"], "400")
        repair_owner_directory(self.home, self.roots, self.run_id, pending["relative"])
        self.assertEqual(stat.S_IMODE(protected.stat().st_mode), 0o400)

        self.assertEqual(diagnose_access(self.home, self.roots, self.run_id)["issues"], [])
        approved = audit.adopt_quarantine_inventory(self.home, self.roots, self.run_id)
        self.assertEqual(approved["adopted"], 1)
        plan = audit.purge_quarantine_run(self.home, self.roots, self.run_id, dry_run=True)
        self.assertEqual(plan["objects"], 1)
        self.assertTrue(protected.exists())
        audit.purge_quarantine_run(self.home, self.roots, self.run_id,
                                   dry_run=False, emit=lambda *_: None)
        self.assertFalse(self.tree.exists())

    def test_readable_directory_without_owner_search_bit_is_repaired_first(self):
        self.pkg.chmod(0o700)
        (self.pkg / "child.txt").write_text("safe")
        self.pkg.chmod(0o400)
        issues = diagnose_access(self.home, self.roots, self.run_id)["issues"]
        self.assertEqual([issue["code"] for issue in issues],
                         ["DIRECTORY_NOT_TRAVERSABLE"])
        self.assertEqual(issues[0]["suggested_mode"], "500")
        report = repair_owner_directory(
            self.home, self.roots, self.run_id, issues[0]["relative"])
        self.assertEqual(report["new_mode"], "500")
        self.assertEqual((self.pkg / "child.txt").read_text(), "safe")
        # The separate owner-write permission still requires approval.
        next_issues = diagnose_access(self.home, self.roots, self.run_id)["issues"]
        self.assertEqual(next_issues[0]["code"], "DIRECTORY_NOT_WRITABLE")

    def test_directory_without_any_permissions_needs_explicit_read_and_search(self):
        self.pkg.chmod(0o000)
        issue = diagnose_access(self.home, self.roots, self.run_id)["issues"][0]
        self.assertEqual(issue["code"], "DIRECTORY_NOT_TRAVERSABLE")
        self.assertEqual(issue["mode"], "000")
        self.assertEqual(issue["suggested_mode"], "500")
        outcome = repair_owner_directory(self.home, self.roots,
                                         self.run_id, issue["relative"])
        self.assertEqual(outcome["new_mode"], "500")

    def test_preflight_denies_readable_but_nonwritable_directory_with_children(self):
        self.pkg.chmod(0o700)
        child = self.pkg / "example"
        child.write_text("must not be partially deleted")
        # Root inventory is readable and hashable, but unlink cannot succeed.
        self.pkg.chmod(0o511)
        self.row["tree_inventory"] = capture_inventory(self.tree)
        self.row["move_status"] = "moved"
        self.write_manifest()

        with self.assertRaises(PermissionError):
            audit.purge_quarantine_run(self.home, self.roots, self.run_id,
                                       dry_run=True, emit=lambda *_: None)
        self.assertTrue(child.exists())
        issues = diagnose_access(self.home, self.roots, self.run_id)["issues"]
        self.assertEqual([i["code"] for i in issues], ["DIRECTORY_NOT_WRITABLE"])

    def test_no_owner_repair_for_hardlinked_unreadable_file(self):
        self.pkg.chmod(0o700)
        file = self.pkg / "private-file"
        file.write_text("text")
        twin = self.pkg / "twin"
        os.link(file, twin)
        file.chmod(0o000)
        self.addCleanup(lambda: file.chmod(0o600) if file.exists() else None)
        report = diagnose_access(self.home, self.roots, self.run_id)
        self.assertIn("HARDLINK_UNSAFE", [i["code"] for i in report["issues"]])
        for issue in report["issues"]:
            self.assertFalse(issue["repairable"])

    def test_repair_refuses_arbitrary_path(self):
        outside = self.home / "outside"
        outside.mkdir()
        outside.chmod(0o111)
        self.addCleanup(lambda: outside.chmod(0o700))
        for relative in ("../outside", "/tmp", "cache/other", "cache/Shelly"):
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):
                    repair_owner_directory(self.home, self.roots, self.run_id, relative)
        self.assertEqual(stat.S_IMODE(outside.lstat().st_mode), 0o111)

    def test_swapped_symlink_does_not_get_repaired(self):
        target = self.home / "important"
        target.mkdir()
        target.chmod(0o700)
        self.pkg.chmod(0o700)
        self.pkg.rmdir()
        self.pkg.symlink_to(target, target_is_directory=True)
        report = diagnose_access(self.home, self.roots, self.run_id)
        self.assertNotIn("cache/Shelly/lib32-gstreamer/pkg",
                         [x["relative"] for x in report["issues"] if x["repairable"]])
        with self.assertRaises(ValueError):
            repair_owner_directory(self.home, self.roots, self.run_id,
                                   "cache/Shelly/lib32-gstreamer/pkg")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)

    def test_corrupt_manifest_prevents_repair(self):
        self.payload["items"][0]["destination"] = "/etc/shadow"
        self.write_manifest()
        with self.assertRaises(ValueError):
            diagnose_access(self.home, self.roots, self.run_id)
        with self.assertRaises(ValueError):
            repair_owner_directory(self.home, self.roots, self.run_id,
                                   "cache/Shelly/lib32-gstreamer/pkg")

    def test_access_diagnosis_does_not_implicitly_seal_or_purge(self):
        diagnose_access(self.home, self.roots, self.run_id)
        self.assertTrue(self.manifest.exists())
        self.assertTrue(self.pkg.exists())
        self.assertEqual(self.row["move_status"], "moving")

    def test_only_known_preflight_failures_start_guided_access_recovery(self):
        self.assertTrue(needs_access_recovery(PermissionError(13, "No read", "pkg")))
        self.assertTrue(needs_access_recovery(
            ValueError("Missing recursive inventory; legacy run requires adoption")))
        self.assertTrue(needs_access_recovery(
            ValueError("Foreign owner or filesystem inside quarantine")))
        for error in (ValueError("Quarantine inode substitution"),
                      ValueError("Invalid inventory row"),
                      ValueError("Unexpected new file in quarantine"),
                      ValueError("Untracked content in quarantine run"),
                      RuntimeError("Other error")):
            with self.subTest(error=str(error)):
                self.assertFalse(needs_access_recovery(error))

    def test_authorization_context_never_guesses_root_password(self):
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland",
                                     "XDG_SESSION_ID": "10"}):
            info = authority_context()
        self.assertEqual(info["uid"], os.getuid())
        self.assertEqual(info["session_type"], "wayland")
        self.assertEqual(info["authorization"], "not_requested")
        self.assertIsInstance(info["pkexec_installed"], bool)


if __name__ == "__main__":
    unittest.main()
