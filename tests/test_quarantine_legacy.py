"""Known v2 recovery binds current data without inventing historical evidence."""
import copy
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_quarantine_legacy as legacy
from xdg_quarantine_history import cleanup_history, completed_history_candidates, history_candidates
from xdg_quarantine_lifecycle import adopt_legacy_run, LegacyQuarantineJournal, purge_run
from xdg_quarantine_messages import quarantine_error_details


class LegacyQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.roots = audit.xdg_roots(self.home)
        for root in self.roots.values():
            root.mkdir(parents=True, exist_ok=True)
        self.run_id = '20000101-010101-123456'
        self.run = audit.quarantine_dir(self.home, self.roots) / self.run_id
        (self.run / 'config/legacy-app').mkdir(parents=True)
        (self.run / 'state').mkdir()
        self.destination = self.run / 'config/legacy-app'
        self.file = self.destination / 'payload'
        self.file.write_bytes(b'original fixture\x00\xff')
        self.original = self.roots['cache'] / 'never-moved'
        self.original.write_bytes(b'original path must survive')
        self.outside = self.home / 'outside-sentinel'
        self.outside.write_bytes(b'outside untouched')
        self.payload = {'format': 'intent-journal-v2', 'created': self.run_id, 'version': '1.7.0-dev',
                        'items': [self.row('config', 'legacy-app', 'moved'),
                                  self.row('cache', 'never-moved', 'planned'),
                                  self.row('state', 'missing-intent', 'moving')]}
        self.manifest = self.run / 'manifest.json'
        self.write()
        self.mounts = lambda _: False

    def row(self, scope, name, status):
        return {'source': str(self.roots[scope] / name),
                'destination': str(self.run / scope / name),
                'scope': scope, 'move_status': status, 'state': 'REVIEW', 'reasons': []}

    def write(self):
        self.manifest.write_text(json.dumps(self.payload))

    def token(self):
        return legacy.adoption_token(legacy.inspect_legacy_run(self.home, self.roots, self.run_id, self.mounts))

    def adopt(self, token=None):
        return adopt_legacy_run(self.home, self.roots, self.run_id, self.mounts,
                                approval_token=token or self.token())

    def assert_sentinels(self):
        self.assertEqual(self.original.read_bytes(), b'original path must survive')
        self.assertEqual(self.outside.read_bytes(), b'outside untouched')

    def test_partial_v2_adoption_then_separate_purge_and_history(self):
        before = self.manifest.read_bytes()
        self.assertEqual(audit.quarantine_runs(self.home, self.roots)[0]['status'], 'INCOMPLETE')
        with self.assertRaises(LegacyQuarantineJournal):
            purge_run(self.home, self.roots, self.run_id, self.mounts, dry_run=False)
        preview = audit.preview_quarantine_adoption(self.home, self.roots, self.run_id)
        self.assertEqual(preview['present'], 1)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(self.adopt(preview['approval_token'])['adopted'], 1)
        current = json.loads(self.manifest.read_text())
        self.assertEqual(current['format'], 'intent-journal-v3')
        self.assertEqual(current['legacy_adoption']['original_journal'], self.payload)
        self.assertFalse(current['legacy_adoption']['historical_identity_verified'])
        self.assertFalse(current['legacy_adoption']['purge_authorized'])
        self.assertEqual(len(current['items']), 1)
        self.assertTrue(self.file.exists())
        self.assertEqual(completed_history_candidates(self.home, self.roots), [])
        purge_run(self.home, self.roots, self.run_id, self.mounts, dry_run=False, emit=lambda _: None)
        self.assertFalse(self.destination.exists())
        self.assertEqual(completed_history_candidates(self.home, self.roots), [self.run_id])
        cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(self.run.exists())
        self.assert_sentinels()

    def test_adopted_v2_can_be_restored_then_history_cleared(self):
        expected = self.file.read_bytes()
        self.adopt()
        result = audit.restore_quarantine_run(self.home, self.roots, self.run_id, emit=lambda _: None)
        self.assertEqual(result['restored'], 1)
        self.assertEqual((self.roots['config'] / 'legacy-app/payload').read_bytes(), expected)
        cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assert_sentinels()

    def test_empty_stale_v2_is_manual_history_only_without_hashing(self):
        shutil.rmtree(self.destination)
        before = self.manifest.read_bytes()
        with patch.object(legacy, 'capture_inventory', side_effect=AssertionError('must not hash')):
            self.assertEqual(audit.quarantine_runs(self.home, self.roots)[0]['status'], 'EMPTY')
            self.assertEqual(completed_history_candidates(self.home, self.roots), [self.run_id])
            self.assertEqual(history_candidates(self.home, self.roots, [self.run_id]), [])
            self.assertEqual(cleanup_history(self.home, self.roots, self.run_id)['status'], 'EMPTY')
            self.assertEqual(self.manifest.read_bytes(), before)
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertFalse(self.run.exists())
        self.assert_sentinels()

    def test_nonempty_v2_history_cleanup_preserves_everything(self):
        before = self.manifest.read_bytes()
        self.assertEqual(completed_history_candidates(self.home, self.roots), [])
        with self.assertRaises(ValueError):
            cleanup_history(self.home, self.roots, self.run_id, dry_run=False)
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertTrue(self.file.exists())

    def test_expired_data_selection_excludes_history_and_unfinished_runs(self):
        self.assertEqual(audit.expired_quarantine_runs(self.home, self.roots), [])
        self.adopt()
        self.assertEqual(audit.expired_quarantine_runs(self.home, self.roots), [self.run_id])
        purge_run(self.home, self.roots, self.run_id, self.mounts, dry_run=False, emit=lambda _: None)
        self.assertEqual(audit.expired_quarantine_runs(self.home, self.roots), [])

    def test_adoption_never_enables_automatic_purge(self):
        self.adopt()
        for dry_run in (True, False):
            with self.assertRaisesRegex(ValueError, 'automatic deletion is blocked'):
                purge_run(self.home, self.roots, self.run_id, self.mounts, automatic=True, dry_run=dry_run)
        self.assertTrue(self.file.exists())
        self.assert_sentinels()

    def test_preview_token_binds_journal_and_current_bytes(self):
        token = self.token()
        before = self.manifest.read_bytes()
        self.file.write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.adopt(token)
        self.assertEqual(self.manifest.read_bytes(), before)
        token = self.token()
        self.payload['version'] = 'changed version'
        self.write()
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.adopt(token)
        with self.assertRaisesRegex(ValueError, 'missing or stale'):
            adopt_legacy_run(self.home, self.roots, self.run_id, self.mounts)

    def test_late_content_change_refuses_atomic_conversion(self):
        original = legacy.inspect_legacy_run
        calls = []
        def inspect(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                self.file.write_bytes(b'late change')
            return original(*args, **kwargs)
        token = self.token()
        before = self.manifest.read_bytes()
        with patch.object(legacy, 'inspect_legacy_run', side_effect=inspect):
            with self.assertRaisesRegex(ValueError, 'changed while adopting'):
                self.adopt(token)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_failed_write_preserves_original_journal_and_payload_and_can_retry(self):
        before = self.manifest.read_bytes()
        with patch.object(legacy, '_write_manifest', side_effect=OSError(errno.ENOSPC, 'fixture disk full')):
            with self.assertRaises(OSError):
                self.adopt()
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertTrue(self.file.exists())
        self.adopt()
        self.assert_sentinels()

    def test_unknown_formats_mismatched_ids_and_downgrades_refused(self):
        original = copy.deepcopy(self.payload)
        for change in ('format', 'created', 'identity', 'tree_inventory', 'filesystem_identity'):
            with self.subTest(change=change):
                self.payload = copy.deepcopy(original)
                if change in ('format', 'created'):
                    self.payload[change] = 'unknown'
                else:
                    self.payload['items'][0][change] = []
                self.write()
                with self.assertRaises(ValueError):
                    self.token()
                self.assertTrue(self.file.exists())

    def test_manipulated_duplicate_paths_and_unknown_states_refused(self):
        original = copy.deepcopy(self.payload)
        for change in ('source', 'destination', 'scope', 'move_status', 'duplicate'):
            with self.subTest(change=change):
                self.payload = copy.deepcopy(original)
                if change == 'duplicate':
                    self.payload['items'].append(copy.deepcopy(self.payload['items'][0]))
                else:
                    self.payload['items'][0][change] = str(self.outside)
                self.write()
                with self.assertRaises(ValueError):
                    self.token()
                self.assert_sentinels()

    def test_untracked_scope_and_root_objects_block_adoption_and_empty_cleanup(self):
        for path in (self.run / 'unexpected', self.run / 'config/untracked'):
            path.write_bytes(b'untracked')
            with self.assertRaises(ValueError):
                self.token()
            self.assertEqual(completed_history_candidates(self.home, self.roots), [])
            self.assertTrue(path.exists())
            path.unlink()

    def test_hardlinks_special_files_and_top_symlinks_refused(self):
        link = self.destination / 'hardlink'
        os.link(self.file, link)
        with self.assertRaises(ValueError):
            self.token()
        link.unlink()
        os.mkfifo(link)
        with self.assertRaises(ValueError):
            self.token()
        link.unlink()
        shutil.rmtree(self.destination)
        self.destination.symlink_to(self.outside)
        with self.assertRaises(ValueError):
            self.token()
        self.assert_sentinels()

    def test_nested_symlink_is_recorded_and_target_survives_purge(self):
        (self.destination / 'link').symlink_to(self.outside)
        self.adopt()
        purge_run(self.home, self.roots, self.run_id, self.mounts, dry_run=False, emit=lambda _: None)
        self.assert_sentinels()

    def test_unknown_mount_inventory_is_a_read_only_refusal(self):
        before = self.manifest.read_bytes()
        with self.assertRaises(ValueError):
            legacy.inspect_legacy_run(self.home, self.roots, self.run_id, lambda _: None)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_foreign_quarantine_root_is_rejected_before_reading_any_journal(self):
        roots = {**self.roots, 'data': self.home.parent / 'foreign-fixture-data'}
        with patch('xdg_quarantine_lifecycle.read_manifest', side_effect=AssertionError('must not read outside HOME')):
            with self.assertRaisesRegex(ValueError, 'Unsafe quarantine location'):
                audit.preview_quarantine_adoption(self.home, roots, self.run_id)
            with self.assertRaisesRegex(ValueError, 'Unsafe quarantine location'):
                adopt_legacy_run(self.home, roots, self.run_id, self.mounts)

    def test_gui_error_explains_adopt_purge_then_history_in_both_languages(self):
        for language in ('en', 'pl'):
            text = quarantine_error_details(LegacyQuarantineJournal(self.run_id), language)
            self.assertIn(self.run_id, text)
            self.assertIn('ADOPT', text)
            self.assertIn('PURGE', text)
            self.assertNotIn('requires a valid v3', text)

    def cli(self, *arguments):
        env = {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.roots['config']),
               'XDG_DATA_HOME': str(self.roots['data']), 'XDG_CACHE_HOME': str(self.roots['cache']),
               'XDG_STATE_HOME': str(self.roots['state'])}
        with patch.object(audit, 'check_no_root'), patch.dict(os.environ, env), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return audit.main(['--home', str(self.home), *arguments])

    def test_cli_adoption_preview_never_prompts_or_writes(self):
        before = self.manifest.read_bytes()
        with patch('builtins.input', side_effect=AssertionError('dry run must not prompt')):
            self.assertEqual(self.cli('--adopt-quarantine', self.run_id, '--dry-run'), 0)
        self.assertEqual(self.manifest.read_bytes(), before)

    def test_cli_cancel_then_adopt_leaves_purge_separate(self):
        class TTY:
            @staticmethod
            def isatty():
                return True
        before = self.manifest.read_bytes()
        with patch.object(audit.sys, 'stdin', TTY()), patch('builtins.input', return_value='NO'):
            with self.assertRaises(SystemExit):
                self.cli('--adopt-quarantine', self.run_id)
        self.assertEqual(self.manifest.read_bytes(), before)
        with patch.object(audit.sys, 'stdin', TTY()), patch('builtins.input', return_value='ADOPT'):
            self.assertEqual(self.cli('--adopt-quarantine', self.run_id), 0)
        self.assertTrue(self.file.exists())
        self.assertEqual(completed_history_candidates(self.home, self.roots), [])

    def test_cli_empty_legacy_history_requires_its_own_token(self):
        shutil.rmtree(self.destination)
        class TTY:
            @staticmethod
            def isatty():
                return True
        with patch.object(audit.sys, 'stdin', TTY()), patch('builtins.input', return_value='PURGE'):
            with self.assertRaises(SystemExit):
                self.cli('--cleanup-all-history', '--execute')
        self.assertTrue(self.manifest.exists())
        with patch.object(audit.sys, 'stdin', TTY()), patch('builtins.input', return_value='HISTORY'):
            self.assertEqual(self.cli('--cleanup-all-history', '--execute'), 0)
        self.assertFalse(self.run.exists())
        self.assert_sentinels()
