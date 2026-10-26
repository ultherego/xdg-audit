"""Unprivileged regression tests for the strictly scoped Polkit self-test."""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import xdg_polkit

HELPER_PATH = Path(__file__).resolve().parents[1] / "packaging/polkit/xdg-audit-polkit-helper"


class PolkitHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="xdg-polkit-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "polkit-selftest"
        self.base.mkdir()
        self.helper = runpy.run_path(str(HELPER_PATH))
        self.uid = os.getuid() or 1001
        # In tests, replace only the trusted-root opener with a fixture opener.
        # Production's /var/lib root-owned chain and required UID 0 stay intact.
        self.open_patch = patch.dict(
            self.helper["test_create"].__globals__,
            {"_open_base": lambda base, owner, create: os.open(self.base, self.helper["FLAGS"])})
        self.open_patch.start()
        self.addCleanup(self.open_patch.stop)

    def fixture(self):
        return self.base / str(self.uid) / self.helper["TEST_NAME"]

    def create(self):
        return self.helper["test_create"](self.base, self.uid, owner=os.getuid())

    def delete(self):
        return self.helper["test_delete"](self.base, self.uid, owner=os.getuid())

    def test_only_known_fixture_created_and_deleted(self):
        sibling = self.base / "unrelated"
        sibling.write_text("preserve")
        created = self.create()
        self.assertEqual(created["status"], "created")
        self.assertEqual(self.create()["status"], "already_exists")
        self.assertTrue(self.fixture().is_dir())
        self.assertTrue((self.fixture() / "test-only.txt").exists())
        self.assertEqual(self.delete()["status"], "deleted")
        self.assertFalse(self.fixture().exists())
        self.assertEqual(sibling.read_text(), "preserve")

    def test_unexpected_data_blocks_privileged_deletion(self):
        self.create()
        extra = self.fixture() / "important"
        extra.write_text("never delete")
        with self.assertRaises(self.helper["Rejected"]):
            self.delete()
        self.assertEqual(extra.read_text(), "never delete")

    def test_modified_marker_blocks_deletion(self):
        self.create()
        marker = self.fixture() / "test-only.txt"
        marker.write_text("a" * len(self.helper["MARKER_DATA"]))
        with self.assertRaises(self.helper["Rejected"]):
            self.delete()
        self.assertTrue(marker.exists())

    def test_symlink_marker_blocks_deletion(self):
        self.create()
        outside = self.base / "outside"
        outside.write_text("protected")
        marker = self.fixture() / "test-only.txt"
        marker.unlink()
        marker.symlink_to(outside)
        with self.assertRaises(self.helper["Rejected"]):
            self.delete()
        self.assertEqual(outside.read_text(), "protected")

    def test_symlink_demo_blocks_deletion(self):
        self.create()
        demo = self.fixture()
        original = demo.with_name("saved-demo")
        demo.rename(original)
        demo.symlink_to(original, target_is_directory=True)
        with self.assertRaises(OSError):
            self.delete()
        self.assertTrue(original.exists())

    def test_direct_invocation_does_not_accept_foreign_paths_or_rootless(self):
        with self.assertRaises(self.helper["Rejected"]):
            self.helper["main"](["test-delete", "/etc"])
        with self.assertRaises(self.helper["Rejected"]):
            self.helper["main"](["--exec", "/bin/sh"])
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(self.helper["Rejected"]):
                self.helper["_authenticated_uid"]()


class PolkitClientTests(unittest.TestCase):
    def test_untrusted_pkexec_is_not_executed(self):
        with patch("xdg_polkit.status", return_value={"ready": False}), \
             patch("xdg_polkit.subprocess.run") as command:
            with self.assertRaises(xdg_polkit.PolkitUnavailable):
                xdg_polkit.run_test("test-auth")
            command.assert_not_called()

    def test_native_pkexec_invokes_only_read_only_id(self):
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=0, stdout="0\\n", stderr="")) as command:
            result = xdg_polkit.run_test("test-auth", graphical=True)
            self.assertEqual(result["effective_uid"], 0)
            self.assertFalse(result["file_operations"])
            self.assertEqual(command.call_args.args[0], [
                "/usr/bin/pkexec", "--disable-internal-agent",
                "/usr/bin/id", "-u"
            ])

    def test_cancelled_auth_is_never_success(self):
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=126, stdout="", stderr="")):
            with self.assertRaisesRegex(xdg_polkit.PolkitUnavailable, "cancelled"):
                xdg_polkit.run_test("test-auth")

    def test_wrong_uid_and_old_privileged_actions_rejected(self):
        with self.assertRaises(ValueError):
            xdg_polkit.run_test("test-delete", graphical=True)
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=0, stdout="1000\\n", stderr="")):
            with self.assertRaises(xdg_polkit.PolkitUnavailable):
                xdg_polkit.run_test("test-auth")


if __name__ == "__main__":
    unittest.main()
