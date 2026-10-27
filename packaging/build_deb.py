#!/usr/bin/env python3
"""Build an architecture-independent DEB from the reviewed runtime payload."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from install_payload import stage, version, package_version


def build(root, output, release='1'):
    if not re.fullmatch(r'[1-9][0-9]*', release):
        raise ValueError('Package release must be a positive integer')
    output.mkdir(parents=True, exist_ok=True)
    native_version = package_version(version(root), 'deb')
    result = output / f'xdg-audit_{native_version}-{release}_all.deb'
    with tempfile.TemporaryDirectory(prefix='xdg-audit-deb-') as temporary:
        payload = Path(temporary) / 'payload'
        stage(root, payload)
        metadata = payload / 'DEBIAN'
        metadata.mkdir()
        control = (root / 'packaging/debian/control.in').read_text().replace(
            '@VERSION@', native_version).replace('@RELEASE@', release)
        size = sum(path.stat().st_size for path in payload.rglob('*') if path.is_file())
        (metadata / 'control').write_text(control + f'Installed-Size: {(size + 1023) // 1024}\n')
        os.chmod(metadata, 0o755)
        env = {**os.environ, 'SOURCE_DATE_EPOCH': os.environ.get('SOURCE_DATE_EPOCH', '0')}
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(payload), str(result)],
                       env=env, check=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--release', default='1')
    args = parser.parse_args()
    print(build(args.source_root.resolve(), args.output_dir.resolve(), args.release))
