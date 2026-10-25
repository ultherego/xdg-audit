"""v1.6.3: update-language-in-place and genuine-sized header artwork."""
import ast
import unittest
from pathlib import Path

from xdg_prefs import scan_inputs_changed

ROOT = Path(__file__).resolve().parents[1]

class V163Tests(unittest.TestCase):
    def test_only_language_does_not_invalidate_scan(self):
        previous={'language':'pl','keep':['niri'],'aliases':{'bravesoftware':['brave*']},
                  'quick_scan':False,'startup_scope':'all','show_active':False}
        for changed in ({'language':'en'}, {'show_active':True},
                        {'startup_scope':'config'}, {'language':'en','show_active':True}):
            with self.subTest(changed=changed):
                self.assertFalse(scan_inputs_changed(previous,{**previous,**changed}))
        for changed in ({'keep':['niri','opera']},
                        {'aliases':{'bravesoftware':['brave*'],'opera':['opera*']}},
                        {'quick_scan':True}):
            with self.subTest(changed=changed):
                self.assertTrue(scan_inputs_changed(previous,{**previous,**changed}))

    def test_all_backends_gate_scans_on_actual_input_changes(self):
        for module in ['xdg_gui_gtk.py','xdg_gui_qt.py','xdg_gui_tk.py']:
            with self.subTest(module=module):
                code=(ROOT/module).read_text()
                self.assertIn('scan_inputs_changed(',code)
                self.assertIn('if needs_scan:',code)
                self.assertIn("['language'] !=",code)
                tree=ast.parse(code)
                self.assertTrue(any(isinstance(node,ast.FunctionDef) and node.name=='apply_language'
                                    for node in ast.walk(tree)))

    def test_language_only_does_not_change_active_tab_or_force_refresh(self):
        gtk=(ROOT/'xdg_gui_gtk.py').read_text()
        tk=(ROOT/'xdg_gui_tk.py').read_text()
        self.assertNotIn("self.stack.set_visible_child_name(new['startup_scope'])", gtk)
        self.assertIn('if self.show_all.get_active() != args.all:',gtk)
        self.assertIn('if self.show_all.get() != args.all:',tk)

    def test_gtk_uses_picture_for_logo_not_theme_icon(self):
        code=(ROOT/'xdg_gui_gtk.py').read_text()
        self.assertIn('brand_icon=Gtk.Picture.new_for_pixbuf(scaled)',code)
        self.assertIn('brand_icon.set_can_shrink(False)',code)
        self.assertIn('from_file_at_scale(str(icon_file),68,68,True)',code)
        self.assertIn('brand_icon.set_size_request(68,68)',code)

    def test_qt_and_tk_logo_correspond_to_two_line_header(self):
        qt=(ROOT/'xdg_gui_qt.py').read_text()
        tk=(ROOT/'xdg_gui_tk.py').read_text()
        self.assertIn('icon_pixmap.scaled(68, 68,',qt)
        self.assertIn("'xdg-audit-128.png')).subsample(2,2)",tk)

    def test_translation_does_not_rebuild_cached_gtk4_or_tk_rows(self):
        for module in ['xdg_gui_gtk.py','xdg_gui_tk.py','xdg_gui_qt.py']:
            with self.subTest(module=module):
                tree=ast.parse((ROOT/module).read_text())
                apply=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='apply_language')
                methods=[n.func.attr for n in ast.walk(apply) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
                self.assertNotIn('start_scan',methods)
                self.assertNotIn('scan_async',methods)
                if module.endswith('_tk.py'):
                    self.assertNotIn('_refresh_tables',methods)
                if module.endswith('_qt.py'):
                    self.assertNotIn('apply_system_theme',methods)

if __name__=='__main__': unittest.main()
