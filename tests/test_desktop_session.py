"""Desktop evidence cannot silently reuse a real profile or unrelated service."""
import importlib.util
import os
import io
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

    def test_exiting_duplicate_does_not_hide_a_required_component_restart(self):
        processes = [{'pid': index, 'executable': name} for index, name in
                     enumerate(desktop.DESKTOPS['xfce']['processes'], 1)]
        baseline = {'services': {'manager': {'pid': 10}}, 'processes': processes,
                    'native_session': 'x11'}
        duplicate = {**baseline, 'processes': processes + [{'pid': 20, 'executable': 'xfsettingsd'}]}
        desktop.require_session_survived('xfce', duplicate, baseline)
        for replacement in ([], [{'pid': 99, 'executable': 'xfsettingsd'}]):
            after = {**baseline, 'processes': processes[:-1] + replacement}
            with self.assertRaisesRegex(AssertionError, 'component restarted'):
                desktop.require_session_survived('xfce', duplicate, after)
        with self.assertRaisesRegex(AssertionError, 'services restarted'):
            desktop.require_session_survived('xfce', baseline, {**baseline, 'services': {'manager': {'pid': 99}}})

    def mountinfo(self, path, filesystem='fuse.portal', owner=None):
        escaped = str(path).replace('\\', r'\134').replace(' ', r'\040')
        owner = os.getuid() if owner is None else owner
        return f'42 1 0:99 / {escaped} rw,nosuid,nodev - {filesystem} portal rw,user_id={owner},group_id=1\n'

    def test_teardown_selects_only_exact_fixture_owned_portals(self):
        base = Path('/tmp/fixture with spaces')
        doc, gvfs = base / 'runtime/doc', base / 'runtime/gvfs'
        evidence = ''.join(self.mountinfo(path, filesystem) for path, filesystem in (
            (doc, 'fuse.portal'), (gvfs, 'fuse.gvfsd-fuse'),
            ('/run/user/1000/doc', 'fuse.portal'), (base / 'runtime/doc/child', 'fuse.portal'),
            (base / 'home/data', 'ext4'), (Path(str(base) + '-other/runtime/doc'), 'fuse.portal')))
        self.assertEqual(desktop.fixture_portal_mounts(base, evidence), [str(doc), str(gvfs)])
        for wrong in (self.mountinfo(doc, 'ext4'), self.mountinfo(doc, owner=os.getuid() + 1)):
            with self.assertRaisesRegex(AssertionError, 'Unexpected filesystem'):
                desktop.fixture_portal_mounts(base, wrong)

    def test_teardown_detaches_a_private_mount_and_checks_kernel_state(self):
        base = Path('/tmp/private-fixture')
        path = base / 'runtime/doc'
        before = self.mountinfo(path) + self.mountinfo('/run/user/1000/doc')
        after = self.mountinfo('/run/user/1000/doc')
        env, log = {'HOME': '/tmp/private-fixture/home'}, io.StringIO()
        with patch.object(Path, 'read_text', side_effect=[before, after]), \
             patch.object(desktop.shutil, 'which', return_value='/usr/bin/fusermount3'), \
             patch.object(desktop.subprocess, 'run') as command:
            self.assertEqual(desktop.cleanup_fixture_portals(base, env, log), [str(path)])
        command.assert_called_once_with(['/usr/bin/fusermount3', '-u', '-z', '--', str(path)],
            env=env, stdin=desktop.subprocess.DEVNULL, stdout=log, stderr=desktop.subprocess.STDOUT,
            timeout=5, check=False)
        with patch.object(Path, 'read_text', return_value=before), \
             patch.object(desktop.shutil, 'which', return_value='/usr/bin/fusermount3'), \
             patch.object(desktop.subprocess, 'run'):
            with self.assertRaisesRegex(AssertionError, 'did not detach'):
                desktop.cleanup_fixture_portals(base, env, log)

    def test_no_fixture_mount_never_invokes_an_unmount_helper(self):
        with patch.object(Path, 'read_text', return_value=self.mountinfo('/run/user/1000/doc')), \
             patch.object(desktop.subprocess, 'run', side_effect=AssertionError('must not unmount')):
            self.assertEqual(desktop.cleanup_fixture_portals(Path('/tmp/fixture'), {}, io.StringIO()), [])
