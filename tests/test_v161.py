"""v1.6.1 responsive layout and live PL/EN regression checks."""
from pathlib import Path
import unittest
from xdg_i18n import translate, translate_ui_text, entries_count, selected_count

BASE=Path(__file__).parents[1]

class LiveLanguageAndSizingTests(unittest.TestCase):
    def test_language_switch_is_bidirectional_without_restart(self):
        self.assertEqual(translate_ui_text('Wszystko','pl','en'),'All')
        self.assertEqual(translate_ui_text('All','en','pl'),'Wszystko')
        self.assertEqual(translate_ui_text('Przenieś do kwarantanny…','pl','en'), 'Move to quarantine…')
        self.assertEqual(translate_ui_text('Move to quarantine…','en','pl'), 'Przenieś do kwarantanny…')
        self.assertEqual(translate_ui_text('/home/user/Aplikacje','pl','en'), '/home/user/Aplikacje')
        self.assertEqual(translate('Dane aplikacji','en'), 'Application data')
        self.assertEqual(entries_count(5,'en'),'5 entries')
        self.assertEqual(selected_count(2,'pl'),'2 wybranych')
    def test_native_gui_layouts_are_responsive(self):
        gtk=(BASE/'xdg_gui_gtk.py').read_text()
        self.assertIn("GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_file),68,68,True)",gtk)
        self.assertIn('column.set_expand(True)',gtk)
        self.assertIn('self.apply_language(new[\'language\'])',gtk)
        self.assertNotIn('Zrestartuj aplikację, aby zastosować język',gtk)
        qt=(BASE/'xdg_gui_qt.py').read_text()
        self.assertIn('QHeaderView.ResizeMode.Stretch',qt)
        self.assertIn('self.apply_language(new[\'language\'])',qt)
        tk=(BASE/'xdg_gui_tk.py').read_text()
        self.assertIn("('name',tr('Nazwa'),170,True)",tk)
        self.assertIn('self.apply_language(new[\'language\'])',tk)
