#!/usr/bin/env python3
"""Native pacman/dpkg/RPM protection and lifecycle checks in a temporary HOME.

No inventory mocking and no system package modification. Run as a regular
user on a supported distribution with an existing, healthy package database.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xdg_audit as audit
from xdg_sources import verified_native_source


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(expected):
    audit.check_no_root()
    with tempfile.TemporaryDirectory(prefix='xdg-native-cycle-') as td:
        home = Path(td)
        env = {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
               'XDG_DATA_HOME': str(home / '.local/share'),
               'XDG_STATE_HOME': str(home / '.local/state'),
               'XDG_CACHE_HOME': str(home / '.cache')}
        with patch.dict(os.environ, env):
            roots = audit.xdg_roots(home)
            fixture = roots['config'] / 'xdg-native-disposable-fixture'
            fixture.mkdir(parents=True)
            original = b'preserve exact fixture bytes\x00\xff\n'
            (fixture / 'settings').write_bytes(original)
            sentinel = home / 'unrelated-sentinel'
            sentinel.write_bytes(b'never change')
            installed = audit.read_active_names(home, roots)
            require(verified_native_source(installed) == expected, 'wrong native provider')
            require(installed.status.get(expected) == 'ok', 'native database unhealthy')
            if expected != 'pacman':
                require(not installed[0], 'non-Arch smoke expects a system without pacman')
            print('PASS real native database:', expected)

            # A directory named after the actual installed package manager must
            # remain ACTIVE and refuse even an explicitly uncertain MOVE.
            protected = roots['config'] / expected
            protected.mkdir()
            (protected / 'settings').write_bytes(original)
            rows, _, report = audit.scan(home, ['config'], set(), {}, True)
            require(report['native_package_source'] == expected, 'report selected the wrong database')
            require(report['native_packages'] > 0, 'report lost the native package count')
            active = next(row for row in rows if row.path == protected)
            require(active.state == 'ACTIVE', 'installed native package was not protected')
            try:
                audit.commit_quarantine([active], roots, home,
                    allow_uncertain=True, emit=lambda _: None)
            except ValueError:
                pass
            else:
                raise AssertionError('installed native package data was accepted for MOVE')
            require((protected / 'settings').read_bytes() == original, 'protected bytes changed')
            print('PASS installed native package protected from MOVE')

            # This is an intentionally unknown test application, not an orphan
            # inferred from missing package records. Uncertain consent is required.
            rows, _, report = audit.scan(home, ['config'], set(), {}, True)
            selected = next(row for row in rows if row.path == fixture)
            require(selected.state == 'UNKNOWN', 'fixture unexpectedly classified as installed/orphan')
            try:
                audit.commit_quarantine([selected], roots, home, emit=lambda _: None)
            except ValueError:
                pass
            else:
                raise AssertionError('UNKNOWN was accepted without explicit uncertain consent')
            result = audit.commit_quarantine([selected], roots, home,
                allow_uncertain=True, emit=lambda _: None)
            require(result['moved'] == [str(fixture)], 'native quarantine did not move fixture')
            payload = json.loads(Path(result['manifest']).read_text())
            destination = Path(payload['items'][0]['destination'])
            require((destination / 'settings').read_bytes() == original, 'MOVE changed bytes')
            restored = audit.restore_quarantine_run(home, roots, result['run_id'], emit=lambda _: None)
            require(restored['restored'] == 1, 'native restore failed')
            require((fixture / 'settings').read_bytes() == original, 'RESTORE changed bytes')
            print('PASS native MOVE -> RESTORE:', sha256(original).hexdigest())

            rows, *_ = audit.scan(home, ['config'], set(), {}, True)
            selected = next(row for row in rows if row.path == fixture)
            result = audit.commit_quarantine([selected], roots, home,
                allow_uncertain=True, emit=lambda _: None)
            preview = audit.purge_quarantine_run(home, roots, result['run_id'])
            require(preview['objects'] == 1, 'PURGE preview lost fixture')
            audit.purge_quarantine_run(home, roots, result['run_id'], dry_run=False, emit=lambda _: None)
            require(not fixture.exists(), 'PURGE recreated original data')
            require(audit.purge_quarantine_run(home, roots, result['run_id'])['objects'] == 0,
                'PURGE was not idempotent')
            require(sentinel.read_bytes() == b'never change', 'unrelated data changed')
            require((protected / 'settings').read_bytes() == original, 'protected data changed')
            print('PASS native PURGE, idempotence and unrelated sentinel')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect', choices=('pacman', 'dpkg', 'rpm'), required=True)
    run(parser.parse_args().expect)
