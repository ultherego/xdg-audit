#!/usr/bin/env python3
"""Create deterministic, install-free xdg-audit source archives and SHA256SUMS.

Requires only Python 3.10+. Distributables do not require or install Qt/GTK.
The optional install_desktop.py script is included but is never run.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import zipfile

SOURCE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = 'scripts/archive-files.json'


def version() -> str:
    source = ast.parse((SOURCE_ROOT / 'xdg_audit.py').read_text(encoding='utf-8'))
    for node in source.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets):
                value = ast.literal_eval(node.value)
                if not isinstance(value, str) or not value or '/' in value or '\\' in value:
                    raise ValueError('Invalid application version')
                return value
    raise ValueError('VERSION constant not found')


def inputs() -> list[Path]:
    # Explicitly reviewed files only. A checkout can contain user reports,
    # credentials and output directories; globbing it can publish those bytes.
    names = json.loads((SOURCE_ROOT / MANIFEST).read_text(encoding='utf-8'))
    if (not isinstance(names, list) or not names or
            any(not isinstance(name, str) for name in names) or len(set(names)) != len(names)):
        raise ValueError('Invalid source archive manifest')
    result = []
    for name in sorted(names):
        relative = Path(name)
        if (relative.is_absolute() or relative.as_posix() != name or
                any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError('Unsafe archive member path')
        path = SOURCE_ROOT
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                raise ValueError('Symlink in archive source: ' + name)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Archive source is not a regular file: ' + name)
        result.append(path)
    return result


def archives(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f'xdg-audit-{version()}'
    sources = [(p, f'{name}/{p.relative_to(SOURCE_ROOT).as_posix()}') for p in inputs()]
    zip_path = output_dir / f'{name}.zip'
    tar_path = output_dir / f'{name}.tar.gz'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for path, member in sources:
            info = zipfile.ZipInfo(member, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if path.name == 'xdg_audit.py' else 0o100644) << 16
            out.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with tar_path.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=9) as gz:
            with tarfile.open(mode='w', fileobj=gz, format=tarfile.PAX_FORMAT) as out:
                for path, member in sources:
                    data = path.read_bytes()
                    info = tarfile.TarInfo(member)
                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o755 if path.name == 'xdg_audit.py' else 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    out.addfile(info, io.BytesIO(data))
    sums_path = output_dir / 'SHA256SUMS'
    sums_path.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
                                 for p in (zip_path, tar_path)), encoding='utf-8')
    return [zip_path, tar_path, sums_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=SOURCE_ROOT / 'dist')
    args = parser.parse_args()
    for archive in archives(args.output_dir.resolve()):
        print(f'{archive.name} ({archive.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
