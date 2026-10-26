"""Read-only installed Debian and RPM inventory never authorizes MOVE."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_sources as sources


class DistroProviderTests(unittest.TestCase):
    def test_dpkg_only_installed_not_residual_or_unpacked(self):
        output = ("firefox\tinstall ok installed\n"
                  "chromium\tdeinstall ok config-files\n"
                  "curl:amd64\thold ok installed\n"
                  "unfinished\tinstall ok unpacked\n")
        with patch.object(sources, "_run", return_value=(
            sources.Probe("dpkg", "ok"), output)) as call:
            packages = sources.dpkg_packages()
        self.assertEqual(packages.status, "ok")
        self.assertIn("firefox", packages.names)
        self.assertIn("curl", packages.names)
        self.assertIn("curl:amd64", packages.names)
        self.assertNotIn("chromium", packages.names)
        self.assertNotIn("unfinished", packages.names)
        self.assertIn("dpkg-query", call.call_args.args[1])

    def test_dpkg_invalid_row_fails_closed(self):
        with patch.object(sources, "_run", return_value=(
            sources.Probe("dpkg", "ok"), "not-a-valid-row")):
            self.assertEqual(sources.dpkg_packages().status, "parse_error")

    def test_rpm_reads_installed_names_only(self):
        with patch.object(sources, "_run", return_value=(
            sources.Probe("rpm", "ok"), "firefox\ncurl\n")) as call:
            result = sources.rpm_packages()
        self.assertEqual(result.names, {"firefox", "curl"})
        self.assertEqual(call.call_args.args[1], [
            "rpm", "-qa", "--qf", "%{NAME}\\n"])

    def test_absent_rpm_is_not_false_negative(self):
        with patch.object(sources, "_run", return_value=(
            sources.Probe("rpm", "absent"), "")):
            self.assertEqual(sources.rpm_packages().status, "absent")


class DistroScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / ".config"
        self.config.mkdir()
        self.folder = self.config / "firefox"
        self.folder.mkdir()
        (self.folder / "config.ini").write_text("keep")

    def inv(self, provider: str):
        return sources.ActiveInventory((
            set(), set(), set(), set(), set(), set(), set(), set()),
            status={"pacman": "absent", provider: "ok"},
            distro={provider: {"firefox"}})

    def test_debian_installed_app_protected_even_with_no_pacman(self):
        with patch.object(audit, "read_active_names", return_value=self.inv("dpkg")), \
             patch.object(audit, "parse_removals", return_value={}):
            rows, *_ = audit.scan(self.home, ["config"], set(), {}, True)
        self.assertEqual(rows[0].state, "ACTIVE")
        self.assertEqual(rows[0].json()["evidence"][0]["source"], "dpkg")

    def test_rpm_installed_app_protected_even_with_no_pacman(self):
        with patch.object(audit, "read_active_names", return_value=self.inv("rpm")), \
             patch.object(audit, "parse_removals", return_value={}):
            rows, *_ = audit.scan(self.home, ["config"], set(), {}, True)
        self.assertEqual(rows[0].state, "ACTIVE")
        self.assertEqual(rows[0].json()["evidence"][0]["source"], "rpm")

    def test_dpkg_rpm_installed_does_not_authorize_non_arch_move(self):
        identity = self.folder.lstat()
        row = audit.Item("config", self.folder, state="CANDIDATE", removable=True,
                         identity=(identity.st_dev, identity.st_ino, stat.S_IFDIR))
        for provider in ("dpkg", "rpm"):
            with self.subTest(provider=provider), \
                 patch.object(audit, "read_active_names", return_value=self.inv(provider)):
                with self.assertRaisesRegex(ValueError, "pacman inventory"):
                    audit.commit_quarantine([row], audit.xdg_roots(self.home), self.home,
                                            emit=lambda *_: None)
        self.assertTrue(self.folder.exists())

    def test_current_rpm_install_blocks_stale_candidate_on_arch(self):
        inventory = sources.ActiveInventory((
            {"python"}, set(), set(), set(), set(), set(), set(), set()),
            status={"pacman": "ok", "rpm": "ok"},
            distro={"rpm": {"firefox"}})
        identity = self.folder.lstat()
        row = audit.Item("config", self.folder, state="CANDIDATE", removable=True,
                         identity=(identity.st_dev, identity.st_ino, stat.S_IFDIR))
        with patch.object(audit, "read_active_names", return_value=inventory):
            with self.assertRaisesRegex(ValueError, "present now"):
                audit.commit_quarantine([row], audit.xdg_roots(self.home), self.home,
                                        emit=lambda *_: None)
        self.assertTrue(self.folder.exists())


if __name__ == "__main__":
    unittest.main()
