"""Empty query semantics, raw identifiers and fresh quarantine rechecks."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_sources as sources


class QueryExitTests(unittest.TestCase):
    def foreign(self, code, stdout='', stderr=''):
        process = subprocess.CompletedProcess(['pacman', '-Qmq'], code, stdout, stderr)
        with patch.object(sources.shutil, 'which', return_value='/usr/bin/pacman'), \
             patch.object(sources.subprocess, 'run', return_value=process):
            return sources.pacman_foreign()

    def test_empty_foreign_filter_exit_one_is_healthy_without_diagnostics(self):
        for text in ('', '\n'):
            with self.subTest(output=repr(text)):
                result = self.foreign(1, text)
                self.assertEqual(result.status, 'ok')
                self.assertFalse(result.names)

    def test_foreign_error_partial_output_and_other_exit_codes_remain_failed(self):
        for code, out, err in ((1, '', 'error: database unavailable'),
                               (1, 'partial-package\n', ''),
                               (2, '', ''), (-9, '', '')):
            with self.subTest(code=code, output=out, error=err):
                result = self.foreign(code, out, err)
                self.assertEqual(result.status, 'failed')
                self.assertFalse(result.names)

    def test_empty_exit_one_exception_does_not_apply_to_native_or_other_queries(self):
        process = subprocess.CompletedProcess([], 1, '', '')
        for source, args in (('pacman', ['pacman', '-Qq']),
                             ('pacman_foreign', ['pacman', '-Qq']),
                             ('dpkg', ['dpkg-query', '-W']),
                             ('rpm', ['rpm', '-qa']),
                             ('flatpak', ['flatpak', 'list']),
                             ('snap', ['snap', 'list'])):
            with self.subTest(source=source, args=args), \
                 patch.object(sources.shutil, 'which', return_value='/usr/bin/tool'), \
                 patch.object(sources.subprocess, 'run', return_value=process):
                probe, output = sources._run(source, args, 1)
            self.assertEqual(probe.status, 'failed')
            self.assertEqual(output, '')

    def test_absent_or_timed_out_foreign_query_is_not_a_healthy_empty_filter(self):
        with patch.object(sources.shutil, 'which', return_value=None):
            self.assertEqual(sources.pacman_foreign().status, 'absent')
        with patch.object(sources.shutil, 'which', return_value='/usr/bin/pacman'), \
             patch.object(sources.subprocess, 'run',
                side_effect=subprocess.TimeoutExpired(['pacman', '-Qmq'], 30)):
            self.assertEqual(sources.pacman_foreign().status, 'timeout')

    def test_successful_foreign_query_retains_installed_names(self):
        result = self.foreign(0, 'local-tool\nexample-bin\n')
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.names, {'local-tool', 'example-bin'})


class IdentifierTests(unittest.TestCase):
    def flatpak(self, identifier):
        listing = 'org.example.Valid\tValid\tuser\n' + identifier + '\tFriendly\tsystem\n'
        with patch.object(sources, '_run', return_value=(sources.Probe('flatpak', 'ok'), listing)):
            return sources.flatpak_apps()

    def test_flatpak_accepts_valid_segments_and_unicode_display_names(self):
        for identifier in ('org._7_zip.App', 'org.example.App-name', 'org.example.-App',
                           'org.example._App', 'org.example.Sub.App', 'Org.Example.App_1'):
            with self.subTest(identifier=identifier):
                result = self.flatpak(identifier)
                self.assertEqual(result.status, 'ok')
                self.assertIn(identifier.casefold(), result.app_ids)
        with patch.object(sources, '_run', return_value=(sources.Probe('flatpak', 'ok'),
                'org.example.App\tFriendly café\tuser\n')):
            result = sources.flatpak_apps()
        self.assertIn('friendly café', result.names)
        self.assertNotIn('friendly café', result.app_ids)

    def test_invalid_flatpak_id_discards_the_entire_partial_inventory(self):
        for identifier in ('org.App', 'org..App', '.org.example.App', 'org.example.App.',
                           'org.ex-ample.App', 'org.7example.App', 'org.example.7App',
                           'org.example.App/x86_64/stable', 'org.example.Friendly App',
                           'org.example.Kelvin', 'org.example.' + 'A' * 244):
            with self.subTest(identifier=identifier):
                result = self.flatpak(identifier)
                self.assertEqual(result.status, 'parse_error')
                self.assertFalse(result.names)
                self.assertFalse(result.app_ids)

    def test_flatpak_255_character_id_is_not_rejected_as_oversized(self):
        identifier = 'org.example.' + 'A' * 243
        self.assertEqual(len(identifier), 255)
        self.assertEqual(self.flatpak(identifier).status, 'ok')

    def test_native_identifiers_are_validated_before_unicode_case_folding(self):
        for source, query, output in (
                ('pacman', sources.pacman_packages, 'valid\nKelvin\n'),
                ('pacman_foreign', sources.pacman_foreign, 'valid\nKelvin\n'),
                ('rpm', sources.rpm_packages, 'valid\nKelvin\n'),
                ('dpkg', sources.dpkg_packages,
                 'valid\tinstall ok installed\nKelvin:amd64\tinstall ok installed\n')):
            with self.subTest(source=source), patch.object(sources, '_run',
                    return_value=(sources.Probe(source, 'ok'), output)):
                result = query()
            self.assertEqual(result.status, 'parse_error')
            self.assertFalse(result.names)

    def test_dpkg_accepts_full_architecture_qualified_names(self):
        output = ('example:amd64\tinstall ok installed\n'
                  'other:arm-linux-gnueabihf\tinstall ok installed\n'
                  'legacy:AMD64\tinstall ok installed\n')
        with patch.object(sources, '_run', return_value=(sources.Probe('dpkg', 'ok'), output)):
            result = sources.dpkg_packages()
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.names, {'example', 'example:amd64', 'other',
            'other:arm-linux-gnueabihf', 'legacy', 'legacy:amd64'})

    def test_invalid_dpkg_architecture_discards_preceding_valid_records(self):
        for name in ('example:', ':amd64', 'example:amd64:extra', 'example:bad_arch',
                     'example:am d64', 'example:/tmp', 'example:-amd64', 'example:K64'):
            with self.subTest(name=name), patch.object(sources, '_run', return_value=(
                    sources.Probe('dpkg', 'ok'),
                    'valid\tinstall ok installed\n' + name + '\tinstall ok installed\n')):
                result = sources.dpkg_packages()
            self.assertEqual(result.status, 'parse_error')
            self.assertFalse(result.names)


class QueryRecheckTests(unittest.TestCase):
    def test_malformed_fresh_native_or_flatpak_records_preserve_selected_data(self):
        for provider in ('dpkg', 'flatpak'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                roots = audit.xdg_roots(home)
                scope = 'flatpak' if provider == 'flatpak' else 'config'
                folder = roots[scope] / 'org.example.Retired'
                folder.mkdir(parents=True)
                settings = folder / 'settings'
                settings.write_bytes(b'preserve exact bytes\x00\xff')
                identity = folder.stat()
                row = audit.Item(scope, folder, state='REVIEW',
                    identity=(identity.st_dev, identity.st_ino, identity.st_mode & 0o170000))
                sentinel = home / 'sentinel'
                sentinel.write_bytes(b'untouched')
                output = ('valid\tinstall ok installed\nbroken:amd64:extra\tinstall ok installed\n'
                          if provider == 'dpkg' else
                          'org.example.Valid\tValid\tuser\nnot-an-id\tBroken\tuser\n')
                with patch.object(sources, '_run', return_value=(sources.Probe(provider, 'ok'), output)):
                    malformed = sources.dpkg_packages() if provider == 'dpkg' else sources.flatpak_apps()
                inventory = sources.ActiveInventory((
                    {'python'} if provider == 'flatpak' else set(),
                    set(malformed.names) if provider == 'flatpak' else set(),
                    set(), set(), set(), set(), set(), set()),
                    native_source='pacman' if provider == 'flatpak' else 'dpkg',
                    status={provider: malformed.status, **({'pacman': 'ok'} if provider == 'flatpak' else {})},
                    distro={'dpkg': malformed.names} if provider == 'dpkg' else {},
                    flatpak_ids=malformed.app_ids)
                with patch.object(audit, 'read_active_names', return_value=inventory), \
                     self.assertRaises(ValueError):
                    audit.commit_quarantine([row], roots, home, allow_uncertain=True, emit=lambda _: None)
                self.assertEqual(settings.read_bytes(), b'preserve exact bytes\x00\xff')
                self.assertEqual(folder.stat().st_ino, identity.st_ino)
                self.assertEqual(sentinel.read_bytes(), b'untouched')
                self.assertFalse(audit.quarantine_dir(home, roots).exists())


if __name__ == '__main__':
    unittest.main()
