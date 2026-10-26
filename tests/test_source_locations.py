"""Additional installation directories remain bounded, non-executing hints."""
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_prefs as prefs
import xdg_sources as sources
import xdg_audit as audit


class SourceLocationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def file(self, relative, *, executable=False):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'never execute this fixture')
        if executable:
            path.chmod(0o700)
        return path

    def test_conventional_and_one_level_appimages(self):
        files = [self.file(path) for path in ('apps/Novel.AppImage', 'Apps/Other.AppImage',
            'opt/Example/Example-2.0-x86_64.AppImage', '.local/opt/Editor/Editor.AppImage',
            '.local/share/AppImages/Writer.AppImage')]
        with patch.object(sources.subprocess, 'run') as execute:
            result = sources.user_appimages(self.home)
        execute.assert_not_called()
        self.assertTrue({str(path) for path in files}.issubset(result.app_ids))
        self.assertIn('example', result.names)

    def test_custom_and_xdg_data_locations_with_spaces(self):
        image = self.file('custom folder/Studio.AppImage')
        xdg = self.home / 'separate data'
        other = self.file('separate data/appimages/Notes.AppImage')
        result = sources.user_appimages(self.home, xdg, [image.parent, image.parent])
        self.assertTrue({str(image), str(other)}.issubset(result.app_ids))

    def test_no_unbounded_recursion_or_symlink_following(self):
        self.file('apps/one/two/Deep.AppImage')
        outside = self.file('private/Linked.AppImage')
        (self.home / 'apps/link').symlink_to(outside.parent, target_is_directory=True)
        result = sources.user_appimages(self.home)
        self.assertNotIn('deep', result.names)
        self.assertNotIn('linked', result.names)

    def test_custom_symlink_directory_is_failed_not_empty(self):
        target = self.file('outside/Linked.AppImage')
        link = self.home / 'custom'
        link.symlink_to(target.parent, target_is_directory=True)
        result = sources.user_appimages(self.home, extra_dirs=[link])
        self.assertEqual(result.status, 'failed')
        self.assertNotIn('linked', result.names)

    def test_cargo_go_and_custom_binaries_are_hints_without_execution(self):
        for location in ('.cargo/bin/rust-tool', 'go/bin/go-tool', 'apps/bin/manual-tool',
                         'custom bins/special-tool'):
            self.file(location, executable=True)
        self.file('custom bins/not-executable')
        with patch.object(sources.subprocess, 'run') as execute:
            result = sources.manual_binaries(self.home, [self.home / 'custom bins'])
        execute.assert_not_called()
        self.assertTrue({'rust-tool', 'go-tool', 'manual-tool', 'special-tool'}.issubset(result.names))
        self.assertNotIn('not-executable', result.names)

    def test_many_application_subdirectories_report_incomplete_inspection(self):
        for number in range(65):
            (self.home / 'apps' / str(number)).mkdir(parents=True)
        self.assertEqual(sources.user_appimages(self.home).status, 'failed')

    def test_settings_roundtrip_expansion_and_scan_invalidation(self):
        configured = prefs.validate({'appimage_dirs': ['~/my images', '/opt/images'],
                                     'binary_dirs': ['~/custom bins']})
        prefs.save(self.home, configured)
        reloaded, error = prefs.load(self.home)
        self.assertIsNone(error)
        self.assertEqual(reloaded, configured)
        self.assertEqual(prefs.source_directories(reloaded, 'binary_dirs', self.home),
                         (self.home / 'custom bins',))
        self.assertTrue(prefs.scan_inputs_changed(prefs.defaults(), configured))

    def test_invalid_relative_traversal_control_and_excessive_paths_are_rejected(self):
        for value in (['relative'], ['~other/bin'], ['~/../outside'], ['/opt/../etc'],
                      ['~//etc'], ['/tmp/line\nbreak'], ['/tmp'] * 33, 'not a list'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prefs.validate({'appimage_dirs': value})

    def test_new_configured_image_after_scan_blocks_stale_move_with_fresh_preferences(self):
        image = self.file('custom images/Configured-App.AppImage')
        data = self.file('.config/configured-app/settings')
        info = data.parent.lstat()
        row = audit.Item('config', data.parent, state='REVIEW',
                         identity=(info.st_dev, info.st_ino, stat.S_IFDIR))
        prefs.save(self.home, {'appimage_dirs': ['~/custom images']})

        def query(provider, *_args, **_kwargs):
            if provider == 'dpkg':
                return sources.Probe(provider, 'ok'), 'unrelated\tinstall ok installed\n'
            return sources.Probe(provider, 'absent'), ''

        with patch.object(sources, '_run', side_effect=query), \
             patch.object(sources, 'native_package_source', return_value='dpkg'), \
             patch.object(sources, 'manual_binaries', return_value=sources.Probe('manual_binary', 'ok')), \
             patch.object(audit, 'command', return_value=''):
            inventory = audit.read_active_names(self.home, audit.xdg_roots(self.home))
            self.assertIn(str(image), inventory.appimage_paths)
            with self.assertRaisesRegex(ValueError, 'present now'):
                audit.commit_quarantine([row], audit.xdg_roots(self.home), self.home, allow_uncertain=True)
        self.assertEqual(data.read_bytes(), b'never execute this fixture')
        self.assertFalse(audit.quarantine_dir(self.home, audit.xdg_roots(self.home)).exists())


if __name__ == '__main__':
    unittest.main()
