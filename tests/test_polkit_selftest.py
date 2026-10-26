"""Tests of system Polkit smoke using only a trusted, read-only binary."""
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import xdg_polkit


class PolkitClientTests(unittest.TestCase):
    def test_untrusted_or_missing_pkexec_is_not_executed(self):
        with patch("xdg_polkit.status", return_value={"ready": False}), \
             patch("xdg_polkit.subprocess.run") as command:
            with self.assertRaises(xdg_polkit.PolkitUnavailable):
                xdg_polkit.run_test("test-auth")
            command.assert_not_called()

    def test_native_pkexec_invokes_only_read_only_id(self):
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=0, stdout="0\n", stderr="")) as command:
            result = xdg_polkit.run_test("test-auth", graphical=True)
            self.assertEqual(result["effective_uid"], 0)
            self.assertFalse(result["file_operations"])
            self.assertEqual(command.call_args.args[0],
                ["/usr/bin/pkexec", "--disable-internal-agent", "/usr/bin/id", "-u"])

    def test_cancelled_auth_never_succeeds(self):
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=126, stdout="", stderr="")):
            with self.assertRaisesRegex(xdg_polkit.PolkitUnavailable, "cancelled"):
                xdg_polkit.run_test("test-auth")

    def test_denied_auth_never_succeeds(self):
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=127, stdout="", stderr="")):
            with self.assertRaisesRegex(xdg_polkit.PolkitUnavailable, "denied"):
                xdg_polkit.run_test("test-auth")

    def test_unsupported_mutating_operation_rejected_before_pkexec(self):
        with patch("xdg_polkit.subprocess.run") as command:
            for action in ("test-create", "test-delete", "/bin/sh", "chmod"):
                with self.subTest(action=action), self.assertRaises(ValueError):
                    xdg_polkit.run_test(action)
            command.assert_not_called()

    def test_wrong_effective_uid_rejected(self):
        with patch("xdg_polkit.status", return_value={"ready": True}), \
             patch("xdg_polkit.shutil.which", return_value="/usr/bin/pkexec"), \
             patch("xdg_polkit.subprocess.run", return_value=SimpleNamespace(
                 returncode=0, stdout="1000\\n", stderr="")):
            with self.assertRaisesRegex(xdg_polkit.PolkitUnavailable, "Unexpected"):
                xdg_polkit.run_test("test-auth")

    def test_untrusted_executable_is_never_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=Path(folder)/"id"
            fake.write_text("echo root")
            fake.chmod(0o777)
            self.assertFalse(xdg_polkit._trusted_system_file(fake))


if __name__ == "__main__":
    unittest.main()
