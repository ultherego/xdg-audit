"""Native package payload boundaries and source/version compatibility."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packaging'))
import install_payload as payload
import repository
from check_version import check


class PackagingTests(unittest.TestCase):
    def test_payload_is_reviewed_and_excludes_checkout_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'payload'
            payload.stage(ROOT, target)
            actual = {p.relative_to(target / 'usr/lib/xdg-audit').as_posix()
                      for p in (target / 'usr/lib/xdg-audit').rglob('*') if p.is_file()}
            self.assertEqual(actual, set(payload.reviewed_files(ROOT)))
            self.assertFalse(any(p.suffix == '.pyc' for p in target.rglob('*')))
            self.assertFalse((target / 'etc').exists())
            self.assertFalse((target / 'usr/lib/systemd').exists())
            self.assertEqual((target / 'usr/bin/xdg-audit').stat().st_mode & 0o777, 0o755)
            self.assertIn('Exec=/usr/bin/xdg-audit --gui',
                          (target / 'usr/share/applications/io.github.xdgaudit.desktop').read_text())
            self.assertEqual((target / 'usr/share/licenses/xdg-audit/LICENSE').read_bytes(),
                             (ROOT / 'LICENSE').read_bytes())

    def test_staging_refuses_symlinked_parent_and_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            actual = base / 'actual'
            actual.mkdir()
            (base / 'link').symlink_to(actual, target_is_directory=True)
            for destination in (base / 'link', base / 'link/child'):
                with self.subTest(destination=destination), self.assertRaises(ValueError):
                    payload.stage(ROOT, destination)
            self.assertEqual(list(actual.iterdir()), [])

    def test_target_symlink_never_overwrites_external_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            sentinel = base / 'sentinel'
            sentinel.write_text('keep')
            (base / 'payload/usr/bin').mkdir(parents=True)
            (base / 'payload/usr/bin/xdg-audit').symlink_to(sentinel)
            with self.assertRaises(ValueError):
                payload.stage(ROOT, base / 'payload')
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_native_prerelease_versions_sort_before_final(self):
        self.assertEqual(payload.package_version('1.7.0-rc2', 'deb'), '1.7.0~rc2')
        self.assertEqual(payload.package_version('1.7.0-rc2', 'rpm'), '1.7.0~rc2')
        self.assertEqual(payload.package_version('1.7.0-rc2', 'arch'), '1.7.0rc2')

    def test_release_tag_must_match_source_version(self):
        check(ROOT, 'v' + payload.version(ROOT))
        with self.assertRaises(ValueError):
            check(ROOT, 'v99.0.0')

    def test_repository_output_refuses_incidental_private_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'private-key.asc').write_text('private test fixture')
            with self.assertRaisesRegex(ValueError, 'Unexpected file'):
                repository.safe_output(base)

    def test_repository_rejects_untrusted_url_and_output_paths(self):
        for url in ('http://example.org', 'https://name:secret@example.org',
                    'https://example.org/?query=1', 'https://example.org/#x',
                    'https://example.org/\nInjected:yes'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                repository.validate_url(url)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / 'link').symlink_to(base / 'outside')
            with self.assertRaises(ValueError):
                repository.safe_output(base / 'link')

    def test_published_package_version_is_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, target = base / 'new.deb', base / 'pool/old.deb'
            source.write_bytes(b'original')
            repository.immutable_copy(source, target)
            repository.immutable_copy(source, target)
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                repository.immutable_copy(source, target)
            self.assertEqual(target.read_bytes(), b'original')
