#!/usr/bin/env python3
"""Publish a previously tested recipe with a dedicated AUR SSH credential."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    private = os.environ.pop('AUR_SSH_PRIVATE_KEY', '')
    hosts = os.environ.pop('AUR_KNOWN_HOSTS', '')
    if not private or not hosts:
        raise ValueError('Configure the dedicated AUR SSH key and independently verified known_hosts')
    with tempfile.TemporaryDirectory(prefix='xdg-aur-publish-') as temporary:
        base = Path(temporary)
        key = base / 'key'
        key.write_text(private + '\n')
        key.chmod(0o600)
        known = base / 'known_hosts'
        known.write_text(hosts + '\n')
        env = dict(os.environ, GIT_SSH_COMMAND=(
            'ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes '
            '-o UserKnownHostsFile=' + shlex.quote(str(known)) + ' -i ' + shlex.quote(str(key))))
        root = base / 'aur'
        def run(*command, **kwargs):
            return subprocess.run(command, env=env, check=True, **kwargs)
        run('git', '-c', 'init.defaultBranch=master', 'clone',
            'ssh://aur@aur.archlinux.org/xdg-audit.git', str(root))
        with zipfile.ZipFile(args.bundle) as bundle:
            if set(bundle.namelist()) != {'PKGBUILD', '.SRCINFO', 'LICENSE'}:
                raise ValueError('Unexpected AUR recipe bundle')
            for name in bundle.namelist():
                target = root / name
                if target.is_symlink():
                    raise ValueError('Refusing a symlink in the existing AUR repository')
                target.write_bytes(bundle.read(name))
        run('git', '-C', str(root), 'config', 'user.name', 'Ulther Ego')
        run('git', '-C', str(root), 'config', 'user.email', 'ultherego@users.noreply.github.com')
        run('git', '-C', str(root), 'add', '--', 'PKGBUILD', '.SRCINFO', 'LICENSE')
        changed = subprocess.run(['git', '-C', str(root), 'diff', '--cached', '--quiet'], env=env)
        if changed.returncode == 0:
            print('AUR recipe already matches this release')
            return
        if changed.returncode != 1:
            raise RuntimeError('Could not inspect staged AUR changes')
        run('git', '-C', str(root), 'commit', '-m', 'Update xdg-audit release recipe')
        run('git', '-C', str(root), 'push', 'origin', 'HEAD:master')


if __name__ == '__main__':
    main()
