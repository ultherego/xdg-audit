"""Persistence and scheduled retention are strictly opt-in."""
import json
import tempfile
import unittest
from pathlib import Path

import xdg_audit as audit
from xdg_retention import DEFAULT, load, save
from scripts.install_retention_timer import render_service, render_timer


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / ".config"
        self.config.mkdir()
        self.roots = audit.xdg_roots(self.home)

    def test_default_policy_disables_automatic_deletion(self):
        self.assertEqual(load(self.home, self.roots), DEFAULT)
        self.assertFalse(load(self.home, self.roots)["automatic"])

    def test_roundtrip_and_bad_config_fail_closed(self):
        save(self.home, self.roots, {"days": 7, "automatic": True})
        self.assertEqual(load(self.home, self.roots), {"days": 7, "automatic": True})
        path = self.config / "xdg-audit" / "retention.json"
        path.write_text('{"days": -1, "automatic": true}')
        with self.assertRaises(ValueError):
            load(self.home, self.roots)

    def test_symlink_config_is_rejected(self):
        path = self.config / "xdg-audit" / "retention.json"
        path.parent.mkdir()
        path.symlink_to(self.home / "other")
        with self.assertRaises(ValueError):
            load(self.home, self.roots)
        with self.assertRaises(ValueError):
            save(self.home, self.roots, {"days": 30, "automatic": False})

    def test_systemd_timer_is_daily_and_installed_separately(self):
        service = render_service()
        self.assertIn("--automatic-purge", service)
        self.assertIn("Type=oneshot", service)
        timer = render_timer()
        self.assertIn("OnCalendar=daily", timer)
        self.assertIn("WantedBy=timers.target", timer)


if __name__ == "__main__":
    unittest.main()
