"""Completed quarantine history retention and safety regression tests."""
import datetime as dt
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

import xdg_audit as audit
from xdg_quarantine_history import (
    HISTORY_DAYS, cleanup_history, history_candidates, history_expired, history_info,
)
from xdg_quarantine_lifecycle import capture_inventory


class CompletedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.roots = audit.xdg_roots(self.home)
        for path in self.roots.values():
            path.mkdir(parents=True, exist_ok=True)
        self.run_id = "20260815-101010-123456"
        self.run = audit.quarantine_dir(self.home, self.roots) / self.run_id
        (self.run / "config").mkdir(parents=True)
        src = self.roots["config"] / "obsolete-app"
        src.write_text("fake user configuration")
        original = src.lstat()
        self.entry = {
            "source": str(src),
            "destination": str(self.run / "config" / src.name),
            "scope": "config",
            "identity": [original.st_dev, original.st_ino, stat.S_IFREG],
            "move_status": "purged",
        }
        src.unlink()
        self.payload = {
            "format": "intent-journal-v3",
            "created": self.run_id,
            "purged_at": "2026-08-15T10:30:00+00:00",
            "items": [self.entry],
        }
        self.write()

    def write(self):
        (self.run / "manifest.json").write_text(json.dumps(self.payload), encoding="utf-8")

    def test_manual_cleanup_removes_only_empty_run_and_manifest(self):
        outside = self.home / "unrelated.txt"
        outside.write_text("protected")
        plan = cleanup_history(self.home, self.roots, self.run_id)
        self.assertEqual(plan["status"], "PURGED")
        self.assertTrue(self.run.exists())
        self.assertTrue((self.run / "manifest.json").exists())
        cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(self.run.exists())
        self.assertEqual(outside.read_text(), "protected")

    def test_exact_30_day_retention_boundary(self):
        self.assertEqual(HISTORY_DAYS, 30)
        info = history_info(self.home, self.roots, self.run_id)
        moment = dt.datetime.fromisoformat(self.payload["purged_at"])
        self.assertFalse(history_expired(info, now=moment + dt.timedelta(days=30, seconds=-1)))
        self.assertTrue(history_expired(info, now=moment + dt.timedelta(days=30)))
        self.assertEqual(history_candidates(self.home, self.roots, [self.run_id],
                          now=moment + dt.timedelta(days=30)), [self.run_id])

    def test_no_timestamp_never_automatically_expires(self):
        del self.payload["purged_at"]
        self.write()
        info = history_info(self.home, self.roots, self.run_id)
        self.assertFalse(history_expired(info, now=dt.datetime(2031, 1, 1, tzinfo=dt.timezone.utc)))
        cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(self.run.exists())

    def test_incomplete_and_purging_runs_never_cleanup(self):
        for status in ("planned", "moving", "moved", "restoring", "purging"):
            with self.subTest(status=status):
                self.entry["move_status"] = status
                self.write()
                with self.assertRaises(ValueError):
                    cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
                self.assertTrue(self.run.exists())
                self.assertTrue((self.run / "manifest.json").exists())

    def test_restored_run_can_be_manually_cleaned_not_auto_expired(self):
        self.entry["move_status"] = "restored"
        del self.payload["purged_at"]
        self.write()
        info = history_info(self.home, self.roots, self.run_id)
        self.assertEqual(info["status"], "RESTORED")
        self.assertFalse(history_expired(info, now=dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)))
        cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(self.run.exists())

    def test_missing_or_invalid_journal_blocks_delete(self):
        (self.run / "manifest.json").write_text("not json")
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertTrue(self.run.exists())

    def test_untracked_file_blocks_delete(self):
        unexpected = self.run / "config" / "do-not-delete"
        unexpected.write_text("unrelated data")
        with self.assertRaises(ValueError):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertTrue(unexpected.exists())
        self.assertTrue((self.run / "manifest.json").exists())

    def test_untracked_file_at_run_root_blocks_delete(self):
        unexpected = self.run / "foreign"
        unexpected.write_text("keep me")
        with self.assertRaises(ValueError):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertEqual(unexpected.read_text(), "keep me")

    def test_symlinked_scope_never_removed(self):
        scope = self.run / "config"
        scope.rmdir()
        scope.symlink_to(self.home)
        with self.assertRaises((ValueError, OSError)):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertTrue(scope.is_symlink())
        self.assertTrue(self.home.exists())

    def test_swapped_manifest_symlink_blocks_cleanup(self):
        manifest = self.run / "manifest.json"
        manifest.unlink()
        external = self.home / "other-journal"
        external.write_text(json.dumps(self.payload))
        manifest.symlink_to(external)
        with self.assertRaises((ValueError, OSError)):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertTrue(external.exists())

    def test_interrupted_metadata_cleanup_resumable(self):
        (self.run / "config").rmdir()
        plan = cleanup_history(self.home, self.roots, self.run_id)
        self.assertEqual(plan["status"], "PURGED")
        cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(self.run.exists())

    def test_manifest_paths_must_stay_inside_run(self):
        self.entry["destination"] = str(self.home / "unrelated.txt")
        self.write()
        with self.assertRaises(ValueError):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)

    def test_untrusted_future_timestamp_does_not_expire(self):
        self.payload["purged_at"] = "2030-01-01T00:00:00+00:00"
        self.write()
        now = dt.datetime(2026, 10, 26, tzinfo=dt.timezone.utc)
        self.assertFalse(history_expired(history_info(self.home, self.roots, self.run_id),
                                         now=now))

    def test_old_journal_format_is_restore_only(self):
        self.payload["format"] = "intent-journal-v2"
        self.write()
        with self.assertRaises(ValueError):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)

    def test_run_list_exposes_purged_status(self):
        runs = audit.quarantine_runs(self.home, self.roots)
        self.assertEqual(runs[0]["status"], "PURGED")
        self.assertEqual(runs[0]["moved"], 0)

    def test_purge_creates_timestamp(self):
        # Place new quarantined bytes and record a complete hash inventory.
        dst = Path(self.entry["destination"])
        dst.write_text("new quarantined bytes")
        info = dst.lstat()
        self.entry["identity"] = [info.st_dev, info.st_ino, stat.S_IFREG]
        self.entry["tree_inventory"] = capture_inventory(dst)
        self.entry["move_status"] = "moved"
        self.payload.pop("purged_at")
        self.write()
        result = audit.purge_quarantine_run(self.home, self.roots, self.run_id,
                                             dry_run=False, emit=lambda _: None)
        self.assertEqual(result["objects"], 1)
        saved = json.loads((self.run / "manifest.json").read_text())
        self.assertEqual(saved["items"][0]["move_status"], "purged")
        self.assertIsNotNone(dt.datetime.fromisoformat(saved["purged_at"]).tzinfo)


if __name__ == "__main__":
    unittest.main()
