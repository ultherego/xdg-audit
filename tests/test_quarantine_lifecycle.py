"""Regression tests for fail-closed quarantine lifecycle."""
import datetime as dt
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_quarantine_lifecycle as lifecycle

import xdg_audit as audit
from xdg_quarantine_lifecycle import inspect_run, purge_run, expired_run_ids, capture_inventory, adopt_legacy_run, recover_manifest_temps


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.roots = audit.xdg_roots(self.home)
        self.source = self.home / ".config" / "purge-demo"
        self.source.parent.mkdir(parents=True)
        self.source.mkdir()
        (self.source / "settings").write_text("preserve-me")
        self.root = audit.quarantine_dir(self.home, self.roots)
        self.run_id = "20261025-103000-123456"
        self.run = self.root / self.run_id
        (self.run / "config").mkdir(parents=True)
        info = self.source.lstat()
        self.dest = self.run / "config" / "purge-demo"
        os.rename(self.source, self.dest)
        self.row = {"source": str(self.source), "destination": str(self.dest),
                    "scope": "config", "state": "CANDIDATE",
                    "identity": [info.st_dev, info.st_ino, stat.S_IFDIR],
                    "move_status": "moved"}
        self.row["tree_inventory"] = capture_inventory(self.dest)
        self.payload = {"format": "intent-journal-v3",
                        "created": self.run_id, "items": [self.row]}
        self.write()

    def write(self):
        (self.run / "manifest.json").write_text(json.dumps(self.payload))

    def check_mounts(self, path):
        return False

    def purge(self, dry_run=True):
        return purge_run(self.home, self.roots, self.run_id,
                         self.check_mounts, dry_run=dry_run, emit=lambda *_: None)

    def test_dry_run_does_not_change_data(self):
        manifest = (self.run / "manifest.json").read_bytes()
        report = self.purge()
        self.assertEqual(report["objects"], 1)
        self.assertTrue(self.dest.exists())
        self.assertEqual((self.run / "manifest.json").read_bytes(), manifest)

    def test_purge_and_idempotent_tombstone(self):
        self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.payload["format"], "intent-journal-v3")
        self.assertEqual(json.loads((self.run / "manifest.json").read_text())["items"][0]["move_status"], "purged")
        self.assertEqual(self.purge()["objects"], 0)
        self.purge(dry_run=False)

    def test_corrupted_identity_rejected(self):
        self.row["identity"][1] += 1
        self.write()
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue(self.dest.exists())

    def test_identity_refusal_reports_exact_evidence_without_changing_bytes(self):
        self.row['identity'][1] += 100
        self.write()
        manifest = (self.run / 'manifest.json').read_bytes()
        with self.assertRaises(lifecycle.QuarantineIdentityMismatch) as caught:
            self.purge(dry_run=False)
        error = caught.exception
        self.assertEqual(error.run_id, self.run_id)
        self.assertEqual(error.path, self.dest)
        self.assertEqual(error.expected, tuple(self.row['identity']))
        self.assertEqual(error.actual[:2], (self.dest.stat().st_dev, self.dest.stat().st_ino))
        self.assertEqual((self.dest / 'settings').read_text(), 'preserve-me')
        self.assertEqual((self.run / 'manifest.json').read_bytes(), manifest)
        self.assertFalse(audit.quarantine_access_recoverable_error(error))

    def test_untracked_entry_rejected(self):
        (self.run / "config" / "unexpected").write_text("keep")
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue(self.dest.exists())

    def test_symlink_swap_rejected(self):
        original = self.dest.with_name("preserved")
        self.dest.rename(original)
        self.dest.symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue((original / "settings").exists())

    def test_hardlink_rejected(self):
        path = self.dest / "settings"
        os.link(path, self.home / "external-link")
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue(path.exists())

    def test_invalid_legacy_format_rejected(self):
        self.payload["format"] = "intent-journal-v2"
        self.write()
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)

    def test_resume_after_deletion_before_journal_finish(self):
        self.row["move_status"] = "purging"
        self.write()
        import shutil
        shutil.rmtree(self.dest)
        self.assertEqual(self.purge()["objects"], 0)
        self.purge(dry_run=False)
        self.assertEqual(json.loads((self.run / "manifest.json").read_text())["items"][0]["move_status"], "purged")

    def test_failed_intent_write_before_deletion_keeps_bytes_and_can_resume(self):
        # Simulate interruption after the purging intent is persisted but
        # before any filesystem object has been unlinked.
        with patch.object(lifecycle, "_delete_entry",
                          side_effect=OSError("simulated interruption")):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                self.purge(dry_run=False)
        self.assertTrue(self.dest.exists())
        self.assertEqual((self.dest / "settings").read_text(), "preserve-me")
        on_disk = json.loads((self.run / "manifest.json").read_text())
        self.assertEqual(on_disk["items"][0]["move_status"], "purging")
        self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())
        self.assertEqual(json.loads((self.run / "manifest.json").read_text())
                         ["items"][0]["move_status"], "purged")

    def test_crash_after_unlink_before_purged_journal_write_is_resumable(self):
        original_write = lifecycle._write_manifest

        def interrupt_only_completion(fd, payload):
            if payload["items"][0]["move_status"] == "purged":
                raise OSError("simulated crash before final journal update")
            return original_write(fd, payload)

        with patch.object(lifecycle, "_write_manifest",
                          side_effect=interrupt_only_completion):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())
        self.assertEqual(json.loads((self.run / "manifest.json").read_text())
                         ["items"][0]["move_status"], "purging")
        self.purge(dry_run=False)
        self.assertEqual(json.loads((self.run / "manifest.json").read_text())
                         ["items"][0]["move_status"], "purged")

    def test_nested_symlink_not_followed(self):
        target = self.home / "outside"
        target.write_text("do not erase")
        (self.dest / "external").symlink_to(target)
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertEqual(target.read_text(), "do not erase")
        self.assertTrue(self.dest.exists())

    def test_new_nested_file_blocks_purge(self):
        (self.dest / "unexpected").write_text("keep me")
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue((self.dest / "unexpected").exists())

    def test_mutated_nested_file_blocks_purge(self):
        (self.dest / "settings").write_text("changed")
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue((self.dest / "settings").exists())

    def test_inventory_missing_blocks_purge(self):
        del self.row["tree_inventory"]
        self.write()
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        self.assertTrue(self.dest.exists())

    def test_adopt_explicit_legacy_inventory(self):
        self.row.pop("tree_inventory")
        self.write()
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        adopted = adopt_legacy_run(self.home, self.roots, self.run_id, self.check_mounts)
        self.assertEqual(adopted["adopted"], 1)
        self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())

    def test_resume_after_partial_nested_delete(self):
        self.row["move_status"] = "purging"
        self.write()
        (self.dest / "settings").unlink()
        self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())

    def test_external_symlink_present_at_capture_is_unlinked_not_followed(self):
        target = self.home / "outside"
        target.write_text("untouched")
        (self.dest / "link").symlink_to(target)
        self.row["tree_inventory"] = capture_inventory(self.dest)
        self.write()
        self.purge(dry_run=False)
        self.assertEqual(target.read_text(), "untouched")

    def test_multi_entry_manifest_uses_correct_inventory_for_every_entry(self):
        source2 = self.home / ".local" / "share" / "unrelated-app"
        source2.parent.mkdir(parents=True, exist_ok=True)
        source2.write_text("different bytes")
        info = source2.lstat()
        destination2 = self.run / "data" / "unrelated-app"
        destination2.parent.mkdir(parents=True)
        source2.rename(destination2)
        row2 = {"source": str(source2), "destination": str(destination2),
                "scope": "data", "state": "CANDIDATE",
                "identity": [info.st_dev, info.st_ino, stat.S_IFREG],
                "tree_inventory": capture_inventory(destination2),
                "move_status": "moved"}
        self.payload["items"].append(row2)
        self.write()
        self.assertEqual(self.purge()["objects"], 2)
        self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())
        self.assertFalse(destination2.exists())

    def test_recovery_cleans_only_abandoned_manifest_temps(self):
        temp = self.run / ".manifest-aabbccddeeff00112233445566778899.tmp"
        temp.write_text("incomplete")
        temp.chmod(0o600)
        with self.assertRaises(ValueError):
            self.purge(dry_run=False)
        report = recover_manifest_temps(self.home, self.roots, self.run_id, dry_run=True)
        self.assertEqual(report["temporary_files"], 1)
        self.assertTrue(temp.exists())
        recover_manifest_temps(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(temp.exists())
        self.purge(dry_run=False)
        self.assertFalse(self.dest.exists())

    def test_recovery_rejects_unknown_untracked_file(self):
        temp = self.run / ".manifest-aabbccddeeff00112233445566778899.tmp"
        temp.write_text("temp")
        temp.chmod(0o600)
        unknown = self.run / "unrelated"
        unknown.write_text("preserve")
        with self.assertRaises(ValueError):
            recover_manifest_temps(self.home, self.roots, self.run_id, dry_run=False)
        self.assertTrue(temp.exists())
        self.assertTrue(unknown.exists())

    def test_retention_boundary(self):
        now = dt.datetime(2026, 10, 26, 12, 0)
        old = "20260925-103000-123456"
        recent = "20261025-103000-123456"
        self.assertEqual(expired_run_ids([{"run_id": old}, {"run_id": recent}], 30, now), [old])
        with self.assertRaises(ValueError):
            expired_run_ids([], 0, now)


if __name__ == "__main__":
    unittest.main()
