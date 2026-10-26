#!/usr/bin/env python3
"""Install an opt-in user-scoped systemd timer for xdg-audit retention.

No root privileges; no daemon is started unless --enable was requested.
Settings automatic=true must additionally be enabled in xdg-audit CLI.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "xdg_audit.py"


def systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def render_service() -> str:
    return ("[Unit]\nDescription=xdg-audit opted-in quarantine retention\n"
            "[Service]\nType=oneshot\n"
            "ExecStart=" + systemd_quote(sys.executable) + " " +
            systemd_quote(str(SCRIPT)) + " --automatic-purge\n"
            "NoNewPrivileges=true\n")


def render_timer() -> str:
    return ("[Unit]\nDescription=Daily xdg-audit quarantine retention check\n"
            "[Timer]\nOnCalendar=daily\nPersistent=true\nRandomizedDelaySec=10m\n"
            "[Install]\nWantedBy=timers.target\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="Install and enable the user timer")
    parser.add_argument("--disable", action="store_true", help="Disable the user timer")
    parser.add_argument("--install-only", action="store_true", help="Install unit files without enabling")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Never run as root or with sudo")
    if sum((args.enable, args.disable, args.install_only)) != 1:
        parser.error("Choose --install-only, --enable or --disable")
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd" / "user"
    if base.is_symlink() or base.parent.is_symlink() or Path.home() not in base.resolve(strict=False).parents:
        parser.error("Unsafe systemd user unit path")
    unit = "xdg-audit-retention"
    if args.disable:
        subprocess.run(["systemctl", "--user", "disable", "--now", unit + ".timer"], check=True)
        print("Retention timer disabled; configuration preserved.")
        return 0
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    service = base / (unit + ".service")
    timer = base / (unit + ".timer")
    if service.is_symlink() or timer.is_symlink():
        parser.error("Refusing to overwrite a systemd unit symlink")
    service.write_text(render_service(), encoding="utf-8")
    timer.write_text(render_timer(), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    if args.enable:
        subprocess.run(["systemctl", "--user", "enable", "--now", unit + ".timer"], check=True)
        print("Timer installed; automatic cleanup will still refuse to run unless enabled via xdg-audit --enable-retention.")
    else:
        print("Timer files installed, not enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
