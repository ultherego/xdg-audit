#!/usr/bin/env python3
"""Run complete desktop sessions and the GUI lifecycle on disposable profiles.

The session manager, shell/window manager, settings services and native display
are real. Inventory in the existing lifecycle harness remains synthetic. This
automated integration check does not replace manual theme/keyboard acceptance.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
DESKTOPS = {
    'gnome': {'desktop': 'GNOME', 'session': 'wayland', 'backend': 'gtk4',
              'command': ['gnome-session', '--session=gnome', '--disable-acceleration-check'],
              'services': {'org.gnome.SessionManager': 'gnome-session-binary',
                           'org.gnome.Shell': 'gnome-shell',
                           'org.gnome.SettingsDaemon.Keyboard': 'gsd-keyboard'},
              'processes': [], 'packages': ['gnome-session', 'gnome-shell', 'gnome-settings-daemon']},
    'plasma': {'desktop': 'KDE', 'session': 'wayland', 'backend': 'qt6',
               'command': ['startplasma-wayland'],
               'services': {'org.kde.ksmserver': 'ksmserver', 'org.kde.plasmashell': 'plasmashell',
                            'org.kde.KWin': 'kwin_wayland', 'org.kde.kded5': 'kded5'},
               'processes': [], 'packages': ['plasma-workspace', 'kwin-wayland', 'plasma-desktop']},
    'xfce': {'desktop': 'XFCE', 'session': 'x11', 'backend': 'tk',
             'command': ['xfce4-session'],
             'services': {'org.xfce.SessionManager': 'xfce4-session', 'org.xfce.Xfconf': 'xfconfd'},
             'processes': ['xfwm4', 'xfce4-panel', 'xfdesktop', 'xfsettingsd'],
             'packages': ['xfce4-session', 'xfwm4', 'xfdesktop4', 'xfce4-settings']},
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def environment(base: Path, desktop: str):
    """Do not inherit a real display, session bus, profile or Actions secrets."""
    spec = DESKTOPS[desktop]
    home = base / 'home'
    env = {'PATH': str(base / 'bin') + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'HOME': str(home), 'XDG_RUNTIME_DIR': str(base / 'runtime'),
           'XDG_CONFIG_HOME': str(home / '.config'), 'XDG_CACHE_HOME': str(home / '.cache'),
           'XDG_DATA_HOME': str(home / '.local/share'), 'XDG_STATE_HOME': str(home / '.local/state'),
           'XDG_CURRENT_DESKTOP': spec['desktop'], 'XDG_SESSION_DESKTOP': desktop,
           'XDG_SESSION_TYPE': spec['session'], 'LIBGL_ALWAYS_SOFTWARE': '1',
           'GALLIUM_DRIVER': 'llvmpipe', 'QT_QUICK_BACKEND': 'software',
           'NO_AT_BRIDGE': '1'}
    # Preserve only commit provenance and the runner's orphan-cleanup marker.
    for key in ('GITHUB_SHA', 'RUNNER_TRACKING_ID'):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def desktop_exec(arguments):
    # Desktop Entry Exec quoting differs from shell quoting, including literal %.
    return ' '.join('"' + re.sub(r'([\\"`$])', r'\\\1', str(arg)).replace('%', '%%') + '"'
                    for arg in arguments)


def prepare(base, desktop, output):
    env = environment(base, desktop)
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME',
                'XDG_STATE_HOME', 'XDG_RUNTIME_DIR'):
        Path(env[key]).mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = base / 'bin'
    binary.mkdir()
    autostart = Path(env['XDG_CONFIG_HOME']) / 'autostart'
    autostart.mkdir()
    worker = [sys.executable, str(SCRIPT), '--desktop', desktop, '--worker', '--output-dir', str(output)]
    (autostart / 'xdg-audit-session-fixture.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=xdg-audit disposable session check\n'
        + 'Exec=' + desktop_exec(worker) + '\nOnlyShowIn=' + DESKTOPS[desktop]['desktop']
        + ';\nX-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Phase=Applications\n', encoding='utf-8')
    if desktop == 'gnome':
        # Retain the installed session and required components; change only the
        # shell's display hardware to Mutter's supported virtual monitor.
        source = Path('/usr/share/applications/org.gnome.Shell.desktop').read_text()
        source = re.sub(r'^Exec=.*$', 'Exec=/usr/bin/gnome-shell --wayland --headless '
                        '--virtual-monitor 1600x1000', source, flags=re.M)
        applications = Path(env['XDG_DATA_HOME']) / 'applications'
        applications.mkdir()
        (applications / 'org.gnome.Shell.desktop').write_text(source)
    elif desktop == 'plasma':
        # Classic startup keeps all session components on the private bus;
        # importing the host's systemd user environment would violate isolation.
        (Path(env['XDG_CONFIG_HOME']) / 'startkderc').write_text('[General]\nsystemdBoot=false\n')
        # KWin's file capabilities otherwise prevent same-user /proc evidence.
        # Virtual rendering needs none: forbid privilege gain rather than read
        # the compositor as root or weaken process/profile identity checks.
        (binary / 'kwin_wayland').write_text(
            '#!/bin/sh\nexec /usr/bin/setpriv --no-new-privs /usr/bin/kwin_wayland '
            '--virtual --width 1600 --height 1000 "$@"\n')
        (binary / 'kwin_wayland').chmod(0o700)
        env['KWIN_COMPOSE'] = 'Q'
    return env


def bus_call(destination, path, method, *arguments):
    return subprocess.check_output(['gdbus', 'call', '--session', '--dest', destination,
                                    '--object-path', path, '--method', method, *arguments],
                                   text=True, timeout=5).strip()


def process_identity(pid, home, executable, proc=Path('/proc')):
    folder = proc / str(pid)
    require(folder.stat().st_uid == os.getuid(), 'Desktop service has another owner')
    require((folder / 'exe').resolve().name == executable, 'Unexpected desktop service executable: ' + executable)
    values = (folder / 'environ').read_bytes().split(b'\0')
    require(os.fsencode('HOME=' + str(home)) in values, 'Desktop service belongs to another profile')
    return {'pid': pid, 'executable': executable, 'fixture_profile': True}


def session_evidence(desktop):
    spec = DESKTOPS[desktop]
    home = Path(os.environ['HOME'])
    names = ast.literal_eval(bus_call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                      'org.freedesktop.DBus.ListNames'))[0]
    require(set(spec['services']).issubset(names), 'Full desktop services are not ready')
    services = {}
    for name, executable in spec['services'].items():
        reply = bus_call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                         'org.freedesktop.DBus.GetConnectionUnixProcessID', name)
        match = re.fullmatch(r'\(uint32 (\d+),\)', reply)
        require(match is not None, 'Invalid D-Bus owner PID reply')
        services[name] = process_identity(int(match[1]), home, executable)
    processes = []
    for executable in spec['processes']:
        found = []
        for folder in Path('/proc').glob('[0-9]*'):
            try:
                if (folder / 'exe').resolve().name == executable:
                    found.append(process_identity(int(folder.name), home, executable))
            except (OSError, AssertionError):
                continue
        require(found, 'Missing full-desktop component: ' + executable)
        processes.extend(found)
    if spec['session'] == 'wayland':
        socket = Path(os.environ['WAYLAND_DISPLAY'])
        if not socket.is_absolute():
            socket = Path(os.environ['XDG_RUNTIME_DIR']) / socket
        require(socket.parent == Path(os.environ['XDG_RUNTIME_DIR']) and socket.is_socket(),
                'Native Wayland socket is outside the disposable session')
    else:
        require(bool(os.environ.get('DISPLAY')) and not os.environ.get('WAYLAND_DISPLAY'),
                'Expected native X11 session')
    return {'services': services, 'processes': processes, 'native_session': spec['session']}


def worker(desktop, output):
    spec = DESKTOPS[desktop]
    report = {'desktop': desktop, 'commit': os.environ.get('GITHUB_SHA'), 'result': 'FAIL',
              'manual_theme_keyboard_acceptance': 'pending', 'inventory': 'synthetic'}
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                report['session'] = session_evidence(desktop)
                break
            except (OSError, AssertionError, subprocess.SubprocessError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.3)
        report['distribution'] = {key: value.strip('"') for line in Path('/etc/os-release').read_text().splitlines()
                                  if '=' in line for key, value in [line.split('=', 1)]
                                  if key in ('ID', 'VERSION_ID', 'PRETTY_NAME')}
        report['packages'] = subprocess.check_output(
            ['dpkg-query', '-W', '-f=${binary:Package} ${Version}\n', *spec['packages']], text=True, timeout=10).splitlines()
        env = os.environ.copy()
        if spec['session'] == 'wayland':
            # Desktops may use XWayland internally; the application must not.
            env.pop('DISPLAY', None)
            env['GDK_BACKEND'] = env['QT_QPA_PLATFORM'] = 'wayland'
            env['QT_IM_MODULE'] = 'compose'
        else:
            env['GDK_BACKEND'], env['QT_QPA_PLATFORM'] = 'x11', 'xcb'
        command = [sys.executable, str(ROOT / 'scripts/gui_lifecycle_smoke.py'), '--backend', spec['backend'],
                   '--expect-session', spec['session'], '--device-revalidation',
                   '--output', str(output / 'lifecycle.json')]
        with (output / 'application.log').open('w') as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=100, check=True)
        lifecycle = json.loads((output / 'lifecycle.json').read_text())
        require(lifecycle['result'] == 'PASS' and lifecycle['native_session'] == spec['session'],
                'Lifecycle did not complete on the required display')
        # Verify the full session survived every dialog and filesystem action.
        report['session_after'] = session_evidence(desktop)
        require(report['session_after'] == report['session'], 'Desktop services restarted during lifecycle')
        report['result'] = 'PASS'
    except BaseException:
        report['failure'] = traceback.format_exc()
    finally:
        pending = output / 'session.json.tmp'
        pending.write_text(json.dumps(report, indent=2) + '\n')
        pending.replace(output / 'session.json')


def manager(desktop, output):
    child = subprocess.Popen(DESKTOPS[desktop]['command'], stdin=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 185
        result = output / 'session.json'
        while not result.exists():
            require(child.poll() is None, 'Desktop session exited before fixture completion')
            require(time.monotonic() < deadline, 'Desktop session fixture timed out')
            time.sleep(0.3)
        report = json.loads(result.read_text())
        require(report['result'] == 'PASS', report.get('failure', 'Desktop fixture failed'))
        print('PASS complete desktop session: ' + desktop, flush=True)
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def run(desktop, output):
    require(os.getuid() != 0, 'Run as a regular user; root bypass is forbidden')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    require(not any(output.iterdir()), 'Use a new, empty evidence directory')
    with tempfile.TemporaryDirectory(prefix='xdg-audit-session-') as temporary:
        base = Path(temporary)
        env = prepare(base, desktop, output)
        command = ['dbus-run-session', '--', sys.executable, str(SCRIPT), '--desktop', desktop,
                   '--manager', '--output-dir', str(output)]
        if desktop == 'xfce':
            command = ['xvfb-run', '-a', '-s', '-screen 0 1600x1000x24 -nolisten tcp', *command]
        with (output / 'desktop.log').open('w') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                require(process.wait(timeout=210) == 0, 'Desktop integration check failed; inspect desktop.log')
            finally:
                # Only the new private process group is signalled; never stop a
                # service in the user's actual desktop/session bus.
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        break
                    time.sleep(0.2)
                process.wait()
                # Xfce may start a detached fixture-only agent. Address only
                # its newly created home, never the user's ordinary agent.
                agent_home = base / 'home/.gnupg'
                if agent_home.is_dir() and Path('/usr/bin/gpgconf').is_file():
                    subprocess.run(['/usr/bin/gpgconf', '--homedir', str(agent_home), '--kill', 'all'],
                                   env=env, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=5, check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', choices=tuple(DESKTOPS), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--manager', action='store_true', help=argparse.SUPPRESS)
    mode.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    require(os.getuid() != 0, 'Run as a regular user')
    (worker if args.worker else manager if args.manager else run)(args.desktop, args.output_dir)
