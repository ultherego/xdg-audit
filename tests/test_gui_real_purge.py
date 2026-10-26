"""Product GUI must expose the real deletion flow, not development smoke controls."""
import unittest
from pathlib import Path


class RealPurgeUserExperienceTests(unittest.TestCase):
    def test_no_polkit_or_config_smoke_buttons_in_graphical_backends(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("xdg_gui_gtk.py", "xdg_gui_qt.py", "xdg_gui_tk.py"):
            with self.subTest(backend=name):
                source = (root / name).read_text(encoding="utf-8")
                self.assertNotIn("Test Polkit…", source)
                self.assertNotIn("Test uprawnień ~/.config…", source)
                self.assertNotIn("def polkit_selftest", source)
                self.assertNotIn("def config_access_selftest", source)
                self.assertIn("resume_purge=True", source)
                self.assertIn("quarantine_access_recoverable_error", source)
                self.assertIn("Zatwierdź aktualny stan", source)
                self.assertIn("PURGE", source)

    def test_recovery_and_deletion_are_separate_confirmations(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("xdg_gui_gtk.py", "xdg_gui_qt.py", "xdg_gui_tk.py"):
            with self.subTest(backend=name):
                source = (root / name).read_text(encoding="utf-8")
                self.assertIn("'ACCESS'", source)
                self.assertIn("'ADOPT'", source)
                self.assertIn("'PURGE'", source)


if __name__ == "__main__":
    unittest.main()
