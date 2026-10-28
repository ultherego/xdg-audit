#!/usr/bin/env python3
"""Run the real GTK4 / Qt6 application on a headless Wayland compositor.

Weston runs without XWayland. HOME and XDG_RUNTIME_DIR are temporary, so
no real user data is scanned. This is not a Niri/KDE real-session test.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / 'scripts' / 'gui_app_smoke.py'


def run(backend: str, duration: float = 3.0, *, lifecycle=False, output_dir=None, debugger=False,
        device_revalidation=False) -> None:
    with tempfile.TemporaryDirectory(prefix='xdg-audit-wayland-') as temp:
        base = Path(temp)
        runtime = base / 'runtime'
        runtime.mkdir(mode=0o700)
        home = base / 'home'
        home.mkdir()
        for folder in ('.config', '.cache', '.local/share', '.local/state', '.var/app'):
            (home / folder).mkdir(parents=True)
        (home / '.config' / 'sample-app').mkdir()
        socket_name = 'wayland-xdg-audit'
        socket = runtime / socket_name
        compositor_log = base / 'weston.log'
        client_log = base / 'client.log'
        env = os.environ.copy()
        env.update(HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_CACHE_HOME=str(home / '.cache'),
                   XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'),
                   WAYLAND_DISPLAY=socket_name, XDG_SESSION_TYPE='wayland',
                   GDK_BACKEND='wayland', QT_QPA_PLATFORM='wayland',
                   WAYLAND_DEBUG='client', LIBGL_ALWAYS_SOFTWARE='1',
                   GALLIUM_DRIVER='llvmpipe')
        if backend == 'qt6':
            # Headless Weston has no input seat. Qt 6.4's compositor input
            # context dereferences it when drawing a QLineEdit cursor. Use Qt's
            # compose context for this harness, keeping native Wayland rendering.
            env['QT_IM_MODULE'] = 'compose'
        env.pop('DISPLAY', None)  # Fail rather than silently falling back to X11.
        with compositor_log.open('w+') as wc, client_log.open('w+') as cc:
            weston = subprocess.Popen(
                ['weston', '--backend=headless-backend.so', '--idle-time=0',
                 '--socket=' + socket_name, '--width=1280', '--height=800'],
                cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                stdout=wc, stderr=subprocess.STDOUT,
            )
            child = None
            try:
                deadline = time.monotonic() + 15
                while not socket.is_socket():
                    if weston.poll() is not None or time.monotonic() > deadline:
                        wc.flush()
                        raise AssertionError('Headless Weston did not start:\n' +
                                             compositor_log.read_text(errors='replace')[-3000:])
                    time.sleep(0.15)
                command = ([sys.executable, str(ROOT / 'scripts/gui_lifecycle_smoke.py'),
                            '--backend', backend, '--expect-session', 'wayland'] if lifecycle else
                           [sys.executable, str(CHILD), '--child', '--backend', backend, '--home', str(home)])
                if lifecycle and output_dir:
                    command += ['--output', str(output_dir / (backend + '-wayland.json'))]
                if lifecycle and device_revalidation:
                    command += ['--device-revalidation']
                if debugger:
                    command = ['gdb', '--batch', '--return-child-result', '-ex', 'run',
                               '-ex', 'thread apply all bt', '--args', *command]
                child = subprocess.Popen(
                    command,
                    cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                    stdout=cc, stderr=subprocess.STDOUT,
                )
                until = time.monotonic() + (90 if lifecycle else duration)
                while time.monotonic() < until:
                    if child.poll() is not None:
                        break
                    time.sleep(0.15)
                cc.flush()
                trace = client_log.read_text(errors='replace')
                failed = (child.poll() != 0 or 'PASS GUI lifecycle:' not in trace) if lifecycle else child.poll() is not None
                if failed or 'create_surface(' not in trace:
                    raise AssertionError(
                        f'{backend}: Wayland GUI did not create a surface and stay alive. '
                        f'exit={child.poll()}\n' + trace[-14000 if debugger else -4500:]
                    )
                if lifecycle:
                    print('\n'.join(line for line in trace.splitlines() if 'PASS ' in line))
                print(f'{backend}: full application created a native Wayland surface (no X11)')
            finally:
                if child is not None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                weston.terminate()
                try:
                    weston.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    weston.kill()
                    weston.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True, choices=('gtk4', 'qt6'))
    parser.add_argument('--duration', type=float, default=3.0)
    parser.add_argument('--lifecycle', action='store_true', help='Run the real GUI lifecycle with synthetic inventory')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--debugger', action='store_true', help='Collect native failure backtraces with gdb')
    parser.add_argument('--device-revalidation', action='store_true')
    arguments = parser.parse_args()
    if arguments.device_revalidation and not arguments.lifecycle:
        parser.error('--device-revalidation requires --lifecycle')
    run(arguments.backend, arguments.duration, lifecycle=arguments.lifecycle, output_dir=arguments.output_dir,
        debugger=arguments.debugger, device_revalidation=arguments.device_revalidation)
