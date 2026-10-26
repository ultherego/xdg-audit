"""Visibility depends on complete scan evidence, not current display filters."""
from types import SimpleNamespace
import unittest

from xdg_gui_layout import DIALOG_PADDING, dialog_limits, visible_optional_scopes
from xdg_i18n import translate


class AdaptiveLayoutTests(unittest.TestCase):
    def test_missing_integrations_without_data_are_hidden(self):
        self.assertEqual(visible_optional_scopes([], {
            'installed_sources': {'flatpak': 'absent', 'snap': 'absent'}}), set())

    def test_leftovers_survive_uninstalled_package_manager(self):
        items = [SimpleNamespace(scope='snap', state='REVIEW')]
        self.assertEqual(visible_optional_scopes(items, {
            'installed_sources': {'flatpak': 'absent', 'snap': 'absent'}}), {'snap'})

    def test_healthy_integrations_remain_available_without_leftovers(self):
        self.assertEqual(visible_optional_scopes([], {
            'installed_sources': {'flatpak': 'ok', 'snap': 'ok'}}), {'flatpak', 'snap'})

    def test_failed_or_unknown_probe_does_not_masquerade_as_absence(self):
        for state in ('failed', 'timeout', 'parse_error', 'partial'):
            with self.subTest(state=state):
                self.assertEqual(visible_optional_scopes([], {
                    'installed_sources': {'flatpak': state, 'snap': 'absent'}}), {'flatpak'})
        self.assertEqual(visible_optional_scopes([], {}), {'flatpak', 'snap'})

    def test_content_limits_reserve_screen_edges_and_decorations(self):
        width, height = dialog_limits(800, 600)
        self.assertEqual(DIALOG_PADDING, 20)
        self.assertLessEqual(width, 800 - 48)
        self.assertLessEqual(height, 600 - 48)

    def test_new_confirmation_labels_follow_selected_language(self):
        for source, english in (('Tak', 'Yes'), ('Nie', 'No'),
                                ('Nieprawidłowa wartość.', 'Invalid value.')):
            self.assertEqual(translate(source, 'en'), english)
            self.assertEqual(translate(source, 'pl'), source)


if __name__ == '__main__':
    unittest.main()
