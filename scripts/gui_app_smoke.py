#!/usr/bin/env python3
"""Smoke-test actual xdg-audit application windows under Xvfb, using disposable HOME.

Checks application startup and X11 window mapping. Does NOT test a real Wayland
compositor or perform quarantine actions.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_child(backend: str, home: Path, scope: str = 'all') -> int:
    import xdg_audit as engine
    from xdg_prefs import defaults

    args = SimpleNamespace(saved_prefs=defaults(), keep=[],
                           quick=True, scope=scope, all=False)
    runtime = dict(desktop='KDE Plasma' if backend == 'qt6' else 'Niri',
                   session='x11', selected=backend,
                   available=[backend], wm='test')
    if backend == 'gtk4':
        from xdg_gui_gtk import launch_gui
    elif backend == 'qt6':
        from xdg_gui_qt import launch_gui
    else:
        from xdg_gui_tk import launch_gui
    return launch_gui(engine, home, args, {}, runtime, backend)


def run_parent(backend: str, seconds: float, scope: str = 'all') -> None:
    if not os.environ.get('DISPLAY'):
        raise RuntimeError('An X11 display is required; run with xvfb-run')
    with tempfile.TemporaryDirectory(prefix='xdg-audit-gui-smoke-') as td:
        home = Path(td)
        for folder in ('.config', '.cache', '.local/share', '.local/state', '.var/app', 'snap'):
            (home / folder).mkdir(parents=True, exist_ok=True)
        (home / '.config' / 'sample-app').mkdir()
        (home / 'snap' / 'xdg-snap-fixture').mkdir()
        env = os.environ.copy()
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_CACHE_HOME=str(home / '.cache'),
                   XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_STATE_HOME=str(home / '.local/state'))
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), '--child',
             '--backend', backend, '--home', str(home), '--scope', scope],
            cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        mapped = False
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if proc.poll() is not None:
                    break
                result = subprocess.run(['xwininfo', '-root', '-tree'], text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=3, check=False)
                if result.returncode == 0 and 'xdg-audit' in result.stdout.lower():
                    mapped = True
                    break
                time.sleep(0.2)
        finally:
            proc.terminate()
            try:
                _out, err = proc.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                _out, err = proc.communicate(timeout=4)
        if not mapped or b'Traceback (most recent call last)' in err:
            raise AssertionError(
                f'{backend}: application startup/mapping failed (exit={proc.returncode}):\n'
                + err.decode('utf-8', errors='replace')[-4000:])
        print(f'{backend}: real application window mapped (disposable HOME)')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True, choices=('gtk4', 'qt6', 'tk'))
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--scope', choices=('all', 'snap'), default='all')
    args = parser.parse_args()
    if args.child:
        if args.home is None:
            parser.error('--child requires --home')
        raise SystemExit(run_child(args.backend, args.home, args.scope))
    run_parent(args.backend, args.timeout, args.scope)


if __name__ == '__main__':
    main()
