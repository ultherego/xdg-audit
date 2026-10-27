#!/usr/bin/env python3
"""Exercise the installed launcher and mapped GUI outside the source checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError('Run installed smoke checks as an unprivileged container user')
    with tempfile.TemporaryDirectory(prefix='xdg-installed-') as temporary:
        home = Path(temporary)
        (home / '.config').mkdir()
        fixture = home / '.config/xdg-package-sentinel'
        fixture.write_bytes(b'untouched user configuration\x00\xff')
        before = fixture.read_bytes()
        env = {key: value for key, value in os.environ.items()
               if key not in ('PYTHONPATH', 'PYTHONHOME') and not key.startswith('XDG_')}
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_CACHE_HOME=str(home / '.cache'), XDG_STATE_HOME=str(home / '.local/state'),
                   PYTHONDONTWRITEBYTECODE='1')
        def run(*command):
            return subprocess.check_output(command, cwd=home, env=env, text=True, timeout=30)
        assert run('/usr/bin/xdg-audit', '--version').strip() == 'xdg-audit v' + args.version
        report = json.loads(run('/usr/bin/xdg-audit', '--scope', 'config', '--quick', '--json'))
        assert isinstance(report, dict), 'Installed CLI did not return a JSON report'
        imported = run('/usr/bin/python3', '-B', '-c',
                       'import sys; sys.path.insert(0,"/usr/lib/xdg-audit"); '
                       'import xdg_audit, xdg_gui, xdg_gui_tk; print(xdg_audit.__file__)')
        assert imported.strip() == '/usr/lib/xdg-audit/xdg_audit.py'
        with tempfile.TemporaryFile(mode='w+') as log:
            process = subprocess.Popen(['/usr/bin/xdg-audit', '--gui', '--scope', 'config', '--quick'],
                                       cwd=home, env=env, stdout=log, stderr=log, text=True)
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    windows = run('xwininfo', '-root', '-tree')
                    if '"xdg-audit' in windows:
                        break
                    time.sleep(0.15)
                else:
                    raise AssertionError('Installed GUI window did not map')
                if process.poll() is not None:
                    log.seek(0)
                    raise AssertionError('Installed GUI exited: ' + log.read())
                assert '"xdg-audit' in windows, 'Installed GUI window did not map'
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        assert fixture.read_bytes() == before
        assert not (home / '.local/share/xdg-audit/quarantine').exists()
    print('PASS installed launcher, imports, read-only CLI and real GUI outside checkout')


if __name__ == '__main__':
    main()
