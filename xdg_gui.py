"""Native GUI dispatcher. No framework is a hard requirement of the CLI.

Detect the compositor/session and the Python bindings ACTUALLY present, then
select a native backend. No installs, subprocess GUI browsers, or env changes.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from xdg_theme import desktop_name


def _gtk_available(version: str) -> bool:
    if importlib.util.find_spec('gi') is None:
        return False
    try:
        import gi
        gi.require_version('Gtk', version)
        from gi.repository import Gtk  # noqa: F401
        return True
    except (ImportError, ValueError, OSError, AttributeError):
        return False


def available_backends(env: dict[str, str] | None = None) -> list[str]:
    env = dict(os.environ if env is None else env)
    available = []
    # GTK 3 and 4 cannot be loaded in the same Python process. Probe each in
    # an independent interpreter when both are advertised, to avoid global GI
    # version pinning. Default is to prefer GTK4 when installed.
    if _gtk_available('4.0'):
        available.append('gtk4')
    else:
        if _gtk_available('3.0'):
            available.append('gtk3')
    if any(importlib.util.find_spec(name) is not None for name in ('PySide6','PyQt6')):
        available.append('qt6')
    # Tcl/Tk uses X11 (including XWayland); on pure Wayland it can't connect.
    if env.get('DISPLAY') and importlib.util.find_spec('_tkinter') is not None:
        available.append('tk')
    return available


def choose_backend(desktop: str, available: list[str]) -> str | None:
    order = (('qt6','gtk4','gtk3','tk') if desktop in {'KDE Plasma','LXQt'} else
             ('gtk4','gtk3','qt6','tk'))
    return next((backend for backend in order if backend in available), None)


def detect_display_manager() -> str:
    """Read display-manager systemd service link without making changes."""
    service = Path('/etc/systemd/system/display-manager.service')
    if service.is_symlink():
        try:
            return service.resolve(strict=True).stem
        except OSError:
            pass
    return 'unknown'


def detect_wm(desktop: str, env: dict[str, str]) -> str:
    """Identify running compositor/WM using user-owned processes if possible."""
    hints = {'KDE Plasma': 'KWin', 'GNOME': 'Mutter/GNOME Shell',
             'Niri': 'Niri', 'Hyprland': 'Hyprland', 'Sway': 'Sway',
             'XFCE': 'xfwm4', 'Cinnamon': 'Muffin', 'MATE': 'Marco'}
    try:
        result = subprocess.run(['ps', '-u', str(os.getuid()), '-o', 'comm='],
            capture_output=True, text=True, timeout=2, check=False)
        if result.returncode == 0:
            processes = {p.strip().casefold() for p in result.stdout.splitlines()}
            for process, label in [('niri','Niri'),('hyprland','Hyprland'),('sway','Sway'),
                                   ('kwin_wayland','KWin Wayland'),('kwin_x11','KWin X11'),
                                   ('gnome-shell','Mutter/GNOME Shell'),('xfwm4','xfwm4'),
                                   ('muffin','Muffin'),('marco','Marco'),
                                   ('openbox','Openbox'),('i3','i3')]:
                if process.casefold() in processes:
                    return label
    except (OSError, subprocess.TimeoutExpired):
        pass
    return hints.get(desktop, 'unknown')


def detect_gui_runtime(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    desktop = desktop_name(env)
    if desktop == 'Inne / nieznane':
        if env.get('NIRI_SOCKET'): desktop = 'Niri'
        elif env.get('HYPRLAND_INSTANCE_SIGNATURE'): desktop = 'Hyprland'
        elif env.get('SWAYSOCK'): desktop = 'Sway'
    session = env.get('XDG_SESSION_TYPE', '').casefold()
    if session not in {'wayland', 'x11'}:
        session = 'Wayland' if env.get('WAYLAND_DISPLAY') else ('X11' if env.get('DISPLAY') else 'headless')
    avail = available_backends(env)
    return {'os': platform.freedesktop_os_release().get('PRETTY_NAME','Linux') if sys.platform == 'linux' else platform.system(),
            'session': session, 'desktop': desktop,
            'display_manager': detect_display_manager(), 'wm': detect_wm(desktop, env),
            'available': avail, 'selected': choose_backend(desktop, avail)}


def launch_gui(engine: Any, home: Path, args: Any, aliases: dict[str, list[str]]) -> int:
    runtime = detect_gui_runtime()
    errors: list[str] = []
    preferred = runtime['selected']
    if not preferred:
        raise RuntimeError('Brak dostępnego backendu GUI. Wykryto: '
            f'{runtime["desktop"]}, sesja {runtime["session"]}. '
            'GTK4/GTK3 (PyGObject), Qt6 (PySide/PyQt) i Tk (X11/XWayland) '
            'nie są dostępne jako działające biblioteki Pythona. '
            'CLI pozostaje dostępne z --scope all. Program niczego nie instaluje.')
    candidates = [preferred] + [v for v in runtime['available'] if v != preferred]
    for backend in candidates:
        try:
            if backend == 'qt6':
                from xdg_gui_qt import launch_gui as run
            elif backend in ('gtk4', 'gtk3'):
                from xdg_gui_gtk import launch_gui as run
            elif backend == 'tk':
                from xdg_gui_tk import launch_gui as run
            else:
                continue
            return run(engine, home, args, aliases, runtime, backend)
        except (ImportError, RuntimeError, OSError) as exc:
            errors.append(f'{backend}: {exc}')
    raise RuntimeError('Żaden wykryty backend GUI nie mógł się uruchomić. ' + ' | '.join(errors))
