#!/usr/bin/env python3
"""Exercise an actual snapd inventory with disposable user data, without mocks.

CI installs/removes only its metadata-only fixture outside this script. The
application and this unprivileged harness never modify installed software.
"""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xdg_audit as audit
from xdg_sources import verified_native_source

BASE = 'xdg-audit-fixture'
PARALLEL = BASE + '_blue'
PAYLOAD = b'live snapd disposable data\x00\xff\n'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(phase):
    audit.check_no_root()
    with tempfile.TemporaryDirectory(prefix='xdg-live-snapd-') as temporary:
        home = Path(temporary)
        env = {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
               'XDG_DATA_HOME': str(home / '.local/share'),
               'XDG_STATE_HOME': str(home / '.local/state'),
               'XDG_CACHE_HOME': str(home / '.cache')}
        with patch.dict(os.environ, env):
            roots = audit.xdg_roots(home)
            sentinel = home / 'untouched-sentinel'
            sentinel.write_bytes(PAYLOAD)
            for name in (BASE, PARALLEL):
                path = roots['snap'] / name
                path.mkdir(parents=True)
                (path / 'settings').write_bytes(PAYLOAD)
            inventory = audit.read_active_names(home, roots)
            require(verified_native_source(inventory) == 'dpkg', 'native inventory is not healthy dpkg')
            require(inventory.status.get('snap') == 'ok', 'actual snap list was not healthy')
            require(PARALLEL in inventory.snap_ids, 'parallel fixture is not installed')
            require((BASE in inventory.snap_ids) == (phase == 'installed'), 'wrong base fixture phase')
            listed = subprocess.run(['snap', 'list', PARALLEL], capture_output=True, text=True,
                check=True, timeout=20, env={**os.environ, 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LANG': 'C'})
            require('disabled' in listed.stdout.splitlines()[-1].split()[-1],
                    'parallel fixture must be disabled to test installed protection')
            print('PASS actual snapd inventory and disabled parallel instance:', phase)

            rows, *_ = audit.scan(home, ['snap'], set(), {}, True)
            by_name = {row.path.name: row for row in rows}
            protected = (BASE, PARALLEL) if phase == 'installed' else (PARALLEL,)
            for name in protected:
                row = by_name[name]
                require(row.state == 'ACTIVE', 'installed instance did not remain ACTIVE: ' + name)
                stale = replace(row, state='REVIEW', protected=False, removable=False)
                try:
                    audit.commit_quarantine([stale], roots, home, allow_uncertain=True, emit=lambda _: None)
                except ValueError as exc:
                    require('present now' in str(exc), 'MOVE failed for an unrelated reason: ' + str(exc))
                else:
                    raise AssertionError('fresh real snapd query accepted an installed instance for MOVE')
                require((row.path / 'settings').read_bytes() == PAYLOAD, 'installed instance data changed')
            require(not audit.quarantine_dir(home, roots).exists(), 'blocked MOVE wrote quarantine data')
            print('PASS ACTIVE and pre-MOVE protection against stale rows:', ','.join(protected))
            if phase == 'installed':
                return

            row = by_name[BASE]
            require(row.state == 'REVIEW', 'removed base instance did not become REVIEW')
            try:
                audit.commit_quarantine([row], roots, home, emit=lambda _: None)
            except ValueError:
                pass
            else:
                raise AssertionError('REVIEW accepted without explicit uncertain consent')
            moved = audit.commit_quarantine([row], roots, home, allow_uncertain=True, emit=lambda _: None)
            require(moved['moved'] == [str(row.path)], 'wrong instance moved')
            manifest = json.loads(Path(moved['manifest']).read_text())
            destination = Path(manifest['items'][0]['destination'])
            require((destination / 'settings').read_bytes() == PAYLOAD, 'MOVE changed bytes')
            restored = audit.restore_quarantine_run(home, roots, moved['run_id'], emit=lambda _: None)
            require(restored['restored'] == 1, 'RESTORE failed')
            require((row.path / 'settings').read_bytes() == PAYLOAD, 'RESTORE changed bytes')
            print('PASS real snapd REVIEW -> explicit MOVE -> RESTORE:', sha256(PAYLOAD).hexdigest())

            rows, *_ = audit.scan(home, ['snap'], set(), {}, True)
            row = next(row for row in rows if row.path.name == BASE)
            moved = audit.commit_quarantine([row], roots, home, allow_uncertain=True, emit=lambda _: None)
            preview = audit.purge_quarantine_run(home, roots, moved['run_id'])
            require(preview['objects'] == 1, 'PURGE preview lost fixture')
            audit.purge_quarantine_run(home, roots, moved['run_id'], dry_run=False, emit=lambda _: None)
            require(audit.purge_quarantine_run(home, roots, moved['run_id'])['objects'] == 0,
                    'PURGE not idempotent')
            require(not row.path.exists(), 'PURGE recreated original data')
            require((roots['snap'] / PARALLEL / 'settings').read_bytes() == PAYLOAD,
                    'different installed namespace was changed')
            require(sentinel.read_bytes() == PAYLOAD, 'unrelated sentinel changed')
            print('PASS real snapd PURGE, idempotence, exact parallel namespace and untouched sentinel')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('installed', 'removed'), required=True)
    run(parser.parse_args().phase)
