"""Native authorization, Snap namespaces and static AppImage regression cases."""
import gzip
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_sources as sources


def inventory(provider='dpkg', *, names=('unrelated',), health='ok', snaps=(),
              snap_health='ok', images=(), native=True):
    return sources.ActiveInventory((
        set(names) if provider == 'pacman' else set(), set(), set(snaps), set(images),
        set(), set(), set(), set()),
        status={provider: health, 'snap': snap_health, 'flatpak': 'absent', 'appimage': 'ok'},
        distro={provider: set(names)} if provider != 'pacman' else {},
        native_source=provider if native else None, snap_ids=snaps)


class NativeSourceTests(unittest.TestCase):
    def test_os_identity_selects_native_database(self):
        cases = [('cachyos', 'arch', 'pacman'), ('ubuntu', 'debian', 'dpkg'),
                 ('debian', '', 'dpkg'), ('fedora', '', 'rpm'),
                 ('rocky', 'rhel fedora', 'rpm'), ('opensuse-tumbleweed', 'suse', 'rpm'),
                 ('custom', 'debian', 'dpkg'), ('custom', '', None)]
        for identity, like, expected in cases:
            with self.subTest(identity=identity), patch.object(sources.platform, 'freedesktop_os_release',
                    return_value={'ID': identity, 'ID_LIKE': like}):
                self.assertEqual(sources.native_package_source(), expected)

    def test_missing_or_unreadable_os_identity_is_not_tool_detection(self):
        with patch.object(sources.platform, 'freedesktop_os_release', side_effect=OSError('unreadable')):
            self.assertIsNone(sources.native_package_source())
        with self.assertRaisesRegex(ValueError, 'determine native'):
            sources.verified_native_source(inventory('pacman', native=False))

    def test_wrong_installed_tool_cannot_replace_native_database(self):
        inv = sources.ActiveInventory(({'firefox'}, set(), set(), set(), set(), set(), set(), set()),
            native_source='dpkg', status={'dpkg': 'failed', 'pacman': 'ok'}, distro={'dpkg': set()})
        with self.assertRaisesRegex(ValueError, 'dpkg inventory'):
            sources.verified_native_source(inv)

    def test_empty_failed_partial_and_timeout_native_database_cannot_authorize(self):
        for provider in ('pacman', 'dpkg', 'rpm'):
            for state in ('absent', 'failed', 'timeout', 'parse_error', 'partial'):
                with self.subTest(provider=provider, state=state), self.assertRaises(ValueError):
                    sources.verified_native_source(inventory(provider, health=state))
            with self.subTest(provider=provider, empty=True), self.assertRaises(ValueError):
                sources.verified_native_source(inventory(provider, names=()))

    def test_dpkg_half_configured_or_reinstall_required_blocks_move(self):
        for state in ('install ok unpacked', 'install ok half-configured', 'install reinstreq installed'):
            with self.subTest(state=state), patch.object(sources, '_run', return_value=(
                    sources.Probe('dpkg', 'ok'), 'python3\tinstall ok installed\npartial\t' + state + '\n')):
                result = sources.dpkg_packages()
            self.assertEqual(result.status, 'partial')
            self.assertIn('python3', result.names)

    def test_dpkg_history_plain_gzip_and_reinstall(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            log = home / 'dpkg.log'
            log.write_text('2026-10-26 12:00:00 remove departed:amd64 1.0 <none>\n'
                           '2026-10-26 12:00:01 status config-files departed:amd64 1.0\n'
                           '2026-10-26 12:00:02 install current:amd64 <none> 1.0\n')
            compressed = home / 'dpkg.log.1.gz'
            with gzip.open(compressed, 'wb') as stream:
                stream.write(b'2026-10-25 12:00:00 purge ancient:amd64 1.0 <none>\n')
            removed = sources.dpkg_removals([log, compressed])
            self.assertEqual(set(removed), {'departed', 'ancient'})
            path = home / '.config/departed'
            path.mkdir(parents=True)
            with patch.object(audit, 'read_active_names', return_value=inventory()), \
                 patch.object(sources, 'dpkg_removals', return_value=removed):
                rows, *_ = audit.scan(home, ['config'], set(), {}, True)
            self.assertEqual(rows[0].state, 'CANDIDATE')
            self.assertEqual(rows[0].json()['evidence'][0]['source'], 'dpkg_history')
            self.assertEqual(rows[0].json()['evidence_level'], 'historical_only')
            with patch.object(audit, 'read_active_names', return_value=inventory(names=('departed',))), \
                 patch.object(sources, 'dpkg_removals', return_value=removed):
                rows, *_ = audit.scan(home, ['config'], set(), {}, True)
            self.assertEqual(rows[0].state, 'ACTIVE')


class SourceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.roots = audit.xdg_roots(self.home)
        self.sentinel = self.home / 'sentinel'
        self.sentinel.write_bytes(b'never change')

    def row(self, scope='config', name='departed'):
        path = self.roots[scope] / name
        path.mkdir(parents=True)
        (path / 'data').write_bytes(b'exact\x00\xff')
        info = path.stat()
        return audit.Item(scope, path, state='REVIEW',
            identity=(info.st_dev, info.st_ino, stat.S_IFDIR))

    def test_native_deb_and_rpm_complete_explicit_restore_and_purge(self):
        for provider in ('dpkg', 'rpm'):
            with self.subTest(provider=provider):
                row = self.row(name='departed-' + provider)
                with patch.object(audit, 'read_active_names', return_value=inventory(provider)):
                    with self.assertRaisesRegex(ValueError, 'Blocked entry'):
                        audit.commit_quarantine([row], self.roots, self.home)
                    moved = audit.commit_quarantine([row], self.roots, self.home,
                        allow_uncertain=True, emit=lambda _: None)
                self.assertEqual(len(moved['moved']), 1)
                restored = audit.restore_quarantine_run(self.home, self.roots, moved['run_id'], emit=lambda _: None)
                self.assertEqual(restored['restored'], 1)
                self.assertEqual((row.path / 'data').read_bytes(), b'exact\x00\xff')
                with patch.object(audit, 'read_active_names', return_value=inventory(provider)):
                    moved = audit.commit_quarantine([row], self.roots, self.home,
                        allow_uncertain=True, emit=lambda _: None)
                purge = audit.purge_quarantine_run(self.home, self.roots, moved['run_id'], dry_run=False, emit=lambda _: None)
                self.assertEqual(purge['objects'], 1)
                self.assertEqual(self.sentinel.read_bytes(), b'never change')

    def test_reinstallation_or_source_failure_before_move_preserves_bytes(self):
        row = self.row()
        for inv in (inventory('rpm', names=('departed',)), inventory('dpkg', names=('departed',)),
                    inventory('dpkg', health='partial'), inventory('rpm', health='timeout')):
            with self.subTest(source=inv.native_source, health=inv.status), \
                 patch.object(audit, 'read_active_names', return_value=inv), self.assertRaises(ValueError):
                audit.commit_quarantine([row], self.roots, self.home, allow_uncertain=True)
            self.assertEqual((row.path / 'data').read_bytes(), b'exact\x00\xff')
        self.assertFalse(audit.quarantine_dir(self.home, self.roots).exists())

    def test_snap_scope_uses_exact_instance_not_native_or_base_names(self):
        row = self.row('snap', 'firefox_work')
        inv = inventory(names=('firefox',), snaps=('firefox',))
        with patch.object(audit, 'read_active_names', return_value=inv):
            rows, *_ = audit.scan(self.home, ['snap'], set(), {}, True)
            self.assertEqual(rows[0].state, 'REVIEW')
            result = audit.commit_quarantine([row], self.roots, self.home, allow_uncertain=True, emit=lambda _: None)
        self.assertEqual(len(result['moved']), 1)
        self.assertEqual(audit.restore_quarantine_run(self.home, self.roots, result['run_id'],
            emit=lambda _: None)['restored'], 1)
        with patch.object(audit, 'read_active_names', return_value=inventory(snaps=('firefox_work',))):
            rows, *_ = audit.scan(self.home, ['snap'], set(), {}, True)
            self.assertEqual(rows[0].state, 'ACTIVE')
            with self.assertRaisesRegex(ValueError, 'present now'):
                audit.commit_quarantine([row], self.roots, self.home, allow_uncertain=True)
        self.assertEqual((row.path / 'data').read_bytes(), b'exact\x00\xff')

        with patch.object(audit, 'read_active_names', return_value=inv):
            result = audit.commit_quarantine([row], self.roots, self.home, allow_uncertain=True, emit=lambda _: None)
        self.assertEqual(audit.purge_quarantine_run(self.home, self.roots, result['run_id'],
            dry_run=False, emit=lambda _: None)['objects'], 1)
        self.assertFalse(row.path.exists())
        self.assertEqual(self.sentinel.read_bytes(), b'never change')

    def test_absent_snap_daemon_cannot_authorize_namespace_move(self):
        row = self.row('snap', 'retired-app')
        with patch.object(audit, 'read_active_names', return_value=inventory(snap_health='absent')):
            with self.assertRaisesRegex(ValueError, 'snap inventory'):
                audit.commit_quarantine([row], self.roots, self.home, allow_uncertain=True)
        self.assertTrue(row.path.exists())

    def test_appimage_appearing_after_scan_blocks_move(self):
        row = self.row(name='notion')
        images = self.home / 'Applications'
        images.mkdir()
        (images / 'Notion-3.0.1-x86_64.AppImage').write_bytes(b'never execute')
        found = sources.user_appimages(self.home)
        with patch.object(audit, 'read_active_names', return_value=inventory(images=found.names)):
            with self.assertRaisesRegex(ValueError, 'present now'):
                audit.commit_quarantine([row], self.roots, self.home, allow_uncertain=True)
        self.assertTrue(row.path.exists())


class SnapParserTests(unittest.TestCase):
    def test_full_rows_parallel_instances_and_disabled_installs(self):
        output = ('Name Version Rev Tracking Publisher Notes\n'
                  'firefox 1.0 123 latest/stable canonical✓ -\n'
                  'firefox_work 2.0 x1 - - disabled\n')
        with patch.object(sources, '_run', return_value=(sources.Probe('snap', 'ok'), output)):
            found = sources.snap_apps()
        self.assertEqual(found.status, 'ok')
        self.assertEqual(found.app_ids, {'firefox', 'firefox_work'})

    def test_truncated_rows_and_malformed_identifiers_discard_partial_inventory(self):
        for bad in ('firefox 1.0', 'firefox 1.0 broken stable publisher -',
                    'Firefox 1.0 123 stable publisher -', 'firefox_bad_bad 1.0 1 stable p -',
                    'a_x 1 1 stable p -', 'foo--bar 1 1 stable p -'):
            with self.subTest(row=bad), patch.object(sources, '_run', return_value=(sources.Probe('snap', 'ok'),
                    'Name Version Rev Tracking Publisher Notes\nvalid-app 1 1 stable p -\n' + bad)):
                result = sources.snap_apps()
            self.assertEqual(result.status, 'parse_error')
            self.assertFalse(result.names)
            self.assertFalse(result.app_ids)

    def test_successful_empty_database_and_forced_locale(self):
        proc = subprocess.CompletedProcess(['snap', 'list'], 0, '', sources.SNAP_EMPTY + '\n')
        with patch.object(sources.shutil, 'which', return_value='/usr/bin/snap'), \
             patch.object(sources.subprocess, 'run', return_value=proc) as run:
            found = sources.snap_apps()
        self.assertEqual(found.status, 'ok')
        self.assertFalse(found.names)
        self.assertEqual(run.call_args.kwargs['env']['LC_MESSAGES'], 'C')
        self.assertEqual(run.call_args.kwargs['env']['LANG'], 'C')

    def test_failed_command_is_not_a_successful_empty_inventory(self):
        proc = subprocess.CompletedProcess(['snap', 'list'], 1, '', sources.SNAP_EMPTY + '\n')
        with patch.object(sources.shutil, 'which', return_value='/usr/bin/snap'), \
             patch.object(sources.subprocess, 'run', return_value=proc):
            found = sources.snap_apps()
        self.assertEqual(found.status, 'failed')
        self.assertFalse(found.names)


class AppImageStaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.desktop = self.home / '.local/share/applications'
        self.desktop.mkdir(parents=True)
        self.image = self.home / 'custom image folder' / 'Obsidian-1.8.2-x86_64.AppImage'
        self.image.parent.mkdir()
        self.image.write_bytes(b'must never execute or mount')

    def launcher(self, target=None):
        target = target or self.image
        (self.desktop / 'appimage-hash.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Obsidian\n'
            f'Exec=env APPIMAGE_TEST=yes "{target}" %U\n')

    def test_static_launcher_versions_and_portable_data_without_execution(self):
        self.launcher()
        with patch.object(sources.subprocess, 'run') as execute:
            result = sources.user_appimages(self.home)
        execute.assert_not_called()
        self.assertEqual(result.status, 'ok')
        self.assertIn('obsidian', result.names)
        self.assertEqual(result.app_ids, {str(self.image)})
        self.assertIn(self.image.name.casefold() + '.home', result.names)
        self.assertEqual(self.image.read_bytes(), b'must never execute or mount')

    def test_stale_launcher_is_not_active_image_evidence(self):
        self.launcher(self.home / 'missing.AppImage')
        result = sources.user_appimages(self.home)
        self.assertEqual(result.status, 'ok')
        self.assertNotIn('obsidian', result.names)

    def test_launcher_symlinked_image_ancestor_is_not_followed(self):
        link = self.home / 'linked'
        link.symlink_to(self.image.parent, target_is_directory=True)
        self.launcher(link / self.image.name)
        result = sources.user_appimages(self.home)
        self.assertNotIn('obsidian', result.names)

    def test_launcher_metadata_without_image_cannot_prove_installation(self):
        (self.desktop / 'made-up.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Obsidian\nExec=sh -c "missing.AppImage"\n')
        with patch.object(sources.subprocess, 'run') as execute:
            result = sources.user_appimages(self.home)
        execute.assert_not_called()
        self.assertNotIn('obsidian', result.names)

    def test_unreadable_appimage_launcher_blocks_evidence_completeness(self):
        (self.desktop / 'broken.desktop').write_text('Exec=/some/App.AppImage\nwithout a section')
        self.assertEqual(sources.user_appimages(self.home).status, 'failed')
