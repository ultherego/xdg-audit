"""No-root ~/.config fixture: restrictions, recovery, collision, tamper safety."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest

from xdg_config_selftest import (
    UnsafeFixture, cleanup, create, diagnose, path, repair, DATA
)
from xdg_quarantine_lifecycle import capture_inventory


class ConfigPermissionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="xdg-config-permissions-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / ".config").mkdir()
        self.fixture = path(self.home)
        self.pkg = self.fixture / "pkg"
        self.marker = self.pkg / "test-only.txt"
        self.addCleanup(self._clean_up_if_owned)

    def _clean_up_if_owned(self):
        if self.pkg.is_dir() and not self.pkg.is_symlink():
            os.chmod(self.pkg, 0o700)
        if self.marker.is_file() and not self.marker.is_symlink():
            os.chmod(self.marker, 0o600)

    def test_reproduces_read_denied_without_root_and_repairs(self):
        self.assertEqual(create(self.home)["status"], "created")
        self.assertEqual(create(self.home)["status"], "already_exists")
        result = diagnose(self.home)
        self.assertEqual(result["directory_mode"], "111")
        self.assertEqual(result["file_mode"], "000")
        self.assertFalse(result["polkit_required"])
        if os.geteuid() != 0:
            with self.assertRaises(PermissionError):
                capture_inventory(self.pkg)
        result = repair(self.home)
        self.assertEqual(result["status"], "repaired")
        self.assertEqual(result["inventory_objects"], 2)
        self.assertEqual(self.marker.read_bytes(), DATA)
        self.assertEqual(diagnose(self.home)["directory_mode"], "511")
        self.assertEqual(cleanup(self.home)["status"], "cleaned")
        self.assertFalse(self.fixture.exists())

    def test_cleanup_before_repair_restores_minimum_read_and_removes_only_fixture(self):
        create(self.home)
        unrelated = self.home / ".config" / "other-app"
        unrelated.mkdir()
        (unrelated / "myconfig").write_text("keep")
        self.assertTrue(cleanup(self.home)["deleted_test_only"])
        self.assertEqual((unrelated / "myconfig").read_text(), "keep")

    def test_preexisting_folder_is_not_overwritten(self):
        self.fixture.mkdir()
        marker = self.fixture / "personal"
        marker.write_text("important")
        with self.assertRaises(UnsafeFixture):
            create(self.home)
        self.assertEqual(marker.read_text(), "important")

    def test_extra_file_blocks_repair_and_cleanup(self):
        create(self.home)
        os.chmod(self.pkg, 0o711)
        extra = self.pkg / "extra"
        extra.write_text("do not erase")
        with self.assertRaises(UnsafeFixture):
            repair(self.home)
        with self.assertRaises(UnsafeFixture):
            cleanup(self.home)
        self.assertEqual(extra.read_text(), "do not erase")

    def test_marker_substituted_with_symlink_never_deleted(self):
        create(self.home)
        os.chmod(self.pkg, 0o711)
        self.marker.unlink()
        important = self.home / "important"
        important.write_text("untouched")
        self.marker.symlink_to(important)
        with self.assertRaises(UnsafeFixture):
            cleanup(self.home)
        self.assertEqual(important.read_text(), "untouched")

    def test_root_test_folder_symlink_is_rejected(self):
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "file").write_text("keep")
        self.fixture.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            create(self.home)
        self.assertEqual((outside / "file").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
