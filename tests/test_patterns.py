"""Regression: package variations override stale removal logs."""
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('xdg_audit_patterns', root / 'xdg_audit.py')
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def inventory(packages, flatpaks=(), desktops=()):
    packages = set(packages)
    flatpaks = set(flatpaks)
    desktops = set(desktops)
    return (packages, flatpaks, set(), set(), set(), set(), desktops,
            {audit.normalize(x) for x in packages | flatpaks | desktops})


class PatternMatchingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / '.cache').mkdir()
        for item in ('BraveSoftware', 'opera', 'go'):
            (self.home / '.cache' / item).mkdir()
        self.remove_log = {'brave-bin': ['[2026-01-01]'],
                           'opera': ['[2026-01-01]'],
                           'go': ['[2026-01-01]']}

    def tearDown(self):
        self.tmp.cleanup()

    def run_scan(self, packages, flatpaks=(), desktops=()):
        with patch.object(audit, 'read_active_names', return_value=inventory(packages, flatpaks, desktops)), \
             patch.object(audit, 'parse_removals', return_value=self.remove_log), \
             patch.object(audit, 'references', return_value={}), \
             patch.object(audit, 'disk_sizes', return_value={}):
            items, *_ = audit.scan(self.home, ['cache'], set(), {}, True)
        return {it.path.name: it for it in items}

    def test_brave_current_alternate_name_overrides_old_remove(self):
        for package in ('brave', 'brave-bin', 'brave-browser', 'brave-nightly-bin',
                        'brave-browser-git', 'brave-beta'):
            with self.subTest(package=package):
                row = self.run_scan({package})['BraveSoftware']
                self.assertEqual(row.state, 'ACTIVE')
                self.assertTrue(any(package in reason and ('brave*' in reason or 'exact/normalized' in reason) for reason in row.reasons))

    def test_opera_package_prefix(self):
        for package in ('opera-stable', 'opera-developer', 'opera-beta'):
            with self.subTest(package=package):
                row = self.run_scan({package})['opera']
                self.assertEqual(row.state, 'ACTIVE')
                self.assertIn(package, ' '.join(row.reasons))

    def test_opera_removed_without_live_signals(self):
        self.assertEqual(self.run_scan({'some-unrelated-app'})['opera'].state, 'CANDIDATE')

    def test_stale_desktop_entry_is_review_not_active(self):
        row = self.run_scan({'some-unrelated-app'}, desktops={'opera'})['opera']
        self.assertEqual(row.state, 'REVIEW')
        self.assertTrue(any('desktop entry' in x for x in row.reasons))

    def test_browser_flatpak_without_pacman(self):
        row = self.run_scan({'some-unrelated-app'}, flatpaks={'com.brave.Browser'})['BraveSoftware']
        self.assertEqual(row.state, 'ACTIVE')

    def test_auxiliary_brave_theme_is_not_app(self):
        row = self.run_scan({'brave-themes'})['BraveSoftware']
        self.assertEqual(row.state, 'REVIEW')
        self.assertFalse(row.removable)

    def test_short_prefix_not_overbroad(self):
        row = self.run_scan({'gobject-introspection'})['go']
        self.assertEqual(row.state, 'CANDIDATE')
        self.assertNotIn('go*', audit.package_patterns('go', audit.ALIASES))

    def test_pattern_engine_does_not_use_substring(self):
        self.assertFalse(audit.match_installed_packages('opera', {'myoperahelper'}, audit.ALIASES)[0])

    def test_quarantine_rechecks_package_inventory(self):
        with patch.object(audit, 'read_active_names', return_value=inventory({'unrelated'})), \
             patch.object(audit, 'parse_removals', return_value=self.remove_log), \
             patch.object(audit, 'references', return_value={}):
            items, roots, _ = audit.scan(self.home, ['cache'], set(), {}, True)
        target = next(x for x in items if x.path.name == 'BraveSoftware')
        self.assertEqual(target.state, 'CANDIDATE')
        with patch.object(audit, 'read_active_names', return_value=inventory({'brave-browser'})):
            with self.assertRaisesRegex(ValueError, 'Application is present now'):
                audit.commit_quarantine([target], roots, self.home)
        self.assertTrue(target.path.exists())
        self.assertFalse(audit.quarantine_dir(self.home, roots).exists())

    def test_unknown_pacman_inventory_fails_closed_at_commit(self):
        with patch.object(audit, 'read_active_names', return_value=inventory({'unrelated'})), \
             patch.object(audit, 'parse_removals', return_value=self.remove_log), \
             patch.object(audit, 'references', return_value={}):
            items, roots, _ = audit.scan(self.home, ['cache'], set(), {}, True)
        target = next(x for x in items if x.path.name == 'BraveSoftware')
        with patch.object(audit, 'read_active_names', return_value=inventory(set())):
            with self.assertRaisesRegex(ValueError, 'Cannot verify current pacman inventory'):
                audit.commit_quarantine([target], roots, self.home)
        self.assertTrue(target.path.exists())

if __name__ == '__main__':
    unittest.main()
