#!/usr/bin/env python3
"""Real Btrfs remount, snapshot refusal and explicit recovery in disposable CI.

Only the root fixture manager mounts/formats its own newly created image files.
Every application operation runs in a regular-user child. Installed inventory
alone is synthetic; no filesystem stat, hash, mount or ioctl is mocked.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def worker(phase, home):
    import xdg_audit as audit
    from xdg_filesystem import filesystem_identity
    from xdg_quarantine_lifecycle import QuarantineIdentityMismatch
    audit.check_no_root()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and home.is_absolute() and
            home.resolve(strict=True).is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve(strict=True)),
            'Worker HOME must be the disposable Actions mount fixture')
    state = json.load(sys.stdin)
    roots = audit.xdg_roots(home)
    content = b'Btrfs remount fixture\x00\xff\n'
    if phase == 'prepare':
        (roots['config']).mkdir(parents=True)
        sentinel = home / 'outside-sentinel'
        sentinel.write_bytes(b'never delete or modify')
        runs = []
        inventory = ({'unrelated-package'}, set(), set(), set(), set(), set(), set(), set())
        for purpose in ['purge', 'restore', 'legacy']:
            source = roots['config'] / ('xdg-btrfs-disposable-' + purpose)
            source.mkdir()
            (source / 'settings').write_bytes(content)
            (source / 'outside-link').symlink_to(sentinel)
            info = source.stat()
            entry = audit.Item('config', source, state='UNKNOWN', removable=False,
                               identity=(info.st_dev, info.st_ino, 16384))
            with patch.object(audit, 'read_active_names', return_value=inventory):
                moved = audit.commit_quarantine([entry], roots, home, allow_uncertain=True, emit=lambda _: None)
            require(len(moved['moved']) == 1, 'Btrfs MOVE did not complete')
            manifest = Path(moved['manifest'])
            payload = json.loads(manifest.read_text())
            row = payload['items'][0]
            require(row.get('filesystem_identity') is not None and
                    row['filesystem_identity'] == filesystem_identity(Path(row['destination'])),
                    'MOVE did not record actual Btrfs filesystem/subvolume identity')
            if purpose == 'legacy':
                row.pop('filesystem_identity')  # Model a pre-feature sealed v3 journal.
                manifest.write_text(json.dumps(payload))
            runs.append({'id': moved['run_id'], 'purpose': purpose, 'manifest': str(manifest),
                         'destination': row['destination'], 'source': row['source']})
        state = {'old_device': home.stat().st_dev, 'binding': filesystem_identity(home), 'runs': runs}
    elif phase == 'snapshot':
        current = filesystem_identity(home)
        require(current['fsid'] == state['binding']['fsid'], 'snapshot is not in the same filesystem')
        require(current['subvolume_id'] != state['binding']['subvolume_id'], 'snapshot did not change subvolume ID')
        require(current['subvolume_uuid'] != state['binding']['subvolume_uuid'], 'snapshot retained subvolume UUID')
        for run in state['runs']:
            if run['purpose'] == 'legacy':
                continue  # Legacy journals cannot prove historical FS/subvolume identity.
            manifest = Path(run['manifest'])
            before = manifest.read_bytes()
            try:
                audit.preview_device_revalidation(home, roots, run['id'])
            except ValueError as error:
                require('Persistent filesystem/subvolume' in str(error), 'snapshot refusal used the wrong reason')
            else:
                raise AssertionError('same-inode/same-hash snapshot was accepted despite different subvolume identity')
            require(manifest.read_bytes() == before, 'snapshot refusal changed its journal')
        state['snapshot_refused'] = True
    else:
        current = home.stat().st_dev
        require(current != state['old_device'], 'real Btrfs st_dev did not change across fixture remount')
        require(filesystem_identity(home) == state['binding'], 'original persistent identity changed across remount')
        for run in state['runs']:
            manifest, destination = Path(run['manifest']), Path(run['destination'])
            before = manifest.read_bytes()
            try:
                audit.purge_quarantine_run(home, roots, run['id'], dry_run=False, emit=lambda _: None)
            except QuarantineIdentityMismatch as error:
                require(error.expected[0] == state['old_device'] and error.actual[0] == current,
                        'remount refusal did not report the actual device transition')
                require(error.expected[1:] == error.actual[1:], 'fixture changed inode/type across remount')
            else:
                raise AssertionError('old binding authorized deletion without explicit revalidation')
            require(manifest.read_bytes() == before, 'blocked PURGE changed the journal')
            original = (destination / 'settings').read_bytes()
            (destination / 'settings').write_bytes(b'changed contents must block revalidation')
            try:
                audit.preview_device_revalidation(home, roots, run['id'])
            except ValueError:
                pass
            else:
                raise AssertionError('changed hashes were accepted for device revalidation')
            (destination / 'settings').write_bytes(original)
            diagnosis = audit.diagnose_quarantine_access(home, roots, run['id'])
            require(diagnosis['device_revalidation']['eligible'], 'actual Btrfs diagnosis lost eligible device-only change')
            require(diagnosis['issues'][0]['filesystem']['filesystem_identity'] == state['binding'],
                    'diagnosis did not report actual Btrfs ioctl identity')
            preview = audit.preview_device_revalidation(home, roots, run['id'])
            require(preview['historical_binding_verified'] == (run['purpose'] != 'legacy'),
                    'legacy historical-identity limitations were misreported')
            audit.revalidate_quarantine_device(home, roots, run['id'], preview['approval_token'])
            require((destination / 'settings').read_bytes() == content, 'revalidation changed payload bytes')
            receipt = json.loads(manifest.read_text())['device_revalidations'][0]
            require(not receipt['purge_authorized'], 'revalidation granted PURGE')
            if run['purpose'] == 'restore':
                restored = audit.restore_quarantine_run(home, roots, run['id'], emit=lambda _: None)
                require(restored['restored'] == 1, 'RESTORE after actual remount/revalidation failed')
                require((Path(run['source']) / 'settings').read_bytes() == content, 'RESTORE changed bytes')
            else:
                audit.purge_quarantine_run(home, roots, run['id'], dry_run=False, emit=lambda _: None)
                require(not destination.exists(), 'separately confirmed PURGE retained fixture')
        require((home / 'outside-sentinel').read_bytes() == b'never delete or modify', 'outside sentinel changed')
        state.update(new_device=current, payload_sha256=sha256(content).hexdigest(),
                     revalidation_and_separate_purge_restore='PASS', sentinel='unchanged')
    print(json.dumps(state))


def manage(args):
    require(os.getuid() == 0 and os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REPOSITORY') == 'ultherego/xdg-audit',
            'Root fixture setup is restricted to this project in disposable GitHub Actions')
    require(args.uid > 0 and args.gid > 0, 'Application checks must use a regular user')
    runner_temp = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    work = args.work_dir
    require(work.is_absolute() and work.parent.resolve(strict=True) == runner_temp and not work.exists(),
            'Use a new direct child of RUNNER_TEMP for all image/mount fixtures')
    work.mkdir(mode=0o755)
    mounts, held = [], []

    def command(*values):
        return subprocess.run(values, check=True, text=True, capture_output=True).stdout

    def mount(source, target, *options):
        command('mount', *options, str(source), str(target))
        mounts.append(target)

    def unmount(target):
        command('umount', str(target))
        mounts.remove(target)

    def child(phase, home, state):
        env = {**os.environ, 'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
               'XDG_CACHE_HOME': str(home / '.cache'), 'XDG_DATA_HOME': str(home / '.local/share'),
               'XDG_STATE_HOME': str(home / '.local/state')}
        def regular_user():
            os.setgroups([])
            os.setgid(args.gid)
            os.setuid(args.uid)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', phase,
                                 '--home', str(home)], input=json.dumps(state), text=True,
                                capture_output=True, env=env, preexec_fn=regular_user, timeout=120)
        if result.returncode:
            raise AssertionError('Unprivileged Btrfs ' + phase + ' failed:\n' + result.stdout + result.stderr)
        return json.loads(result.stdout)

    try:
        first, holder = work / 'first', work / 'holder'
        first.mkdir()
        holder.mkdir()
        images = []
        for name in ('original.img', 'holder.img'):
            path = work / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.ftruncate(fd, 1024 * 1024 * 1024)
            finally:
                os.close(fd)
            command('mkfs.btrfs', '-q', str(path))
            images.append(path)
        mount(images[0], first, '-o', 'loop')
        command('btrfs', 'subvolume', 'create', str(first / 'home'))
        home = first / 'home' / 'user'
        home.mkdir()
        os.chown(home, args.uid, args.gid)
        state = child('prepare', home, {})
        unmount(first)
        # Keep another filesystem/subvolumes active so the kernel cannot reuse
        # every anonymous device number for the original filesystem's roots.
        mount(images[1], holder, '-o', 'loop')
        held.append(os.open(holder, os.O_RDONLY | os.O_DIRECTORY))
        for number in range(8):
            sub = holder / ('occupy-' + str(number))
            command('btrfs', 'subvolume', 'create', str(sub))
            held.append(os.open(sub, os.O_RDONLY | os.O_DIRECTORY))
        mount(images[0], first, '-o', 'loop')
        require(home.stat().st_dev != state['old_device'], 'fixture could not produce a real device renumbering')
        clone = first / 'snapshot'
        command('btrfs', 'subvolume', 'snapshot', str(first / 'home'), str(clone))
        mount(clone, first / 'home', '--bind')
        state = child('snapshot', home, state)
        unmount(first / 'home')
        state = child('verify', home, state)
        state['kernel'] = os.uname().release
        state['btrfs_tools'] = command('btrfs', 'version').strip()
        state['filesystem_operations'] = 'actual unprivileged syscalls; no filesystem mocks'
        state['installed_inventory'] = 'synthetic; native provider CI is separate'
        # Paths name only disposable runner fixtures; never archive their data.
        state.pop('runs')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state, indent=2))
    finally:
        for fd in held:
            os.close(fd)
        failures = []
        for target in list(reversed(mounts)):
            try:
                unmount(target)
            except subprocess.CalledProcessError:
                failures.append(str(target))
        if failures:
            raise RuntimeError('Unmount failed; fixtures retained without recursive cleanup: ' + ', '.join(failures))
        shutil.rmtree(work)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('prepare', 'snapshot', 'verify'))
    parser.add_argument('--home', type=Path)
    parser.add_argument('--uid', type=int)
    parser.add_argument('--gid', type=int)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.home)
    else:
        if any(value is None for value in (args.uid, args.gid, args.work_dir, args.output)):
            parser.error('Manager requires --uid, --gid, --work-dir and --output')
        manage(args)
