"""Read-only providers of installed-app evidence, never executable payloads.

The installer of an application is unrelated to how xdg-audit itself ships.
Unsuccessful probes are not empty installed-package inventories. None of the
commands below requests package installation or root privileges.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


@dataclass(frozen=True)
class Probe:
    source: str
    status: str  # ok | absent | failed | timeout | parse_error
    names: frozenset[str] = frozenset()
    note: str = ""

    @property
    def healthy(self) -> bool:
        return self.status in ("ok", "absent")


class ActiveInventory(tuple):
    """Backward-compatible 8-field tuple carrying provider health metadata."""

    def __new__(cls, values, *, status=None, foreign=(), manual=(),
                distro=None, provenance=None):
        obj = super().__new__(cls, values)
        if len(obj) != 8:
            raise ValueError("Invalid installed-application inventory shape")
        obj.status = dict(status or {})
        obj.foreign = frozenset(foreign)
        obj.manual = frozenset(manual)
        obj.distro = {name: frozenset(values) for name, values in (distro or {}).items()}
        obj.provenance = dict(provenance or {})
        return obj


def _run(source: str, args: list[str], timeout: int) -> tuple[Probe, str]:
    if shutil.which(args[0]) is None:
        return Probe(source, "absent"), ""
    try:
        proc = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout,
                              check=False, errors="replace")
    except subprocess.TimeoutExpired:
        return Probe(source, "timeout", note="query exceeded time limit"), ""
    except OSError as exc:
        return Probe(source, "failed", note=exc.__class__.__name__), ""
    if proc.returncode != 0:
        return Probe(source, "failed", note=f"exit code {proc.returncode}"), ""
    if len(proc.stdout) > 16 * 1024 * 1024:
        return Probe(source, "parse_error", note="oversized query output"), ""
    return Probe(source, "ok"), proc.stdout


_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_.@-]{0,199}$")


def pacman_packages() -> Probe:
    base, output = _run("pacman", ["pacman", "-Qq"], 30)
    if base.status != "ok":
        return base
    names = [line.strip().casefold() for line in output.splitlines() if line.strip()]
    if any(not _PACKAGE.fullmatch(name) for name in names):
        return Probe("pacman", "parse_error", note="unexpected package identifier")
    return Probe("pacman", "ok", frozenset(names))


def pacman_foreign() -> Probe:
    """'foreign' includes AUR *and* locally installed packages; not AUR proof."""
    base, output = _run("pacman_foreign", ["pacman", "-Qmq"], 30)
    if base.status != "ok":
        return base
    names = [line.strip().casefold() for line in output.splitlines() if line.strip()]
    if any(not _PACKAGE.fullmatch(name) for name in names):
        return Probe("pacman_foreign", "parse_error", note="unexpected package identifier")
    return Probe("pacman_foreign", "ok", frozenset(names))


def dpkg_packages() -> Probe:
    """Only fully installed Debian packages (not residual config-files)."""
    base, output = _run("dpkg", [
        "dpkg-query", "-W", "-f=${binary:Package}\\t${Status}\\n"], 30)
    if base.status != "ok":
        return base
    names = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t", 1)
        if len(fields) != 2 or not fields[0].strip():
            return Probe("dpkg", "parse_error", note="invalid dpkg-query fields")
        name = fields[0].casefold().strip()
        base_name = name.split(":", 1)[0]  # Multi-Arch qualified identifiers
        if not _PACKAGE.fullmatch(base_name):
            return Probe("dpkg", "parse_error", note="invalid dpkg package name")
        state = fields[1].strip().casefold()
        if state.endswith(" ok installed") and state.split()[0] in ("install", "hold"):
            names.add(base_name)
            names.add(name)
    return Probe("dpkg", "ok", frozenset(names))


def rpm_packages() -> Probe:
    """Only RPM's installed database; no yum/dnf/zypper side effects."""
    base, output = _run("rpm", ["rpm", "-qa", "--qf", "%{NAME}\\n"], 30)
    if base.status != "ok":
        return base
    names = [x.strip().casefold() for x in output.splitlines() if x.strip()]
    if any(not _PACKAGE.fullmatch(x) for x in names):
        return Probe("rpm", "parse_error", note="invalid rpm package identifier")
    return Probe("rpm", "ok", frozenset(names))


