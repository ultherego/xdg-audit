"""Selection summary is shared by all native GUI backends."""
import unittest
from pathlib import Path
from dataclasses import dataclass
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xdg_inspector import details_text

@dataclass
class Item:
    path: Path
    state: str
    bytes: int
    scope: str = 'config'
    reasons: tuple[str,...] = ()

def human(n):return f'{n} B'

class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.one=Item(Path('/home/example/.config/orphan'), 'CANDIDATE', 12, reasons=('removed in pacman.log',))
        self.two=Item(Path('/home/example/.cache/unknown'), 'UNKNOWN', 34, scope='cache')

    def test_closed_when_no_selection(self):
        self.assertEqual(details_text([],human),'')

    def test_row_click_opens_one_record(self):
        text=details_text([],human,self.one)
        self.assertIn('removed in pacman.log',text)
        self.assertIn('/home/example/.config/orphan',text)
        self.assertIn('Rozmiar: 12 B',text)

    def test_new_clicked_row_replaces_previous_checkbox_details(self):
        text=details_text([self.two],human,self.one)
        self.assertIn('/home/example/.config/orphan',text)
        self.assertNotIn('/home/example/.cache/unknown',text)

    def test_checkbox_selection_without_row_click(self):
        text=details_text([self.two],human)
        self.assertIn('/home/example/.cache/unknown',text)

    def test_multiple_selection_summary_on_checkbox_change(self):
        text=details_text([self.one,self.two],human)
        self.assertIn('Zaznaczono 2 pozycje',text)
        self.assertIn('Łącznie: 46 B',text)
        self.assertIn('UNKNOWN: 1',text)
        self.assertIn('CANDIDATE: 1',text)
        self.assertIn('osobną operacją',text)

    def test_row_click_switches_from_multi_summary_to_clicked_details(self):
        text=details_text([self.one,self.two],human,self.two)
        self.assertIn('/home/example/.cache/unknown',text)
        self.assertNotIn('Zaznaczono 2 pozycje',text)

    def test_row_click_switches_twice(self):
        checked=[self.one]
        first=details_text(checked,human,self.one)
        second=details_text(checked,human,self.two)
        self.assertIn('orphan',first)
        self.assertIn('unknown',second)
        self.assertNotIn('orphan',second)

    def test_summary_is_capped(self):
        text=details_text([Item(Path('/x')/f'd{i}','UNKNOWN',1) for i in range(31)],human)
        self.assertIn('… i 6 dalszych',text)

if __name__ == '__main__':unittest.main()
