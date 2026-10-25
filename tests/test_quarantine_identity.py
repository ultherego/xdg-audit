"""Verify quarantine restores the original object, never a substituted one."""
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import xdg_audit as audit


def inventory():
    packages = {'unrelated-package'}
    return packages, set(), set(), set(), set(), set(), set(), {'unrelatedpackage'}


class RestoreIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / '.config'
        self.config.mkdir()
        self.roots = audit.xdg_roots(self.home)

    def move(self):
        source = self.config / 'removed-app'
        source.mkdir()
        (source / 'config.ini').write_text('preserve=original')
        st = source.lstat()
        row = audit.Item('config', source, state='CANDIDATE', removable=True,
                         identity=(st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode)))
        with patch.object(audit, 'read_active_names', return_value=inventory()):
            result = audit.commit_quarantine([row], self.roots, self.home, emit=lambda *_: None)
        self.assertEqual(len(result['moved']), 1)
        manifest = Path(result['manifest'])
        payload = json.loads(manifest.read_text())
        self.assertEqual(payload['format'], 'intent-journal-v3')
        self.assertEqual(payload['items'][0]['identity'], list(row.identity))
        destination = Path(payload['items'][0]['destination'])
        return source, destination, manifest, payload, result['run_id']

    def test_restore_intact_object(self):
        source, dest, _, _, run_id = self.move()
        result = audit.restore_quarantine_run(self.home, self.roots, run_id, emit=lambda *_: None)
        self.assertEqual(result['restored'], 1)
        self.assertFalse(dest.exists())
        self.assertEqual((source / 'config.ini').read_text(), 'preserve=original')

    def test_replacement_inside_quarantine_never_restored(self):
        source, dest, _, _, run_id = self.move()
        dest.rename(dest.with_name('original-kept-aside'))
        dest.mkdir()
        (dest / 'other.ini').write_text('wrong directory')
        result = audit.restore_quarantine_run(self.home, self.roots, run_id, emit=lambda *_: None)
        self.assertEqual(result['restored'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())

    def test_corrupted_identity_fails_closed(self):
        source, dest, manifest, payload, run_id = self.move()
        payload['items'][0]['identity'] = ['bad', 0, stat.S_IFDIR]
        manifest.write_text(json.dumps(payload))
        result = audit.restore_quarantine_run(self.home, self.roots, run_id, emit=lambda *_: None)
        self.assertEqual(result['restored'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())

    def test_missing_v3_identity_fails_closed(self):
        source, dest, manifest, payload, run_id = self.move()
        del payload['items'][0]['identity']
        manifest.write_text(json.dumps(payload))
        result = audit.restore_quarantine_run(self.home, self.roots, run_id, emit=lambda *_: None)
        self.assertEqual(result['restored'], 0)
        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())

    def test_v2_journal_still_restores(self):
        source, dest, manifest, payload, run_id = self.move()
        payload['format'] = 'intent-journal-v2'
        del payload['items'][0]['identity']
        manifest.write_text(json.dumps(payload))
        result = audit.restore_quarantine_run(self.home, self.roots, run_id, emit=lambda *_: None)
        self.assertEqual(result['restored'], 1)
        self.assertFalse(dest.exists())
        self.assertTrue(source.exists())

    def test_crash_state_moving_is_reconciled_and_restorable(self):
        source, dest, manifest, payload, run_id = self.move()
        payload['items'][0]['move_status'] = 'moving'
        manifest.write_text(json.dumps(payload))
        runs = audit.quarantine_runs(self.home, self.roots)
        self.assertEqual(runs[0]['items'][0]['move_status'], 'moved')
        result = audit.restore_quarantine_run(self.home, self.roots, run_id, emit=lambda *_: None)
        self.assertEqual(result['restored'], 1)
        self.assertTrue(source.exists())
        self.assertFalse(dest.exists())
