#!/usr/bin/env python3
"""Build, install, upgrade and remove packages inside a disposable CI container.

APT and DNF must authenticate locally generated test repositories. The signing
key exists only inside this test's temporary directory and is never published.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from install_payload import package_version, reviewed_files, version
from build_deb import build as build_deb
from build_rpm import build as build_rpm
from prepare_aur import prepare
import repository

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print('+ ' + ' '.join(str(arg) for arg in args), flush=True)
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def rejected(args):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, text=True)
    if result.returncode == 0:
        raise AssertionError('Tampered repository/package unexpectedly accepted')
    print('PASS tampered input refused:', result.stdout[-500:], result.stderr[-500:], flush=True)


def check_payload():
    installed = Path('/usr/lib/xdg-audit')
    actual = {path.relative_to(installed).as_posix() for path in installed.rglob('*') if path.is_file()}
    assert actual == set(reviewed_files(ROOT)), 'Unexpected installed runtime payload'
    for name in actual:
        assert (installed / name).read_bytes() == (ROOT / name).read_bytes(), name
    run(['desktop-file-validate', '/usr/share/applications/io.github.xdgaudit.desktop'])
    run(['runuser', '-u', 'package-test', '--', 'xvfb-run', '-a', '/usr/bin/python3',
         '-B', ROOT / 'packaging/smoke_installed.py', '--version', version(ROOT)])


def signing_key(work):
    home = work / 'gnupg'
    home.mkdir(mode=0o700)
    os.environ['GNUPGHOME'] = str(home)
    run(['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '',
         '--quick-generate-key', 'xdg-audit disposable CI key', 'rsa3072', 'sign', '1d'])
    listing = subprocess.check_output(['gpg', '--batch', '--with-colons', '--list-secret-keys'], text=True)
    return next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))


def archive_sources(output):
    run([sys.executable, ROOT / 'scripts/build_archives.py', '--output-dir', output])
    return output / ('xdg-audit-' + version(ROOT) + '.tar.gz')


def deb_cycle(work, output, key):
    first = build_deb(ROOT, output, '1')
    second = build_deb(ROOT, work / 'upgrade', '2')
    public = work / 'public'
    repository.build(public, key, 'https://example.invalid/xdg-audit', debs=[first])
    source = work / 'test.sources'
    source.write_text(f'Types: deb\nURIs: file:{public}/deb\nSuites: candidate\nComponents: main\n'
                      f'Signed-By: {public}/xdg-audit-keyring.gpg\n')
    lists = work / 'apt-lists'
    lists.mkdir()
    options = ['-o', 'Dir::Etc::sourcelist=' + str(source), '-o', 'Dir::Etc::sourceparts=-',
               '-o', 'Dir::State::lists=' + str(lists), '-o', 'APT::Update::Error-Mode=any',
               '-o', 'APT::Sandbox::User=root']
    def apt(*args):
        return ['apt-get', *options, *args]
    run(apt('update'))
    run(apt('install', '-y', '--no-install-recommends', 'xdg-audit'))
    check_payload()
    repository.build(public, key, 'https://example.invalid/xdg-audit', debs=[second])
    run(apt('update'))
    run(apt('install', '-y', '--no-install-recommends', 'xdg-audit'))
    installed = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'xdg-audit'], text=True)
    assert installed == package_version(version(ROOT), 'deb') + '-2'
    check_payload()
    target = public / 'deb/pool/candidate/main/x/xdg-audit' / second.name
    original = target.read_bytes()
    target.write_bytes(original + b'corrupted-package')
    rejected(apt('download', 'xdg-audit'))
    target.write_bytes(original)
    release = public / 'deb/dists/candidate/InRelease'
    release.write_text(release.read_text().replace('Origin: xdg-audit', 'Origin: forged-data'))
    shutil.rmtree(lists)
    lists.mkdir()
    rejected(apt('update'))
    run(['apt-get', 'remove', '--purge', '-y', 'xdg-audit'])


def rpm_cycle(work, output, key):
    first = build_rpm(ROOT, output, '1')
    second = build_rpm(ROOT, work / 'upgrade', '2')
    public = work / 'public'
    before = hashlib.sha256(first.read_bytes()).hexdigest()
    repository.build(public, key, 'https://example.invalid/xdg-audit', rpms=[first])
    assert hashlib.sha256(first.read_bytes()).hexdigest() == before, 'Signing changed original artifact'
    configuration = work / 'repos'
    configuration.mkdir()
    (configuration / 'xdg-audit.repo').write_text(
        '[xdg-audit]\nname=Disposable xdg-audit test repository\n'
        f'baseurl=file://{public}/rpm/candidate\nenabled=1\ngpgcheck=1\nrepo_gpgcheck=1\n'
        f'gpgkey=file://{public}/xdg-audit-key.asc\nmetadata_expire=0\n')
    options = ['--setopt=reposdir=' + str(configuration), '--setopt=install_weak_deps=False',
               '--setopt=cachedir=' + str(work / 'dnf-cache')]
    def dnf(*args):
        return ['dnf', '-y', *options, *args]
    run(dnf('install', 'xdg-audit'))
    check_payload()
    repository.build(public, key, 'https://example.invalid/xdg-audit', rpms=[second])
    run(dnf('--refresh', 'upgrade', 'xdg-audit'))
    installed = subprocess.check_output(['rpm', '-q', '--qf', '%{RELEASE}', 'xdg-audit'], text=True)
    assert installed.startswith('2'), installed
    check_payload()
    signed = next((public / 'rpm/candidate/Packages').glob('*-2*.rpm'))
    run(['rpmkeys', '--checksig', signed])
    corrupted = work / 'corrupted.rpm'
    data = bytearray(signed.read_bytes())
    data[-100] ^= 0xFF
    corrupted.write_bytes(data)
    rejected(['rpmkeys', '--checksig', corrupted])
    metadata = public / 'rpm/candidate/repodata/repomd.xml'
    metadata.write_bytes(metadata.read_bytes().replace(b'<revision>', b'<revision>forged', 1))
    shutil.rmtree(work / 'dnf-cache', ignore_errors=True)
    rejected(dnf('--refresh', 'makecache'))
    run(['rpm', '-e', 'xdg-audit'])


def arch_cycle(work, output):
    archive = archive_sources(work / 'sources')
    aur = work / 'aur'
    prepare(ROOT, archive, aur)
    shutil.copyfile(archive, aur / archive.name)
    # makepkg refuses root. Build in a private, unprivileged fixture directory.
    run(['chown', '-R', 'package-test:package-test', work])
    def makepkg(*args, **kwargs):
        return run(['runuser', '-u', 'package-test', '--', 'makepkg', *args], cwd=aur, **kwargs)
    makepkg('--noconfirm', '--cleanbuild', '--force')
    package = next(aur.glob('xdg-audit-*.pkg.tar.zst'))
    shutil.copyfile(package, output / package.name)
    metadata = subprocess.check_output(['runuser', '-u', 'package-test', '--',
                                        'makepkg', '--printsrcinfo'], cwd=aur)
    (aur / '.SRCINFO').write_bytes(metadata)
    with zipfile.ZipFile(output / 'xdg-audit-aur.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in ('PKGBUILD', '.SRCINFO', 'LICENSE'):
            bundle.write(aur / name, name)
    vcs = ROOT / 'packaging/arch'
    actual = subprocess.check_output(['runuser', '-u', 'package-test', '--',
                                      'makepkg', '--printsrcinfo'], cwd=vcs)
    assert actual == (vcs / '.SRCINFO').read_bytes(), 'Regenerate the VCS .SRCINFO'
    run(['pacman', '-U', '--noconfirm', package])
    check_payload()
    prepare(ROOT, archive, aur, '2')
    makepkg('--noconfirm', '--cleanbuild', '--force')
    upgraded = next(aur.glob('xdg-audit-*-2-any.pkg.tar.zst'))
    run(['pacman', '-U', '--noconfirm', upgraded])
    check_payload()
    run(['pacman', '-R', '--noconfirm', 'xdg-audit'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=('deb', 'rpm', 'arch'), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not Path('/.dockerenv').exists() or os.environ.get('CI') != 'true':
        raise RuntimeError('Native lifecycle checks require a disposable GitHub Actions container')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sentinel = Path('/home/package-test/package-sentinel')
    sentinel.write_bytes(b'package upgrade and removal must preserve user data')
    original = sentinel.read_bytes()
    with tempfile.TemporaryDirectory(prefix='xdg-native-ci-') as temporary:
        work = Path(temporary)
        work.chmod(0o755)
        if args.family == 'arch':
            arch_cycle(work, output)
        else:
            key = signing_key(work)
            {'deb': deb_cycle, 'rpm': rpm_cycle}[args.family](work, output, key)
    assert sentinel.read_bytes() == original
    assert not Path('/usr/bin/xdg-audit').exists()
    assert not Path('/usr/lib/xdg-audit').exists()
    assert not Path('/usr/share/applications/io.github.xdgaudit.desktop').exists()
    (output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in sorted(output.iterdir()) if path.name != 'SHA256SUMS'))
    print('PASS native build, authenticated installation, upgrade, GUI and removal:', args.family)


if __name__ == '__main__':
    main()
