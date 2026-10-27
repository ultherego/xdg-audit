#!/usr/bin/env python3
"""Build signed APT/RPM repositories with an existing GnuPG signing key.

The output contains public material only. Supply GNUPGHOME separately; this
script neither creates production keys nor accepts private keys as arguments.
"""
import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit


def command(args, **kwargs):
    return subprocess.check_output(args, **kwargs)


def validate_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            any(char.isspace() for char in value)):
        raise ValueError('Use an HTTPS repository root without credentials, query or fragment')
    return value.rstrip('/')


def safe_output(root):
    if not root.is_absolute() or root == Path('/') or '..' in root.parts:
        raise ValueError('Use an explicit absolute repository staging directory')
    current = Path('/')
    for part in root.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError('Symlink in repository output path')
    root.mkdir(parents=True, exist_ok=True)
    files = {'xdg-audit-keyring.gpg', 'xdg-audit-key.asc', 'signing-key-fingerprint.txt',
             'SHA256SUMS', 'SHA256SUMS.asc', '.git'}
    files.update('xdg-audit-' + suite + extension for suite in ('candidate', 'stable')
                 for extension in ('.sources', '.repo'))
    for path in root.iterdir():
        if path.name not in files and path.name not in ('deb', 'rpm', 'releases'):
            raise ValueError('Unexpected file in public repository staging directory: ' + path.name)
    if any(path.is_symlink() for path in root.rglob('*')):
        raise ValueError('Symlink in existing repository output')


def fingerprint(value):
    if not re.fullmatch(r'[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}', value):
        raise ValueError('Use the full signing-key fingerprint')
    value = value.upper()
    listing = command(['gpg', '--batch', '--with-colons', '--list-secret-keys', value]).decode()
    if not any(line.startswith('fpr:') and line.split(':')[9] == value for line in listing.splitlines()):
        raise ValueError('Signing secret key does not match the supplied fingerprint')
    return value


def sign(path, key, *, clear=False):
    destination = path.with_name('InRelease') if clear else path.with_name(path.name + '.asc')
    subprocess.run(['gpg', '--batch', '--yes', '--local-user', key, '--digest-algo', 'SHA256',
                    '--armor', '--output', str(destination),
                    '--clearsign' if clear else '--detach-sign', str(path)], check=True)
    return destination


def immutable_copy(source, target):
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 512 * 1024 * 1024:
        raise ValueError('Invalid package input')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if source.read_bytes() != target.read_bytes():
            raise ValueError('Refusing to replace an existing package version: ' + target.name)
    else:
        shutil.copyfile(source, target)
    target.chmod(0o644)


def apt(root, packages, key, suite):
    base = root / 'deb'
    for package in packages:
        metadata = command(['dpkg-deb', '-f', str(package), 'Package', 'Version', 'Architecture']).decode()
        fields = dict(line.split(': ', 1) for line in metadata.splitlines())
        if (fields.get('Package') != 'xdg-audit' or fields.get('Architecture') != 'all' or
                not re.fullmatch(r'[0-9][0-9A-Za-z.+~:-]*', fields.get('Version', ''))):
            raise ValueError('Unexpected DEB identity')
        name = 'xdg-audit_' + fields['Version'] + '_all.deb'
        immutable_copy(package, base / 'pool' / suite / 'main/x/xdg-audit' / name)
    index = command(['apt-ftparchive', 'packages', 'pool/' + suite], cwd=base)
    distribution = base / 'dists' / suite
    for architecture in ('amd64', 'arm64', 'all'):
        directory = distribution / 'main' / ('binary-' + architecture)
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in (('Packages', index), ('Packages.gz', gzip.compress(index, mtime=0))):
            (directory / name).write_bytes(data)
            # Keep earlier by-hash indexes in subsequent publications so clients
            # with an older Release can finish fetching the immutable index.
            digest = hashlib.sha256(data).hexdigest()
            immutable = directory / 'by-hash/SHA256' / digest
            immutable.parent.mkdir(parents=True, exist_ok=True)
            immutable.write_bytes(data)
    options = {'Origin': 'xdg-audit', 'Label': 'xdg-audit', 'Suite': suite,
               'Codename': suite, 'Architectures': 'amd64 arm64 all', 'Components': 'main',
               'Acquire-By-Hash': 'yes',
               'Description': 'Signed xdg-audit packages',
               'Valid-Until': (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
                   '%a, %d %b %Y %H:%M:%S UTC')}
    args = ['apt-ftparchive']
    for name, value in options.items():
        args += ['-o', 'APT::FTPArchive::Release::' + name + '=' + value]
    args += ['release', str(distribution)]
    # Old signatures are excluded by apt-ftparchive's default index patterns.
    release = distribution / 'Release'
    release.unlink(missing_ok=True)
    release.write_bytes(command(args))
    sign(release, key, clear=True)
    subprocess.run(['gpg', '--batch', '--yes', '--local-user', key, '--digest-algo', 'SHA256',
                    '--armor', '--detach-sign', '--output', str(distribution / 'Release.gpg'),
                    str(release)], check=True)


