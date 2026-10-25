"""User preferences are explicit-save only; interrupted moves remain restorable."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xdg_prefs as prefs
import xdg_audit as audit


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.config = self.home / '.config'
        self.config.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_only_does_not_create_settings(self):
        self.assertEqual(prefs.load(self.home)[0], prefs.defaults())
        self.assertFalse(prefs.settings_path(self.home).exists())

    def test_persist_aliases_and_dotfile_keep(self):
        data = prefs.defaults()
        data['keep'] = ['.claude', 'BraveSoftware']
        data['aliases'] = {'Opera': ['opera*'], 'BraveSoftware': ['brave*']}
        path = prefs.save(self.home, data)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        reloaded, issue = prefs.load(self.home)
        self.assertIsNone(issue)
        self.assertIn('.claude', reloaded['keep'])
        self.assertIn('opera*', reloaded['aliases']['opera'])

    def test_injection_and_traversal_rejected(self):
        for payload in [{'keep':['../../etc/passwd']}, {'aliases':{'../bad':['brave*']}},
                        {'aliases':{'brave':['$(touch /tmp/oops)']}},
                        {'startup_scope':'/root'}, {'quick_scan':'true'}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                prefs.save(self.home, payload)
        self.assertFalse(prefs.settings_path(self.home).exists())

    def test_symlink_settings_refused(self):
        settings = prefs.settings_path(self.home)
        settings.parent.mkdir()
        external = self.home / 'other.json'
        external.write_text('important')
        settings.symlink_to(external)
        with self.assertRaises(ValueError):
            prefs.save(self.home, prefs.defaults())
        self.assertEqual(external.read_text(), 'important')

    def test_reconcile_interrupted_move_readonly_then_restore(self):
        roots = audit.xdg_roots(self.home)
        data_root = roots['data']
        data_root.mkdir(parents=True)
        source = self.config / 'test-config'
        source.mkdir()
        (source / 'marker').write_text('hello')
        run_id = '20261025-010203-112233'
        run = audit.quarantine_dir(self.home, roots) / run_id
        (run / 'config').mkdir(parents=True)
        moved = run / 'config' / source.name
        source.rename(moved)  # simulate crash before manifest update
        (run / 'manifest.json').write_text(json.dumps({'items':[{'source':str(source),
             'destination':str(moved), 'scope':'config', 'move_status':'planned'}]}))
        history = audit.quarantine_runs(self.home, roots)
        self.assertEqual(history[0]['moved'],1)
        self.assertTrue(history[0]['items'][0]['recovered_from_interrupted_manifest'])
        self.assertFalse(source.exists())  # inspection was read-only
        restored = audit.restore_quarantine_run(self.home, roots, run_id, emit=lambda x: None)
        self.assertEqual(restored['restored'],1)
        self.assertEqual((source/'marker').read_text(),'hello')
        history_after = audit.quarantine_runs(self.home, roots)
        self.assertEqual(history_after[0]['moved'], 0)
        self.assertEqual(history_after[0]['items'][0]['move_status'], 'restored')

    def test_new_keep_rule_blocks_stale_candidate_move(self):
        roots = audit.xdg_roots(self.home)
        source = self.config/'do-not-move'
        source.mkdir()
        info = source.lstat()
        import stat as stat_module
        item = audit.Item(scope='config', path=source, state='CANDIDATE', removable=True,
                          identity=(info.st_dev, info.st_ino, stat_module.S_IFMT(info.st_mode)))
        prefs.save(self.home, {'keep':['do-not-move']},roots)
        inventory = ({'unrelated'},set(),set(),set(),set(),set(),set(),set())
        with patch.object(audit,'read_active_names',return_value=inventory):
            with self.assertRaisesRegex(ValueError,'explicitly protected'):
                audit.commit_quarantine([item], roots, self.home, emit=lambda x: None)
        self.assertTrue(source.exists())
        self.assertFalse(audit.quarantine_dir(self.home, roots).exists())

    def test_scanning_progress_is_phases_not_fake_percent(self):
        roots = audit.xdg_roots(self.home)
        (self.config/'toy').mkdir()
        with patch.object(audit, 'read_active_names', return_value=({'unrelated'},set(),set(),set(),set(),set(),set(),set())), \
             patch.object(audit, 'parse_removals', return_value={}), \
             patch.object(audit, 'references', return_value={}):
            stages=[]
            items, _, stats = audit.scan(self.home,['config'],set(),{},True,progress=stages.append)
        self.assertEqual(stages[0],'Pakiety i aplikacje')
        self.assertIn('Powiązania konfiguracji',stages)
        self.assertIn('phase_times_ms',stats)
        self.assertEqual(len(items),1)


if __name__ == '__main__': unittest.main()
