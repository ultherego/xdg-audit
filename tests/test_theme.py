"""Theme detection is testable without Qt, a running desktop or any user files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import xdg_theme as t
import xdg_audit as audit


class ThemeTests(unittest.TestCase):
    def test_detect_known_desktops(self):
        for value, expected in [("KDE", "KDE Plasma"), ("KDE:Plasma", "KDE Plasma"),
                                ("GNOME", "GNOME"), ("Niri", "Niri"),
                                ("Hyprland", "Hyprland"), ("XFCE", "XFCE"),
                                ("sway", "Sway")]:
            with self.subTest(value=value):
                self.assertEqual(t.desktop_name({"XDG_CURRENT_DESKTOP": value}), expected)

    def test_kde_globals_actual_palette(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root)
            (config / "kdeglobals").write_text('''[Colors:Window]
BackgroundNormal=36,39,58
ForegroundNormal=205,214,244
[Colors:View]
BackgroundNormal=30,30,46
ForegroundNormal=205,214,244
[Colors:Selection]
BackgroundNormal=250,179,135
ForegroundNormal=30,30,46
''')
            colors = t.kde_palette(config)
            self.assertEqual(colors["window"], (36,39,58))
            self.assertEqual(colors["highlight"], (250,179,135))
            with patch.object(t, "portal_appearance", return_value=("unknown", None)):
                a = t.detect_appearance(config, {"XDG_CURRENT_DESKTOP":"KDE", "XDG_CONFIG_HOME":root})
                self.assertEqual(a.scheme, "dark")
                self.assertEqual(a.accent, None)
                self.assertEqual(a.kde_colors["window_text"], (205,214,244))

    def test_kde_does_not_use_other_desktops_palette(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(t, "portal_appearance", return_value=("light", (12,34,56))):
                a = t.detect_appearance(Path(root), {"XDG_CURRENT_DESKTOP":"KDE"})
            self.assertEqual(a.scheme, "light")
            self.assertEqual(a.accent, (12,34,56))

    def test_portal_scheme_and_accent(self):
        def fake(args):
            if args[-1] == "color-scheme":
                return "(<uint32 1>,)"
            return "(<(0.98, 0.7, 0.5)>,)"
        with patch.object(t, "_run", side_effect=fake):
            self.assertEqual(t.portal_appearance(), ("dark", (250,178,128)))

    def test_gnome_portal_preferred(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(t, "portal_appearance", return_value=("light", (1,2,3))):
                with patch.object(t, "gtk_preference", return_value=("dark", "gsettings")):
                    a = t.detect_appearance(Path(root), {"XDG_CURRENT_DESKTOP":"GNOME"})
            self.assertEqual(a.scheme, "light")
            self.assertEqual(a.accent, (1,2,3))
            self.assertEqual(a.source, "XDG portal")

    def test_niri_fallback_gtk(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / '.config' / 'gtk-3.0'
            config.mkdir(parents=True)
            (config / 'settings.ini').write_text('[Settings]\ngtk-application-prefer-dark-theme=1\n')
            with patch.object(t, "portal_appearance", return_value=("unknown", None)):
                with patch.object(t, "_run", return_value=""):
                    a = t.detect_appearance(Path(root), {"XDG_CURRENT_DESKTOP":"niri"})
            self.assertEqual(a.scheme, "dark")
            self.assertIn("gtk-3.0", a.source)

    def test_invalid_color_safe(self):
        self.assertIsNone(t._rgb('777,1,2'))
        self.assertIsNone(t._rgb('foobar'))
        self.assertEqual(t._rgb('#FABC87'), (250,188,135))

    def test_cli_only_still_available(self):
        self.assertEqual(audit.VERSION, "1.7.0-rc2")
        self.assertTrue(callable(audit.main))

    def test_optional_qt_dependency_helpful(self):
        import xdg_gui
        self.assertTrue(callable(xdg_gui.launch_gui))


if __name__ == '__main__':
    unittest.main()
