"""AUR name availability is bounded, read-only and never MOVE authorization."""
import gzip
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_aur as aur
from xdg_sources import ActiveInventory


def inventory(metadata=None, *, explicit=True):
    kwargs = {'native_source': 'pacman'} if explicit else {}
    return ActiveInventory(({'listed-app', 'local-app', 'unrelated'}, set(), set(), set(),
        set(), set(), set(), set()), status={'pacman': 'ok', 'pacman_foreign': 'ok'},
        foreign={'listed-app', 'local-app'}, aur=metadata, **kwargs)


class AurMetadataTests(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(aur, '_cache', None)
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def test_exact_public_name_membership_and_cache_without_package_queries(self):
        compressed = gzip.compress(b'# public index\nlisted-app\nlisted-app-bin\n')
        with patch.object(aur.urllib.request, 'urlopen', return_value=io.BytesIO(compressed)) as fetch:
            result = aur.classify_foreign({'listed-app', 'local-app', 'listed'})
            again = aur.classify_foreign({'listed-app-bin'})
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0].full_url, aur.INDEX_URL)
        self.assertNotIn('local-app', str(fetch.call_args))
        self.assertEqual(result.listed, {'listed-app'})
        self.assertEqual(result.unlisted, {'local-app', 'listed'})
        self.assertEqual(again.listed, {'listed-app-bin'})
        self.assertFalse(result.summary()['verified_build_origin'])

    def test_download_parse_and_decompression_failures_remain_unknown(self):
        cases = [b'not gzip', gzip.compress(b'bad/name\n'), gzip.compress(b'# no names\n'),
                 gzip.compress(b'bad\xff\n'), gzip.compress(b'listed-app\n')[:8]]
        for raw in cases:
            with self.subTest(raw=raw), patch.object(aur, '_cache', None), \
                 patch.object(aur.urllib.request, 'urlopen', return_value=io.BytesIO(raw)):
                result = aur.classify_foreign({'local-app'})
                self.assertEqual(result.status, 'failed')
                self.assertEqual(result.unknown, {'local-app'})
                self.assertFalse(result.unlisted)

    def test_download_and_expanded_size_limits(self):
        for key, raw in [('MAX_COMPRESSED', b'x' * 65),
                         ('MAX_EXPANDED', gzip.compress(b'app-name\n' * 100))]:
            with self.subTest(limit=key), patch.object(aur, '_cache', None), patch.object(aur, key, 64), \
                 patch.object(aur.urllib.request, 'urlopen', return_value=io.BytesIO(raw)):
                self.assertEqual(aur.classify_foreign({'app-name'}).unknown, {'app-name'})

    def test_failure_cache_expires_and_can_recover(self):
        with patch.object(aur, '_read_index', side_effect=[TimeoutError(), frozenset({'listed-app'})]) as read, \
             patch.object(aur.time, 'monotonic', side_effect=[0, 1, 61]):
            self.assertEqual(aur.classify_foreign({'listed-app'}).status, 'timeout')
            self.assertEqual(aur.classify_foreign({'listed-app'}).status, 'timeout')
            self.assertEqual(aur.classify_foreign({'listed-app'}).listed, {'listed-app'})
        self.assertEqual(read.call_count, 2)

    def test_empty_foreign_and_legacy_inventory_stay_offline(self):
        with patch.object(aur, '_read_index') as read:
            self.assertEqual(aur.classify_foreign(()).status, 'absent')
            aur.enrich_inventory(inventory(explicit=False))
        read.assert_not_called()

    def test_explicit_inventory_can_use_precomputed_offline_metadata(self):
        metadata = aur.ForeignClassification('ok', listed=frozenset({'listed-app'}))
        with patch.object(aur, '_read_index') as read:
            inv = aur.enrich_inventory(inventory(metadata))
            self.assertIs(inv.aur, metadata)
        read.assert_not_called()

    def test_scan_shows_distinction_without_changing_installed_protection_or_writing(self):
        metadata = aur.ForeignClassification('ok', listed=frozenset({'listed-app'}),
            unlisted=frozenset({'local-app'}))
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            for name in ('listed-app', 'local-app'):
                (home / '.config' / name).mkdir(parents=True)
            before = sorted(str(path.relative_to(home)) for path in home.rglob('*'))
            with patch.object(audit, 'read_active_names', return_value=inventory(metadata)), \
                 patch.object(audit, 'parse_removals', return_value={}):
                rows, _, stats = audit.scan(home, ['config'], set(), {}, True)
            after = sorted(str(path.relative_to(home)) for path in home.rglob('*'))
        self.assertEqual(before, after)
        self.assertEqual({row.state for row in rows}, {'ACTIVE'})
        evidence = {row.path.name: row.json()['evidence'] for row in rows}
        self.assertTrue(any('AUR name listed:' in item['detail'] for item in evidence['listed-app']))
        self.assertTrue(any(item['source'] == 'aur_metadata' and item['strength'] == 'weak'
                            for item in evidence['local-app']))
        self.assertEqual(stats['foreign_provenance']['not_listed_in_aur'], 1)

    def test_move_does_not_query_aur_and_unlisted_installed_package_still_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path = home / '.config/local-app'
            path.mkdir(parents=True)
            (path / 'data').write_bytes(b'unchanged')
            info = path.lstat()
            row = audit.Item('config', path, state='REVIEW',
                identity=(info.st_dev, info.st_ino, stat.S_IFDIR))
            with patch.object(audit, 'read_active_names', return_value=inventory()), \
                 patch.object(aur, '_read_index') as read, self.assertRaisesRegex(ValueError, 'present now'):
                audit.commit_quarantine([row], audit.xdg_roots(home), home, allow_uncertain=True)
            read.assert_not_called()
            self.assertEqual((path / 'data').read_bytes(), b'unchanged')


if __name__ == '__main__':
    unittest.main()
