"""Regression tests for per-user desktop registration, with disposable data only."""
from __future__ import annotations

import os
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install_desktop


class DesktopRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "checkout"
        (self.project / "assets").mkdir(parents=True)
        (self.project / "xdg_audit.py").write_text("print('fixture')\n")
        (self.project / "assets" / "xdg-audit.png").write_bytes(b"fixture icon")

    def register(self):
        with patch.object(install_desktop.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home / ".local/share")}):
            return install_desktop.install(self.home, self.project)

    def test_installs_only_two_user_assets_without_touching_other_entry(self):
        data = self.home / ".local/share"
        unrelated = data / "applications" / "other.desktop"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_bytes(b"must survive")
        created = self.register()
        self.assertEqual(len(created), 2)
        self.assertTrue(all(self.home in path.parents for path in created))
        self.assertEqual(unrelated.read_bytes(), b"must survive")
        self.assertIn(str(self.project / "xdg_audit.py"), created[0].read_text())
        self.assertEqual(created[1].read_bytes(), b"fixture icon")

    def test_rejects_symlink_for_desktop_entry(self):
        data = self.home / ".local/share"
        applications = data / "applications"
        applications.mkdir(parents=True)
        outside = self.root / "do-not-overwrite"
        outside.write_bytes(b"safe")
        (applications / "io.github.xdgaudit.desktop").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.register()
        self.assertEqual(outside.read_bytes(), b"safe")

    def test_rejects_destination_outside_home(self):
        with patch.object(install_desktop.os, "geteuid", return_value=1000), \
             patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "outside")}):
            with self.assertRaisesRegex(ValueError, "HOME"):
                install_desktop.install(self.home, self.project)

    def test_rejects_root(self):
        with patch.object(install_desktop.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "root"):
                install_desktop.install(self.home, self.project)

    def test_rejects_symlinked_ancestor_inside_home(self):
        data = self.home / '.local/share'
        target = self.home / 'other-icons'
        target.mkdir()
        data.mkdir(parents=True)
        (data / 'icons').symlink_to(target, target_is_directory=True)
        with self.assertRaises((OSError, ValueError)):
            self.register()
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((data / 'applications/io.github.xdgaudit.desktop').exists())

    def test_failed_update_preserves_existing_registration(self):
        paths = self.register()
        before = [path.read_bytes() for path in paths]
        with patch.object(install_desktop.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'full disk')):
            with self.assertRaises(OSError) as caught:
                self.register()
        self.assertEqual(caught.exception.errno, errno.ENOSPC)
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertFalse(list(self.home.rglob('.xdg-audit-*.tmp')))

    def test_update_replaces_only_registered_assets(self):
        paths = self.register()
        sentinel = self.home / '.local/share/xdg-audit-quarantine/keep'
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b'preserved quarantine')
        (self.project / 'assets/xdg-audit.png').write_bytes(b'new icon')
        self.assertEqual(self.register(), paths)
        self.assertEqual(paths[1].read_bytes(), b'new icon')
        for path in paths:
            path.unlink()  # documented unregistration: the two exact files
        self.assertEqual(sentinel.read_bytes(), b'preserved quarantine')

    def test_exec_quotes_percent_and_rejects_newline_injection(self):
        self.assertEqual(install_desktop._quote_exec('/tmp/50%/app.py'), '"/tmp/50%%/app.py"')
        for value in ('/tmp/app\nHidden=true', '/tmp/app\rExec=bad', '/tmp/app\x00'):
            with self.subTest(path=value), self.assertRaises(ValueError):
                install_desktop._quote_exec(value)

    def test_rejects_hardlinked_existing_icon(self):
        paths = self.register()
        outside = self.home / 'unrelated-icon'
        os.link(paths[1], outside)
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(outside.read_bytes(), b'fixture icon')


if __name__ == "__main__":
    unittest.main()
