"""Read-only providers of installed-app evidence, never executable payloads.

The installer of an application is unrelated to how xdg-audit itself ships.
Unsuccessful probes are not empty installed-package inventories. None of the
commands below requests package installation or root privileges.
"""
from __future__ import annotations

from dataclasses import dataclass
import configparser
from itertools import islice
import gzip
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess

_UNSET = object()


@dataclass(frozen=True)
class Probe:
    source: str
    status: str  # ok | absent | failed | timeout | parse_error | partial
    names: frozenset[str] = frozenset()
    note: str = ""
    app_ids: frozenset[str] = frozenset()

    @property
    def healthy(self) -> bool:
        return self.status in ("ok", "absent")


class ActiveInventory(tuple):
    """Backward-compatible 8-field tuple carrying provider health metadata."""

    def __new__(cls, values, *, status=None, foreign=(), manual=(),
                distro=None, provenance=None, npm_global=(), pipx=(), flatpak_ids=None,
                native_source=_UNSET, snap_ids=None, appimage_paths=None, aur=None):
        obj = super().__new__(cls, values)
        if len(obj) != 8:
            raise ValueError("Invalid installed-application inventory shape")
        obj.status = dict(status or {})
        obj.foreign = frozenset(foreign)
        obj.manual = frozenset(manual)
        obj.npm_global = frozenset(npm_global)
        obj.pipx = frozenset(pipx)
        obj.flatpak_ids = (frozenset(flatpak_ids) if flatpak_ids is not None else None)
        obj.snap_ids = (frozenset(snap_ids) if snap_ids is not None else None)
        obj.appimage_paths = (frozenset(appimage_paths) if appimage_paths is not None else None)
        obj.distro = {name: frozenset(values) for name, values in (distro or {}).items()}
        obj.provenance = dict(provenance or {})
        obj.aur = aur
        obj.native_source_explicit = native_source is not _UNSET
        # Compatibility for older Python callers; production always supplies
        # the OS-selected source, including explicit None for unknown systems.
        obj.native_source = (('pacman' if obj[0] and obj.status.get('pacman') == 'ok' else None)
                             if native_source is _UNSET else native_source)
        return obj


def native_package_source() -> str | None:
    """Identify the OS package database, never an arbitrary installed tool."""
    try:
        release = platform.freedesktop_os_release()
    except (OSError, ValueError, UnicodeError):
        return None
    families = {
        'pacman': {'arch', 'cachyos', 'manjaro', 'endeavouros'},
        'dpkg': {'debian', 'ubuntu', 'linuxmint', 'pop', 'kali', 'raspbian', 'neon'},
        'rpm': {'fedora', 'rhel', 'centos', 'rocky', 'almalinux', 'ol', 'suse',
                'opensuse', 'opensuse-leap', 'opensuse-tumbleweed', 'mageia'},
    }
    for identity in (release.get('ID', ''), *release.get('ID_LIKE', '').split()):
        for source, ids in families.items():
            if identity.casefold() in ids:
                return source
    return None


def verified_native_source(inventory) -> str:
    """Require a fresh, nonempty native database before authorizing MOVE."""
    health = getattr(inventory, 'status', None)
    source = getattr(inventory, 'native_source', 'pacman')
    if source not in ('pacman', 'dpkg', 'rpm'):
        raise ValueError('Cannot determine native package inventory before quarantine; no changes')
    names = inventory[0] if source == 'pacman' else inventory.distro.get(source, ())
    if not names or (health is not None and health.get(source) != 'ok'):
        raise ValueError(f'Cannot verify current {source} inventory before quarantine; no changes')
    return source


def package_name_count(source: str | None, names) -> int:
    """Count unique installed names, excluding dpkg architecture aliases."""
    return (len({name.partition(':')[0] for name in names})
            if source == 'dpkg' else len(names))


def dpkg_removals(logs: list[Path] | None = None) -> dict[str, list[str]]:
    """Bounded historical dpkg actions, including APT-triggered removals.

    Missing/unreadable/truncated logs provide no evidence. Historical records
    never override a currently installed package or authorize removal alone.
    """
    if logs is None:
        logs = [Path('/var/log/dpkg.log'),
                *sorted(Path('/var/log').glob('dpkg.log.*'))[:15]]
    pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) '
                         r'(?:remove|purge) ([a-z0-9][a-z0-9+.-]*)(?::[a-z0-9-]+)? \S+ \S+$')
    result = {}
    for path in logs[:16]:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            opener = gzip.open if path.suffix == '.gz' else open
            if path.suffix in ('.xz', '.zst'):
                continue
            with opener(path, 'rb') as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                continue
            content = raw.decode('utf-8')
        except (OSError, EOFError, UnicodeError):
            continue
        for line in content.splitlines():
            match = pattern.fullmatch(line)
            if match:
                result.setdefault(match[2], []).append(match[1])
    return result


