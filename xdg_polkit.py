"""No-install Polkit authorization smoke using an existing root-owned id binary.

GUI never receives or stores credentials. A successful run proves only that
Polkit authorized the *read-only* fixed id -u command, not general privileges
for xdg-audit or real quarantine changes.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess


class PolkitUnavailable(RuntimeError):
    pass


def _trusted_system_file(path: Path) -> bool:
    """Only accept a root-owned, non-writable regular executable, no symlinks."""
    if not path.is_absolute() or ".." in path.parts:
        return False
    cur = Path("/")
    try:
        for part in path.parts[1:]:
            cur = cur / part
            info = cur.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                return False
            if cur != path and not stat.S_ISDIR(info.st_mode):
                return False
            if cur == path and (not stat.S_ISREG(info.st_mode) or not info.st_mode & stat.S_IXUSR):
                return False
        return True
    except OSError:
        return False


def status() -> dict:
    """Report capability, not a claim of granted authorization."""
    pkexec = shutil.which("pkexec")
    trusted_pkexec = bool(pkexec and _trusted_system_file(Path(pkexec)))
    id_binary = Path("/usr/bin/id")
    trusted_id = _trusted_system_file(id_binary)
    return {
        "pkexec_installed": pkexec is not None,
        "pkexec_trusted": trusted_pkexec,
        "system_id_trusted": trusted_id,
        "helper_required": False,
        "ready": trusted_pkexec and trusted_id,
        "requesting_uid": os.getuid(),
        "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
        "scope": "auth_smoke_only",
        "note": "The system Polkit policy/agent decides which administrator authenticates. "
                "No elevated file operation is granted to xdg-audit.",
    }


def run_test(action: str = "test-auth", *, graphical: bool = False) -> dict:
    """Request Polkit authentication for root id -u only; no filesystem writes."""
    if action != "test-auth":
        raise ValueError("Unsupported no-install Polkit test action")
    info = status()
    if not info["ready"]:
        raise PolkitUnavailable("pkexec or the trusted /usr/bin/id binary is unavailable")
    pkexec = shutil.which("pkexec")
    command = [pkexec]
    if graphical:
        command.append("--disable-internal-agent")
    command.extend(["/usr/bin/id", "-u"])
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PolkitUnavailable("Polkit authentication timed out") from exc
    if proc.returncode == 126:
        raise PolkitUnavailable("Polkit authorization was cancelled")
    if proc.returncode == 127:
        raise PolkitUnavailable("Polkit denied the request or no session agent was available")
    if proc.returncode != 0 or proc.stdout.strip() != "0":
        raise PolkitUnavailable("Unexpected Polkit authorization result")
    return {"status": "authorized", "effective_uid": 0,
            "requesting_uid": os.getuid(), "scope": "auth_smoke_only",
            "file_operations": False}
