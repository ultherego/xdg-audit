"""Native report counts and health must describe the selected OS database."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
from xdg_sources import ActiveInventory


class NativeReportingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def report(self, inventory):
        with patch.object(audit, 'read_active_names', return_value=inventory), \
             patch.object(audit, 'parse_removals', return_value={}), \
             patch('xdg_sources.dpkg_removals', return_value={}):
            rows, _, stats = audit.scan(self.home, ['config'], set(), {}, True)
        output = io.StringIO()
        with redirect_stdout(output):
            audit.print_report(rows, stats, all_items=True)
        # These exact statistics also appear in the public JSON report.
        return json.loads(json.dumps(stats)), output.getvalue()

    def inventory(self, native, *, packages=('foreign-pacman',),
                  dpkg=('debian-app',), rpm=('rpm-app',), health='ok'):
        return ActiveInventory((set(packages), set(), set(), set(), set(), set(), set(), set()),
            native_source=native,
            status={'pacman': health if native == 'pacman' else 'ok',
                    'dpkg': health if native == 'dpkg' else 'ok',
                    'rpm': health if native == 'rpm' else 'ok'},
            distro={'dpkg': set(dpkg), 'rpm': set(rpm)})

    def test_os_database_not_a_foreign_tool_determines_report_count(self):
        for source in ('pacman', 'dpkg', 'rpm'):
            with self.subTest(source=source):
                stats, output = self.report(self.inventory(source,
                    packages=('foreign-one', 'foreign-two', 'foreign-three'),
                    dpkg=('deb-one', 'deb-two'), rpm=('rpm-one',)))
                expected = {'pacman': 3, 'dpkg': 2, 'rpm': 1}[source]
                self.assertEqual(stats['native_package_source'], source)
                self.assertEqual(stats['native_packages'], expected)
                self.assertIn(f'NATIVE={source} PACKAGES={expected} SOURCE_HEALTH=ok', output)
                self.assertEqual(stats['pacman_packages'], 3)  # Existing JSON field retained.

    def test_dpkg_architecture_aliases_count_each_package_name_once(self):
        stats, output = self.report(self.inventory('dpkg',
            dpkg=('libexample', 'libexample:amd64', 'libexample:i386', 'python3')))
        self.assertEqual(stats['native_packages'], 2)
        self.assertIn('NATIVE=dpkg PACKAGES=2', output)

    def test_incomplete_inventory_is_visible_alongside_known_package_count(self):
        stats, output = self.report(self.inventory('dpkg', health='partial'))
        self.assertEqual(stats['installed_sources']['dpkg'], 'partial')
        self.assertIn('NATIVE=dpkg PACKAGES=1 SOURCE_HEALTH=partial', output)

    def test_unknown_os_does_not_report_foreign_database_as_native(self):
        stats, output = self.report(self.inventory(None))
        self.assertIsNone(stats['native_package_source'])
        self.assertEqual(stats['native_packages'], 0)
        self.assertIn('NATIVE=unknown PACKAGES=0 SOURCE_HEALTH=unknown', output)

    def test_empty_native_database_does_not_fall_back_to_foreign_packages(self):
        stats, output = self.report(self.inventory('dpkg', dpkg=()))
        self.assertEqual(stats['native_packages'], 0)
        self.assertIn('NATIVE=dpkg PACKAGES=0 SOURCE_HEALTH=ok', output)

    def test_explicit_inventory_without_health_is_unknown_rather_than_legacy(self):
        inventory = ActiveInventory(({'python'}, set(), set(), set(), set(), set(), set(), set()),
            native_source='pacman', status={})
        stats, output = self.report(inventory)
        self.assertEqual(stats['installed_sources'], {})
        self.assertIn('NATIVE=pacman PACKAGES=1 SOURCE_HEALTH=unknown', output)

    def test_installed_sources_diagnostic_uses_the_same_dpkg_count(self):
        inventory = self.inventory('dpkg',
            dpkg=('libexample', 'libexample:amd64', 'libexample:i386', 'python3'), health='partial')
        output = io.StringIO()
        with patch.object(audit, 'read_active_names', return_value=inventory), \
             patch.object(audit, 'check_no_root'), redirect_stdout(output):
            result = audit.main(['--home', str(self.home), '--installed-sources'])
        self.assertEqual(result, 0)
        diagnostic = json.loads(output.getvalue())
        self.assertEqual(diagnostic['native_package_source'], 'dpkg')
        self.assertEqual(diagnostic['native_packages'], 2)
        self.assertEqual(diagnostic['counts']['dpkg'], 2)
        self.assertEqual(diagnostic['health']['dpkg'], 'partial')

    def test_legacy_pacman_inventory_keeps_statistics_and_reports_legacy_health(self):
        inventory = ({'python', 'git'}, set(), set(), set(), set(), set(), set(), set())
        stats, output = self.report(inventory)
        self.assertEqual(stats['pacman_packages'], 2)
        self.assertEqual(stats['native_packages'], 2)
        self.assertIn('NATIVE=pacman PACKAGES=2 SOURCE_HEALTH=legacy', output)


if __name__ == '__main__':
    unittest.main()
