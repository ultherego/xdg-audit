"""Read the real dpkg database; never authorize a native non-Arch MOVE."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_sources as sources


@unittest.skipUnless(shutil.which('dpkg-query') and not shutil.which('pacman'),
                     'requires a native dpkg host without pacman')
class NativeReadOnlyTests(unittest.TestCase):
    def test_real_dpkg_scan_and_mutation_refusal_preserve_fixture(self):
        with tempfile.TemporaryDirectory(prefix='xdg-native-readonly-') as temp:
            home = Path(temp)
            db = home / 'fixture-dpkg-db'
            db.mkdir()
            (db / 'status').write_text(''.join(
                f'Package: fixture-{want}\nStatus: {want} ok installed\n'
                'Architecture: all\nVersion: 1.0\nMaintainer: Fixture\n'
                'Description: disposable fixture\n\n' for want in ('deinstall', 'purge')))
            native = subprocess.run(['dpkg-query', '--admindir=' + str(db), '-W',
                '-f=${binary:Package}\t${Status}\n'], capture_output=True, text=True, check=True)
            with patch.object(sources, '_run', return_value=(sources.Probe('dpkg', 'ok'), native.stdout)):
                pending = sources.dpkg_packages()
            self.assertEqual(pending.status, 'ok')
            self.assertEqual(pending.names, {'fixture-deinstall', 'fixture-purge'})
            source = home / '.config/xdg-native-fixture'
            source.mkdir(parents=True)
            (source / 'settings').write_bytes(b'preserve\x00\xff')
            env = {'XDG_CONFIG_HOME': str(home / '.config'),
                   'XDG_DATA_HOME': str(home / '.local/share'),
                   'XDG_STATE_HOME': str(home / '.local/state'),
                   'XDG_CACHE_HOME': str(home / '.cache'), 'HOME': str(home)}
            with patch.dict(os.environ, env):
                actual = sources.dpkg_packages()
                self.assertEqual(actual.status, 'ok', actual.note)
                self.assertIn('dpkg', actual.names)
                rows, roots, report = audit.scan(home, ['config'], set(), {}, True)
                self.assertEqual(report['installed_sources']['dpkg'], 'ok')
                self.assertEqual(report['installed_sources']['pacman'], 'absent')
                selected = next(row for row in rows if row.path == source)
                with self.assertRaisesRegex(ValueError, 'pacman inventory'):
                    audit.commit_quarantine([selected], roots, home, allow_uncertain=True, emit=lambda _: None)
            self.assertEqual((source / 'settings').read_bytes(), b'preserve\x00\xff')
            self.assertFalse(audit.quarantine_dir(home, roots).exists())