def _run(source: str, args: list[str], timeout: int) -> tuple[Probe, str]:
    if shutil.which(args[0]) is None:
        return Probe(source, "absent"), ""
    try:
        proc = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout,
                              check=False, errors="replace",
                              env={**os.environ, 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LANG': 'C'})
    except subprocess.TimeoutExpired:
        return Probe(source, "timeout", note="query exceeded time limit"), ""
    except OSError as exc:
        return Probe(source, "failed", note=exc.__class__.__name__), ""
    # The foreign filter uses exit 1 when nothing matches. Restrict this
    # informational exception to the exact query with no output/diagnostics;
    # it cannot authorize MOVE or excuse a failed native database read.
    empty_foreign = (source == 'pacman_foreign' and args == ['pacman', '-Qmq']
                     and proc.returncode == 1 and not proc.stdout.strip()
                     and not proc.stderr.strip())
    if proc.returncode != 0 and not empty_foreign:
        return Probe(source, "failed", note=f"exit code {proc.returncode}"), ""
    if len(proc.stdout) > 16 * 1024 * 1024:
        return Probe(source, "parse_error", note="oversized query output"), ""
    output = proc.stdout
    if source == 'snap' and not output.strip() and proc.stderr.strip() == SNAP_EMPTY:
        output = SNAP_EMPTY
    return Probe(source, "ok"), output


_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_.@-]{0,199}$")
_DEB_ARCH = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]*')
_FLATPAK_ID = re.compile(r'(?:[A-Za-z_][A-Za-z0-9_]*\.){2,}[A-Za-z_-][A-Za-z0-9_-]*')
SNAP_EMPTY = "No snaps are installed yet. Try 'snap install hello-world'."
_SNAP_ID = re.compile(r'(?=.{2,51}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:_[a-z0-9]{1,10})?')


def valid_snap_id(value: str) -> bool:
    base = value.partition('_')[0]
    return bool(_SNAP_ID.fullmatch(value) and 2 <= len(base) <= 40
                and '--' not in base and re.search('[a-z]', base))


def valid_flatpak_id(value: str) -> bool:
    """Validate Flatpak's ASCII, segment and length rules before case folding."""
    return 0 < len(value) <= 255 and bool(_FLATPAK_ID.fullmatch(value))


def pacman_packages() -> Probe:
    base, output = _run("pacman", ["pacman", "-Qq"], 30)
    if base.status != "ok":
        return base
    names = [line.strip() for line in output.splitlines() if line.strip()]
    if any(not _PACKAGE.fullmatch(name) for name in names):
        return Probe("pacman", "parse_error", note="unexpected package identifier")
    return Probe("pacman", "ok", frozenset(name.casefold() for name in names))


def pacman_foreign() -> Probe:
    """'foreign' includes AUR *and* locally installed packages; not AUR proof."""
    base, output = _run("pacman_foreign", ["pacman", "-Qmq"], 30)
    if base.status != "ok":
        return base
    names = [line.strip() for line in output.splitlines() if line.strip()]
    if any(not _PACKAGE.fullmatch(name) for name in names):
        return Probe("pacman_foreign", "parse_error", note="unexpected package identifier")
    return Probe("pacman_foreign", "ok", frozenset(name.casefold() for name in names))


def dpkg_packages() -> Probe:
    """Only fully installed Debian packages (not residual config-files)."""
    base, output = _run("dpkg", [
        "dpkg-query", "-W", "-f=${binary:Package}\\t${Status}\\n"], 30)
    if base.status != "ok":
        return base
    names = set()
    incomplete = False
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t", 1)
        if len(fields) != 2 or not fields[0].strip():
            return Probe("dpkg", "parse_error", note="invalid dpkg-query fields")
        raw_name = fields[0].strip()
        raw_base, qualifier, architecture = raw_name.partition(':')
        if (not _PACKAGE.fullmatch(raw_base)
                or (qualifier and not _DEB_ARCH.fullmatch(architecture))):
            return Probe("dpkg", "parse_error", note="invalid dpkg package name")
        name = raw_name.casefold()
        base_name = raw_base.casefold()
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
        # Want is the requested future action, not the current package state.
        # deinstall/purge can still be fully installed until dpkg executes it.
        if state[1:] == ["ok", "installed"]:
            names.add(base_name)
            names.add(name)
        if state[1] != 'ok' or state[2] not in ('installed', 'config-files', 'not-installed'):
            incomplete = True
    return Probe("dpkg", "partial" if incomplete else "ok", frozenset(names),
                 note='package configuration is incomplete; MOVE is blocked' if incomplete else '')


