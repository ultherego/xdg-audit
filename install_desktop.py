#!/usr/bin/env python3
"""Optional explicit per-user desktop registration. Never requires sudo."""
from __future__ import annotations
import os
from contextlib import ExitStack
import stat
import sys
from pathlib import Path
import uuid

from xdg_quarantine_lifecycle import _open_path


def _user_directory(home: Path, relative: Path) -> int:
    """Create/open each component under HOME without following symlinks."""
    fd = _open_path(home)
    try:
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o755, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            if os.fstat(fd).st_uid != os.getuid():
                raise ValueError('Foreign owner in installation location')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _check_asset(fd: int, name: str) -> None:
    try:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()):
        raise ValueError('Refusing to replace symlink, linked or foreign asset')


def _write_asset(fd: int, name: str, content: bytes) -> None:
    temp = '.xdg-audit-' + uuid.uuid4().hex + '.tmp'
    raw = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
    try:
        stream = os.fdopen(raw, 'wb')
        raw = -1
        with stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _check_asset(fd, name)
        os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        if raw != -1:
            os.close(raw)
        try:
            os.unlink(temp, dir_fd=fd)
        except FileNotFoundError:
            pass


def _quote_exec(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Control character in launcher path')
    # Desktop Entry string escaping precedes Exec argument unquoting.
    # https://xdg.pages.freedesktop.org/xdg-specs/desktop-entry/latest/exec-variables.html
    quoted = ''.join('\\' + char if char in '\\"$`' else
                     '%%' if char == '%' else char for char in value)
    return '"' + quoted.replace('\\', '\\\\') + '"'


def install(home: Path, project: Path) -> list[Path]:
    if os.geteuid() == 0:
        raise ValueError('Do not run as root')
    script = project / 'xdg_audit.py'
    icon = project / 'assets' / 'xdg-audit.png'
    if not script.is_file() or not icon.is_file():
        raise ValueError('Missing app code/icon (extract the complete package)')
    data = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share'))
    if (not home.is_absolute() or not data.is_absolute() or '..' in data.parts
            or (data != home and home not in data.parents)):
        raise ValueError('XDG_DATA_HOME must remain in this HOME for this helper')
    desktop_dir = data / 'applications'
    icon_dir = data / 'icons/hicolor/256x256/apps'
    desktop = desktop_dir / 'io.github.xdgaudit.desktop'
    icon_path = icon_dir / 'io.github.xdgaudit.png'
    launcher = ('[Desktop Entry]\nType=Application\nName=xdg-audit\n'
                'Comment=Safe audit of leftover user configuration and cache\n'
                f'Exec={_quote_exec(sys.executable)} {_quote_exec(str(script.resolve()))}\n'
                'Icon=io.github.xdgaudit\nTerminal=false\nCategories=System;Utility;\n'
                'StartupNotify=true\n')
    icon_bytes = icon.read_bytes()
    with ExitStack() as stack:
        descriptors = []
        for dest in (desktop_dir, icon_dir):
            fd = _user_directory(home, dest.relative_to(home))
            stack.callback(os.close, fd)
            descriptors.append(fd)
        for fd, path in zip(descriptors, (desktop, icon_path)):
            _check_asset(fd, path.name)
        _write_asset(descriptors[1], icon_path.name, icon_bytes)
        _write_asset(descriptors[0], desktop.name, launcher.encode('utf-8'))
    return [desktop, icon_path]


if __name__ == '__main__':
    try:
        for path in install(Path.home(), Path(__file__).resolve().parent):
            print('Installed', path)
        print('Launcher points to the current project directory; do not move it without re-registering.')
    except (ValueError, OSError) as exc:
        print('Error:',exc,file=sys.stderr)
        raise SystemExit(1)
