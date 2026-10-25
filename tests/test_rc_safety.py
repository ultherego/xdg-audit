"""Conservative classification and quarantine regression tests for the RC."""
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xdg_audit as audit


def inventory(packages):
    packages = set(packages)
    return (packages, set(), set(), set(), set(), set(), set(), {audit.normalize(p) for p in packages})


class CandidateSafety(unittest.TestCase):
    def test_protect_saves_developer_profiles_and_themes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for base, name in ((home / '.local/share', 'Larian Studios'),
                               (home / '.local/share', 'Euro Truck Simulator 2'),
                               (home / '.local/share', 'umu'),
                               (home, '.claude'), (home, '.codex'),
                               (home, '.vscode'), (home, '.icons'), (home, '.themes')):
                (base / name).mkdir(parents=True, exist_ok=True)
            with patch.object(audit, 'read_active_names', return_value=inventory({'unrelated-package'})), \
                 patch.object(audit, 'parse_removals', return_value={'umu': ['[historical]']}), \
                 patch.object(audit, 'references', return_value={}):
                entries, *_ = audit.scan(home, ['data', 'dotfiles'], set(), {}, True)
            for entry in entries:
                self.assertEqual(entry.state, 'PROTECTED', str(entry.path))
                self.assertFalse(entry.removable, str(entry.path))

    def test_kdeconnect_installed_package_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            p = home / '.local/state' / 'kdeconnect.smsstaterc'
            p.parent.mkdir(parents=True)
            p.touch()
            with patch.object(audit, 'read_active_names', return_value=inventory({'kdeconnect'})), \
                 patch.object(audit, 'parse_removals', return_value={}):
                entries, *_ = audit.scan(home, ['state'], set(), {}, True)
            self.assertEqual(entries[0].state, 'ACTIVE')
            self.assertEqual(entries[0].json()['evidence'][0]['source'], 'pacman')

    def test_auxiliary_package_is_not_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            p = home / '.cache' / 'opera'
            p.mkdir(parents=True)
            with patch.object(audit, 'read_active_names', return_value=inventory({'opera-themes'})), \
                 patch.object(audit, 'parse_removals', return_value={}):
                entries, *_ = audit.scan(home, ['cache'], set(), {}, True)
            self.assertEqual(entries[0].state, 'REVIEW')
            self.assertIn('pacman_helper', [e['source'] for e in entries[0].json()['evidence']])

    def test_ancestor_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = root / 'real'
            (actual / 'nested').mkdir(parents=True)
            (actual / 'nested' / 'payload').write_text('keep')
            (root / 'link').symlink_to(actual, target_is_directory=True)
            with self.assertRaises(OSError):
                audit._safe_rename_noreplace(root / 'link' / 'nested' / 'payload', root / 'moved')
            self.assertEqual((actual / 'nested' / 'payload').read_text(), 'keep')

    def test_restore_rejects_modified_manifest_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            src = home / '.config' / 'orphan'
            src.mkdir(parents=True)
            (src / 'important').write_text('keep')
            st = src.lstat()
            entry = audit.Item('config', src, state='CANDIDATE', removable=True,
                               identity=(st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode)))
            roots = audit.xdg_roots(home)
            with patch.object(audit, 'read_active_names', return_value=inventory({'independent'})):
                result = audit.commit_quarantine([entry], roots, home, emit=lambda _: None)
            self.assertEqual(len(result['moved']), 1)
            manifest = Path(result['manifest'])
            payload = json.loads(manifest.read_text())
            payload['items'][0]['destination'] = str(home / 'wrong' / 'orphan')
            manifest.write_text(json.dumps(payload))
            restored = audit.restore_quarantine_run(home, roots, result['run_id'], emit=lambda _: None)
            self.assertEqual(restored['restored'], 0)
            self.assertFalse(src.exists())


if __name__ == '__main__':
    unittest.main()