def flatpak_apps() -> Probe:
    # Standard combined listing covers the user, default system and named
    # installations; installation source is collected only as provenance.
    base, output = _run("flatpak", [
        "flatpak", "list", "--app", "--columns=application,name,installation"], 25)
    if base.status != "ok":
        return base
    names = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 2 or not fields[0].strip():
            return Probe("flatpak", "parse_error", note="unexpected column format")
        names.add(fields[0].strip().casefold())
        if fields[1].strip():
            names.add(fields[1].strip().casefold())
    return Probe("flatpak", "ok", frozenset(names),
                 note="user, system and additional installations")


def snap_apps() -> Probe:
    base, output = _run("snap", ["snap", "list"], 15)
    if base.status != "ok":
        return base
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return Probe("snap", "parse_error", note="missing snap list header")
    if lines[0].split()[0].casefold() != "name":
        return Probe("snap", "parse_error", note="unexpected snap list header")
    names = set()
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 2 or not _PACKAGE.fullmatch(fields[0]):
            return Probe("snap", "parse_error", note="invalid installed snap row")
        names.add(fields[0].casefold())
    return Probe("snap", "ok", frozenset(names))


def _safe_direct_children(base: Path, *, extensions=(), require_exec=False):
    if base.is_symlink() or not base.is_dir():
        return set(), "absent" if not base.exists() else "unsafe"
    names = set()
    try:
        for item in base.iterdir():
            info = item.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()):
                continue
            if require_exec and not info.st_mode & 0o111:
                continue
            if extensions:
                if not item.name.casefold().endswith(extensions):
                    continue
                name = item.name.rsplit(".", 1)[0]
            else:
                name = item.name
            if name:
                names.add(name.casefold())
    except OSError:
        return set(), "failed"
    return names, "ok"


def user_appimages(home: Path) -> Probe:
    """Static filename evidence only; never run or mount an AppImage."""
    names = set()
    problems = []
    for folder in (home / "Applications", home / ".local/bin", home / "bin",
                   home / ".local/share/applications"):
        found, state = _safe_direct_children(folder, extensions=(".appimage",))
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    if problems:
        return Probe("appimage", "failed", frozenset(names),
                     note="cannot safely inspect: " + ",".join(problems[:3]))
    return Probe("appimage", "ok", frozenset(names))


def _app_directories(base: Path) -> tuple[set[str], str]:
    """Shallow /opt-style directory evidence; no traversal or code execution."""
    if base.is_symlink() or not base.is_dir():
        return set(), "absent" if not base.exists() else "unsafe"
    names = set()
    try:
        for idx, entry in enumerate(base.iterdir()):
            if idx >= 2000:
                return set(), "failed"
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid()):
                names.add(entry.name.casefold())
    except OSError:
        return set(), "failed"
    return names, "ok"


def manual_binaries(home: Path) -> Probe:
    """Protective filename hints from bounded trusted bins, never run binaries."""
    names = set()
    problems = []
    for folder in (home / ".local/bin", home / "bin", home / "Applications",
                   Path("/usr/local/bin")):
        found, state = _safe_direct_children(folder, require_exec=True)
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    # An application copied to /opt or ~/.local/opt does not necessarily
    # expose a bin symlink or desktop launcher. Top-level directory names
    # are hints only; they must NEVER become ownership/deletion evidence.
    for folder in (Path("/opt"), home / ".local/opt"):
        found, state = _app_directories(folder)
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    if problems:
        return Probe("manual_binary", "failed", frozenset(names),
                     note="cannot safely inspect: " + ",".join(problems[:3]))
    return Probe("manual_binary", "ok", frozenset(names))


def health_failed(probes: dict[str, Probe]) -> tuple[str, ...]:
    """Unavailable optional commands are not equivalent to a failing command."""
    return tuple(sorted(name for name, probe in probes.items()
                        if probe.status not in ("ok", "absent")))
