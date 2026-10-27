#!/usr/bin/env python3
"""Build a noarch RPM using native rpmbuild and explicit source inputs."""
import argparse
import gzip
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from install_payload import version, package_version


def build(root, output, release='1'):
    if not re.fullmatch(r'[1-9][0-9]*', release):
        raise ValueError('Package release must be a positive integer')
    sys.path.insert(0, str(root / 'scripts'))
    import build_archives
    build_archives.SOURCE_ROOT = root
    output.mkdir(parents=True, exist_ok=True)
    native_version = package_version(version(root), 'rpm')
    with tempfile.TemporaryDirectory(prefix='xdg-audit-rpm-') as temporary:
        top = Path(temporary)
        for name in ('SOURCES', 'SPECS', 'BUILD', 'RPMS', 'SRPMS', 'BUILDROOT'):
            (top / name).mkdir()
        with (top / 'SOURCES/xdg-audit-source.tar.gz').open('wb') as stream:
            with gzip.GzipFile(fileobj=stream, mode='wb', mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w') as archive:
                    for path in build_archives.inputs():
                        raw = path.read_bytes()
                        entry = tarfile.TarInfo('xdg-audit-source/' + str(path.relative_to(root)))
                        entry.size, entry.mode = len(raw), 0o644
                        archive.addfile(entry, io.BytesIO(raw))
        spec = (root / 'packaging/rpm/xdg-audit.spec.in').read_text().replace(
            '@VERSION@', native_version).replace('@RELEASE@', release)
        spec_path = top / 'SPECS/xdg-audit.spec'
        spec_path.write_text(spec)
        subprocess.run(['rpmbuild', '-bb', '--define', '_topdir ' + str(top),
                        '--define', '_build_id_links none', str(spec_path)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': os.environ.get('SOURCE_DATE_EPOCH', '0')})
        packages = list((top / 'RPMS/noarch').glob('xdg-audit-*.rpm'))
        if len(packages) != 1:
            raise ValueError('Expected one noarch package')
        result = output / packages[0].name
        shutil.copyfile(packages[0], result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--release', default='1')
    args = parser.parse_args()
    print(build(args.source_root.resolve(), args.output_dir.resolve(), args.release))
