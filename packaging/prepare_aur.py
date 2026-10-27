#!/usr/bin/env python3
"""Prepare a checksum-pinned release PKGBUILD from the exact source archive."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil

from install_payload import package_version, version


def prepare(root, archive, output, release='1'):
    source_version = version(root)
    if not re.fullmatch(r'[1-9][0-9]*', release):
        raise ValueError('Package release must be a positive integer')
    if archive.name != f'xdg-audit-{source_version}.tar.gz' or archive.is_symlink():
        raise ValueError('Use the exact versioned source archive')
    output.mkdir(parents=True, exist_ok=True)
    template = (root / 'packaging/arch/PKGBUILD.release.in').read_text()
    values = {'SOURCE_VERSION': source_version,
              'VERSION': package_version(source_version, 'arch'),
              'RELEASE': release, 'SHA256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    for key, value in values.items():
        template = template.replace('@' + key + '@', value)
    (output / 'PKGBUILD').write_text(template)
    shutil.copyfile(root / 'LICENSE', output / 'LICENSE')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--release', default='1')
    args = parser.parse_args()
    prepare(args.source_root.resolve(), args.archive, args.output_dir, args.release)
