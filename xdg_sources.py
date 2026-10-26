"""Read-only providers of installed-app evidence, never executable payloads.

The installer of an application is unrelated to how xdg-audit itself ships.
Unsuccessful probes are not empty installed-package inventories. None of the
commands below requests package installation or root privileges.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
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
    app_ids: frozenset[str] = frozenset()

    @property
    def healthy(self) -> bool:
        return self.status in ("ok", "absent")


class ActiveInventory(tuple):
    """Backward-compatible 8-field tuple carrying provider health metadata."""

    def __new__(cls, values, *, status=None, foreign=(), manual=(),
                distro=None, provenance=None, npm_global=(), pipx=(), flatpak_ids=None):
        obj = super().__new__(cls, values)
        if len(obj) != 8:
            raise ValueError("Invalid installed-application inventory shape")
        obj.status = dict(status or {})
        obj.foreign = frozenset(foreign)
        obj.manual = frozenset(manual)
        obj.npm_global = frozenset(npm_global)
        obj.pipx = frozenset(pipx)
        obj.flatpak_ids = (frozenset(flatpak_ids) if flatpak_ids is not None else None)
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
        state = fields[1].strip().casefold().split()
        # dpkg Status is a three-part tuple: Want / Err? / Status.
        # Malformed rows must not turn a partial inventory into "ok".
        if (len(state) != 3
                or state[0] not in ("unknown", "install", "hold", "deinstall", "purge")
                or state[1] not in ("ok", "reinstreq")
                or state[2] not in ("not-installed", "config-files", "half-installed",
                                    "unpacked", "half-configured", "triggers-awaited",
                                    "triggers-pending", "installed")):
            return Probe("dpkg", "parse_error", note="invalid dpkg package status")
        if state[0] in ("install", "hold") and state[1:] == ["ok", "installed"]:
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
    app_ids = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not fields[0].strip() or not fields[2].strip():
            return Probe("flatpak", "parse_error", note="unexpected column format")
        app_id = fields[0].strip().casefold()
        names.add(app_id)
        app_ids.add(app_id)
        if fields[1].strip():
            names.add(fields[1].strip().casefold())
    return Probe("flatpak", "ok", frozenset(names),
                 note="user, system and additional installations",
                 app_ids=frozenset(app_ids))


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


def _safe_direct_children(base: Path, *, extensions=(), require_exec=False,
                          anchor: Path | None = None):
    if anchor is not None:
        status = _source_directory_status(anchor, base)
        if status != "ok":
            return set(), status
    elif base.is_symlink() or not base.is_dir():
        return set(), "absent" if not base.exists() else "unsafe"
    names = set()
    try:
        for idx, item in enumerate(base.iterdir()):
            if idx >= 2000:
                return set(), "failed"
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
        found, state = _safe_direct_children(folder, extensions=(".appimage",), anchor=home)
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    if problems:
        return Probe("appimage", "failed", frozenset(names),
                     note="cannot safely inspect: " + ",".join(problems[:3]))
    return Probe("appimage", "ok", frozenset(names))


def _app_directories(base: Path, *, anchor: Path | None = None) -> tuple[set[str], str]:
    """Shallow /opt-style directory hints with checked ancestor directories."""
    if anchor is not None:
        status = _source_directory_status(anchor, base)
        if status != "ok":
            return set(), status
    elif base.is_symlink() or not base.is_dir():
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
        found, state = _safe_direct_children(folder, require_exec=True,
                                             anchor=home if folder.is_relative_to(home) else Path("/"))
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    # An application copied to /opt or ~/.local/opt does not necessarily
    # expose a bin symlink or desktop launcher. Top-level directory names
    # are hints only; they must NEVER become ownership/deletion evidence.
    for folder in (Path("/opt"), home / ".local/opt"):
        found, state = _app_directories(folder,
                                        anchor=home if folder.is_relative_to(home) else Path("/"))
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    if problems:
        return Probe("manual_binary", "failed", frozenset(names),
                     note="cannot safely inspect: " + ",".join(problems[:3]))
    return Probe("manual_binary", "ok", frozenset(names))


def _source_directory_status(home: Path, base: Path) -> str:
    """Reject symlinked/interrupted ancestors below HOME before reading names."""
    try:
        parts = base.relative_to(home).parts
    except ValueError:
        return "unsafe"
    current = home
    try:
        for part in parts:
            current = current / part
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode):
                return "unsafe"
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "failed"
    return "ok"


def _package_directories(base: Path, *, scoped=False, home: Path | None = None) -> tuple[set[str], str]:
    """Read bounded package directory names without following ancestor symlinks."""
    if home is not None:
        status = _source_directory_status(home, base)
        if status != "ok":
            return set(), status
    elif base.is_symlink() or not base.is_dir():
        return set(), "absent" if not base.exists() else "unsafe"
    names = set()
    try:
        entries = list(islice(base.iterdir(), 2001))
        if len(entries) > 2000:
            return set(), "failed"
        for item in entries:
            info = item.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()):
                continue
            if item.name.startswith("."):
                continue
            if scoped and item.name.startswith("@"):
                nested = list(islice(item.iterdir(), 2001))
                if len(nested) > 2000:
                    return set(), "failed"
                for child in nested:
                    ci = child.lstat()
                    if (stat.S_ISDIR(ci.st_mode) and ci.st_uid in (0, os.getuid())
                            and not child.name.startswith(".")):
                        names.add(child.name.casefold())
                        names.add((item.name + "/" + child.name).casefold())
            else:
                names.add(item.name.casefold())
    except OSError:
        return set(), "failed"
    return names, "ok"


def npm_global_packages(home: Path) -> Probe:
    """Bounded npm global directory hints (not package ownership assertions)."""
    candidates = (home / ".local/lib/node_modules",
                  home / ".npm-global/lib/node_modules",
                  home / ".local/share/npm/lib/node_modules")
    names, problems = set(), []
    for folder in candidates:
        found, state = _package_directories(folder, scoped=True, home=home)
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    # NVM-managed installations have versioned subdirectories.
    versions = home / ".nvm/versions/node"
    version_status = _source_directory_status(home, versions)
    if version_status == "ok":
        try:
            items = list(islice(versions.iterdir(), 65))
            if len(items) > 64:
                problems.append(str(versions))
            else:
                for item in items:
                    info = item.lstat()
                    if stat.S_ISLNK(info.st_mode):
                        problems.append(str(item))
                    elif stat.S_ISDIR(info.st_mode):
                        found, state = _package_directories(
                            item / "lib/node_modules", scoped=True, home=home)
                        names.update(found)
                        if state in ("failed", "unsafe"):
                            problems.append(str(item))
        except OSError:
            problems.append(str(versions))
    elif version_status in ("unsafe", "failed"):
        problems.append(str(versions))
    return Probe("npm_global", "failed" if problems else "ok",
                 frozenset(names), note="cannot inspect some directories" if problems else
                 "limited static directory evidence; not an exhaustive npm inventory")


def pipx_environments(home: Path) -> Probe:
    """Read virtualenv names only; pipx executables or packages are never run."""
    names, problems = set(), []
    for folder in (home / ".local/share/pipx/venvs",
                   home / ".local/pipx/venvs"):
        found, state = _package_directories(folder, home=home)
        names.update(found)
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    return Probe("pipx", "failed" if problems else "ok",
                 frozenset(names), note="cannot inspect some directories" if problems else
                 "limited virtualenv-name evidence; not an exhaustive pipx inventory")


def health_failed(probes: dict[str, Probe]) -> tuple[str, ...]:
    """Unavailable optional commands are not equivalent to a failing command."""
    return tuple(sorted(name for name, probe in probes.items()
                        if probe.status not in ("ok", "absent")))
