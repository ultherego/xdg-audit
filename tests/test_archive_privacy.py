"""Source archives never collect incidental checkout files or symlink targets."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_archives as builder


class ArchivePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'xdg_audit.py').write_text('VERSION = "1.7.0-rc2"\n')
        self.names = ['xdg_audit.py', builder.MANIFEST]
        self.save_manifest()

    def save_manifest(self):
        (self.root / builder.MANIFEST).write_text(json.dumps(self.names))

    def test_incidental_reports_credentials_and_output_are_excluded(self):
        for name in ('.env', 'audit-private.json', 'personal.py', 'ssh-private-key.pem'):
            (self.root / name).write_text('fixture-private-bytes')
        with patch.object(builder, 'SOURCE_ROOT', self.root):
            one = builder.archives(self.root / 'custom-output')
            two = builder.archives(self.root / 'custom-output')
        with zipfile.ZipFile(two[0]) as archive:
            self.assertEqual(set(archive.namelist()),
                {'xdg-audit-1.7.0-rc2/' + name for name in self.names})
            self.assertNotIn(b'fixture-private-bytes', b''.join(archive.read(name) for name in archive.namelist()))

    def test_declared_symlink_never_publishes_external_bytes(self):
        external = self.root / 'external-private'
        external.write_text('fixture must stay private')
        (self.root / 'linked.py').symlink_to(external)
        self.names.append('linked.py')
        self.save_manifest()
        with patch.object(builder, 'SOURCE_ROOT', self.root), self.assertRaisesRegex(ValueError, 'Symlink'):
            builder.inputs()

    def test_declared_symlinked_ancestor_is_rejected(self):
        target = self.root / 'actual'
        target.mkdir()
        (target / 'private.md').write_text('private fixture')
        (self.root / 'docs').symlink_to(target, target_is_directory=True)
        self.names.append('docs/private.md')
        self.save_manifest()
        with patch.object(builder, 'SOURCE_ROOT', self.root), self.assertRaisesRegex(ValueError, 'Symlink'):
            builder.inputs()

    def test_traversal_duplicate_and_absolute_members_are_rejected(self):
        for names in (['../private'], ['/etc/hostname'], ['xdg_audit.py'] * 2):
            with self.subTest(names=names):
                self.names = names
                self.save_manifest()
                with patch.object(builder, 'SOURCE_ROOT', self.root), self.assertRaises(ValueError):
                    builder.inputs()
