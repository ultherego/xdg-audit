#!/usr/bin/env python3
"""Launch an installed fixture through Gio, including special path characters."""
from pathlib import Path
import os
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_desktop
from gi.repository import Gio


def run():
    if os.geteuid() == 0:
        raise SystemExit('Use a regular user for the desktop acceptance smoke.')
    with tempfile.TemporaryDirectory(prefix='xdg-desktop-') as temp:
        home = Path(temp)
        project = home / 'checkout with spaces 50% "quotes" $dollar `tick` \\ żółć'
        (project / 'assets').mkdir(parents=True)
        marker = home / 'launched'
        (project / 'xdg_audit.py').write_text(
            'from pathlib import Path\nPath(' + repr(str(marker)) + ').write_bytes(b"fixture launched")\n')
        (project / 'assets/xdg-audit.png').write_bytes(b'fixture icon')
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(home / '.local/share')}):
            desktop, icon = install_desktop.install(home, project)
            app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            if app is None or not app.launch([], None):
                raise AssertionError('Desktop launcher could not be loaded/launched')
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            if not marker.exists() or marker.read_bytes() != b'fixture launched':
                raise AssertionError('Exec did not preserve the fixture script path')
            desktop.unlink()
            icon.unlink()
        print('PASS desktop registration -> actual Gio launch -> exact unregistration')


if __name__ == '__main__':
    run()
