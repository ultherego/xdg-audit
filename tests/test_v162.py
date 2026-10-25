"""v1.6.2: regression for real GTK NameError and complete live switch (without Gtk installed)."""
from __future__ import annotations

import ast
from pathlib import Path
import textwrap
import types
import unittest
from xdg_i18n import translate

BASE = Path(__file__).resolve().parents[1]


class Label:
    def __init__(self):
        self.text = None
    def set_text(self, value): self.text = value
    def set_label(self, value): self.text = value
    def set_markup(self, value): self.text = value
    def get_visible(self): return False
    def set_title(self, value): self.text = value


class Stack:
    def __init__(self): self.pages = {}
    def get_child_by_name(self, scope): return scope
    def get_page(self, scope):
        if scope not in self.pages: self.pages[scope] = Label()
        return self.pages[scope]


class Columns:
    def __init__(self): self.cells = [Label() for _ in range(5)]
    def get_item(self, index): return self.cells[index]


class View:
    def __init__(self): self.columns = Columns()
    def get_columns(self): return self.columns


class MockWindow:
    def __init__(self):
        self.prefs = {'language': 'pl'}
        self.win = Label()
        self.subtitle = Label()
        self.environment_first = Label()
        self.environment_second = Label()
        self.appearance = types.SimpleNamespace(source='XDG portal')
        self.metric_captions = {x: Label() for x in ('CANDIDATE','REVIEW','UNKNOWN','ACTIVE','PROTECTED')}
        self.heading = Label()
        self.rescan_label = Label()
        self.cancel_button = Label()
        self.settings_button = Label()
        self.search = types.SimpleNamespace(set_placeholder_text=lambda text: setattr(self.search, 'text', text))
        for name in ('show_all','all_button','clear_button','uncertain','export_button',
                     'compare_button','move_button','inspector_heading','inspector_note',
                     'loading_title','loading_note','visible_count','selected_count','status'):
            setattr(self, name, Label())
        self.stack = Stack()
        self.gtk_columns = {'config': View()}
        self.checked = set()
        self.items = []
        self.busy = False
        self.scan_complete = True
        self.inspector = Label()
    def _visible(self): return iter([])
    def show_inspector(self): return None


def load_real_gtk_method():
    """Execute the actual GTK apply_language method, not a rewritten imitation.

    Only replace nonlocal with global to provide the enclosing language state
    without importing GTK. All other code and accesses are from production.
    """
    source = (BASE/'xdg_gui_gtk.py').read_text()
    mod = ast.parse(source)
    gui = next(n for n in mod.body if isinstance(n, ast.FunctionDef) and n.name == 'launch_gui')
    window = next(n for n in gui.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
    method = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == 'apply_language')
    text = textwrap.dedent(ast.get_source_segment(source, method))
    text = text.replace('nonlocal _language', 'global _language')
    globs = {'_language':'pl', 'runtime':{'desktop':'Niri','session':'wayland'},
             'gtk_version':'4.0', 'GTK4':True,
             'GLib':types.SimpleNamespace(markup_escape_text=lambda s:s),
             'SCOPES':[('Wszystko','all'),('Konfiguracja','config'),('Dane','data'),
                       ('Stan','state'),('Cache','cache'),('Flatpak','flatpak'),('Dotfiles','dotfiles')],
             'entries_count': lambda n,lang: f'{n} entries',
             'selected_count': lambda n,lang: f'{n} selected',
             'tr':lambda value: translate(value, globs['_language'])}
    exec(compile(text, 'xdg_gui_gtk.py', 'exec'), globs)
    return globs['apply_language'],globs


class LiveGTKRegressionTests(unittest.TestCase):
    def test_real_gtk_method_switches_everything_without_appearance_name_error(self):
        apply, lang_globals = load_real_gtk_method()
        window = MockWindow()
        apply(window, 'en')
        self.assertEqual(lang_globals['_language'], 'en')
        self.assertIn('Desktop: Niri', window.environment_first.text)
        self.assertIn('Style: XDG portal', window.environment_second.text)
        self.assertEqual(window.metric_captions['REVIEW'].text, 'Review')
        self.assertEqual(window.stack.pages['config'].text, 'Configuration')
        self.assertEqual(window.gtk_columns['config'].columns.cells[1].text, 'Name')
        self.assertEqual(window.settings_button.text, '⚙ Settings')
        self.assertIn('Scanned', window.status.text)
        apply(window, 'pl')
        self.assertEqual(lang_globals['_language'], 'pl')
        self.assertIn('Środowisko: Niri', window.environment_first.text)
        self.assertIn('Styl: XDG portal', window.environment_second.text)
        self.assertEqual(window.gtk_columns['config'].columns.cells[1].text, 'Nazwa')
        self.assertEqual(window.stack.pages['config'].text, 'Konfiguracja')

    def test_all_three_implementations_use_proportional_icon(self):
        gtk=(BASE/'xdg_gui_gtk.py').read_text()
        qt=(BASE/'xdg_gui_qt.py').read_text()
        tk=(BASE/'xdg_gui_tk.py').read_text()
        self.assertIn('from_file_at_scale(str(icon_file),68,68,True)',gtk)
        self.assertIn('icon_pixmap.scaled(68, 68,', qt)
        self.assertIn('subsample(2,2)', tk)
        self.assertIn('self.appearance=detect_appearance(home)',gtk)


if __name__ == '__main__':
    unittest.main()
