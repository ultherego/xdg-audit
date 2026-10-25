"""Static GTK layout regressions, runnable without Gtk on the test host."""
import ast
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]

class LoadingLayoutTests(unittest.TestCase):
    def setUp(self):
        self.source = (BASE / 'xdg_gui_gtk.py').read_text()

    def test_source_parses(self):
        ast.parse(self.source)

    def test_one_header_font_size(self):
        self.assertIn('font-size: 1.08em', self.source)
        heading = self.source.split('def _add_table_heading(self,rows):', 1)[1].split('def refresh(self):', 1)[0]
        self.assertNotIn('size="large"', heading)

    def test_spinner_and_progress_fit_inside_loading_card(self):
        self.assertIn('padding: 26px 30px 28px;', self.source)
        self.assertIn('self.loading_card.set_size_request(400, -1)', self.source)
        self.assertIn('self.loading_spinner.set_size_request(24, 24)', self.source)
        self.assertIn('self.loading_progress.set_margin_top(6)', self.source)
        self.assertNotIn('self.loading_card.set_margin_top(18)', self.source)

    def test_loading_stays_indeterminate(self):
        self.assertIn('self.loading_progress.pulse()', self.source)
        self.assertIn('self.rescan_spinner.start()', self.source)
        self.assertIn('self.rescan_spinner.stop()', self.source)

if __name__ == '__main__':
    unittest.main()
