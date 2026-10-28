"""Desktop evidence cannot silently reuse a real profile or unrelated service."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('desktop_session_smoke',
    Path(__file__).resolve().parents[1] / 'scripts/gui_desktop_session_smoke.py')
desktop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desktop)


class DesktopSessionTests(unittest.TestCase):
    def test_private_profile_cannot_inherit_display_bus_or_credentials(self):
        inherited = {'HOME': '/real-home', 'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'real-wayland',
                     'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/real-bus', 'XAUTHORITY': '/real-cookie',
                     'GH_TOKEN': 'private-test-token', 'GITHUB_SHA': 'reviewed-test-commit'}
        with patch.dict(os.environ, inherited, clear=True):
            env = desktop.environment(Path('/disposable-session'), 'gnome')
        self.assertEqual(env['HOME'], '/disposable-session/home')
        self.assertEqual(env['GITHUB_SHA'], 'reviewed-test-commit')
        self.assertFalse(set(inherited) - {'HOME', 'GITHUB_SHA'} & set(env))
        self.assertNotIn('private-test-token', repr(env))

    def test_same_named_process_from_another_profile_is_not_session_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = Path(temp)
            process = proc / '123'
            process.mkdir()
            (process / 'exe').symlink_to('/usr/bin/gnome-shell')
            (process / 'environ').write_bytes(b'HOME=/real-home\0')
            with self.assertRaisesRegex(AssertionError, 'another profile'):
                desktop.process_identity(123, Path('/fixture-home'), 'gnome-shell', proc)
            (process / 'environ').write_bytes(b'HOME=/fixture-home\0')
            self.assertTrue(desktop.process_identity(123, Path('/fixture-home'), 'gnome-shell', proc)['fixture_profile'])
            with self.assertRaisesRegex(AssertionError, 'Unexpected desktop service'):
                desktop.process_identity(123, Path('/fixture-home'), 'gnome-session-binary', proc)

    def test_compositor_alone_cannot_establish_a_full_desktop_session(self):
        with patch.object(desktop, 'bus_call', return_value="(['org.gnome.Shell'],)"), \
             patch.dict(os.environ, {'HOME': '/fixture-home'}):
            with self.assertRaisesRegex(AssertionError, 'Full desktop services are not ready'):
                desktop.session_evidence('gnome')
