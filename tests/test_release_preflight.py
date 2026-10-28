"""Release approval pins application bytes; signing probes never expose keys."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packaging'))
import release_preflight as preflight


class ReleaseRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        names = ['xdg_audit.py', 'xdg_fixture.py', 'assets/xdg-audit.png',
                 'assets/xdg-audit-128.png', 'assets/io.github.xdgaudit.png',
                 'scripts/install_retention_timer.py']
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('VERSION = "1.7.0-rc2"\n' if name == 'xdg_audit.py' else 'fixture\n')
        (self.root / 'scripts/archive-files.json').write_text(json.dumps(names))
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Release fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.commit()
        self.accepted = self.git('rev-parse', 'HEAD').strip()
        (self.root / '.github').mkdir()
        (self.root / 'docs').mkdir()
        (self.root / 'docs/acceptance.md').write_text('Owner-reported acceptance fixture.\n')
        self.request = {'version': '1.7.0-rc2', 'accepted_application_sha': self.accepted,
                        'owner_acceptance': 'docs/acceptance.md'}
        self.write_request()
        self.commit()

    def git(self, *arguments):
        return subprocess.check_output(['git', '-C', str(self.root), *arguments],
                                       stderr=subprocess.PIPE, text=True)

    def commit(self):
        self.git('add', '--all')
        self.git('commit', '-q', '-m', 'Disposable release fixture')

    def write_request(self):
        (self.root / preflight.REQUEST).write_text(json.dumps(self.request))

    def resolve(self, manual=''):
        return preflight.release_request(self.root, self.git('rev-parse', 'HEAD').strip(), manual)

    def test_valid_request_accepts_only_unchanged_application(self):
        self.assertEqual(self.resolve(), self.request)
        preflight.verify_accepted_runtime(self.root, self.resolve())
        (self.root / 'docs/release-notes.md').write_text('Documentation-only preparation.\n')
        self.commit()
        preflight.verify_accepted_runtime(self.root, self.resolve())

    def test_changed_application_requires_new_acceptance(self):
        (self.root / 'xdg_fixture.py').write_text('changed runtime\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'changed since owner acceptance'):
            preflight.verify_accepted_runtime(self.root, self.resolve())

    def test_added_runtime_module_cannot_inherit_old_approval(self):
        (self.root / 'xdg_added.py').write_text('new runtime\n')
        manifest = self.root / 'scripts/archive-files.json'
        manifest.write_text(json.dumps(json.loads(manifest.read_text()) + ['xdg_added.py']))
        self.commit()
        with self.assertRaisesRegex(ValueError, 'runtime changed'):
            preflight.verify_accepted_runtime(self.root, self.resolve())

    def test_wrong_commit_and_dirty_checkout_refused(self):
        with self.assertRaisesRegex(ValueError, 'does not match'):
            preflight.release_request(self.root, self.accepted)
        with self.assertRaisesRegex(ValueError, 'full SHA'):
            preflight.release_request(self.root, 'main')
        (self.root / 'untracked-output').write_text('unreviewed\n')
        with self.assertRaisesRegex(ValueError, 'must be clean'):
            preflight.verify_accepted_runtime(self.root, self.resolve())

    def test_stale_version_request_is_not_an_automatic_release(self):
        self.request['version'] = '1.7.0-rc1'
        self.write_request()
        self.commit()
        self.assertIsNone(self.resolve())
        with self.assertRaises(ValueError):
            self.resolve('1.7.0-rc2')

    def test_missing_request_is_a_noop_but_not_a_manual_approval(self):
        (self.root / preflight.REQUEST).unlink()
        self.assertIsNone(self.resolve())
        with self.assertRaisesRegex(ValueError, 'Commit a release request'):
            self.resolve('1.7.0-rc2')

    def test_manipulated_record_paths_and_versions_refused(self):
        for field, value in (('owner_acceptance', '../outside.md'),
                             ('owner_acceptance', '/outside.md'),
                             ('accepted_application_sha', '--help'),
                             ('version', '1.7.0-rc2\nmalicious_output=true')):
            with self.subTest(field=field, value=value):
                original = self.request[field]
                self.request[field] = value
                self.write_request()
                with self.assertRaises(ValueError):
                    self.resolve()
                self.request[field] = original

    def test_symlinked_acceptance_record_refused(self):
        record = self.root / 'docs/acceptance.md'
        record.unlink()
        record.symlink_to(self.root / 'xdg_audit.py')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.resolve()


class MissingSigningConfigurationTests(unittest.TestCase):
    def test_missing_configuration_never_starts_gnupg(self):
        with patch.object(preflight.subprocess, 'run', side_effect=AssertionError('must not spawn')):
            result = preflight.signing_report('', '')
        self.assertFalse(result['ready'])
        self.assertEqual(result['missing'], ['PACKAGES_SIGNING_KEY', 'PACKAGES_SIGNING_FINGERPRINT'])

    def test_invalid_fingerprint_never_echoes_private_input(self):
        marker = 'PRIVATE-FIXTURE-MUST-NOT-APPEAR'
        result = preflight.signing_report(marker, marker)
        self.assertEqual(result['error'], 'invalid_fingerprint')
        self.assertNotIn(marker, json.dumps(result))

    def test_malformed_key_report_and_logs_contain_no_key_data(self):
        if not shutil.which('gpg'):
            self.skipTest('GnuPG not installed')
        marker = 'PRIVATE-FIXTURE-MUST-NOT-APPEAR'
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            result = preflight.signing_report(marker, 'A' * 40)
        self.assertFalse(result['ready'])
        self.assertNotIn(marker, json.dumps(result) + out.getvalue() + err.getvalue())


@unittest.skipUnless(all(shutil.which(tool) for tool in ('gpg', 'gpgconf', 'gpg-agent')),
                     'GnuPG and its agent required')
class ActualSigningProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='xdg-preflight-TEST-ONLY-')
        cls.addClassCleanup(cls.temp.cleanup)
        # GnuPG requires a local agent socket. Some development sandboxes
        # prohibit socket creation; Actions runs the actual signing cases.
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.bind(str(Path(cls.temp.name) / 'agent-capability.socket'))
        except PermissionError as error:
            raise unittest.SkipTest('Sandbox disallows the Unix sockets required by GnuPG') from error
        cls.keys = []
        for index, password in enumerate(('', 'fixture-password')):
            home = Path(cls.temp.name) / str(index)
            home.mkdir(mode=0o700)
            prefix = ['gpg', '--no-options', '--homedir', str(home), '--batch',
                      '--pinentry-mode', 'loopback', '--passphrase', password]
            subprocess.run([*prefix, '--quick-generate-key', 'xdg-audit TEST ONLY signer',
                            'rsa2048', 'sign', '1d'], check=True, capture_output=True, timeout=45)
            listing = subprocess.check_output([*prefix, '--with-colons', '--list-secret-keys'], stderr=subprocess.PIPE).decode()
            fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
            private = subprocess.check_output([*prefix, '--armor', '--export-secret-keys', fingerprint], stderr=subprocess.PIPE).decode()
            public = subprocess.check_output([*prefix, '--armor', '--export', fingerprint], stderr=subprocess.PIPE).decode()
            cls.keys.append((private, public, fingerprint))
            subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'gpg-agent'], check=True, capture_output=True)

    def test_existing_unattended_key_signs_without_touching_parent_keyring(self):
        private, _, fingerprint = self.keys[0]
        with tempfile.TemporaryDirectory() as parent:
            sentinel = Path(parent) / 'sentinel'
            sentinel.write_text('preserve parent keyring')
            with patch.dict(os.environ, {'GNUPGHOME': parent}):
                result = preflight.signing_report(private, fingerprint)
                self.assertEqual(os.environ['GNUPGHOME'], parent)
            self.assertEqual(list(Path(parent).iterdir()), [sentinel])
        self.assertTrue(result['ready'])
        self.assertEqual(result['signing_fingerprint'], fingerprint)

    def test_wrong_fingerprint_refused(self):
        private, _, _ = self.keys[0]
        result = preflight.signing_report(private, self.keys[1][2])
        self.assertFalse(result['ready'])
        self.assertEqual(result['error'], 'signing_key_mismatch')

    def test_public_key_alone_cannot_authorize_release(self):
        _, public, fingerprint = self.keys[0]
        result = preflight.signing_report(public, fingerprint)
        self.assertFalse(result['ready'])

    def test_password_protected_key_cannot_silently_pass_unattended_probe(self):
        private, _, fingerprint = self.keys[1]
        result = preflight.signing_report(private, fingerprint)
        self.assertFalse(result['ready'])
        self.assertEqual(result['error'], 'unattended_signing_failed')
