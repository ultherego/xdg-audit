#!/usr/bin/env python3
"""Isolated quarantine/restore integration test using disposable XDG data.

By default this exercises the machine's real installed-package detection (pacman
is required for the mutation to be authorized). --synthetic-inventory replaces
only the installed-applications probe, for CI and non-Arch test hosts.

All file operations are restricted to a freshly created TemporaryDirectory.
Never run with sudo; do not point it at any existing HOME or XDG directory.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import xdg_audit as audit


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def snapshot(path: Path) -> dict[str, tuple[str, str]]:
    """Compare relative paths and actual bytes, not only item counts."""
    result: dict[str, tuple[str, str]] = {}
    for item in (path, *sorted(path.rglob('*'))):
        relative = str(item.relative_to(path))
        check(not item.is_symlink(), f'unexpected fixture symlink: {item}')
        if item.is_file():
            result[relative] = ('file', sha256(item.read_bytes()).hexdigest())
        elif item.is_dir():
            result[relative] = ('directory', '')
        else:
            raise AssertionError(f'unexpected fixture type: {item}')
    return result


def fake_inventory(*_args: object) -> tuple:
    packages = {'python', 'coreutils'}
    return (packages, set(), set(), set(), set(), set(), set(),
            {audit.normalize(name) for name in packages})


def make_fixture(root: Path) -> dict[str, tuple[str, str]]:
    root.mkdir(parents=True, exist_ok=False)
    (root / 'settings.ini').write_text('test=zażółć gęślą jaźń\n', encoding='utf-8')
    (root / 'nested').mkdir()
    (root / 'nested' / 'bytes.bin').write_bytes(bytes(range(256)) * 4)
    return snapshot(root)


def run(synthetic_inventory: bool) -> None:
    if os.geteuid() == 0:
        raise SystemExit('Run as a regular user, never via sudo.')
    with tempfile.TemporaryDirectory(prefix='xdg-audit-e2e-') as temporary:
        home = Path(temporary).resolve()
        check(home != Path.home().resolve(), 'refusing current HOME')
        config, data = home / '.config', home / '.local/share'
        state, cache = home / '.local/state', home / '.cache'
        for path in (config, data, state, cache):
            path.mkdir(parents=True, exist_ok=True)
        marker = f'xdg-audit-e2e-{uuid4().hex[:12]}'
        names = [marker + '-' + part for part in ('config', 'data', 'conflict', 'swap', 'missing-inventory')]
        log = home / 'fixture-pacman.log'
        log.write_text(''.join(f'[2026-10-20T12:00:00+0200] [ALPM] removed {name} (0.1-1)\n'
                               for name in names), encoding='utf-8')
        env = {
            'HOME': str(home), 'XDG_CONFIG_HOME': str(config),
            'XDG_DATA_HOME': str(data), 'XDG_STATE_HOME': str(state),
            'XDG_CACHE_HOME': str(cache), 'XDG_AUDIT_PACMAN_LOG': str(log),
        }
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, env))
            if synthetic_inventory:
                stack.enter_context(patch.object(audit, 'read_active_names', side_effect=fake_inventory))
            roots = audit.xdg_roots(home)
            check(roots['config'] == config and roots['data'] == data, 'XDG isolation failed')
            protected = config / 'niri'
            expected_protected = make_fixture(protected)
            main_paths = [config / names[0], data / names[1]]
            expected = {p: make_fixture(p) for p in main_paths}

            items, _, info = audit.scan(home, ['config', 'data'], set(), {}, True)
            by_path = {item.path: item for item in items}
            check(info['pacman_packages'] > 0, 'pacman inventory is unavailable; refusing quarantine')
            for path in main_paths:
                check(by_path[path].state == 'CANDIDATE' and by_path[path].removable,
                      f'fixture is not an eligible CANDIDATE: {path} ({by_path[path].state})')
            check(by_path[protected].state == 'PROTECTED', 'expected Niri protection')
            try:
                audit.commit_quarantine([by_path[protected]], roots, home, emit=lambda _: None)
            except ValueError:
                pass
            else:
                raise AssertionError('PROTECTED data was accepted for quarantine')
            check(snapshot(protected) == expected_protected, 'protected data changed')
            print('PASS scan & protection: 2 CANDIDATE, 1 PROTECTED')

            log_messages: list[str] = []
            result = audit.commit_quarantine([by_path[p] for p in main_paths], roots, home,
                                             emit=log_messages.append)
            check(result['planned'] == 2 and len(result['moved']) == 2,
                  f'quarantine failed: {result}; messages={log_messages}')
            manifest_path = Path(result['manifest'])
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            check(manifest['format'] == 'intent-journal-v3', 'unexpected journal format')
            for row in manifest['items']:
                source, dest = Path(row['source']), Path(row['destination'])
                check(source in expected and not source.exists(), 'source still exists after move')
                check(snapshot(dest) == expected[source], f'changed bytes in quarantine: {source}')
                check(len(row['identity']) == 3, 'missing original object identity')
            check(snapshot(protected) == expected_protected, 'quarantine changed protected data')
            print('PASS quarantine: 2 objects moved, contents/hash and journal verified')

            restore = audit.restore_quarantine_run(home, roots, result['run_id'],
                                                    emit=log_messages.append)
            check(restore['restored'] == 2 and restore['skipped'] == 0,
                  f'first restore failed: {restore}; messages={log_messages}')
            for path in main_paths:
                check(snapshot(path) == expected[path], f'restored content changed: {path}')
            check(snapshot(protected) == expected_protected, 'restore changed protected data')
            print('PASS restore: 2 objects returned with original bytes')

            # Deliberate target collision: the pre-existing destination must survive.
            conflict = config / names[2]
            wanted_conflict = make_fixture(conflict)
            entries, _, _ = audit.scan(home, ['config'], set(), {}, True)
            item = next(it for it in entries if it.path == conflict)
            check(item.state == 'CANDIDATE', 'conflict case not classified as candidate')
            result = audit.commit_quarantine([item], roots, home, emit=log_messages.append)
            check(len(result['moved']) == 1, 'collision fixture not moved to quarantine')
            quarantined = Path(json.loads(Path(result['manifest']).read_text())['items'][0]['destination'])
            conflict.mkdir()
            (conflict / 'do-not-overwrite').write_text('unrelated data', encoding='utf-8')
            restore = audit.restore_quarantine_run(home, roots, result['run_id'],
                                                    emit=log_messages.append)
            check(restore['restored'] == 0 and quarantined.exists(), 'restore overwrote a collision')
            check((conflict / 'do-not-overwrite').read_text() == 'unrelated data',
                  'preexisting file was corrupted')
            conflict.rename(home / 'preserved-collision')
            restore = audit.restore_quarantine_run(home, roots, result['run_id'],
                                                    emit=log_messages.append)
            check(restore['restored'] == 1 and snapshot(conflict) == wanted_conflict,
                  'restore did not recover after moving collision aside')
            print('PASS collision: no overwrite; restore works once destination is clear')

            # Deliberate quarantine substitution: same path, different inode must be blocked.
            swapped = config / names[3]
            wanted_swap = make_fixture(swapped)
            entries, _, _ = audit.scan(home, ['config'], set(), {}, True)
            item = next(it for it in entries if it.path == swapped)
            result = audit.commit_quarantine([item], roots, home, emit=log_messages.append)
            check(len(result['moved']) == 1, 'swap fixture not quarantined')
            quarantined = Path(json.loads(Path(result['manifest']).read_text())['items'][0]['destination'])
            original = quarantined.with_name(quarantined.name + '-original')
            quarantined.rename(original)
            quarantined.mkdir()
            (quarantined / 'forgery').write_text('replacement data')
            restore = audit.restore_quarantine_run(home, roots, result['run_id'],
                                                    emit=log_messages.append)
            check(restore['restored'] == 0 and not swapped.exists(),
                  'substituted quarantine object was restored')
            quarantined.rename(quarantined.with_name(quarantined.name + '-forgery'))
            original.rename(quarantined)
            restore = audit.restore_quarantine_run(home, roots, result['run_id'],
                                                    emit=log_messages.append)
            check(restore['restored'] == 1 and snapshot(swapped) == wanted_swap,
                  'original object did not restore after recovering from substitution')
            print('PASS substitution: different inode refused; original restored')

            # No pacman inventory must not authorize any move.
            inventory_path = config / names[4]
            make_fixture(inventory_path)
            candidate_items, _, _ = audit.scan(home, ['config'], set(), {}, True)
            candidate = next(it for it in candidate_items if it.path == inventory_path)
            with patch.object(audit, 'read_active_names', return_value=(set(),) * 8):
                try:
                    audit.commit_quarantine([candidate], roots, home, emit=log_messages.append)
                except ValueError:
                    pass
                else:
                    raise AssertionError('missing pacman inventory did not fail closed')
            check(inventory_path.exists(), 'failed inventory check removed a file')
            check(snapshot(protected) == expected_protected, 'protected sentinel changed')
            print('PASS fail-closed: missing inventory denied; protected fixture untouched')

            # Full second cycle: explicitly test irreversible purge on isolated
            # fixtures. Verify the protected tree and unrelated data survive.
            entries, _, _ = audit.scan(home, ['config', 'data'], set(), {}, True)
            selected = [next(item for item in entries if item.path == path)
                        for path in main_paths]
            purged = audit.commit_quarantine(selected, roots, home, emit=log_messages.append)
            check(len(purged['moved']) == 2, 'purge cycle quarantine failed')
            for inspected in json.loads(Path(purged['manifest']).read_text())['items']:
                check(inspected['identity'] == inspected.get('tree_inventory', [{}])[0].get('identity'),
                      'quarantine root inode inconsistent: journal=%r snapshot=%r' %
                      (inspected['identity'], inspected.get('tree_inventory', [{}])[0].get('identity')))
            before = Path(purged['manifest']).read_bytes()
            preview = audit.purge_quarantine_run(home, roots, purged['run_id'], dry_run=True)
            check(preview['objects'] == 2, 'purge preview expected two entries')
            check(before == Path(purged['manifest']).read_bytes(),
                  'dry run unexpectedly modified journal')
            check(all(not path.exists() for path in main_paths),
                  'source still exists during purge preview')
            finished = audit.purge_quarantine_run(home, roots, purged['run_id'], dry_run=False)
            check(finished['objects'] == 2, 'purge returned wrong object count')
            payload = json.loads(Path(purged['manifest']).read_text())
            check(all(row['move_status'] == 'purged' for row in payload['items']),
                  'purge journal is not a tombstone')
            check(all(not Path(row['destination']).exists() for row in payload['items']),
                  'purge left quarantined objects')
            check(snapshot(protected) == expected_protected,
                  'purge damaged protected data')
            check((home / 'preserved-collision' / 'do-not-overwrite').read_text()
                  == 'unrelated data', 'purge damaged unrelated data')
            print('PASS purge: dry-run immutable, 2 objects deleted, journal retained, protected untouched')
            again = audit.purge_quarantine_run(home, roots, purged['run_id'], dry_run=False)
            check(again['objects'] == 0, 'repeated purge should do nothing')
            print('PASS purge idempotence: no deletion outside run')

    print('PASS cleanup: isolated temporary HOME removed automatically')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-inventory', action='store_true',
                        help='replace only the pacman/live-app probe for CI and non-Arch hosts')
    args = parser.parse_args()
    run(args.synthetic_inventory)