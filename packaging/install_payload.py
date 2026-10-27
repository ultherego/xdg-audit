#!/usr/bin/env python3
"""Stage reviewed runtime files for native packages; never register user assets."""
import argparse
import ast
import json
from pathlib import Path
import re
import shutil

NAME = 'xdg-audit'
LAUNCHER = '#!/bin/sh\nexec /usr/bin/python3 -B /usr/lib/xdg-audit/xdg_audit.py "$@"\n'
DESKTOP = '''[Desktop Entry]
Type=Application
Name=xdg-audit
Comment=Audit and safely quarantine leftover user configuration and data
Exec=/usr/bin/xdg-audit --gui
Icon=io.github.xdgaudit
Terminal=false
Categories=System;
StartupNotify=true
'''


def version(root):
    for node in ast.parse((root / 'xdg_audit.py').read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-(?:rc|dev)[0-9]*)?', value):
                return value
    raise ValueError('Unsupported source version')


def package_version(value, family):
    return value.replace('-', '~') if family in ('deb', 'rpm') else value.replace('-', '')


def validate_inputs(root, names):
    if len(names) != len(set(names)):
        raise ValueError('Duplicate package inputs')
    for name in names:
        if Path(name).is_absolute():
            raise ValueError('Unsafe package input path')
        path = root
        for part in Path(name).parts:
            if part in ('.', '..'):
                raise ValueError('Unsafe package input path')
            path = path / part
            if path.is_symlink():
                raise ValueError('Symlink in package input')
        if not path.is_file():
            raise ValueError('Missing package input: ' + name)
    return names


def reviewed_files(root):
    manifest = json.loads((root / 'scripts/archive-files.json').read_text())
    names = [name for name in manifest if Path(name).parent == Path('.') and
             name.startswith('xdg_') and name.endswith('.py')]
    names += ['assets/xdg-audit.png', 'assets/xdg-audit-128.png', 'assets/io.github.xdgaudit.png',
              'scripts/install_retention_timer.py']
    if 'xdg_audit.py' not in names:
        raise ValueError('Invalid runtime file manifest')
    return validate_inputs(root, names)


def reviewed_documentation(root):
    manifest = json.loads((root / 'scripts/archive-files.json').read_text())
    required = {'README.md', 'CHANGELOG.md', 'RELEASE_NOTES.md', 'RESEARCH_ROADMAP.md', 'LICENSE'}
    names = [name for name in manifest if name in required or
             (name.startswith('docs/') and Path(name).suffix in {'.md', '.webp', '.png'}) or
             (name.startswith('assets/') and Path(name).suffix == '.png')]
    if not required.issubset(names):
        raise ValueError('Missing reviewed documentation')
    return validate_inputs(root, names)


def stage(root, destination):
    root = root.resolve()
    if not destination.is_absolute() or destination == Path('/') or '..' in destination.parts:
        raise ValueError('Use an explicit absolute package staging directory')
    current = Path('/')
    for part in destination.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError('Symlink in package staging path')
    destination.mkdir(parents=True, exist_ok=True)

    def target(relative):
        path = destination / relative
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != Path('/')):
            raise ValueError('Unsafe package target')
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def copy(source, relative):
        if source.is_symlink() or not source.is_file():
            raise ValueError('Unsafe package input: ' + str(source))
        path = target(relative)
        shutil.copyfile(source, path)
        path.chmod(0o644)

    for name in reviewed_files(root):
        copy(root / name, 'usr/lib/xdg-audit/' + name)
    command = target('usr/bin/xdg-audit')
    command.write_text(LAUNCHER)
    command.chmod(0o755)
    desktop = target('usr/share/applications/io.github.xdgaudit.desktop')
    desktop.write_text(DESKTOP)
    desktop.chmod(0o644)
    copy(root / 'assets/xdg-audit.png', 'usr/share/icons/hicolor/512x512/apps/io.github.xdgaudit.png')
    copy(root / 'assets/xdg-audit-128.png', 'usr/share/icons/hicolor/128x128/apps/io.github.xdgaudit.png')
    copy(root / 'LICENSE', 'usr/share/licenses/xdg-audit/LICENSE')
    copy(root / 'LICENSE', 'usr/share/doc/xdg-audit/copyright')
    for name in reviewed_documentation(root):
        copy(root / name, 'usr/share/doc/xdg-audit/' + name)
    return version(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destdir', type=Path)
    parser.add_argument('--version', choices=('source', 'deb', 'rpm', 'arch'))
    args = parser.parse_args()
    if args.version:
        value = version(args.source_root)
        print(value if args.version == 'source' else package_version(value, args.version))
    elif args.destdir:
        stage(args.source_root, args.destdir)
    else:
        parser.error('Specify --destdir or --version')


if __name__ == '__main__':
    main()