def rpm(root, packages, key, suite):
    base = root / 'rpm' / suite
    for package in packages:
        identity = command(['rpm', '-qp', '--qf', '%{NAME} %{VERSION} %{RELEASE} %{ARCH}',
                            str(package)]).decode().split()
        if (len(identity) != 4 or identity[0] != 'xdg-audit' or identity[3] != 'noarch' or
                any(not re.fullmatch(r'[0-9A-Za-z.+~_-]+', part) for part in identity)):
            raise ValueError('Unexpected RPM identity')
        target = base / 'Packages' / ('-'.join(identity[:3]) + '.noarch.rpm')
        if target.exists():
            # Signed RPM bytes differ from the unsigned CI artifact. Refuse
            # replacement entirely; publish a new package release instead.
            raise ValueError('RPM version already published: ' + target.name)
        immutable_copy(package, target)
        subprocess.run(['rpmsign', '--define', '_openpgp_sign gpg',
                        '--define', '_openpgp_sign_id ' + key,
                        '--define', '_gpg_name ' + key,
                        '--define', '__gpg /usr/bin/gpg', '--addsign', str(target)], check=True)
    base.mkdir(parents=True, exist_ok=True)
    subprocess.run(['createrepo_c', '--checksum', 'sha256', '--general-compress-type', 'gz',
                    '--retain-old-md', '2', str(base)], check=True)
    sign(base / 'repodata/repomd.xml', key)


def build(root, key, url, *, suite='candidate', debs=(), rpms=()):
    if suite not in ('candidate', 'stable'):
        raise ValueError('Unsupported repository channel')
    url = validate_url(url)
    safe_output(root)
    key = fingerprint(key)
    previous = root / 'signing-key-fingerprint.txt'
    if previous.exists() and previous.read_text().strip() != key:
        raise ValueError('Signing-key rotation requires a separate reviewed migration')
    public = command(['gpg', '--batch', '--export', key])
    (root / 'xdg-audit-keyring.gpg').write_bytes(public)
    (root / 'xdg-audit-key.asc').write_bytes(command(['gpg', '--batch', '--armor', '--export', key]))
    previous.write_text(key + '\n')
    if debs or (root / 'deb/pool' / suite).is_dir():
        apt(root, debs, key, suite)
    if rpms or (root / 'rpm' / suite / 'Packages').is_dir():
        rpm(root, rpms, key, suite)
    (root / ('xdg-audit-' + suite + '.sources')).write_text(
        'Types: deb\nURIs: ' + url + '/deb\nSuites: ' + suite + '\nComponents: main\n'
        'Architectures: amd64 arm64\nSigned-By: /etc/apt/keyrings/xdg-audit.gpg\n')
    (root / ('xdg-audit-' + suite + '.repo')).write_text(
        '[xdg-audit-' + suite + ']\nname=xdg-audit (' + suite + ')\nbaseurl=' + url + '/rpm/' + suite +
        '\nenabled=1\ngpgcheck=1\nrepo_gpgcheck=1\nskip_if_unavailable=0\ngpgkey=' + url + '/xdg-audit-key.asc\n')
    # Publish receipts and checksums, never signing material or arbitrary output.
    names = sorted(path for path in root.rglob('*') if path.is_file() and
                   path.name not in ('SHA256SUMS', 'SHA256SUMS.asc') and '.git' not in path.parts)
    sums = root / 'SHA256SUMS'
    sums.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' +
                            path.relative_to(root).as_posix() + '\n' for path in names))
    sign(sums, key)
    return key


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--signing-key', required=True, help='Full existing secret-key fingerprint')
    parser.add_argument('--base-url', required=True, help='Public HTTPS root')
    parser.add_argument('--suite', choices=('candidate', 'stable'), default='candidate')
    parser.add_argument('--deb', type=Path, action='append', default=[])
    parser.add_argument('--rpm', type=Path, action='append', default=[])
    parser.add_argument('--refresh-existing', action='store_true',
                        help='Refresh existing metadata without replacing package versions')
    args = parser.parse_args()
    if not args.deb and not args.rpm and not args.refresh_existing:
        parser.error('Supply at least one native package')
    print(build(args.output_dir, args.signing_key, args.base_url, suite=args.suite,
                debs=args.deb, rpms=args.rpm))
