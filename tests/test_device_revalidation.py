"""Explicit device revalidation preserves all other identity and content checks."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_filesystem as filesystem
import xdg_quarantine_lifecycle as lifecycle

BINDING = {"kind": "btrfs", "fsid": "11111111-2222-3333-4444-555555555555",
           "subvolume_id": 256, "subvolume_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}


class DeviceRevalidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='xdg-device-revalidation-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.roots = audit.xdg_roots(self.home)
        self.run_id = '20261027-100000-123456'
        self.run = audit.quarantine_dir(self.home, self.roots) / self.run_id
        self.entry = self.run / 'config' / 'fixture'
        self.entry.mkdir(parents=True)
        (self.entry / 'settings').write_bytes(b'exact original bytes\x00\xff')
        self.current = self.entry.stat().st_dev
        self.old = self.current + 1
        identity = [self.old, self.entry.stat().st_ino, stat.S_IFDIR]
        inventory = lifecycle.capture_inventory(self.entry)
        for node in inventory:
            node['identity'][0] = self.old
        self.row = {'scope': 'config', 'source': str(self.roots['config'] / 'fixture'),
                    'destination': str(self.entry), 'move_status': 'moved',
                    'identity': identity, 'tree_inventory': inventory}
        self.payload = {'format': 'intent-journal-v3', 'created': self.run_id, 'items': [self.row]}
        self.manifest = self.run / 'manifest.json'
        self.write()
        self.probe = patch.object(filesystem, 'btrfs_identity', return_value=copy.deepcopy(BINDING))
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def write(self):
        self.manifest.write_text(json.dumps(self.payload))

    def preview(self):
        return lifecycle.device_revalidation_summary(lifecycle.device_revalidation_plan(
            self.home, self.roots, self.run_id, lambda _: False))

    def execute(self, token=None):
        return lifecycle.revalidate_device(self.home, self.roots, self.run_id, lambda _: False,
                                          approval_token=token or self.preview()['approval_token'])

    def test_read_only_preview_does_not_authorize_purge_or_rewrite_journal(self):
        before = self.manifest.read_bytes()
        result = self.preview()
        self.assertEqual((result['old_device'], result['new_device']), (self.old, self.current))
        self.assertFalse(result['historical_binding_verified'])
        self.assertFalse(result['purge_authorized'])
        self.assertEqual(self.manifest.read_bytes(), before)
        with self.assertRaises(lifecycle.QuarantineIdentityMismatch):
            audit.purge_quarantine_run(self.home, self.roots, self.run_id, dry_run=False)
        self.assertTrue((self.entry / 'settings').exists())

    def test_explicit_revalidation_only_changes_device_binding_then_separate_purge_works(self):
        expected = copy.deepcopy(self.row['tree_inventory'])
        result = self.execute()
        saved = json.loads(self.manifest.read_text())
        for node in expected:
            node['identity'][0] = self.current
        self.assertEqual(saved['items'][0]['tree_inventory'], expected)
        self.assertEqual(saved['items'][0]['identity'], [self.current, *self.row['identity'][1:]])
        self.assertEqual(saved['items'][0]['move_status'], 'moved')
        self.assertEqual(saved['items'][0]['filesystem_identity'], BINDING)
        self.assertFalse(saved['device_revalidations'][0]['historical_binding_verified'])
        self.assertFalse(result['purge_authorized'])
        self.assertEqual((self.entry / 'settings').read_bytes(), b'exact original bytes\x00\xff')
        self.assertEqual(audit.purge_quarantine_run(self.home, self.roots, self.run_id)['objects'], 1)
        audit.purge_quarantine_run(self.home, self.roots, self.run_id, dry_run=False, emit=lambda _: None)
        self.assertFalse(self.entry.exists())
        self.assertEqual(json.loads(self.manifest.read_text())['device_revalidations'], saved['device_revalidations'])

    def test_revalidated_original_is_restore_capable_with_persistent_binding(self):
        self.execute()
        self.roots['config'].mkdir(parents=True)
        result = audit.restore_quarantine_run(self.home, self.roots, self.run_id, emit=lambda _: None)
        self.assertEqual(result['restored'], 1)
        self.assertEqual((self.roots['config'] / 'fixture/settings').read_bytes(), b'exact original bytes\x00\xff')

    def test_recorded_persistent_identity_must_match_and_snapshots_are_refused(self):
        self.row['filesystem_identity'] = copy.deepcopy(BINDING)
        self.write()
        self.assertTrue(self.preview()['historical_binding_verified'])
        for key, value in [('fsid', '99999999-2222-3333-4444-555555555555'),
                           ('subvolume_id', 257), ('subvolume_uuid', 'ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee')]:
            self.row['filesystem_identity'] = {**BINDING, key: value}
            self.write()
            before = self.manifest.read_bytes()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Persistent filesystem'):
                self.preview()
            self.assertEqual(self.manifest.read_bytes(), before)

    def test_changed_names_hashes_inodes_and_unsealed_inventory_remain_blocked(self):
        original = copy.deepcopy(self.row)
        variants = [lambda: self.row['identity'].__setitem__(1, self.row['identity'][1] + 1),
                    lambda: self.row.__setitem__('tree_inventory', None),
                    lambda: self.row['tree_inventory'][1].__setitem__('sha256', '0' * 64),
                    lambda: self.row['tree_inventory'][1]['identity'].__setitem__(0, self.old + 2)]
        for change in variants:
            self.row.clear()
            self.row.update(copy.deepcopy(original))
            change()
            self.write()
            before = self.manifest.read_bytes()
            with self.subTest(row=self.row), self.assertRaises(ValueError):
                self.preview()
            self.assertEqual(self.manifest.read_bytes(), before)
        self.row.clear()
        self.row.update(original)
        self.write()
        (self.entry / 'new-file').write_text('must survive')
        with self.assertRaises(ValueError):
            self.preview()
        self.assertTrue((self.entry / 'new-file').exists())

    def test_incomplete_and_destructive_states_cannot_be_revalidated(self):
        for state in ['planned', 'moving', 'restoring', 'purging']:
            self.row['move_status'] = state
            self.write()
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, 'completed MOVE'):
                self.preview()

    def test_missing_hardlinked_and_special_files_are_refused_without_journal_changes(self):
        before = self.manifest.read_bytes()
        file = self.entry / 'settings'
        os.link(file, self.home / 'hardlink')
        with self.assertRaises(ValueError):
            self.preview()
        (self.home / 'hardlink').unlink()
        os.mkfifo(self.entry / 'special')
        with self.assertRaises(ValueError):
            self.preview()
        (self.entry / 'special').unlink()
        file.unlink()
        with self.assertRaises(ValueError):
            self.preview()
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_one_changed_entry_blocks_the_whole_run_before_any_rebinding(self):
        other = self.entry.with_name('second')
        other.mkdir()
        (other / 'settings').write_bytes(b'original second entry')
        inventory = lifecycle.capture_inventory(other)
        for node in inventory:
            node['identity'][0] = self.old
        self.payload['items'].append({**self.row, 'source': str(self.roots['config'] / 'second'),
            'destination': str(other), 'identity': [self.old, other.stat().st_ino, stat.S_IFDIR],
            'tree_inventory': inventory})
        self.write()
        before = self.manifest.read_bytes()
        (other / 'settings').write_bytes(b'changed second entry')
        with self.assertRaises(ValueError):
            self.preview()
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual((self.entry / 'settings').read_bytes(), b'exact original bytes\x00\xff')

    def test_diagnosis_explains_device_only_change_without_permission_repair(self):
        report = audit.diagnose_quarantine_access(self.home, self.roots, self.run_id)
        self.assertTrue(report['device_revalidation']['eligible'])
        self.assertEqual(report['issues'][0]['changed_fields'], ['device'])
        self.assertFalse(report['issues'][0]['repairable'])
        self.assertEqual(report['issues'][0]['filesystem']['filesystem_identity'], BINDING)
        error = lifecycle.QuarantineIdentityMismatch(self.run_id, self.entry,
            self.row['identity'], [self.current, *self.row['identity'][1:]])
        self.assertTrue(audit.quarantine_access_recoverable_error(error))
        from xdg_quarantine_messages import device_revalidation_details
        text = device_revalidation_details(self.preview(), 'en')
        self.assertIn('LEGACY JOURNAL', text)
        self.assertIn('CURRENT filesystem', text)
        self.assertIn('separate confirmation', text)

    def test_unsupported_filesystem_and_nested_mounts_do_not_allow_revalidation(self):
        with patch.object(filesystem, 'btrfs_identity', return_value=None), self.assertRaises(ValueError):
            self.preview()
        with self.assertRaisesRegex(ValueError, 'Nested mounts'):
            lifecycle.device_revalidation_plan(self.home, self.roots, self.run_id, lambda _: True)

    def test_confirmation_is_bound_to_exact_manifest_and_current_filesystem(self):
        token = self.preview()['approval_token']
        self.payload['review_note'] = 'changed while dialog was open'
        self.write()
        before = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed after confirmation'):
            self.execute(token)
        self.assertEqual(self.manifest.read_bytes(), before)
        token = self.preview()['approval_token']
        with patch.object(filesystem, 'btrfs_identity', return_value={**BINDING, 'subvolume_id': 300}), \
                self.assertRaisesRegex(ValueError, 'changed after confirmation'):
            self.execute(token)

    def test_late_content_or_journal_change_never_commits_rebinding(self):
        report = lifecycle.device_revalidation_plan(self.home, self.roots, self.run_id, lambda _: False)
        token = lifecycle.device_revalidation_summary(report)['approval_token']
        before = self.manifest.read_bytes()
        (self.entry / 'settings').write_text('changed after preflight')
        with patch.object(lifecycle, 'device_revalidation_plan', return_value=report), \
                self.assertRaisesRegex(ValueError, 'Contents changed'):
            self.execute(token)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_persistent_binding_is_checked_by_normal_purge_and_restore(self):
        self.execute()
        with patch.object(filesystem, 'btrfs_identity', return_value={**BINDING, 'subvolume_id': 300}):
            with self.assertRaisesRegex(ValueError, 'Persistent filesystem'):
                audit.purge_quarantine_run(self.home, self.roots, self.run_id, dry_run=False)
            result = audit.restore_quarantine_run(self.home, self.roots, self.run_id, emit=lambda _: None)
            self.assertEqual(result['restored'], 0)
        self.assertTrue(self.entry.exists())

    def test_cli_preview_and_cancellation_do_not_execute_revalidation(self):
        before = self.manifest.read_bytes()
        with patch.object(audit, 'check_no_root'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.main(['--home', str(self.home), '--revalidate-device', self.run_id, '--dry-run']), 0)
        with patch.object(audit, 'check_no_root'), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', return_value='cancel'), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(SystemExit, 'cancelled'):
            audit.main(['--home', str(self.home), '--revalidate-device', self.run_id])
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_cli_revalidate_requires_separate_purge(self):
        with patch.object(audit, 'check_no_root'), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', return_value='REVALIDATE'), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(audit.main(['--home', str(self.home), '--revalidate-device', self.run_id]), 0)
        self.assertIn('LEGACY JOURNAL', output.getvalue())
        self.assertTrue(self.entry.exists())
        self.assertEqual(json.loads(self.manifest.read_text())['items'][0]['move_status'], 'moved')

    def test_enabled_retention_cannot_delete_a_revalidated_run(self):
        from xdg_retention import save
        self.execute()
        before = self.manifest.read_bytes()
        save(self.home, self.roots, {'days': 30, 'automatic': True})
        # Age selection has separate tests; make this run eligible to isolate
        # the timer's consent boundary after successful revalidation.
        with patch.object(audit, 'check_no_root'), \
                patch.object(lifecycle, 'expired_run_ids', return_value=[self.run_id]), \
                patch('builtins.input', side_effect=AssertionError('Timer must not prompt')), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            result = audit.main(['--home', str(self.home), '--automatic-purge'])
        self.assertTrue((self.entry / 'settings').exists())
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(result, 1)
        self.assertIn('explicit PURGE', errors.getvalue())

    def test_revalidated_run_still_requires_exact_manual_purge_confirmation(self):
        self.execute()
        before = self.manifest.read_bytes()
        with patch.object(audit, 'check_no_root'), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', return_value='REVALIDATE'), \
                contextlib.redirect_stdout(io.StringIO()):
            result = audit.main(['--home', str(self.home), '--purge', self.run_id])
        self.assertEqual(result, 0)
        self.assertTrue(self.entry.exists())
        self.assertEqual(self.manifest.read_bytes(), before)
        with patch.object(audit, 'check_no_root'), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', return_value='PURGE'), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.main(['--home', str(self.home), '--purge', self.run_id]), 0)
        self.assertFalse(self.entry.exists())

    def test_engine_blocks_automatic_revalidated_purge_in_preview_and_execution(self):
        self.execute()
        before = self.manifest.read_bytes()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), self.assertRaisesRegex(ValueError, 'explicit PURGE'):
                lifecycle.purge_run(self.home, self.roots, self.run_id, lambda _: False,
                                    dry_run=dry_run, automatic=True)
            self.assertEqual(self.manifest.read_bytes(), before)
            self.assertEqual((self.entry / 'settings').read_bytes(), b'exact original bytes\x00\xff')
