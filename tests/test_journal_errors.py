"""Real journal writes fail closed on disk errors and symlinked ancestors."""
import errno
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_quarantine_lifecycle as lifecycle


class JournalErrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.roots = audit.xdg_roots(self.home)
        self.source = self.home / '.config' / 'fixture-orphan'
        self.source.mkdir(parents=True)
        (self.source / 'settings').write_bytes(b'preserve exactly\x00\xff')
        info = self.source.stat()
        self.item = audit.Item('config', self.source, state='CANDIDATE', removable=True,
            identity=(info.st_dev, info.st_ino, stat.S_IFDIR))

    def move(self):
        with patch.object(audit, 'read_active_names', return_value=(
                {'unrelated'}, set(), set(), set(), set(), set(), set(), {'unrelated'})):
            return audit.commit_quarantine([self.item], self.roots, self.home, emit=lambda _: None)

    def test_manifest_fsync_error_preserves_errno_and_old_journal(self):
        manifest = self.home / 'manifest.json'
        audit._write_manifest_atomic(manifest, {'old': True})
        original = manifest.read_bytes()
        for number in (errno.ENOSPC, errno.EACCES, errno.EIO):
            with self.subTest(errno=number), patch.object(lifecycle.os, 'fsync',
                    side_effect=OSError(number, os.strerror(number))):
                with self.assertRaises(OSError) as caught:
                    audit._write_manifest_atomic(manifest, {'new': True})
            self.assertEqual(caught.exception.errno, number)
            self.assertEqual(manifest.read_bytes(), original)
            self.assertFalse(list(self.home.glob('.manifest-*.tmp')))

    def test_manifest_ancestor_symlink_never_writes_target(self):
        real = self.home / 'real'
        real.mkdir()
        link = self.home / 'link'
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            audit._write_manifest_atomic(link / 'manifest.json', {'unsafe': True})
        self.assertEqual(list(real.iterdir()), [])

    def test_full_disk_before_move_keeps_source_bytes(self):
        with patch.object(lifecycle.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'disk full')):
            with self.assertRaises(OSError) as caught:
                self.move()
        self.assertEqual(caught.exception.errno, errno.ENOSPC)
        self.assertEqual((self.source / 'settings').read_bytes(), b'preserve exactly\x00\xff')

    def test_full_disk_before_restore_keeps_quarantined_bytes(self):
        result = self.move()
        manifest = Path(result['manifest'])
        before = manifest.read_bytes()
        destination = Path(json.loads(before)['items'][0]['destination'])
        with patch.object(lifecycle.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'disk full')):
            outcome = audit.restore_quarantine_run(self.home, self.roots, result['run_id'], emit=lambda _: None)
        self.assertEqual(outcome['restored'], 0)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual((destination / 'settings').read_bytes(), b'preserve exactly\x00\xff')
        self.assertEqual(audit.restore_quarantine_run(self.home, self.roots, result['run_id'],
            emit=lambda _: None)['restored'], 1)

    def test_full_disk_before_purge_intent_keeps_quarantined_bytes(self):
        result = self.move()
        manifest = Path(result['manifest'])
        before = manifest.read_bytes()
        destination = Path(json.loads(before)['items'][0]['destination'])
        with patch.object(lifecycle.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'disk full')):
            with self.assertRaises(OSError) as caught:
                audit.purge_quarantine_run(self.home, self.roots, result['run_id'], dry_run=False)
        self.assertEqual(caught.exception.errno, errno.ENOSPC)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual((destination / 'settings').read_bytes(), b'preserve exactly\x00\xff')
        self.assertEqual(audit.purge_quarantine_run(self.home, self.roots, result['run_id'],
            dry_run=False, emit=lambda _: None)['objects'], 1)

    def test_directory_sync_failure_after_move_keeps_accurate_count_and_restore(self):
        sync = audit._sync_directory
        def fail_source_sync(path):
            if path == self.source.parent:
                raise OSError(errno.ENOSPC, 'disk full')
            sync(path)
        with patch.object(audit, '_sync_directory', side_effect=fail_source_sync):
            result = self.move()
        self.assertEqual(result['moved'], [str(self.source)])
        self.assertFalse(self.source.exists())
        self.assertEqual(audit.restore_quarantine_run(self.home, self.roots, result['run_id'],
            emit=lambda _: None)['restored'], 1)
        self.assertEqual((self.source / 'settings').read_bytes(), b'preserve exactly\x00\xff')

    def test_sync_failure_after_restore_can_reconcile_without_double_count(self):
        result = self.move()
        with patch.object(audit, '_sync_directory', side_effect=OSError(errno.ENOSPC, 'disk full')):
            outcome = audit.restore_quarantine_run(self.home, self.roots, result['run_id'], emit=lambda _: None)
        self.assertEqual((outcome['restored'], outcome['skipped']), (1, 0))
        self.assertEqual((self.source / 'settings').read_bytes(), b'preserve exactly\x00\xff')
        outcome = audit.restore_quarantine_run(self.home, self.roots, result['run_id'], emit=lambda _: None)
        self.assertEqual(outcome['restored'], 1)
        self.assertEqual(audit.quarantine_runs(self.home, self.roots)[0]['status'], 'RESTORED')

    def test_reconciliation_never_accepts_new_original_path_collision(self):
        result = self.move()
        manifest = Path(result['manifest'])
        payload = json.loads(manifest.read_text())
        destination = Path(payload['items'][0]['destination'])
        destination.rename(self.home / 'original-preserved')
        self.source.mkdir()
        (self.source / 'unrelated').write_bytes(b'collision survives')
        before = manifest.read_bytes()
        outcome = audit.restore_quarantine_run(self.home, self.roots, result['run_id'], emit=lambda _: None)
        self.assertEqual(outcome['restored'], 0)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual((self.source / 'unrelated').read_bytes(), b'collision survives')
