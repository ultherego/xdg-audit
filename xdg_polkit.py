"""Rootless Polkit integration for a purpose-built isolated self-test.

Never execute repository scripts with pkexec. The target must be a root-owned,
non-writable installed executable, matched by a root-owned Polkit policy.
This proves desktop authorization, but never grants quarantine PURGE privileges.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

HELPER = Path("/usr/libexec/xdg-audit/xdg-audit-polkit-helper")
POLICY = Path("/usr/share/polkit-1/actions/io.github.ultherego.xdg-audit.policy")


class PolkitUnavailable(RuntimeError):
    pass


def _trusted_system_file(path: Path, *, executable: bool) -> bool:
    """Fail closed for missing, symlinked, non-root or writable components."""
    if not path.is_absolute() or ".." in path.parts:
        return False
    check = Path("/")
    try:
        for part in path.parts[1:]:
            check = check / part
            st = check.lstat()
            if st.st_uid != 0 or st.st_mode & 0o022 or stat.S_ISLNK(st.st_mode):
                return False
            if part != path.parts[-1]:
                if not stat.S_ISDIR(st.st_mode):
                    return False
            elif not stat.S_ISREG(st.st_mode) or (executable and not st.st_mode & stat.S_IXUSR):
                return False
        return True
    except OSError:
        return False


def status() -> dict:
    """Diagnostics are read-only; pkexec availability is NOT authorization."""
    available = shutil.which("pkexec") is not None
    helper_ok = _trusted_system_file(HELPER, executable=True)
    policy_ok = _trusted_system_file(POLICY, executable=False)
    return {
        "pkexec_installed": available,
        "helper_trusted": helper_ok,
        "policy_trusted": policy_ok,
        "ready": available and helper_ok and policy_ok,
        "requesting_uid": os.getuid(),
        "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
        "note": "Polkit chooses the authentication identity at execution time",
    }


def run_test(action: str, *, graphical: bool = False) -> dict:
    if action not in ("test-create", "test-delete"):
        raise ValueError("Unsupported Polkit action")
    info = status()
    if not info["ready"]:
        raise PolkitUnavailable(
            "Polkit test is not installed securely. Follow packaging/polkit/README.md.")
    executable = shutil.which("pkexec")
    if not executable:
        raise PolkitUnavailable("pkexec is unavailable")
    command = [executable]
    if graphical:
        # Never silently fall back to an invisible terminal-agent prompt.
        command.append("--disable-internal-agent")
    command.extend([str(HELPER), action])
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PolkitUnavailable("System authentication timed out") from exc
    if proc.returncode == 126:
        raise PolkitUnavailable("Polkit authentication was cancelled")
    if proc.returncode == 127:
        raise PolkitUnavailable("Polkit denied authentication or no agent was available")
    if proc.returncode != 0:
        raise PolkitUnavailable(
            "Restricted helper refused the request: " + proc.stderr.strip()[:400])
    if len(proc.stdout) > 16384:
        raise PolkitUnavailable("Unexpected helper response length")
    try:
        data = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise PolkitUnavailable("Unexpected non-JSON helper response") from exc
    required_status = {"test-create": ("created", "already_exists"),
                       "test-delete": ("deleted",)}[action]
    if (not isinstance(data, dict) or data.get("status") not in required_status
            or data.get("uid") != os.getuid()):
        raise PolkitUnavailable("Unexpected helper response or different caller UID")
    return data
