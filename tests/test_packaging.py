"""Build pipeline integrity / reproducibility tests."""
import hashlib
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_archives import archives, version


class PackageTests(unittest.TestCase):
    def test_package_archive_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = archives(Path(tmp))
            self.assertEqual(len(paths), 3)
            zipped, tarred, sums = paths
            self.assertEqual(zipped.stem, 'xdg-audit-' + version())
            with zipfile.ZipFile(zipped) as z:
                self.assertIsNone(z.testzip())
                filenames = z.namelist()
                self.assertIn(f'xdg-audit-{version()}/xdg_audit.py', filenames)
                self.assertTrue(all('__pycache__' not in n and '.pytest_cache' not in n for n in filenames))
                self.assertIn(f'xdg-audit-{version()}/assets/xdg-audit-128.png', filenames)
            with tarfile.open(tarred, 'r:gz') as t:
                self.assertIn(f'xdg-audit-{version()}/xdg_audit.py', t.getnames())
            lines = sums.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            for path, line in zip((zipped, tarred), lines):
                self.assertEqual(line, f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')

    def test_archive_reproducibility(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            built_one, built_two = archives(Path(one)), archives(Path(two))
            for a, b in zip(built_one, built_two):
                self.assertEqual(hashlib.sha256(a.read_bytes()).digest(),
                                 hashlib.sha256(b.read_bytes()).digest())
