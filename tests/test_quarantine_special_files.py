"""Real FIFO opens must never stall quarantine inspection or file hashing."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import json
import os
from pathlib import Path
import stat
import sys
from unittest.mock import patch

import xdg_audit as audit
from xdg_quarantine_lifecycle import capture_inventory

home, case = Path(sys.argv[1]), sys.argv[2]
roots = audit.xdg_roots(home)
run_id = '20261028-100000-123456'
run = audit.quarantine_dir(home, roots) / run_id
entry = run / 'config/fixture'
entry.parent.mkdir(parents=True)
content = b'original quarantined bytes\x00\xff'
if case == 'inventory-root':
    entry.write_bytes(content)
    target = entry
else:
    entry.mkdir()
    target = entry / 'payload'
    target.write_bytes(content)
sentinel = home / 'outside-sentinel'
sentinel.write_bytes(b'outside data stays unchanged')
info = entry.stat()
payload = {'format': 'intent-journal-v3', 'created': run_id, 'items': [{
    'scope': 'config', 'source': str(roots['config'] / entry.name),
    'destination': str(entry), 'identity': [info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)],
    'move_status': 'moved', 'tree_inventory': capture_inventory(entry)}]}
manifest = run / 'manifest.json'
manifest.write_text(json.dumps(payload))
original_manifest = manifest.read_bytes()
assert audit.inspect_quarantine_run(home, roots, run_id)['present'] == 1
saved_manifest = home / 'saved-manifest'
saved_payload = home / 'saved-payload'

def substitute_manifest():
    manifest.rename(saved_manifest)
    os.mkfifo(manifest, 0o600)

real_open, real_is_file = os.open, Path.is_file
swapped = False

def checked_is_file(path):
    global swapped
    result = real_is_file(path)
    if path == manifest and result and not swapped:
        substitute_manifest()
        swapped = True
    return result

def raced_open(name, flags, *args, **kwargs):
    global swapped
    if name == target.name and kwargs.get('dir_fd') is not None and not flags & os.O_DIRECTORY:
        assert not swapped
        os.rename(name, saved_payload, src_dir_fd=kwargs['dir_fd'])
        os.mkfifo(name, 0o600, dir_fd=kwargs['dir_fd'])
        swapped = True
    return real_open(name, flags, *args, **kwargs)

def operation():
    if case == 'manifest-access' or case == 'access-race':
        return audit.diagnose_quarantine_access(home, roots, run_id)
    if case == 'manifest-history':
        return audit.cleanup_quarantine_history(home, roots, run_id, dry_run=False)
    if case == 'manifest-list':
        assert audit.quarantine_runs(home, roots) == []
        return 'blocked listing'
    if case == 'manifest-restore':
        return audit.restore_quarantine_run(home, roots, run_id, emit=lambda _: None)
    if case == 'manifest-cli-restore':
        with patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', side_effect=AssertionError('Unsafe manifest must not reach confirmation')):
            return audit.restore(home, roots, run_id)
    return audit.purge_quarantine_run(home, roots, run_id, dry_run=False, emit=lambda _: None)

manifest_race = case in ('manifest-list', 'manifest-restore', 'manifest-cli-restore')
if case.startswith('manifest-') and not manifest_race:
    substitute_manifest()
try:
    with patch.object(Path, 'is_file', checked_is_file) if manifest_race else \
            patch.object(os, 'open', raced_open) if not case.startswith('manifest-') else \
            patch.object(os, 'open', real_open):
        result = operation()
        assert result == 'blocked listing', 'Unsafe operation unexpectedly completed'
        error = result
except (ValueError, OSError) as caught:
    error = str(caught)

assert sentinel.read_bytes() == b'outside data stays unchanged'
if case.startswith('manifest-'):
    assert stat.S_ISFIFO(manifest.lstat().st_mode)
    assert saved_manifest.read_bytes() == original_manifest
    assert target.read_bytes() == content
else:
    assert swapped and stat.S_ISFIFO(target.lstat().st_mode)
    assert saved_payload.read_bytes() == content
    assert manifest.read_bytes() == original_manifest
print(json.dumps({'blocked': True, 'error': error, 'sentinel': 'unchanged'}))
'''


class SpecialFileReadTests(unittest.TestCase):
    def check_case(self, case):
        with tempfile.TemporaryDirectory(prefix='xdg-fifo-') as home:
            # A child timeout kills a blocked open, so a regression cannot hang
            # the test runner. FIFO behavior itself uses real kernel syscalls.
            result = subprocess.run([sys.executable, '-c', CHILD, home, case],
                                    cwd=ROOT, text=True, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['blocked'])
            self.assertEqual(report['sentinel'], 'unchanged')
            self.assertTrue(report['error'])
            expected = ('Quarantine file substituted' if case == 'access-race' else
                        'File replaced during inventory' if case.startswith('inventory-') else
                        'blocked listing' if case == 'manifest-list' else 'Unsafe manifest file')
            self.assertEqual(report['error'], expected)

    def test_fifo_manifest_cannot_stall_purge(self):
        self.check_case('manifest-purge')

    def test_fifo_manifest_cannot_stall_access_diagnosis(self):
        self.check_case('manifest-access')

    def test_fifo_manifest_cannot_stall_history_cleanup(self):
        self.check_case('manifest-history')

    def test_manifest_fifo_swap_cannot_stall_listing(self):
        self.check_case('manifest-list')

    def test_manifest_fifo_swap_cannot_stall_restore(self):
        self.check_case('manifest-restore')

    def test_manifest_fifo_swap_cannot_stall_cli_restore(self):
        self.check_case('manifest-cli-restore')

    def test_fifo_swap_cannot_stall_recursive_inventory(self):
        self.check_case('inventory-child')

    def test_fifo_swap_cannot_stall_root_file_inventory(self):
        self.check_case('inventory-root')

    def test_fifo_swap_cannot_stall_access_probe(self):
        self.check_case('access-race')
