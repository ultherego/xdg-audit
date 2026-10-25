"""Regression tests for GTK table header and selection/inspector routing."""
import sys
import unittest
from pathlib import Path
from dataclasses import dataclass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xdg_inspector import click_is_inside_control, details_text


class Widget:
    def __init__(self, parent=None):
        self.parent=parent
    def get_parent(self):
        return self.parent

class Checkbox(Widget):
    pass

@dataclass
class Item:
    path: Path
    scope: str='cache'
    state: str='UNKNOWN'
    bytes: int=0
    reasons: tuple=()


class RowClickRegressionTests(unittest.TestCase):
    def test_gtk_header_is_an_unselectable_row_in_same_list(self):
        source=(Path(__file__).resolve().parents[1]/'xdg_gui_gtk.py').read_text()
        self.assertIn('heading_row=Gtk.ListBoxRow()',source)
        self.assertIn('heading_row.set_selectable(False)',source)
        self.assertIn('heading_row.set_activatable(False)',source)
        self.assertIn('append(rows,heading_row)',source)
        self.assertIn('self._add_table_heading(rows)',source)
        self.assertIn('append(rows,row)',source)

    def test_click_inside_checkbox_is_reserved_for_bulk_selection(self):
        row=Widget()
        checkbox=Checkbox(row)
        target=Widget(checkbox)
        self.assertTrue(click_is_inside_control(target,row,Checkbox))

    def test_click_anywhere_else_goes_to_inspector(self):
        row=Widget()
        inner=Widget(row)
        label=Widget(inner)
        whitespace=row
        self.assertFalse(click_is_inside_control(label,row,Checkbox))
        self.assertFalse(click_is_inside_control(whitespace,row,Checkbox))

    def test_clicked_new_row_replaces_stale_inspector_while_old_checkbox_checked(self):
        wayland=Item(Path('/home/test/.local/share/wayland-xsessions'))
        brave=Item(Path('/home/test/.cache/BraveSoftware'),'cache','CANDIDATE',25,('removed earlier',))
        initial=details_text([wayland],lambda n:f'{n} B')
        updated=details_text([wayland],lambda n:f'{n} B',brave)
        self.assertIn('wayland-xsessions',initial)
        self.assertIn('BraveSoftware',updated)
        self.assertNotIn('wayland-xsessions',updated)

    def test_multi_selection_after_checkbox_does_not_use_last_clicked_focus(self):
        a=Item(Path('/tmp/a'))
        b=Item(Path('/tmp/b'))
        summary=details_text([a,b],lambda n:f'{n} B')
        self.assertIn('Zaznaczono 2 pozycje',summary)

    def test_row_capture_does_not_depend_on_selection_change(self):
        source=(Path(__file__).resolve().parents[1]/'xdg_gui_gtk.py').read_text()
        self.assertIn('Gtk.SingleSelection.new(None)',source)
        self.assertIn("selection.connect('notify::selected-item', changed)",source)
        self.assertIn('Gtk.ColumnView.new(selection)',source)

if __name__=='__main__':
    unittest.main()
