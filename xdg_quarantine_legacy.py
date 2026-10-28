"""Explicit adoption of CURRENT data in known pre-identity v2 journals.

The original journal is preserved in the receipt. No historical inode/hash
proof is inferred, and this module never deletes quarantined payloads.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat

from xdg_quarantine_lifecycle import (
    RUN_ID, MAX_MANIFEST, _open_path, _directory, _identity, _check_owner,
    _load_manifest, _write_manifest, capture_inventory,
)


def inspect_legacy_run(home, roots, run_id, mounts_checker, *, empty_only=False):
    """Read-only, complete validation of the known v2 namespace and contents."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError('Invalid legacy run ID')
    base = roots.get('data', home / '.local/share') / 'xdg-audit-quarantine'
    if not base.is_absolute() or home not in base.parents:
        raise ValueError('Unsafe quarantine location')
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            info = os.fstat(runfd)
            _check_owner(info, info.st_dev)
            if mounts_checker(base / run_id) is not False:
                raise ValueError('Nested mounts or unavailable mount inventory')
            payload = _load_manifest(runfd, info.st_dev)
            if payload.get('format') != 'intent-journal-v2' or payload.get('created') != run_id:
                raise ValueError('Only a known v2 journal with a matching run ID can be adopted')
            rows = payload.get('items')
            if not isinstance(rows, list) or not rows or len(rows) > 10000:
                raise ValueError('Invalid legacy journal items')
            names, entries = {}, []
            for row in rows:
                if (not isinstance(row, dict) or not isinstance(row.get('scope'), str) or
                        row['scope'] not in roots):
                    raise ValueError('Invalid legacy journal scope')
                # A v3 journal cannot be downgraded to bypass saved evidence.
                if any(key in row for key in ('identity', 'tree_inventory', 'filesystem_identity')):
                    raise ValueError('Unexpected identity evidence in a pre-identity v2 journal')
                if row.get('move_status') not in ('planned', 'moving', 'moved', 'restoring', 'restored'):
                    raise ValueError('Unknown or destructive legacy journal state')
                scope = row['scope']
                source, destination = row.get('source'), row.get('destination')
                if not isinstance(source, str) or not isinstance(destination, str):
                    raise ValueError('Malformed legacy paths')
                src, dst = Path(source), Path(destination)
                if (not src.is_absolute() or '..' in src.parts or '..' in dst.parts or
                        src.parent != roots[scope] or dst.parent != base / run_id / scope or
                        src.name != dst.name or src.name in ('', '.', '..') or
                        src.name in names.setdefault(scope, set())):
                    raise ValueError('Foreign, duplicate or manipulated legacy path')
                names[scope].add(src.name)
                entries.append({'row': row, 'scope': scope, 'name': src.name,
                                'source': src, 'destination': dst})
            visible = set(os.listdir(runfd))
            if visible - {'manifest.json'} - set(names):
                raise ValueError('Untracked content in legacy run')
            scope_identities = {}
            current = []
            for scope in sorted(visible - {'manifest.json'}):
                fd = _directory(runfd, scope)
                try:
                    scope_info = os.fstat(fd)
                    _check_owner(scope_info, info.st_dev)
                    scope_identities[scope] = _identity(scope_info)
                    objects = set(os.listdir(fd))
                    if objects - names[scope]:
                        raise ValueError('Untracked object in legacy scope')
                    if empty_only and objects:
                        raise ValueError('Legacy run still contains quarantined data')
                    for entry in (e for e in entries if e['scope'] == scope):
                        try:
                            present = os.stat(entry['name'], dir_fd=fd, follow_symlinks=False)
                        except FileNotFoundError:
                            continue
                        _check_owner(present, info.st_dev)
                        if (stat.S_IFMT(present.st_mode) not in (stat.S_IFREG, stat.S_IFDIR) or
                                entry['row']['move_status'] == 'restored'):
                            raise ValueError('Unsafe or inconsistent legacy payload')
                        inventory = capture_inventory(entry['destination'])
                        if inventory[0]['identity'] != list(_identity(present)):
                            raise ValueError('Legacy object changed during inspection')
                        from xdg_filesystem import filesystem_identity
                        binding = filesystem_identity(entry['destination'], _identity(present))
                        row = copy.deepcopy(entry['row'])
                        row.update(identity=list(_identity(present)), tree_inventory=inventory, move_status='moved')
                        if binding is not None:
                            row['filesystem_identity'] = binding
                        current.append(row)
                finally:
                    os.close(fd)
            active_scopes = {row['scope'] for row in current}
            return {'run_id': run_id, 'payload': payload, 'run_identity': _identity(info),
                    'scopes': sorted(names), 'existing_scopes': sorted(scope_identities),
                    'scope_identities': scope_identities,
                    'empty_scopes': sorted(set(scope_identities) - active_scopes),
                    'items': current, 'present': len(current),
                    'bytes': sum(n.get('size', 0) for row in current for n in row['tree_inventory'])}
        finally:
            os.close(runfd)
    finally:
        os.close(basefd)


def adoption_token(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def adopt_v2_run(home, roots, run_id, mounts_checker, approval_token):
    """Bind current contents after ADOPT; subsequent PURGE remains separate."""
    report = inspect_legacy_run(home, roots, run_id, mounts_checker)
    if approval_token != adoption_token(report):
        raise ValueError('Legacy approval is missing or stale; preview the current contents again')
    if not report['present']:
        raise ValueError('Legacy run is empty; use completed-history cleanup instead')
    payload = {'format': 'intent-journal-v3', 'created': run_id,
               'version': report['payload'].get('version'), 'items': report['items'],
               'legacy_adoption': {'adopted_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                                   'historical_identity_verified': False, 'purge_authorized': False,
                                   'original_journal': report['payload']}}
    if len(json.dumps(payload, indent=2, ensure_ascii=False).encode('utf-8')) > MAX_MANIFEST:
        raise ValueError('Adopted journal would exceed the manifest size limit')
    base = roots.get('data', home / '.local/share') / 'xdg-audit-quarantine'
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            if (inspect_legacy_run(home, roots, run_id, mounts_checker) != report or
                    _identity(os.fstat(runfd)) != report['run_identity'] or
                    _load_manifest(runfd, os.fstat(runfd).st_dev) != report['payload'] or
                    _identity(os.stat(run_id, dir_fd=basefd, follow_symlinks=False)) != report['run_identity']):
                raise ValueError('Legacy run changed while adopting')
            # Old intents may include scopes that never received any data.
            # rmdir refuses a late insertion; no recursive deletion is used.
            for scope in report['empty_scopes']:
                if _identity(os.stat(scope, dir_fd=runfd, follow_symlinks=False)) != report['scope_identities'][scope]:
                    raise ValueError('Empty legacy scope changed')
                os.rmdir(scope, dir_fd=runfd)
            _write_manifest(runfd, payload)
            return {'run_id': run_id, 'adopted': report['present'], 'migrated_from': 'intent-journal-v2'}
        finally:
            os.close(runfd)
    finally:
        os.close(basefd)