def rpm_packages() -> Probe:
    """Only RPM's installed database; no yum/dnf/zypper side effects."""
    base, output = _run("rpm", ["rpm", "-qa", "--qf", "%{NAME}\\n"], 30)
    if base.status != "ok":
        return base
    names = [x.strip() for x in output.splitlines() if x.strip()]
    if any(not _PACKAGE.fullmatch(x) for x in names):
        return Probe("rpm", "parse_error", note="invalid rpm package identifier")
    return Probe("rpm", "ok", frozenset(name.casefold() for name in names))


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
        raw_id = fields[0].strip()
        if not valid_flatpak_id(raw_id):
            return Probe('flatpak', 'parse_error', note='invalid Flatpak application ID')
        app_id = raw_id.casefold()
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
    if output.strip() == SNAP_EMPTY:
        return Probe('snap', 'ok', app_ids=frozenset())
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return Probe("snap", "parse_error", note="missing snap list header")
    if lines[0].split() != ['Name', 'Version', 'Rev', 'Tracking', 'Publisher', 'Notes']:
        return Probe("snap", "parse_error", note="unexpected snap list header")
    names = set()
    for line in lines[1:]:
        fields = line.split()
        if (len(fields) != 6 or not valid_snap_id(fields[0])
                or not re.fullmatch(r'x?[0-9]+', fields[2])):
            return Probe("snap", "parse_error", note="invalid installed snap row")
        names.add(fields[0].casefold())
    return Probe("snap", "ok", frozenset(names), app_ids=frozenset(names))


def _safe_direct_children(base: Path, *, extensions=(), require_exec=False,
                          anchor: Path | None = None, paths: set[str] | None = None,
                          budget: list[int] | None = None):
    if anchor is not None:
        status = _source_directory_status(anchor, base)
        if status != "ok":
            return set(), status
    elif base.is_symlink() or not base.is_dir():
        return set(), "absent" if not base.exists() else "unsafe"
    names = set()
    unsafe_image = False
    try:
        for idx, item in enumerate(base.iterdir()):
            if idx >= 2000:
                return set(), "failed"
            if budget is not None:
                budget[0] -= 1
                if budget[0] < 0:
                    return set(), 'failed'
            info = item.lstat()
            if (extensions and item.name.casefold().endswith(extensions)
                    and (stat.S_ISLNK(info.st_mode) or info.st_uid not in (0, os.getuid()))):
                unsafe_image = True
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
                if paths is not None:
                    paths.add(str(item))
    except OSError:
        return set(), "failed"
    return names, "failed" if unsafe_image else "ok"


def _appimage_aliases(path: Path) -> set[str]:
    stem = path.name[:-len('.AppImage')].casefold()
    candidate = stem
    for _ in range(2):
        candidate = re.sub(r'[-_.](?:x86_64|amd64|aarch64|arm64|x64|i[3-6]86)$', '', candidate)
        candidate = re.sub(r'[-_](?:v)?[0-9][0-9a-z.+_-]*$', '', candidate)
    names = {stem, path.name.casefold() + '.home', path.name.casefold() + '.config'}
    if len(candidate) >= 3:
        names.add(candidate)
    return names


def _safe_appimage(path: Path, home: Path) -> bool:
    if not path.is_absolute() or '..' in path.parts or path.suffix.casefold() != '.appimage':
        return False
    anchor = home if path.is_relative_to(home) else Path('/')
    status = _source_directory_status(anchor, path.parent)
    if status in ('failed', 'unsafe'):
        raise ValueError('Cannot safely inspect AppImage target')
    if status != 'ok':
        return False
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('AppImage target is a symlink')
    return stat.S_ISREG(info.st_mode) and info.st_uid in (0, os.getuid())


def _read_launcher(path: Path) -> str:
    from xdg_quarantine_lifecycle import _open_path
    parent = _open_path(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()):
                raise ValueError('Unsafe launcher')
            raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError('Launcher exceeds inspection limit')
            return raw.decode('utf-8')
    finally:
        os.close(parent)


