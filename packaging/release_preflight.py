#!/usr/bin/env python3
"""Validate a committed release request and an existing unattended signing key.

Only public readiness metadata is returned. Private key data is supplied on
stdin to GnuPG in an isolated temporary keyring, never as a command argument.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from check_version import check
from install_payload import reviewed_files, validate_inputs, version

ROOT = Path(__file__).resolve().parents[1]
REQUEST = '.github/release-request.json'


def git(root, *arguments):
    return subprocess.check_output(['git', '-C', str(root), *arguments], stderr=subprocess.PIPE)


def release_request(root, commit, requested_version=''):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Release commit must be a full SHA')
    if git(root, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('Checkout does not match the release commit')
    path = root / REQUEST
    if not path.exists():
        if requested_version:
            raise ValueError('Commit a release request before creating a version tag')
        return None
    validate_inputs(root, [REQUEST])
    if path.stat().st_size > 4096:
        raise ValueError('Release request is too large')
    request = json.loads(path.read_text())
    if (not isinstance(request, dict) or
            set(request) != {'version', 'accepted_application_sha', 'owner_acceptance'} or
            not isinstance(request['accepted_application_sha'], str) or
            not re.fullmatch(r'[0-9a-f]{40}', request['accepted_application_sha']) or
            not isinstance(request['version'], str) or
            not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-(?:rc|dev)[0-9]+)?', request['version']) or
            not isinstance(request['owner_acceptance'], str) or
            not request['owner_acceptance'].startswith('docs/') or
            not request['owner_acceptance'].endswith('.md')):
        raise ValueError('Malformed release request')
    validate_inputs(root, [request['owner_acceptance']])
    current = version(root)
    if requested_version and requested_version != request['version']:
        raise ValueError('Requested version does not match the committed owner approval')
    if request['version'] != current:
        if requested_version:
            raise ValueError('Release request does not match source VERSION')
        return None  # An old request never authorizes a different version.
    check(root, 'v' + current)
    return request


def verify_accepted_runtime(root, request):
    """Documentation/release preparation cannot inherit new application code."""
    accepted = request['accepted_application_sha']
    old_manifest = json.loads(git(root, 'show', accepted + ':scripts/archive-files.json'))
    old_runtime = {name for name in old_manifest if Path(name).parent == Path('.')
                   and name.startswith('xdg_') and name.endswith('.py')}
    old_runtime.update(('assets/xdg-audit.png', 'assets/xdg-audit-128.png',
                        'assets/io.github.xdgaudit.png', 'scripts/install_retention_timer.py'))
    current_runtime = set(reviewed_files(root))
    if current_runtime != old_runtime:
        raise ValueError('Application runtime changed since owner acceptance')
    for name in sorted(current_runtime):
        if (root / name).read_bytes() != git(root, 'show', accepted + ':' + name):
            raise ValueError('Application file changed since owner acceptance: ' + name)
    if git(root, 'status', '--porcelain').strip():
        raise ValueError('Release checkout must be clean')


def signing_report(private_key, expected):
    """Probe an existing signer without changing the caller's GnuPG home."""
    result = {'ready': False, 'missing': []}
    if not private_key.strip():
        result['missing'].append('PACKAGES_SIGNING_KEY')
    if not expected.strip():
        result['missing'].append('PACKAGES_SIGNING_FINGERPRINT')
    if result['missing']:
        return result
    expected = expected.strip().upper()
    if not re.fullmatch(r'[0-9A-F]{40}|[0-9A-F]{64}', expected):
        return {**result, 'error': 'invalid_fingerprint'}
    if not shutil.which('gpg'):
        return {**result, 'error': 'gnupg_unavailable'}
    stage = 'key_import_failed'
    with tempfile.TemporaryDirectory(prefix='xdg-release-preflight-') as temporary:
        os.chmod(temporary, 0o700)
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': temporary,
               'GNUPGHOME': temporary, 'LC_ALL': 'C'}
        if os.environ.get('RUNNER_TRACKING_ID'):
            env['RUNNER_TRACKING_ID'] = os.environ['RUNNER_TRACKING_ID']
        prefix = ['gpg', '--no-options', '--batch', '--no-tty', '--homedir', temporary,
                  '--pinentry-mode', 'loopback', '--passphrase', '', '--no-auto-key-retrieve']

        def run(arguments, **kwargs):
            return subprocess.run([*prefix, *arguments], env=env, capture_output=True,
                                  check=True, timeout=30, **kwargs).stdout
        try:
            run(['--import'], input=private_key.encode('utf-8'))
            stage = 'signing_key_mismatch'
            listing = run(['--with-colons', '--list-secret-keys', expected]).decode()
            primary = []
            want_fingerprint = False
            for line in listing.splitlines():
                fields = line.split(':')
                if fields[0] in ('sec', 'ssb'):
                    want_fingerprint = fields[0] == 'sec'
                elif fields[0] == 'fpr' and want_fingerprint:
                    primary.append(fields[9])
                    want_fingerprint = False
            if expected not in primary:
                return {**result, 'error': stage}
            stage = 'unattended_signing_failed'
            message = Path(temporary) / 'probe.txt'
            signature = Path(temporary) / 'probe.asc'
            message.write_bytes(b'xdg-audit release signing preflight\n')
            run(['--yes', '--local-user', expected, '--digest-algo', 'SHA256', '--armor',
                 '--output', str(signature), '--detach-sign', str(message)])
            stage = 'signature_verification_failed'
            run(['--verify', str(signature), str(message)])
            return {**result, 'ready': True, 'signing_fingerprint': expected}
        except (OSError, UnicodeError, subprocess.SubprocessError):
            # GnuPG stderr may contain key UIDs or malformed input. Keep the
            # public report to fixed error codes, never raw subprocess output.
            return {**result, 'error': stage}
        finally:
            try:
                subprocess.run(['gpgconf', '--homedir', temporary, '--kill', 'gpg-agent'],
                               env=env, capture_output=True, timeout=5, check=False)
            except (OSError, subprocess.SubprocessError):
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('request', 'runtime', 'signing'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--commit')
    parser.add_argument('--requested-version', default='')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.mode == 'signing':
        secret = os.environ.pop('PACKAGES_SIGNING_KEY', '')
        result = signing_report(secret, os.environ.get('PACKAGES_SIGNING_FINGERPRINT', ''))
        if args.report:
            args.report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, sort_keys=True))
        return 0 if result['ready'] else 1
    request = release_request(args.root, args.commit or '', args.requested_version)
    if args.mode == 'runtime':
        if request is None:
            raise ValueError('No release request matches this source version')
        verify_accepted_runtime(args.root, request)
        print('Application runtime matches accepted commit ' + request['accepted_application_sha'])
    elif args.github_output:
        with args.github_output.open('a') as output:
            output.write('requested=' + ('true' if request else 'false') + '\n')
            if request:
                output.write('version=' + request['version'] + '\n')
                output.write('commit=' + args.commit + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
