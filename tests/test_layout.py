"""Smoke tests for the modern UI modules that do not require a display."""
import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LayoutTests(unittest.TestCase):
    def test_optional_toolkits_remain_lazy(self):
        # Importing GUI modules must not unconditionally import Qt, GTK or Tk.
        for module in ('xdg_gui', 'xdg_gui_qt', 'xdg_gui_gtk', 'xdg_gui_tk'):
            importlib.import_module(module)
        self.assertNotIn('gi.repository.Gtk',sys.modules)
        self.assertNotIn('PySide6.QtWidgets',sys.modules)
        self.assertNotIn('PyQt6.QtWidgets',sys.modules)
        self.assertNotIn('tkinter',sys.modules)

    def test_all_safety_states_have_a_tabular_representation(self):
        from xdg_gui_tk import STATES, SCOPE_LABELS
        self.assertEqual(set(STATES), {'CANDIDATE','REVIEW','UNKNOWN','ACTIVE','PROTECTED'})
        self.assertEqual({scope for _, scope in SCOPE_LABELS},
                         {'all','config','data','state','cache','flatpak','snap','dotfiles'})

    def test_gtk_header_information_is_right_anchored(self):
        from types import SimpleNamespace
        from xdg_gui_gtk import align_header_edges

        class FakeWidget:
            def __init__(self):
                self.hexpand = False
                self.halign = None
                self.valign = None
            def set_hexpand(self, value): self.hexpand = value
            def set_halign(self, value): self.halign = value
            def set_valign(self, value): self.valign = value

        header, title, info = FakeWidget(), FakeWidget(), FakeWidget()
        gtk = SimpleNamespace(Align=SimpleNamespace(END='end', CENTER='center'))
        align_header_edges(header, title, info, gtk)
        self.assertTrue(header.hexpand)
        self.assertTrue(title.hexpand)
        self.assertEqual(info.halign, 'end')
        self.assertEqual(info.valign, 'center')

    def test_gtk_shared_grid_and_theme_color_cards(self):
        source = (Path(__file__).resolve().parents[1] / 'xdg_gui_gtk.py').read_text()
        self.assertIn('grid = Gtk.Grid()', source)
        self.assertIn('self._add_table_heading(rows)', source)
        self.assertNotIn('append(page,columns)', source)
        self.assertIn('h=make_cells([check_box,name,st,size,location])', source)
        self.assertIn('button.xdg-metric.xdg-active', source)
        self.assertIn('border: 2px solid @theme_selected_bg_color', source)
        self.assertIn("rows.set_show_separators(True)", source)

    def test_gtk_headings_have_accessible_larger_text(self):
        source = (Path(__file__).resolve().parents[1] / 'xdg_gui_gtk.py').read_text()
        self.assertIn('font-size: 1.08em',source)
        self.assertIn('title.set_markup(',source)
        self.assertIn('grid.set_margin_top(12 if heading else 7)',source)
        self.assertIn('title.set_markup(',source)
        self.assertIn('self.stack.add_titled(page,scope,title)',source)

    def test_gtk_inspector_can_reopen_with_single_click(self):
        source = (Path(__file__).resolve().parents[1] / 'xdg_gui_gtk.py').read_text()
        self.assertIn('click=Gtk.GestureClick()',source)
        self.assertIn('click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)',source)
        self.assertIn("click.connect('pressed', self._pressed_row, it, row)",source)
        self.assertIn('row.add_controller(click)',source)
        self.assertIn('self.show_inspector(focused=entry)',source)
        self.assertIn("rows.connect('row-selected',self._row_selected)",source)
        self.assertIn('rows.unselect_all()',source)

    def test_original_tabbed_layout_and_contextual_inspector(self):
        source = (Path(__file__).resolve().parents[1] / 'xdg_gui_gtk.py').read_text()
        self.assertIn('Gtk.StackSwitcher(stack=self.stack)', source)
        self.assertIn('inspector.set_visible(False)', source)
        self.assertNotIn('Gtk.StackSidebar', source)

    def test_native_backend_order_unchanged(self):
        from xdg_gui import choose_backend
        self.assertEqual(choose_backend('KDE Plasma',['gtk4','qt6','tk']),'qt6')
        self.assertEqual(choose_backend('Niri',['gtk4','qt6','tk']),'gtk4')


if __name__=='__main__':unittest.main()
