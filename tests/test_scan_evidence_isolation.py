"""Flatpak namespace and dotfile version matching regressions."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import xdg_audit as audit
from xdg_sources import ActiveInventory


class ScanEvidenceIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.flatpak = self.home / ".var" / "app" / "org.mozilla.firefox"
        self.flatpak.mkdir(parents=True)

    def inventory(self, flatpak_ids=(), status="ok"):
        return ActiveInventory(
            ({"firefox"}, set(flatpak_ids), set(), set(),
             set(), {"firefox"}, {"firefox"}, {"firefox"}),
            status={"pacman": "ok", "flatpak": status, "snap": "absent",
                    "appimage": "ok", "manual_binary": "ok"})

    def test_native_firefox_cannot_mark_uninstalled_flatpak_active(self):
        with (patch.object(audit, "read_active_names",
                           return_value=self.inventory({"org.example.OtherApp"})),
              patch.object(audit, "parse_removals", return_value={}),
              patch.object(audit, "references", return_value={})):
            items, *_ = audit.scan(self.home, ["flatpak"], set(), {}, True)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].state, "REVIEW")
        self.assertFalse(items[0].removable)
        self.assertEqual(items[0].reasons, [
            "Flatpak app-id is not currently installed; check manually"])

    def test_exact_installed_flatpak_appid_is_active(self):
        with (patch.object(audit, "read_active_names",
                           return_value=self.inventory({"org.mozilla.firefox"})),
              patch.object(audit, "parse_removals", return_value={})):
            items, *_ = audit.scan(self.home, ["flatpak"], set(), {}, True)
        self.assertEqual(items[0].state, "ACTIVE")
        self.assertEqual(items[0].json()["evidence"][0]["source"], "flatpak")

    def test_failed_flatpak_probe_does_not_trust_stale_result(self):
        with (patch.object(audit, "read_active_names",
                           return_value=self.inventory({"org.mozilla.firefox"}, "failed")),
              patch.object(audit, "parse_removals", return_value={})):
            items, *_ = audit.scan(self.home, ["flatpak"], set(), {}, True)
        self.assertEqual(items[0].state, "REVIEW")
        self.assertIn("inventory unavailable", items[0].reasons[0])
        self.assertFalse(items[0].removable)

    def test_numeric_version_tail_is_not_a_desktop_app_name(self):
        path = self.home / ".zcompdump-cachyos-5.9.1"
        path.write_text("synthetic user data")
        inventory = ActiveInventory(
            ({"python"}, set(), set(), set(), set(), set(), {"1"}, set()),
            status={"pacman": "ok", "flatpak": "ok"})
        with (patch.object(audit, "read_active_names", return_value=inventory),
              patch.object(audit, "parse_removals", return_value={}),
              patch.object(audit, "references", return_value={})):
            items, *_ = audit.scan(self.home, ["dotfiles"], set(), {}, True)
        self.assertEqual(items[0].state, "UNKNOWN")
        self.assertFalse(items[0].removable)
        self.assertNotIn("desktop entry", " ".join(items[0].reasons))


if __name__ == "__main__":
    unittest.main()