def _appimage_launchers(home: Path, data: Path) -> tuple[set[str], set[str], bool]:
    """Inspect bounded user launchers; never invoke Exec, wrappers or images."""
    folder = data / 'applications'
    status = _source_directory_status(home if folder.is_relative_to(home) else Path('/'), folder)
    if status == 'absent':
        return set(), set(), False
    if status != 'ok':
        return set(), set(), True
    names, paths, failed = set(), set(), False
    try:
        entries = list(islice(folder.iterdir(), 2001))
        if len(entries) > 2000:
            return set(), set(), True
        for entry in entries:
            info = entry.lstat()
            if (entry.suffix != '.desktop' or not stat.S_ISREG(info.st_mode)
                    or info.st_uid not in (0, os.getuid())):
                continue
            # Unknown oversized launchers cannot establish image absence.
            if info.st_size > 65536:
                failed = True
                continue
            text = _read_launcher(entry)
            if '.appimage' not in text.casefold():
                continue
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            try:
                parser.read_string(text)
                section = parser['Desktop Entry']
                if section.get('Type') != 'Application':
                    continue
                raw = section.get('Exec', '')
                escapes = {'s': ' ', 'n': '\n', 't': '\t', 'r': '\r', '\\': '\\'}
                raw = re.sub(r'\\([sntr\\])', lambda m: escapes[m[1]], raw)
                tokens = shlex.split(raw)
                if tokens and Path(tokens[0]).name == 'env':
                    tokens = tokens[1:]
                    while tokens and (tokens[0] == '--' or re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[0])):
                        tokens = tokens[1:]
                targets = [section.get('TryExec', ''), section.get('X-AppImage-Path', '')]
                if tokens:
                    targets.append(tokens[0])
                present = [Path(value) for value in targets if value and _safe_appimage(Path(value), home)]
                if not present:
                    continue  # stale launchers remain weak desktop hints in the engine
                for image in present:
                    names.update(_appimage_aliases(image))
                    paths.add(str(image))
                for alias in (section.get('Name', ''), section.get('X-AppImage-Name', ''), entry.stem):
                    if 3 <= len(alias) <= 200 and not any(ord(c) < 32 for c in alias):
                        names.add(alias.casefold())
            except (ValueError, KeyError, configparser.Error):
                failed = True
    except (OSError, UnicodeError, ValueError):
        failed = True
    return names, paths, failed


def _shallow_source_folders(home: Path, bases) -> tuple[list[Path], bool]:
    """Inspect at most one application directory level, without following links."""
    folders, failed = [], False
    for base in bases:
        status = _source_directory_status(home if base.is_relative_to(home) else Path('/'), base)
        if status == 'absent':
            continue
        if status != 'ok':
            failed = True
            continue
        try:
            entries = list(islice(base.iterdir(), 2001))
            if len(entries) > 2000:
                failed = True
                continue
            children = []
            for entry in entries:
                info = entry.lstat()
                if stat.S_ISLNK(info.st_mode):
                    continue
                if stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid()):
                    children.append(entry)
            if len(children) > 64:
                failed = True
            else:
                folders.extend(children)
        except OSError:
            failed = True
    return folders, failed


def user_appimages(home: Path, data: Path | None = None, extra_dirs=()) -> Probe:
    """Bounded file/launcher evidence, with version aliases; never execute code."""
    names = set()
    image_paths = set()
    problems = []
    data = data or home / '.local/share'
    app_roots = (home / 'Applications', home / 'AppImages', home / 'apps', home / 'Apps',
                 home / 'opt', home / '.local/opt', data / 'AppImages', data / 'appimages', Path('/opt'))
    nested, failed = _shallow_source_folders(home, app_roots)
    if failed:
        problems.append('application subdirectories')
    folders = (*app_roots, home / 'Downloads', home / '.local/bin', home / 'bin',
               home / '.local/share/applications', data / 'applications', *nested, *extra_dirs)
    budget = [12000]
    for folder in dict.fromkeys(folders):
        found, state = _safe_direct_children(folder, extensions=(".appimage",),
            anchor=home if folder.is_relative_to(home) else Path('/'), paths=image_paths, budget=budget)
        names.update(found)
        for stem in found:
            names.update(_appimage_aliases(Path(stem + '.AppImage')))
        if state in ("failed", "unsafe"):
            problems.append(str(folder))
    launcher_names, launcher_paths, failed = _appimage_launchers(home, data)
    names.update(launcher_names)
    image_paths.update(launcher_paths)
    if failed:
        problems.append('desktop launchers')
    if problems:
        return Probe("appimage", "failed", frozenset(names),
                     note="cannot safely inspect: " + ",".join(problems[:3]), app_ids=frozenset(image_paths))
    return Probe("appimage", "ok", frozenset(names),
                 note='static filenames, version aliases and verified launcher targets; no execution',
                 app_ids=frozenset(image_paths))


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


def manual_binaries(home: Path, extra_dirs=()) -> Probe:
    """Protective filename hints from bounded trusted bins, never run binaries."""
    names = set()
    problems = []
    budget = [12000]
    folders = (home / '.local/bin', home / 'bin', home / 'Applications',
               home / '.cargo/bin', home / 'go/bin', home / 'apps/bin', home / 'Apps/bin',
               home / 'Applications/bin', home / 'opt/bin', home / '.local/opt/bin',
               Path('/usr/local/bin'), Path('/usr/local/sbin'), *extra_dirs)
    for folder in dict.fromkeys(folders):
        found, state = _safe_direct_children(folder, require_exec=True,
            anchor=home if folder.is_relative_to(home) else Path('/'), budget=budget)
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
