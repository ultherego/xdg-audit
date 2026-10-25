"""Prevent regressions in PL/EN safety dialogs and evidence localization."""
import ast
from pathlib import Path
from string import Formatter
import unittest

from xdg_i18n import (EN, entries_count, format_message, localize_evidence,
                      translate, translate_ui_text)
from xdg_inspector import details_text

ROOT = Path(__file__).resolve().parent.parent
GUIS = ('xdg_gui_gtk.py', 'xdg_gui_qt.py', 'xdg_gui_tk.py')


class LocalizationCompletenessTests(unittest.TestCase):
    def test_every_gui_translation_key_exists(self):
        """Catch keys forgotten when new controls/dialogs are added."""
        for file in GUIS:
            with self.subTest(gui=file):
                tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                        continue
                    if node.func.id not in ('tr', 'tf') or not node.args:
                        continue
                    if not isinstance(node.args[0], ast.Constant):
                        continue
                    key = node.args[0].value
                    if isinstance(key, str):
                        self.assertIn(key, EN, f'{file}:{node.lineno}: {key}')

    def test_no_local_variable_shadows_translation_formatter(self):
        for file in GUIS:
            tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
            launch = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'launch_gui')
            for node in ast.walk(launch):
                if isinstance(node, ast.FunctionDef) and node.name == 'tf':
                    continue
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id == 'tf':
                            self.fail(f'{file}:{node.lineno}: local variable shadows tf()')

    def test_translations_have_matching_template_placeholders(self):
        parse = lambda v: {field for _, field, _, _ in Formatter().parse(v) if field}
        for key, en in EN.items():
            with self.subTest(key=key):
                self.assertEqual(parse(key), parse(en))

    def test_confirmation_tokens_are_unmodified_in_both_languages(self):
        for token in ('MOVE', 'UNCERTAIN', 'RESTORE', 'EXPORT'):
            for lang in ('pl', 'en'):
                with self.subTest(token=token,language=lang):
                    prompt = format_message('Wpisz {token}', lang, token=token)
                    self.assertIn(token, prompt)
                    self.assertEqual(prompt.count(token), 1)

    def test_quarantine_plan_pluralization_and_paths(self):
        path = '/home/example/.local/share/some-app'
        for count in (1, 2, 5, 21, 22):
            for language in ('pl', 'en'):
                plan = format_message('Plan: {count}, {size}.', language,
                                      count=entries_count(count, language), size='38.4MiB')
                description = plan + '\nCANDIDATE 38.4MiB ' + path + '\n\n' + translate(
                    'Dane zostaną PRZENIESIONE, nie usunięte.', language)
                self.assertIn(path, description)
                self.assertIn('38.4MiB', description)
                self.assertIn('CANDIDATE', description)
                if language == 'en':
                    self.assertIn(f"Plan: {count} {'entry' if count == 1 else 'entries'}", description)
                    self.assertIn('Files will be MOVED', description)
                    self.assertNotIn('Dane zostaną', description)
                else:
                    self.assertIn('nie usunięte', description)

    def test_safety_dialog_templates_are_localized(self):
        keys = ('Ostateczne potwierdzenie', 'Niepewne pozycje',
                'Zamknij powiązane aplikacje.', 'Plan przywracania',
                'Istniejące pliki NIE zostaną nadpisane. Kontynuować?',
                'Potwierdzenie', 'Wpisz RESTORE:',
                'Dane nie zostaną trwale usunięte.', 'Zawartość kwarantanny',
                'Błąd przywracania')
        for key in keys:
            with self.subTest(key=key):
                self.assertNotEqual(translate(key, 'en'), key)
                self.assertEqual(translate(key, 'pl'), key)

    def test_evidence_translation_is_display_only(self):
        source = 'installed pacman package: opera (match: opera*)'
        self.assertEqual(localize_evidence(source, 'en'), source)
        self.assertEqual(localize_evidence(source, 'pl'),
                         'zainstalowany pakiet pacman: opera (dopasowanie: opera*)')
        self.assertIn('nie ustalono', localize_evidence(
            'no verified installed application or owner (NOT proof of orphan)', 'pl'))
        self.assertEqual(localize_evidence('/home/example/.cache/my-app', 'pl'),
                         '/home/example/.cache/my-app')

    def test_switching_fixed_labels_can_round_trip(self):
        for source in ('Przywróć operację…', 'Plan kwarantanny', 'Błąd skanowania'):
            english = translate(source, 'en')
            self.assertEqual(translate_ui_text(english, 'en', 'pl'), source)

    def test_critical_dialogs_use_translation_calls(self):
        for file in GUIS:
            source = (ROOT / file).read_text(encoding='utf-8')
            with self.subTest(file=file):
                self.assertIn("tr('Ostateczne potwierdzenie')" if file != 'xdg_gui_tk.py'
                              else "tr('Potwierdzenie')", source)
                self.assertIn("tr('Zamknij powiązane aplikacje.')" if file == 'xdg_gui_gtk.py'
                              else "tr('Zamknij powiązane aplikacje.", source)


if __name__ == '__main__':
    unittest.main()
