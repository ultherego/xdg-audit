#!/usr/bin/env python3
"""Exercise production signing/publication against a temporary local Git remote.

Never contacts a publishing service. Uses an ephemeral test key and previously
tested package artifacts; no production credential or repository is needed.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from install_payload import version

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='xdg-publish-rehearsal-') as temporary:
        base = Path(temporary)
        gnupg = base / 'offline-test-key'
        gnupg.mkdir(mode=0o700)
        env = dict(os.environ, GNUPGHOME=str(gnupg))
        def run(command, **kwargs):
            return subprocess.run([str(arg) for arg in command], check=True, env=env, **kwargs)
        run(['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '',
             '--quick-generate-key', 'xdg-audit disposable publication rehearsal',
             'rsa3072', 'sign', '1d'])
        listing = subprocess.check_output(['gpg', '--batch', '--with-colons', '--list-secret-keys'],
                                          text=True, env=env)
        fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
        private = subprocess.check_output(['gpg', '--batch', '--armor', '--export-secret-keys', fingerprint],
                                          env=env).decode()
        remote, checkout = base / 'origin.git', base / 'source'
        run(['git', 'init', '--bare', remote])
        run(['git', 'init', '--initial-branch=main', checkout])
        run(['git', '-C', checkout, 'config', 'user.name', 'Disposable test'])
        run(['git', '-C', checkout, 'config', 'user.email', 'fixture@example.invalid'])
        (checkout / 'README').write_text('Disposable publication fixture\n')
        run(['git', '-C', checkout, 'add', 'README'])
        run(['git', '-C', checkout, 'commit', '-m', 'Initialize disposable publication fixture'])
        run(['git', '-C', checkout, 'remote', 'add', 'origin', remote])
        run(['git', '-C', checkout, 'push', 'origin', 'main'])
        publish_env = dict(env, GITHUB_REPOSITORY='ultherego/xdg-audit', GITHUB_REF_TYPE='tag',
                           GITHUB_REF_NAME='v' + version(ROOT),
                           GITHUB_SHA=os.environ['GITHUB_SHA'], PACKAGES_SIGNING_KEY=private,
                           PACKAGES_SIGNING_FINGERPRINT=fingerprint, PUBLISH_NEW='true')
        def publish(number, *, refresh=False, reject=False):
            release = base / ('release-' + str(number))
            result = subprocess.run(['python3', '-B', str(ROOT / 'packaging/publish_repository.py'),
                '--work-dir', str(base / ('public-' + str(number))),
                '--artifact-dir', str(args.artifact_dir.resolve()), '--release-dir', str(release)],
                cwd=checkout, env={**publish_env, 'PUBLISH_NEW': 'false' if refresh else 'true'},
                capture_output=reject, text=reject)
            if reject:
                assert result.returncode != 0 and 'checksum mismatch' in result.stderr, result.stderr
            else:
                result.check_returncode()
            return release
        first = publish(1)
        run(['gpgv', '--keyring', first / 'xdg-audit-keyring.gpg',
             first / 'SHA256SUMS.asc', first / 'SHA256SUMS'])
        second = publish(2)
        for name in ('BUILD.json', next(first.glob('*.rpm')).name):
            assert (first / name).read_bytes() == (second / name).read_bytes(), name
        publish(3, refresh=True)
        # Corruption in previously published public files must block renewal.
        corrupt = base / 'corrupt'
        run(['git', 'clone', '--branch', 'packages', remote, corrupt])
        run(['git', '-C', corrupt, 'config', 'user.name', 'Disposable test'])
        run(['git', '-C', corrupt, 'config', 'user.email', 'fixture@example.invalid'])
        (corrupt / 'xdg-audit-key.asc').write_text('forged public bytes')
        run(['git', '-C', corrupt, 'add', 'xdg-audit-key.asc'])
        run(['git', '-C', corrupt, 'commit', '-m', 'Inject disposable corruption fixture'])
        run(['git', '-C', corrupt, 'push', 'origin', 'HEAD:packages'])
        publish(4, refresh=True, reject=True)
        for path in (base / 'public-2').rglob('*'):
            if path.is_file() and path.name != '.git':
                assert b'BEGIN PGP PRIVATE KEY BLOCK' not in path.read_bytes()
        run(['gpgconf', '--kill', 'gpg-agent'])
    print('PASS production publication, signatures, immutable rerun, refresh and corruption refusal (local remote)')


if __name__ == '__main__':
    main()
