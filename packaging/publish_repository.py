#!/usr/bin/env python3
"""Publish authenticated package snapshots from tested Actions artifacts.

The packages branch contains only public files. A worktree commit publishes
metadata together; historical by-hash indexes and packages remain available.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_version import check
from install_payload import version
import repository

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def verified_files(directory):
    result = []
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        relative = Path(name)
        if (relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts or
                relative.as_posix() != name):
            raise ValueError('Unsafe checksum member')
        path = directory / relative
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError('Symlink in public package snapshot')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Package snapshot checksum mismatch: ' + name)
        result.append(path)
    if not result or len(result) != len(set(result)):
        raise ValueError('Empty or duplicate checksum manifest')
    return result


def publish(work, artifacts, release_dir, key, publish_new):
    if publish_new:
        if os.environ.get('GITHUB_REF_TYPE') != 'tag':
            raise ValueError('New packages can only be published from a version tag')
        check(ROOT, os.environ.get('GITHUB_REF_NAME'))
    repository_name = os.environ['GITHUB_REPOSITORY']
    if repository_name != 'ultherego/xdg-audit':
        raise ValueError('Review repository URLs before publishing from a fork')
    remote = subprocess.run(['git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/packages'],
                            capture_output=True, text=True)
    if remote.returncode == 0:
        run(['git', 'fetch', '--no-tags', 'origin', 'refs/heads/packages'])
        run(['git', 'worktree', 'add', '--detach', work, 'FETCH_HEAD'])
        trusted = work.parent / 'xdg-package-trusted.gpg'
        trusted.write_bytes(repository.command(['gpg', '--batch', '--export', key]))
        run(['gpgv', '--keyring', trusted, work / 'SHA256SUMS.asc', work / 'SHA256SUMS'])
        verified_files(work)
    elif remote.returncode == 2 and publish_new:
        run(['git', 'worktree', 'add', '--detach', work, 'HEAD'])
        run(['git', '-C', work, 'switch', '--orphan', 'packages'])
    else:
        raise RuntimeError('Cannot read the packages branch; first publish requires a version tag')
    url = 'https://raw.githubusercontent.com/' + repository_name + '/packages'
    published = []
    if publish_new:
        inputs = [path for sums in sorted(artifacts.rglob('SHA256SUMS'))
                  for path in verified_files(sums.parent)]
        debs = [p for p in inputs if p.suffix == '.deb']
        rpms = [p for p in inputs if p.suffix == '.rpm']
        if len(debs) != 1 or len(rpms) != 1:
            raise ValueError('Expected exactly one tested DEB and RPM artifact')
        suite = 'candidate' if '-' in version(ROOT) else 'stable'
        tag = os.environ['GITHUB_REF_NAME']
        receipt = work / 'releases' / (tag + '.json')
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        if len(hashes) != len(inputs):
            raise ValueError('Duplicate release artifact names')
        if receipt.exists():
            old = json.loads(receipt.read_text())
            if old['inputs'] != hashes or old['commit'] != os.environ['GITHUB_SHA']:
                raise ValueError('A published version is immutable; use a new version tag')
        else:
            repository.build(work, key, url, suite=suite, debs=debs, rpms=rpms)
            receipt.parent.mkdir(exist_ok=True)
            receipt.write_text(json.dumps({'tag': tag, 'commit': os.environ['GITHUB_SHA'],
                                           'inputs': hashes}, indent=2, sort_keys=True) + '\n')
        release_dir.mkdir(parents=True, exist_ok=True)
        for path in inputs:
            if path.suffix == '.rpm':
                path = work / 'rpm' / suite / 'Packages' / path.name
            shutil.copyfile(path, release_dir / path.name)
        shutil.copyfile(receipt, release_dir / 'BUILD.json')
        published = [suite]
    # Refresh both channels, including when no new release exists. APT clients
    # reject metadata after 30 days, so the weekly workflow renews signatures.
    for suite in ('candidate', 'stable'):
        if (suite in published or (work / 'deb/dists' / suite).exists() or
                (work / 'rpm' / suite).exists()):
            repository.build(work, key, url, suite=suite)
    if publish_new:
        for name in ('xdg-audit-keyring.gpg', 'xdg-audit-key.asc', 'signing-key-fingerprint.txt'):
            shutil.copyfile(work / name, release_dir / name)
        sums = release_dir / 'SHA256SUMS'
        sums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                                for p in sorted(release_dir.iterdir())
                                if p.name not in ('SHA256SUMS', 'SHA256SUMS.asc')))
        repository.sign(sums, key)
        verified_files(release_dir)
    run(['git', '-C', work, 'config', 'user.name', 'github-actions[bot]'])
    run(['git', '-C', work, 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'])
    run(['git', '-C', work, 'add', '--all'])
    run(['git', '-C', work, 'commit', '-m', 'Publish signed xdg-audit package snapshot'])
    run(['git', '-C', work, 'push', 'origin', 'HEAD:refs/heads/packages'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    parser.add_argument('--release-dir', type=Path, required=True)
    args = parser.parse_args()
    secret = os.environ.pop('PACKAGES_SIGNING_KEY', '')
    expected = os.environ.get('PACKAGES_SIGNING_FINGERPRINT', '').upper()
    if not secret or not expected:
        raise ValueError('Configure PACKAGES_SIGNING_KEY and PACKAGES_SIGNING_FINGERPRINT before tagging a release')
    with tempfile.TemporaryDirectory(prefix='xdg-package-signing-') as temporary:
        os.chmod(temporary, 0o700)
        os.environ['GNUPGHOME'] = temporary
        run(['gpg', '--batch', '--import'], input=secret.encode(), stdout=subprocess.DEVNULL)
        key = repository.fingerprint(expected)
        try:
            publish(args.work_dir, args.artifact_dir, args.release_dir, key,
                    os.environ.get('PUBLISH_NEW') == 'true')
        finally:
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], check=False)


if __name__ == '__main__':
    main()
