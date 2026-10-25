"""v1.6.0 streaming, language and safety regression tests; display independent."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import xdg_audit as audit
import xdg_prefs as prefs
from xdg_i18n import translate
from xdg_inspector import details_text


class StreamingAndLanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / '.config').mkdir()
        (self.home / '.config' / 'sample-app').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_classification_arrives_before_sizes(self):
        events = []
        inventory = ({'something'}, set(), set(), set(), set(), set(), set(), set())
        def simulated_du(paths, on_chunk=None, stop=None):
            self.assertEqual(events[0][0], 'classified')
            answer = {str(path): 4096 for path in paths}
            if on_chunk: on_chunk(answer, len(paths), len(paths))
            return answer
        with patch.object(audit,'read_active_names',return_value=inventory), \
             patch.object(audit,'parse_removals',return_value={}), \
             patch.object(audit,'references',return_value={}), \
             patch.object(audit,'disk_sizes',side_effect=simulated_du):
            items, _, stats = audit.scan(self.home, ['config'], set(), {}, False,
                on_batch=lambda phase, batch, done, total: events.append((phase, done, total)))
        self.assertEqual([event[0] for event in events], ['classified','sizes'])
        self.assertEqual(items[0].bytes,4096)
        self.assertIn('phase_times_ms',stats)

    def test_scan_cancelled_does_not_touch_paths(self):
        before = list((self.home / '.config').iterdir())
        with self.assertRaises(audit.ScanCancelled):
            audit.scan(self.home, ['config'], set(), {}, True, cancelled=lambda:True)
        self.assertEqual(before,list((self.home / '.config').iterdir()))

    def test_pref_languages_persist_and_reject_invalid(self):
        data = prefs.defaults()
        self.assertEqual(data['language'], 'pl')
        data['language']='en'
        prefs.save(self.home,data)
        self.assertEqual(prefs.load(self.home)[0]['language'],'en')
        with self.assertRaises(ValueError):
            prefs.validate({'language':'de'})

    def test_english_details_and_translation(self):
        it=audit.Item('config',self.home/'.config'/'sample-app',state='REVIEW',reasons=['desktop entry stale'])
        content=details_text([it],audit.human,language='en')
        self.assertIn('Evidence:',content)
        self.assertIn('Path:',content)
        self.assertEqual(translate('Kwarantanna','en'),'Quarantine')
        self.assertEqual(translate('Kwarantanna','pl'),'Kwarantanna')

    def test_native_table_modules_are_loadable_without_bindings(self):
        import xdg_gui_gtk, xdg_gui_qt, xdg_gui_tk
        self.assertTrue(hasattr(xdg_gui_gtk,'launch_gui'))
        self.assertTrue(hasattr(xdg_gui_qt,'launch_gui'))
        self.assertTrue(hasattr(xdg_gui_tk,'launch_gui'))

    def test_models_are_native_and_lazy(self):
        src=(Path(__file__).parents[1]/'xdg_gui_gtk.py').read_text()
        self.assertIn('Gtk.ColumnView.new(selection)',src)
        self.assertIn('Gtk.SortListModel.new',src)
        src=(Path(__file__).parents[1]/'xdg_gui_qt.py').read_text()
        self.assertIn('QtCore.QAbstractTableModel',src)
        self.assertIn('QtCore.QSortFilterProxyModel',src)
        self.assertIn('self.table=QtWidgets.QTableView()',src)

    def test_manifest_atomic_helper_preserves_permissions(self):
        manifest=self.home/'manifest.json'
        audit._write_manifest_atomic(manifest,{'version':'test','items':[]})
        audit._write_manifest_atomic(manifest,{'version':'test2','items':[{'move_status':'moving'}]})
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(manifest.read_text())['version'],'test2')
        self.assertFalse(list(self.home.glob('.manifest-*')))

if __name__ == '__main__':
    unittest.main()
