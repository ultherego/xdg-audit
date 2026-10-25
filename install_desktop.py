#!/usr/bin/env python3
"""Optional explicit per-user desktop registration. Never requires sudo."""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path


def install(home: Path, project: Path) -> list[Path]:
    if os.geteuid() == 0:
        raise ValueError('Do not run as root')
    script = project / 'xdg_audit.py'
    icon = project / 'assets' / 'xdg-audit.png'
    if not script.is_file() or not icon.is_file():
        raise ValueError('Missing app code/icon (extract the complete package)')
    data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    if not data.is_absolute() or (home.resolve() not in data.resolve(strict=False).parents and data.resolve(strict=False) != home.resolve()):
        raise ValueError('XDG_DATA_HOME must remain in this HOME for this helper')
    desktop_dir = data / 'applications'
    icon_dir = data / 'icons/hicolor/256x256/apps'
    for dest in (desktop_dir, icon_dir):
        if dest.is_symlink():
            raise ValueError('Symlink in installation location')
        dest.mkdir(parents=True, exist_ok=True)
    desktop = desktop_dir / 'io.github.xdgaudit.desktop'
    icon_path = icon_dir / 'io.github.xdgaudit.png'
    if desktop.is_symlink() or icon_path.is_symlink():
        raise ValueError('Refusing to replace symlink')
    # Freedesktop Exec quoting requires double quotes and escaped \ / " / $ / `.
    def quote(value: str) -> str:
        return '"' + value.replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('`','\\`') + '"'
    launcher = ('[Desktop Entry]\nType=Application\nName=xdg-audit\n'
                'Comment=Safe audit of leftover user configuration and cache\n'
                f'Exec={quote(sys.executable)} {quote(str(script.resolve()))}\n'
                'Icon=io.github.xdgaudit\nTerminal=false\nCategories=System;Utility;\n'
                'StartupNotify=true\n')
    desktop.write_text(launcher, encoding='utf-8')
    shutil.copyfile(icon, icon_path)
    return [desktop, icon_path]


if __name__ == '__main__':
    try:
        for path in install(Path.home(), Path(__file__).resolve().parent):
            print('Installed', path)
        print('Launcher points to the current project directory; do not move it without re-registering.')
    except (ValueError, OSError) as exc:
        print('Error:',exc,file=sys.stderr)
        raise SystemExit(1)
