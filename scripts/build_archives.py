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
import os
from pathlib import Path
import tarfile
import zipfile

SOURCE_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', '.venv', '.env', 'dist', '.build', '.idea', '.vscode'}
SKIP_SUFFIXES = {'.pyc', '.pyo', '.swp'}


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
    return sorted((p for p in SOURCE_ROOT.rglob('*') if p.is_file()
                   and not any(part in SKIP_DIRS for part in p.relative_to(SOURCE_ROOT).parts)
                   and p.suffix not in SKIP_SUFFIXES),
                  key=lambda p: p.relative_to(SOURCE_ROOT).as_posix())


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
