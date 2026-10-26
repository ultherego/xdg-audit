"""Integration tests for CLI history cleanup and the opt-in timer execution."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
from xdg_retention import save


class HistoryCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        env = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
        }
        env_patch = patch.dict(os.environ, env)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.roots = audit.xdg_roots(self.home)
        for path in self.roots.values():
            path.mkdir(parents=True, exist_ok=True)
        self.run_id = "20260815-120000-123456"
        self.run = audit.quarantine_dir(self.home, self.roots) / self.run_id
        (self.run / "config").mkdir(parents=True)
        path = self.roots["config"] / "old-app"
        path.write_bytes(b"old")
        info = path.lstat()
        path.unlink()
        self.payload = {
            "format": "intent-journal-v3",
            "created": self.run_id,
            "purged_at": "2026-08-15T12:00:00+00:00",
            "items": [{
                "source": str(path),
                "destination": str(self.run / "config" / "old-app"),
                "scope": "config",
                "identity": [info.st_dev, info.st_ino, stat.S_IFREG],
                "move_status": "purged",
            }],
        }
        (self.run / "manifest.json").write_text(json.dumps(self.payload))
        self.block_root = patch.object(audit, "check_no_root")
        self.block_root.start()
        self.addCleanup(self.block_root.stop)

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return audit.main(["--home", str(self.home), *args])

    def test_history_preview_is_read_only(self):
        original = (self.run / "manifest.json").read_bytes()
        self.assertEqual(self.run_cli("--cleanup-history", self.run_id, "--dry-run"), 0)
        self.assertEqual((self.run / "manifest.json").read_bytes(), original)

    def test_interactive_cleanup_requires_exact_token(self):
        class TTY:
            @staticmethod
            def isatty():
                return True
        with patch.object(audit.sys, "stdin", TTY()), patch("builtins.input", return_value="NO"):
            with self.assertRaises(SystemExit):
                self.run_cli("--cleanup-history", self.run_id)
        self.assertTrue(self.run.exists())
        with patch.object(audit.sys, "stdin", TTY()), patch("builtins.input", return_value="HISTORY"):
            self.assertEqual(self.run_cli("--cleanup-history", self.run_id), 0)
        self.assertFalse(self.run.exists())

    def test_all_history_preview_includes_fresh_purged_tombstone(self):
        self.payload["purged_at"] = "2030-01-01T00:00:00+00:00"
        (self.run / "manifest.json").write_text(json.dumps(self.payload))
        before = (self.run / "manifest.json").read_bytes()
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(audit.main(["--home", str(self.home),
                                         "--cleanup-all-history"]), 0)
        self.assertIn("HISTORY PLAN", buf.getvalue())
        self.assertEqual(before, (self.run / "manifest.json").read_bytes())
        self.assertTrue(self.run.exists())

    def test_all_history_requires_explicit_history_confirmation(self):
        self.payload["purged_at"] = "2030-01-01T00:00:00+00:00"
        (self.run / "manifest.json").write_text(json.dumps(self.payload))
        class TTY:
            @staticmethod
            def isatty():
                return True
        with patch.object(audit.sys, "stdin", TTY()), patch("builtins.input", return_value="PURGE"):
            with self.assertRaises(SystemExit):
                self.run_cli("--cleanup-all-history", "--execute")
        self.assertTrue(self.run.exists())
        with patch.object(audit.sys, "stdin", TTY()), patch("builtins.input", return_value="HISTORY"):
            self.assertEqual(self.run_cli("--cleanup-all-history", "--execute"), 0)
        self.assertFalse(self.run.exists())

    def test_all_history_does_not_touch_active_quarantine(self):
        self.payload["items"][0]["move_status"] = "moved"
        (self.run / "manifest.json").write_text(json.dumps(self.payload))
        self.assertEqual(self.run_cli("--cleanup-all-history", "--execute"), 0)
        self.assertTrue((self.run / "manifest.json").exists())

    def test_automatic_cleanup_is_default_off(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--automatic-purge")
        self.assertTrue((self.run / "manifest.json").exists())

    def test_opted_in_timer_deletes_expired_completed_history(self):
        save(self.home, self.roots, {"days": 30, "automatic": True})
        self.assertEqual(self.run_cli("--automatic-purge"), 0)
        self.assertFalse(self.run.exists())

    def test_restored_history_is_never_auto_deleted(self):
        self.payload["items"][0]["move_status"] = "restored"
        self.payload.pop("purged_at")
        (self.run / "manifest.json").write_text(json.dumps(self.payload))
        save(self.home, self.roots, {"days": 30, "automatic": True})
        self.assertEqual(self.run_cli("--automatic-purge"), 0)
        self.assertTrue(self.run.exists())

    def test_no_timestamp_is_never_auto_deleted(self):
        self.payload.pop("purged_at")
        (self.run / "manifest.json").write_text(json.dumps(self.payload))
        save(self.home, self.roots, {"days": 30, "automatic": True})
        self.assertEqual(self.run_cli("--automatic-purge"), 0)
        # Running the purge routine against an existing old tombstone can
        # safely backfill the timestamp to TODAY; it cannot expire today.
        self.assertTrue(self.run.exists())


if __name__ == "__main__":
    unittest.main()
