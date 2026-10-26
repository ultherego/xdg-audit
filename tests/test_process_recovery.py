"""SIGKILL at real journal checkpoints, using disposable data only.

Unlike exception injection, the worker cannot execute Python finally blocks.
Only the installed-package inventory is synthetic; filesystem operations,
durable journal writes, renameat2, hashes and restart recovery are real.
"""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit


INVENTORY = ({'unrelated'}, set(), set(), set(), set(), set(), set(), {'unrelated'})
WORKER = r'''
import os
from pathlib import Path
import signal
import stat
import sys
from unittest.mock import patch
import xdg_audit as audit
import xdg_quarantine_lifecycle as lifecycle

home, checkpoint, run_id = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
roots = audit.xdg_roots(home)

def kill():
    print('CHECKPOINT ' + checkpoint, flush=True)
    os.kill(os.getpid(), signal.SIGKILL)

rename = audit._safe_rename_noreplace
def interrupted_rename(source, destination, identity=None):
    if checkpoint.endswith('before-rename'):
        kill()
    rename(source, destination, identity)
    audit._sync_directory(source.parent)
    audit._sync_directory(destination.parent)
    kill()

delete = lifecycle._delete_entry
def interrupted_delete(*args):
    if checkpoint == 'purge-before-delete':
        kill()
    delete(*args)
    kill()

unlink = os.unlink
def interrupted_unlink(name, *args, **kwargs):
    unlink(name, *args, **kwargs)
    if name == 'a-first':
        os.fsync(kwargs['dir_fd'])
        kill()

def interrupted_journal_replace(*args, **kwargs):
    kill()  # temp file is already flushed and fsynced; old manifest is intact

if checkpoint.startswith('move-'):
    source = home / '.config' / 'fixture-orphan'
    info = source.stat()
    row = audit.Item('config', source, state='CANDIDATE', removable=True,
        identity=(info.st_dev, info.st_ino, stat.S_IFDIR))
    inventory = ({'unrelated'}, set(), set(), set(), set(), set(), set(), {'unrelated'})
    with patch.object(audit, 'read_active_names', return_value=inventory), \
         patch.object(audit, '_safe_rename_noreplace', side_effect=interrupted_rename):
        audit.commit_quarantine([row], roots, home, emit=lambda _: None)
elif checkpoint.startswith('restore-'):
    with patch.object(audit, '_safe_rename_noreplace', side_effect=interrupted_rename):
        audit.restore_quarantine_run(home, roots, run_id, emit=lambda _: None)
elif checkpoint == 'purge-after-first-unlink':
    with patch.object(lifecycle.os, 'unlink', side_effect=interrupted_unlink):
        audit.purge_quarantine_run(home, roots, run_id, dry_run=False, emit=lambda _: None)
elif checkpoint == 'purge-before-journal-replace':
    with patch.object(lifecycle.os, 'replace', side_effect=interrupted_journal_replace):
        audit.purge_quarantine_run(home, roots, run_id, dry_run=False, emit=lambda _: None)
else:
    with patch.object(lifecycle, '_delete_entry', side_effect=interrupted_delete):
        audit.purge_quarantine_run(home, roots, run_id, dry_run=False, emit=lambda _: None)
raise AssertionError('worker did not reach crash checkpoint')
'''


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux renameat2 and SIGKILL required')
class LiveProcessRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xdg-audit-crash-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.roots = audit.xdg_roots(self.home)
        self.source = self.home / '.config' / 'fixture-orphan'
        self.source.mkdir(parents=True)
        self.expected = {'a-first': b'first\x00\xff', 'z-last': b'last\n'}
        for name, content in self.expected.items():
            (self.source / name).write_bytes(content)
        self.sentinel = self.home / 'unrelated-sentinel'
        self.sentinel.write_bytes(b'never touch')

    def move(self):
        info = self.source.stat()
        row = audit.Item('config', self.source, state='CANDIDATE', removable=True,
            identity=(info.st_dev, info.st_ino, stat.S_IFDIR))
        with patch.object(audit, 'read_active_names', return_value=INVENTORY):
            return audit.commit_quarantine([row], self.roots, self.home, emit=lambda _: None)

    def crash(self, checkpoint, run_id=''):
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE='1')
        # Do not inherit XDG overrides pointing at an actual user's directories.
        env.update({name: str(self.roots[key]) for name, key in (
            ('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
            ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache'))})
        proc = subprocess.run([sys.executable, '-c', WORKER, str(self.home), checkpoint, run_id],
            cwd=Path(__file__).resolve().parents[1], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr)
        self.assertIn('CHECKPOINT ' + checkpoint, proc.stdout)
        self.assertEqual(self.sentinel.read_bytes(), b'never touch')

    def assert_original(self):
        self.assertEqual({p.name: p.read_bytes() for p in self.source.iterdir()}, self.expected)
        self.assertEqual(self.sentinel.read_bytes(), b'never touch')

    def test_sigkill_move_before_rename_preserves_original(self):
        self.crash('move-before-rename')
        self.assert_original()
        run = audit.quarantine_runs(self.home, self.roots)[0]
        manifest = audit.quarantine_dir(self.home, self.roots) / run['run_id'] / 'manifest.json'
        self.assertEqual(json.loads(manifest.read_text())['items'][0]['move_status'], 'moving')
        audit.restore_quarantine_run(self.home, self.roots, run['run_id'], emit=lambda _: None)
        self.assert_original()

    def test_sigkill_move_after_rename_restores_exact_bytes(self):
        self.crash('move-after-rename')
        self.assertFalse(self.source.exists())
        run = audit.quarantine_runs(self.home, self.roots)[0]
        restored = audit.restore_quarantine_run(self.home, self.roots, run['run_id'], emit=lambda _: None)
        self.assertEqual(restored['restored'], 1)
        self.assert_original()

    def test_sigkill_restore_before_rename_can_resume(self):
        result = self.move()
        self.crash('restore-before-rename', result['run_id'])
        self.assertFalse(self.source.exists())
        restored = audit.restore_quarantine_run(self.home, self.roots, result['run_id'], emit=lambda _: None)
        self.assertEqual(restored['restored'], 1)
        self.assert_original()

    def test_sigkill_restore_after_rename_preserves_returned_data(self):
        result = self.move()
        self.crash('restore-after-rename', result['run_id'])
        self.assert_original()
        audit.restore_quarantine_run(self.home, self.roots, result['run_id'], emit=lambda _: None)
        self.assert_original()
        self.assertEqual(audit.quarantine_runs(self.home, self.roots)[0]['status'], 'RESTORED')

    def resume_purge(self, checkpoint):
        result = self.move()
        self.crash(checkpoint, result['run_id'])
        manifest = Path(result['manifest'])
        self.assertEqual(json.loads(manifest.read_text())['items'][0]['move_status'], 'purging')
        audit.purge_quarantine_run(self.home, self.roots, result['run_id'], dry_run=False, emit=lambda _: None)
        self.assertFalse(self.source.exists())
        payload = json.loads(manifest.read_text())
        self.assertEqual(payload['items'][0]['move_status'], 'purged')
        self.assertFalse(Path(payload['items'][0]['destination']).exists())
        self.assertEqual(self.sentinel.read_bytes(), b'never touch')
        self.assertEqual(audit.purge_quarantine_run(self.home, self.roots, result['run_id'],
            dry_run=False, emit=lambda _: None)['objects'], 0)

    def test_sigkill_purge_before_delete_can_resume(self):
        self.resume_purge('purge-before-delete')

    def test_sigkill_purge_after_one_unlink_can_resume(self):
        self.resume_purge('purge-after-first-unlink')

    def test_sigkill_purge_after_delete_before_journal_can_resume(self):
        self.resume_purge('purge-after-delete')

    def test_sigkill_during_intent_write_recovers_only_temporary_journal(self):
        from xdg_quarantine_lifecycle import recover_manifest_temps
        result = self.move()
        self.crash('purge-before-journal-replace', result['run_id'])
        manifest = Path(result['manifest'])
        payload = json.loads(manifest.read_text())
        self.assertEqual(payload['items'][0]['move_status'], 'moved')
        destination = Path(payload['items'][0]['destination'])
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, self.expected)
        with self.assertRaisesRegex(ValueError, 'Untracked'):
            audit.purge_quarantine_run(self.home, self.roots, result['run_id'], dry_run=False)
        preview = recover_manifest_temps(self.home, self.roots, result['run_id'])
        self.assertEqual(preview['temporary_files'], 1)
        recover_manifest_temps(self.home, self.roots, result['run_id'], dry_run=False)
        self.assertEqual(json.loads(manifest.read_text()), payload)
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, self.expected)
        audit.purge_quarantine_run(self.home, self.roots, result['run_id'], dry_run=False, emit=lambda _: None)
        self.assertFalse(destination.exists())
        self.assertEqual(self.sentinel.read_bytes(), b'never touch')
