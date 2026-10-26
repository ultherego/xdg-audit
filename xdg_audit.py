#!/usr/bin/env python3
"""Conservative, user-scoped Linux XDG leftovers auditor.

READ ONLY by default. --remove moves explicitly selected entries to quarantine.
Python >= 3.10, standard library only. Never run with sudo.
"""
from __future__ import annotations

import argparse
import configparser
import datetime as dt
from fnmatch import fnmatchcase
import json
import os
import re
import shlex
import shutil
import stat
import time
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "1.7.0-rc2"
SCOPES = ("config", "data", "state", "cache", "flatpak", "snap", "dotfiles")
# These entries are generic OS/session infrastructure or particularly sensitive data.
# The protection is intentional even when a matching executable is not found.
PROTECTED = {
    "config": {"autostart", "systemd", "dconf", "gtk-3.0", "gtk-4.0", "pulse", "pipewire",
               "user-dirs.dirs", "user-dirs.locale", "mimeapps.list", "xdg-desktop-portal",
               "xdg-terminals.list", "menus", "fish", "niri", "dms", "DankMaterialShell",
               "psd", "mozilla", "chromium", "google-chrome", "vivaldi", "BraveSoftware", "xdg-audit", ".claude", ".codex", ".continue", ".copilot", ".vscode",
               # Access tokens, desktop/account integration and session configuration.
               "anthropic", "gh", "goa-1.0", "cachyos", "cachyos-hello.json",
               # User-generated game saves, VM metadata, mod managers and manual backups.
               "unity3d", "7DaysToDie", "StoneShard", "Vortex", "VirtualBox", "niri_back",
               "chromium-backup", "google-chrome-backup", "vivaldi-backup", "chromium-back-ovfs",
               "google-chrome-back-ovfs", "vivaldi-back-ovfs", "ssh", "gnupg", "keyring", "keyrings"},
    "data": {"keyrings", "gnupg", "Trash", "applications", "icons", "fonts", "mime", "dbus-1",
             "flatpak", "systemd", "xdg-audit-quarantine", "Steam", "steam", "containers",
             "Larian Studios", "Euro Truck Simulator 2", "Baldur's Gate - Enhanced Edition",
             "umu", "gtk-4.0", "desktop-directories", "wayland-sessions", "xsessions"},
    "state": {"systemd", "wireplumber", "xdg-audit"},
    "cache": {"mesa_shader_cache", "fontconfig", "thumbnails", "paru", "yay", "go-build"},
    "flatpak": set(),
    "snap": set(),
    "dotfiles": {".config", ".local", ".cache", ".var", ".ssh", ".gnupg", ".pki", ".mozilla",
                 ".profile", ".bashrc", ".zshrc", ".bash_profile", ".gitconfig", ".Xauthority",
                 ".ICEauthority", ".lesshst", ".password-store", ".rustup", ".cargo",
                 ".docker", ".kube", ".aws", ".vagrant.d", ".npm", ".nvm", ".steam",
                 ".steampath", ".steampid", ".claude", ".codex", ".continue",
                 ".copilot", ".vscode", ".icons", ".themes"},
}
# Case-insensitive backup/PSD names must never be removed automatically.
BACKUP_RE = re.compile(r"(?:backup|back-ovfs|crashrecovery|\.bak(?:\W|$)|snapshot)", re.I)
SENSITIVE_RE = re.compile(r"(?:secret|token|pass(word)?|wallet|keyring|credentials|vault|auth)", re.I)
PACKAGE_SUFFIX_RE = re.compile(r"(?:(?:-git|-bin|-appimage|-nightly|-stable|-wayland|-desktop|-gtk|-qt|-electron|_git))+$", re.I)
# Known application->package name associations. Extend with --alias NAME=PKG.
ALIASES = {
    "code": ["visual-studio-code-bin", "code", "vscode"],
    "vscode": ["visual-studio-code-bin", "code"],
    "mozilla": ["firefox", "librewolf", "zen-browser"],
    "bravesoftware": ["brave", "brave-bin", "brave-browser"],
    "dms": ["dms-shell-git", "dms-shell"],
    "dankmaterialshell": ["dms-shell-git", "dms-shell"],
    "proton pass": ["proton-pass-bin", "proton-pass"],
    "proton mail": ["proton-mail", "proton-mail-bin"],
    "slack": ["slack-desktop-wayland", "slack-desktop"],
    "discord": ["discord", "vesktop"],
    "vortex": ["vortex"],
    "logi-ghub-linux": ["logi-ghub-linux", "logi-ghubd"],
    "betterdiscord": ["discord", "vesktop", "discord-canary", "discord-ptb"],
    "vencord": ["discord", "vesktop", "vencord-installer"],
    "easyeffectsrc": ["easyeffects", "easyeffects-git"],
    "okularrc": ["okular"],
    "okularpartrc": ["okular"],
    "microsoft-edge": ["microsoft-edge-stable", "microsoft-edge-bin", "microsoft-edge-beta", "microsoft-edge-dev"],
    "ghostty": ["ghostty", "ghostty-git", "ghostty-bin"],
    "7daystodie": ["7daystodie", "7-days-to-die"],
    "com.sigma-file-manager.app": ["sigma-file-manager-bin"],
    "kdeconnect.smsstaterc": ["kdeconnect"],
    "kdeconnect.daemon": ["kdeconnect"],
    "gitkrakencli": ["gitkraken-cli", "gitkraken"],
    "zen": ["zen-browser", "zen-browser-bin"],
    "stormshield": ["stormshield-ssl-vpn-client", "stormshield-vpn"],
    "tracker3": ["tracker3", "localsearch"],
    "gstreamer-1.0": ["gstreamer", "gst-plugins-base"],
    "pip": ["python-pip"],
}


# Strongly grounded application families. A prefix such as brave* is checked
# against the CURRENT package inventory, never against removal history alone.
# Other folders use derived aliases with a minimum 5-character root. A matching
# theme/translation/helper package does not, by itself, prove the app is present.
APP_PACKAGE_PATTERNS = {
    "bravesoftware": ("brave*",),
    "opera": ("opera*",),
    "microsoftedge": ("microsoft-edge*",),
    "googlechrome": ("google-chrome*",),
    "kdeconnectsmsstaterc": ("kdeconnect*",),
    "kdeconnectdaemon": ("kdeconnect*",),
    "discord": ("discord*", "vesktop*"),
    "betterdiscord": ("discord*", "vesktop*"),
    "vencord": ("discord*", "vesktop*"),
}
AUXILIARY_PACKAGE_MARKERS = (
    "theme", "themes", "icon", "icons", "plugin", "plugins", "extension",
    "extensions", "common", "data", "docs", "doc", "l10n", "locale",
    "locales", "lang", "translations", "keyring", "debug", "headers",
)


def package_looks_auxiliary(package: str, pattern: str) -> bool:
    """Avoid proving an application is installed with only a theme/helper pkg."""
    prefix = pattern.partition('*')[0].rstrip('-_')
    remainder = package.casefold()[len(prefix):].lstrip('-_.')
    tokens = [x for x in re.split(r"[-_.]+", remainder) if x]
    return bool(tokens and tokens[0] in AUXILIARY_PACKAGE_MARKERS)


def package_patterns(folder: str, alias_map: dict[str, list[str]]) -> tuple[str, ...]:
    """Generate anchored prefix patterns, never arbitrary substring matching.

    Tiny names (go, gh, qt, etc.) deliberately do not get wildcard matches.
    An explicit alias/pattern such as brave* is allowed.
    """
    normalized = normalize(folder)
    patterns = set(APP_PACKAGE_PATTERNS.get(normalized, ()))
    candidates = {folder, *alias_map.get(folder.casefold(), [])}
    for candidate in candidates:
        candidate = candidate.casefold()
        if '*' in candidate or '?' in candidate:
            patterns.add(candidate)
            continue
        stem = stem_package(candidate)
        if len(normalize(stem)) >= 5:
            patterns.add(stem + '*')
    return tuple(sorted(patterns, key=lambda x: (len(x), x)))


def match_installed_packages(folder: str, packages: set[str],
                             aliases: dict[str, list[str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return verified app packages and weak accessory matches, with evidence.

    Patterns are compared to real package names first and to their stripped AUR
    variants second; matching both doesn't duplicate a package.
    """
    keys = names_for(folder, aliases)
    patterns = package_patterns(folder, aliases)
    strong: dict[str, str] = {}
    weak: dict[str, str] = {}
    for pkg in packages:
        canonical = pkg.casefold()
        if normalize(canonical) in keys or normalize(stem_package(canonical)) in keys:
            strong[pkg] = 'exact/normalized'
            continue
        for pattern in patterns:
            if fnmatchcase(canonical, pattern) or fnmatchcase(stem_package(canonical), pattern):
                (weak if package_looks_auxiliary(canonical, pattern) else strong)[pkg] = pattern
                break
    return sorted(strong.items()), sorted(weak.items())


def nonpacman_matches(folder: str, observed: set[str], aliases: dict[str, list[str]]) -> list[str]:
    """Match identity or bounded app-id segments, not arbitrary substrings.

    A desktop entry can be stale, so callers should treat this only as a
    corroborating hint, except for explicitly installed Flatpaks / Snaps.
    """
    keys = names_for(folder, aliases)
    patterns = package_patterns(folder, aliases)
    matches = []
    for name in observed:
        parts = [part for part in re.split(r"[./\\\s]+", name.casefold()) if part]
        variants = {normalize(name), *(normalize(part) for part in parts if len(part) >= 5)}
        if keys & variants or any(fnmatchcase(part, pat) for part in parts for pat in patterns):
            matches.append(name)
    return sorted(set(matches))


def protection_reason(scope: str, name: str) -> str:
    """Explain rather than silently asserting ownership of protected entries."""
    low = name.casefold()
    if name in {"anthropic", "gh", "goa-1.0", "ssh", "gnupg"} or any(
        w in low for w in ("keyring", "wallet", "credential")
    ):
        return "protected: potential account credentials or authentication data (ownership not verified)"
    if low in {"niri_back", "vortex", "virtualbox", "unity3d", "7daystodie", "stoneshard"}:
        return "protected: user backup, game/mod or virtual-machine data (ownership not verified)"
    if low in {"psd", "mozilla", "chromium", "google-chrome", "vivaldi", "bravesoftware"}:
        return "protected: browser profile / profile-sync-daemon; deletion requires separate audit"
    if scope == "config" and low in {"dms", "dankmaterialshell", "niri", "fish", "systemd", "autostart"}:
        return "protected: desktop/session/shell configuration"
    return "protected: shared system component or manually safeguarded user data (ownership not verified)"


def is_backup_reference(path: Path) -> bool:
    """Do not treat mentions found ONLY in dated/disabled backups as live references."""
    return BACKUP_RE.search(path.name) is not None or path.suffix.casefold() in {
        ".old", ".orig", ".disabled", ".save", ".swp", ".swo", ".tmp", "~"
    } or path.name.endswith("~")


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def stem_package(value: str) -> str:
    return PACKAGE_SUFFIX_RE.sub("", value.casefold())


def command(args: list[str], timeout: int = 15) -> str:
    if not shutil.which(args[0]):
        return ""
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=False)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def valid_root(value: str | None, fallback: Path, home: Path) -> Path | None:
    path = Path(value) if value else fallback
    if not path.is_absolute():
        path = fallback
    # Ignore invalid/outside-home XDG overrides; do not ever reach another user's directory.
    try:
        resolved = path.resolve(strict=False)
        if resolved != home and home not in resolved.parents:
            return fallback if fallback != home else None
    except (OSError, RuntimeError):
        return fallback if fallback != home else None
    return path


def xdg_roots(home: Path) -> dict[str, Path]:
    roots = {
        "config": valid_root(os.environ.get("XDG_CONFIG_HOME"), home / ".config", home),
        "data": valid_root(os.environ.get("XDG_DATA_HOME"), home / ".local/share", home),
        "state": valid_root(os.environ.get("XDG_STATE_HOME"), home / ".local/state", home),
        "cache": valid_root(os.environ.get("XDG_CACHE_HOME"), home / ".cache", home),
        "flatpak": valid_root(None, home / ".var/app", home),
        "snap": valid_root(None, home / 'snap', home),
        "dotfiles": home,
    }
    return {k: v for k, v in roots.items() if v is not None}


def parse_removals(home: Path) -> dict[str, list[str]]:
    logs = [Path("/var/log/pacman.log")]
    logs.extend(sorted(Path("/var/log").glob("pacman.log.*")))
    # Optional test fixture; never privileged paths under --home by default.
    override = os.environ.get("XDG_AUDIT_PACMAN_LOG")
    if override:
        logs = [Path(override)]
    removals: dict[str, list[str]] = {}
    regex = re.compile(r"^(\[[^]]+\]) \[ALPM\] removed ([^ ]+) ")
    for log in logs:
        if not log.is_file() or log.suffix in {".gz", ".xz", ".zst"}:
            continue
        try:
            with log.open("r", encoding="utf-8", errors="replace") as file:
                for line in file:
                    hit = regex.match(line)
                    if hit:
                        removals.setdefault(hit[2].lower(), []).append(hit[1])
        except OSError:
            continue
    return removals


def read_desktop_names(home: Path, data: Path) -> set[str]:
    locations = [Path("/usr/share/applications"), Path("/usr/local/share/applications"),
                 data / "applications", home / ".local/share/flatpak/exports/share/applications",
                 Path("/var/lib/flatpak/exports/share/applications")]
    names: set[str] = set()
    for base in locations:
        if not base.is_dir():
            continue
        for entry in base.glob("*.desktop"):
            names.add(normalize(entry.stem))
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            try:
                with entry.open(encoding="utf-8", errors="replace") as source:
                    parser.read_file(source)
                if not parser.has_section("Desktop Entry"):
                    continue
                section = parser["Desktop Entry"]
                for key in ("Name", "GenericName", "StartupWMClass", "Icon", "TryExec"):
                    if section.get(key):
                        names.add(normalize(section[key]))
                exec_line = section.get("Exec", "").strip()
                if exec_line:
                    try:
                        tokens = shlex.split(exec_line)
                    except ValueError:
                        tokens = exec_line.split()
                    # Env wrapper may be first argument.
                    for token in tokens[:4]:
                        token = Path(token).name
                        if token not in {"env", "flatpak", "run", "sh", "bash", "-c"} and not token.startswith("%"):
                            names.add(normalize(token))
            except (OSError, UnicodeError, configparser.Error):
                continue
    return names


def read_active_names(home: Path, roots: dict[str, Path]):
    """Backward-compatible inventory carrying provider health and provenance.

    A failed query is NOT treated as an empty installed-app list; no provider
    output is executed. pacman -Qmq is informational (foreign is not AUR).
    """
    from xdg_sources import (ActiveInventory, pacman_packages, pacman_foreign,
                             dpkg_packages, rpm_packages, flatpak_apps, snap_apps,
                             user_appimages, manual_binaries,
                             npm_global_packages, pipx_environments, native_package_source)

    installed = pacman_packages()
    foreign = pacman_foreign() if installed.status == "ok" else None
    dpkg = dpkg_packages()
    rpm = rpm_packages()
    flatpak = flatpak_apps()
    snap = snap_apps()
    appimage = user_appimages(home, roots.get('data', home / '.local/share'))
    manual = manual_binaries(home)
    npm = npm_global_packages(home)
    pipx = pipx_environments(home)
    probes = {"pacman": installed, "dpkg": dpkg, "rpm": rpm,
              "npm_global": npm, "pipx": pipx,
              "flatpak": flatpak, "snap": snap,
              "appimage": appimage, "manual_binary": manual}
    if foreign is not None:
        probes["pacman_foreign"] = foreign

    packages = set(installed.names)
    flatpaks = set(flatpak.names)
    snaps = set(snap.names)
    appimages = set(appimage.names)
    # Runtime process and user service checks remain protective, not ownership
    # evidence, and should not authorize deletion if the package DB is absent.
    processes = {line.strip().casefold() for line in command(
        ["ps", "-eo", "comm="], 12).splitlines() if line.strip()}
    units = set()
    for line in command(["systemctl", "--user", "list-unit-files",
                         "--no-legend", "--plain"], 15).splitlines():
        if line.split():
            units.add(line.split()[0].lower().split(".")[0])
    desktops = read_desktop_names(home, roots.get("data", home / ".local/share"))
    binary_candidates = {normalize(v) for v in (
        packages | flatpaks | snaps | appimages | units | processes)}
    binary_candidates |= {normalize(stem_package(x)) for x in packages}
    return ActiveInventory(
        (packages, flatpaks, snaps, appimages, units, processes, desktops,
         binary_candidates),
        status={name: p.status for name, p in probes.items()},
        foreign=foreign.names if foreign and foreign.status == "ok" else (),
        manual=manual.names,
        npm_global=npm.names, pipx=pipx.names,
        flatpak_ids=flatpak.app_ids if flatpak.status == "ok" else (),
        snap_ids=snap.app_ids if snap.status == 'ok' else (),
        appimage_paths=appimage.app_ids,
        native_source=native_package_source(),
        distro={"dpkg": dpkg.names, "rpm": rpm.names},
        provenance={name: p.note for name, p in probes.items() if p.note})

def references(home: Path, roots: dict[str, Path], names: set[str]) -> dict[str, set[str]]:
    """Search small session configs in one pass per file, not once per item.

    Keep the old token boundary semantics; `go`, `gh` and other very short
    names do not provide reliable ownership evidence. Never traverse symlinks.
    """
    sources = [roots.get("config", home / ".config") / p for p in
               ("niri", "dms", "DankMaterialShell", "fish", "systemd/user", "autostart", "quickshell")]
    sources.extend((home / ".profile", home / ".bashrc"))
    output = {n: set() for n in names}
    eligible: dict[str, set[str]] = {}
    for name in names:
        if len(name) >= 5:
            eligible.setdefault(name.casefold(), set()).add(name)
    if not eligible:
        return output
    # Longest first avoids partial matches when two directory names overlap.
    terms = sorted(eligible, key=lambda value: (-len(value), value))
    matches = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(v) for v in terms)
                         + r")(?![a-z0-9])")
    for base in sources:
        if base.is_symlink() or not base.exists():
            continue
        candidates = [base] if base.is_file() else []
        if base.is_dir():
            for parent, dirs, files in os.walk(base, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink() and d != ".git"]
                for filename in files:
                    candidates.append(Path(parent) / filename)
                if len(candidates) > 2500:
                    break
        for path in candidates:
            try:
                if (path.is_symlink() or is_backup_reference(path) or not path.is_file()
                        or path.stat().st_size > 262144):
                    continue
                if path.suffix.lower() in {".png", ".jpg", ".sqlite", ".db", ".so", ".ico", ".ttf", ".woff"}:
                    continue
                content = path.read_text(encoding="utf-8", errors="replace").casefold()
            except OSError:
                continue
            for found in set(matches.findall(content)):
                for name in eligible.get(found, ()):
                    output[name].add(str(path))
    return output


def nested_mounts_status(source: Path) -> bool | None:
    """True if source contains a mount point; None if mount table cannot be verified.

    /proc/self/mountinfo includes bind mounts and paths with escaped whitespace.
    Fail closed rather than ignoring an unavailable mount table.
    """
    def unescape_mount(value: str) -> str:
        return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), value)

    try:
        with Path("/proc/self/mountinfo").open("r", encoding="utf-8") as file:
            for line in file:
                cols = line.split()
                if len(cols) < 5:
                    return None
                mountpoint = unescape_mount(cols[4])
                if mountpoint == str(source) or mountpoint.startswith(str(source) + "/"):
                    return True
    except OSError:
        return None
    return False


def disk_sizes(paths: list[Path], on_chunk=None, stop=None) -> dict[str, int]:
    """du batch with NUL framing, does not follow root symlink and doesn't write anything."""
    result = {str(p): 0 for p in paths}
    if not paths or not shutil.which("du"):
        return result
    for start in range(0, len(paths), 25):
        if stop and stop():
            raise ScanCancelled()
        chunk = paths[start:start+25]
        try:
            p = subprocess.run(["du", "-s", "-B1", "-0", "--", *(str(p) for p in chunk)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120, check=False)
            for item in p.stdout.split(b"\0"):
                if not item:
                    continue
                size, separator, path = item.partition(b"\t")
                if separator:
                    result[os.fsdecode(path)] = int(size)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if on_chunk:
            on_chunk({str(p): result[str(p)] for p in chunk}, min(len(paths), start + len(chunk)), len(paths))
    return result


class ScanCancelled(Exception):
    """Scan was cancelled by the user. No filesystem changes were made."""


@dataclass
class Item:
    scope: str
    path: Path
    state: str = "UNKNOWN"
    reasons: list[str] = field(default_factory=list)
    bytes: int = 0
    protected: bool = False
    removable: bool = False
    identity: tuple[int, int, int] | None = None
    size_known: bool = False

    def json(self):
        signals = []
        for reason in self.reasons:
            normalized = reason.lower()
            evidence_types = (
                ('installed pacman package:', 'pacman', 'strong'),
                ('installed dpkg package:', 'dpkg', 'strong'),
                ('installed rpm package:', 'rpm', 'strong'),
                ('installed flatpak:', 'flatpak', 'strong'),
                ('installed snap:', 'snap', 'strong'),
                ('appimage found:', 'appimage', 'medium'),
                ('manual executable found', 'manual_binary', 'weak'),
                ('npm global directory found', 'npm_global', 'weak'),
                ('pipx environment found', 'pipx', 'weak'),
                ('installed-app inventory failed:', 'source_health', 'weak'),
                ('executable on path:', 'executable', 'medium'),
                ('running executable:', 'process', 'medium'),
                ('user systemd unit:', 'systemd_user', 'medium'),
                ('desktop entry', 'desktop', 'weak'),
                ('auxiliary installed package', 'pacman_helper', 'weak'),
                ('removed in pacman.log:', 'pacman_history', 'historical'),
                ('removed in dpkg.log:', 'dpkg_history', 'historical'),
                ('historical removed package:', 'pacman_history', 'historical'),
                ('mentioned in user session', 'session_reference', 'weak'),
                ('protected:', 'protection_policy', 'policy'),
                ('user allowlist', 'user_allowlist', 'policy'),
            )
            source, strength = next(((source, strength)
                for prefix, source, strength in evidence_types
                if normalized.startswith(prefix)), ('heuristic', 'unknown'))
            signals.append({'source': source, 'strength': strength, 'detail': reason})
        strong_installed = any(signal['strength'] == 'strong' for signal in signals)
        historical_only = (self.state == 'CANDIDATE' and bool(signals)
                           and all(signal['strength'] == 'historical' for signal in signals))
        evidence_level = ('installed_evidence' if strong_installed else
                          'historical_only' if historical_only else
                          'protective_hint' if self.state in {'ACTIVE', 'REVIEW'} else
                          'policy_protected' if self.state == 'PROTECTED' else 'unknown')
        return {'schema_version': 2, 'scope': self.scope, 'path': str(self.path),
                'state': self.state, 'size_bytes': self.bytes if self.size_known else None,
                'size_calculated': self.size_known,
                'evidence_level': evidence_level, 'orphan_ownership_verified': False,
                'reasons': self.reasons, 'evidence': signals,
                'protected': self.protected, 'removable': self.removable,
                'risk_flags': (["protected"] if self.protected else
                               (["unverified_owner"] + (["history_only"] if historical_only else [])
                                if self.state in ('CANDIDATE','UNKNOWN','REVIEW') else []))}


def names_for(name: str, aliases: dict[str, list[str]] | None = None) -> set[str]:
    aliases = ALIASES if aliases is None else aliases
    values = {name, name.lower(), stem_package(name)}
    values.update(aliases.get(name.casefold(), []))
    if "." in name:
        suffix = name.rsplit(".", 1)[-1]
        # A version tail like ".1" in a zcompdump file is not an app ID.
        # Only sufficiently descriptive alphabetic app-id components qualify.
        if len(suffix) >= 3 and re.search(r"[a-z]", suffix, re.I):
            values.add(suffix)
    return {normalize(x) for x in values if x}


def scan(home: Path, scopes: list[str], keeps: set[str], extra_aliases: dict[str, list[str]],
         quick: bool, progress=None, on_batch=None, cancelled=None):
    """Scan without writes. progress(stage) reports phases, not fictitious percents."""
    times = {}
    clock = time.perf_counter()
    def stage(name):
        if cancelled and cancelled():
            raise ScanCancelled()
        nonlocal clock
        now = time.perf_counter()
        if name != 'Pakiety i aplikacje':
            times[previous[0]] = round((now - clock) * 1000)
        clock = now
        previous[0] = name
        if progress:
            progress(name)
    previous = ['Pakiety i aplikacje']
    stage('Pakiety i aplikacje')
    roots = xdg_roots(home)
    inventory = read_active_names(home, roots)
    packages, flatpaks, snaps, appimages, units, processes, desktops, active = inventory
    health = getattr(inventory, "status", None)
    from xdg_sources import verified_native_source, dpkg_removals, package_name_count
    native_source = getattr(inventory, 'native_source', 'pacman')
    try:
        verified_native_source(inventory)
        native_available = True
    except ValueError:
        native_available = False
    provider_failures = set() if health is None else {
        name for name, state in health.items()
        if name != "pacman_foreign" and state not in ("ok", "absent")
    }
    removals = (dpkg_removals() if native_source == 'dpkg' else
                {} if native_source == 'rpm' else parse_removals(home))
    removal_log = 'dpkg.log' if native_source == 'dpkg' else 'pacman.log'
    current_native = (packages if native_source == 'pacman' else
                      getattr(inventory, 'distro', {}).get(native_source, ()))
    native_count = package_name_count(native_source, current_native)
    removed_normal = {normalize(p): p for p in removals if p not in current_native}
    removed_normal.update({normalize(stem_package(p)): p for p in removals if p not in current_native})
    alias_map = {**ALIASES, **{k.casefold(): v for k, v in extra_aliases.items()}}
    stage('Katalogi i klasyfikacja')
    items: list[Item] = []
    for scope in scopes:
        base = roots.get(scope)
        if not base or not base.is_dir():
            continue
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for path in children:
            if cancelled and cancelled():
                raise ScanCancelled()
            if scope == "dotfiles" and (not path.name.startswith(".") or path.name in {".", ".."}):
                continue
            it = Item(scope=scope, path=path)
            try:
                info = path.lstat()
                it.identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
            except OSError:
                # An entry disappearing during the scan is never removable.
                it.state, it.protected = "PROTECTED", True
                it.reasons.append("entry disappeared / cannot stat safely")
                items.append(it)
                continue
            keys = names_for(path.name, alias_map)
            # A scan without installed package listing is intrinsically inconclusive.
            if path.is_symlink():
                it.state, it.protected = "PROTECTED", True
                it.reasons.append("symlink; no operations on links")
            elif path.name in PROTECTED[scope] or normalize(path.name) in {normalize(x) for x in PROTECTED[scope]}:
                it.state, it.protected = "PROTECTED", True
                it.reasons.append(protection_reason(scope, path.name))
            elif BACKUP_RE.search(path.name):
                it.state, it.protected = "PROTECTED", True
                it.reasons.append("backup / PSD recovery")
            elif SENSITIVE_RE.search(path.name):
                it.state, it.protected = "PROTECTED", True
                it.reasons.append("name suggests credentials or sensitive user data")
            elif path.is_mount():
                it.state, it.protected = "PROTECTED", True
                it.reasons.append("mount point")
            elif normalize(path.name) in keeps:
                it.state, it.protected = "PROTECTED", True
                it.reasons.append("user allowlist")
            else:
                if scope == "flatpak":
                    # ~/.var/app/<id> belongs to the Flatpak installation
                    # namespace. Native pacman/dpkg/rpm Firefox and arbitrary
                    # executables cannot prove that the *Flatpak app ID* is
                    # installed. Preserve REVIEW for old/unverified data.
                    flatpak_health = (health or {}).get("flatpak")
                    flatpak_ids = getattr(inventory, "flatpak_ids", None)
                    if flatpak_ids is None:  # legacy unit-test inventory tuple
                        flatpak_ids = flatpaks
                    if path.name.casefold() in flatpak_ids and flatpak_health in (None, "ok"):
                        it.state = "ACTIVE"
                        it.reasons.append("installed Flatpak: " + path.name)
                    else:
                        it.state = "REVIEW"
                        if flatpak_health not in (None, "ok"):
                            it.reasons.append(
                                "Flatpak inventory unavailable; cannot verify app ID")
                        else:
                            it.reasons.append(
                                "Flatpak app-id is not currently installed; check manually")
                    items.append(it)
                    continue
                if scope == 'snap':
                    from xdg_sources import valid_snap_id
                    snap_health = (health or {}).get('snap')
                    snap_ids = getattr(inventory, 'snap_ids', None)
                    if snap_ids is None:
                        snap_ids = snaps  # legacy inventory callers
                    if not valid_snap_id(path.name):
                        it.state, it.protected = 'PROTECTED', True
                        it.reasons.append('not a canonical Snap instance directory')
                    elif path.name in snap_ids and snap_health in (None, 'ok'):
                        it.state = 'ACTIVE'
                        it.reasons.append('installed Snap: ' + path.name)
                    else:
                        it.state = 'REVIEW'
                        it.reasons.append('Snap instance is not verified as installed; check manually'
                            if snap_health in (None, 'ok') else
                            'Snap inventory unavailable; cannot verify instance')
                    items.append(it)
                    continue
                # Current installed inventory is authoritative. An old removal
                # event must not override a package now present under a new
                # variant (brave-bin -> brave-browser, opera -> opera-stable).
                installed, helpers = match_installed_packages(path.name, packages, alias_map)
                installed_distro = {}
                for provider, names in getattr(inventory, "distro", {}).items():
                    matches, _aux = match_installed_packages(path.name, names, alias_map)
                    if matches:
                        installed_distro[provider] = matches
                installed_flatpak = nonpacman_matches(path.name, flatpaks, alias_map)
                installed_snap = nonpacman_matches(path.name, snaps, alias_map)
                installed_appimage = nonpacman_matches(path.name, appimages, alias_map)
                manual_matches = nonpacman_matches(
                    path.name, getattr(inventory, "manual", ()), alias_map)
                npm_matches = nonpacman_matches(
                    path.name, getattr(inventory, "npm_global", ()), alias_map)
                pipx_matches = nonpacman_matches(
                    path.name, getattr(inventory, "pipx", ()), alias_map)
                # Generic units cannot establish application ownership.
                generic_units = {"app", "session", "service", "scope", "slice",
                                 "timer", "target", "socket", "path"}
                found_units = nonpacman_matches(
                    path.name, units.difference(generic_units), alias_map)
                found_processes = nonpacman_matches(path.name, processes, alias_map)
                found_desktops = nonpacman_matches(path.name, desktops, alias_map)
                found_exec = [x for x in {path.name, path.name.lower(), stem_package(path.name),
                                         *alias_map.get(path.name.casefold(), [])}
                              if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{2,}", x) and shutil.which(x)]
                if (installed or installed_distro or installed_flatpak or installed_snap
                        or installed_appimage or found_units or found_processes or found_exec):
                    it.state = "ACTIVE"
                    reasons = []
                    if installed:
                        foreign = getattr(inventory, "foreign", ())
                        reasons += [f"installed pacman package: {pkg} (match: {pat})" +
                                    (" [foreign: AUR or local]" if pkg in foreign else "")
                                    for pkg, pat in installed[:5]]
                    for provider, matches in sorted(installed_distro.items()):
                        reasons += [f"installed {provider} package: {pkg} (match: {pat})"
                                    for pkg, pat in matches[:5]]
                    if installed_flatpak:
                        reasons.append("installed Flatpak: " + ",".join(installed_flatpak[:3]))
                    if installed_snap:
                        reasons.append("installed Snap: " + ",".join(installed_snap[:3]))
                    if installed_appimage:
                        reasons.append("AppImage found: " + ",".join(installed_appimage[:3]))
                    if found_units:
                        reasons.append("user systemd unit: " + ",".join(found_units[:3]))
                    if found_processes:
                        reasons.append("running executable: " + ",".join(found_processes[:3]))
                    if found_exec:
                        reasons.append("executable on PATH: " + ",".join(sorted(found_exec)[:3]))
                    if found_desktops:
                        reasons.append("desktop entry (supporting evidence): " + ",".join(found_desktops[:3]))
                    it.reasons = reasons
                else:
                    removed = [removed_normal[k] for k in keys if k in removed_normal]
                    if helpers or found_desktops or manual_matches or npm_matches or pipx_matches:
                        it.state = "REVIEW"
                        if helpers:
                            it.reasons.append("auxiliary installed package, not proof of app: "
                                              + ",".join(f"{pkg} ({pat})" for pkg, pat in helpers[:4]))
                        if found_desktops:
                            it.reasons.append("desktop entry exists; may be stale: " + ",".join(found_desktops[:3]))
                        if manual_matches:
                            it.reasons.append("manual executable found (protective hint only): " +
                                              ",".join(manual_matches[:3]))
                        if npm_matches:
                            it.reasons.append("npm global directory found (protective hint only): " +
                                              ",".join(npm_matches[:3]))
                        if pipx_matches:
                            it.reasons.append("pipx environment found (protective hint only): " +
                                              ",".join(pipx_matches[:3]))
                        if removed:
                            it.reasons.append(f"removed in {removal_log}: " + ",".join(sorted(set(removed))[:4]))
                    elif removed:
                        it.state = ("CANDIDATE" if native_available and not provider_failures
                                    else "REVIEW")
                        it.reasons.append(f"removed in {removal_log}: " + ",".join(sorted(set(removed))[:4]))
                        if not native_available:
                            it.reasons.append("native package inventory unavailable; cannot confirm removal")
                        if provider_failures:
                            it.reasons.append("installed-app inventory failed: " +
                                              ",".join(sorted(provider_failures)))
                    else:
                        it.state = "UNKNOWN"
                        it.reasons.append("no verified installed application or owner (NOT proof of orphan)")
            items.append(it)
    # A session reference provides protective evidence even for UNKNOWN entries.
    # Limit scanning to ambiguous entries; ACTIVE and PROTECTED need no further handling.
    ambiguous = {i.path.name for i in items if i.state in {"CANDIDATE", "UNKNOWN"}}
    stage('Powiązania konfiguracji')
    refs = references(home, roots, ambiguous) if ambiguous else {}
    for it in items:
        if it.state in {"CANDIDATE", "UNKNOWN"} and refs.get(it.path.name):
            it.state = "REVIEW"
            it.reasons.append("mentioned in user session config: " + ",".join(sorted(refs[it.path.name])[:3]))
        if it.state == "UNKNOWN" and it.path.name.casefold() == "sha256sums":
            it.state = "REVIEW"
            it.reasons.append("checksum manifest in XDG config, not an application ID; inspect contents")
        if it.state == "CANDIDATE":
            it.removable = True
    # The first batch is ready as soon as classification and reference checks
    # finish. Sizes may still be unknown. GUI updates are queued on its UI thread.
    if on_batch:
        on_batch('classified', tuple(items), 0, len(items))
    stage('Rozmiary katalogów' if not quick else 'Zakończenie')
    if not quick:
        by_path = {str(it.path): it for it in items}
        def updated(partial, done, total):
            changed = []
            for path, number in partial.items():
                if path in by_path:
                    by_path[path].bytes = number
                    by_path[path].size_known = True
                    changed.append(by_path[path])
            if on_batch:
                on_batch('sizes', tuple(changed), done, total)
        disk_sizes([it.path for it in items if not it.path.is_symlink()],
                   on_chunk=updated, stop=cancelled)
    if cancelled and cancelled():
        raise ScanCancelled()
    # Candidates first; order stable within group, larger entries first.
    priority = {"CANDIDATE": 0, "REVIEW": 1, "UNKNOWN": 2, "ACTIVE": 3, "PROTECTED": 4}
    items.sort(key=lambda i: (priority[i.state], -i.bytes, i.scope, i.path.name.casefold()))
    times[previous[0]] = round((time.perf_counter() - clock) * 1000)
    return items, roots, {"pacman_packages": len(packages), "flatpak_entries": len(flatpaks),
                          "removed_package_names": len(removals), "desktop_names": len(desktops),
                          "phase_times_ms": times,
                          "installed_sources": dict(health if health is not None else {"pacman": "legacy"}),
                          'native_package_source': native_source,
                          'native_packages': native_count,
                          "pacman_foreign_count": len(getattr(inventory, "foreign", ()))} 


def human(size: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}B"
        size /= 1024
    return "?"


def compare_report(items: list[Item], previous_file: Path, scopes: list[str] | None = None) -> list[dict]:
    """Read a previously exported JSON report, no writes or background state."""
    try:
        payload = json.loads(previous_file.read_text(encoding="utf-8"))
        old_entries = payload["entries"]
        if scopes is not None and "scopes" in payload and payload["scopes"] != scopes:
            raise ValueError("different scan scopes; compare reports from the same --scope")
        if not isinstance(old_entries, list):
            raise ValueError("entries is not an array")
        before = {}
        for row in old_entries:
            if (not isinstance(row, dict) or not isinstance(row.get("path"), str)
                    or row.get("state") not in {"CANDIDATE", "REVIEW", "UNKNOWN", "ACTIVE", "PROTECTED"}
                    or not isinstance(row.get("reasons", []), list)):
                raise ValueError("invalid entry in JSON report")
            before[row["path"]] = row
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"ERROR: invalid --compare report: {exc}") from exc
    now = {str(item.path): item for item in items}
    changes = []
    for path in sorted(before.keys() | now.keys()):
        old = before.get(path)
        current = now.get(path)
        old_state = old["state"] if old else "NOT_SCANNED"
        new_state = current.state if current else "NOT_SCANNED"
        old_reasons = old.get("reasons", []) if old else []
        new_reasons = current.reasons if current else []
        if old_state != new_state or old_reasons != new_reasons:
            changes.append({"path": path, "old_state": old_state,
                            "new_state": new_state, "old_reasons": old_reasons,
                            "new_reasons": new_reasons})
    return changes


def print_comparison(changes: list[dict]):
    print(f"\nCHANGES FROM PREVIOUS REPORT: {len(changes)}")
    for change in changes:
        print(f"  {change['old_state']} -> {change['new_state']}: {change['path']}")
        for reason in change["old_reasons"]:
            if reason not in change["new_reasons"]:
                print(f"    - {reason}")
        for reason in change["new_reasons"]:
            if reason not in change["old_reasons"]:
                print(f"    + {reason}")



def print_report(items: list[Item], stats: dict, all_items: bool, removal_mode: bool = False):
    from collections import Counter
    counts = Counter(i.state for i in items)
    native = stats.get('native_package_source', 'pacman')
    native_count = stats.get('native_packages', stats.get('pacman_packages', 0) if native == 'pacman' else 0)
    native_health = stats.get('installed_sources', {}).get(native, 'unknown')
    print(f"xdg-audit v{VERSION} | NATIVE={native or 'unknown'} PACKAGES={native_count} "
          f"SOURCE_HEALTH={native_health} FLATPAK={stats['flatpak_entries']} "
          f"DESKTOP_TOKENS={stats['desktop_names']} HISTORY={stats['removed_package_names']}")
    print(" | ".join(f"{state}={counts[state]}" for state in ("CANDIDATE", "REVIEW", "UNKNOWN", "ACTIVE", "PROTECTED")))
    print(("AUDIT READ ONLY; --remove requires explicit selection + confirmation."
           if removal_mode else "READ ONLY. No changes to your files."))
    print("CANDIDATE != verified orphan. --remove only moves to quarantine.")
    for n, it in enumerate(items, 1):
        if not all_items and it.state in {"ACTIVE", "PROTECTED"}:
            continue
        reason = "; ".join(it.reasons)
        print(f"[{n:3}] {it.state:<10} {human(it.bytes):>9} [{it.scope:8}] {it.path}\n"
              f"      {reason}")


def check_no_root():
    if os.geteuid() == 0:
        raise SystemExit("ERROR: Don't run this as root or via sudo; scan only your own HOME.")


def quarantine_dir(home: Path, roots: dict[str, Path]) -> Path:
    data = roots.get("data", home / ".local/share")
    return data / "xdg-audit-quarantine"


def tokenize_selection(raw: str) -> list[str]:
    """Accept comma or whitespace separators, quoted paths and 2-5 numeric ranges."""
    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    lexer.whitespace += ","
    lexer.commenters = ""  # a # in a path is not a comment
    return list(lexer)


def resolve_selection(raw: str, items: list[Item], home: Path) -> tuple[list[str], list[str]]:
    """Stable absolute paths (or ~/...) and report-local IDs, never arbitrary globs."""
    try:
        tokens = tokenize_selection(raw)
    except ValueError as exc:
        return [], [f"Invalid selection syntax: {exc}. Example: 1,2,3 or 1 2 3"]
    by_index = {str(i): str(item.path) for i, item in enumerate(items, 1)}
    by_path = {str(item.path) for item in items}
    selected: list[str] = []
    errors: list[str] = []
    for token in tokens:
        values = []
        if re.fullmatch(r"[0-9]+-[0-9]+", token):
            first, last = map(int, token.split("-"))
            if first <= 0 or last < first or last - first > 10000:
                errors.append(f"Invalid range {token!r}; example 1-3")
                continue
            values = [str(i) for i in range(first, last+1)]
        else:
            values = [token]
        for value in values:
            if value in by_index:
                path = by_index[value]
            elif value.isdecimal():
                errors.append(f"Unknown report ID {value!r}; use an ID from this scan")
                continue
            else:
                # No fuzzy matching, no filename-only lookup: such matches are unsafe.
                path = str(home / value[2:]) if value.startswith("~/") else value
                if not Path(path).is_absolute() or path not in by_path:
                    errors.append(f"Unknown path {value!r}; use exact absolute path or an ID")
                    continue
            if path not in selected:
                selected.append(path)
    return selected, errors


def move_items(items: list[Item], roots: dict[str, Path], home: Path,
               selected: list[str], allow_uncertain: bool, extra_aliases=None, keep_names=()):
    if not sys.stdin.isatty():
        raise SystemExit("ERROR: --remove requires an interactive TTY; unattended cleanup is disabled.")
    lookup = {str(i.path): i for i in items}
    errors = []
    if not selected:
        print("Select IDs (1,2,3 / 1 2 3 / 1-3) or exact paths (empty = cancel):")
        raw = input("IDs> ").strip()
        if not raw:
            print("Cancelled; no changes.")
            return
        selected, errors = resolve_selection(raw, items, home)
    chosen: list[Item] = []
    uncertain: list[Item] = []
    for path in selected:
        if path not in lookup:
            errors.append(f"Unknown path {path!r}; use an exact path from this report")
            continue
        it = lookup[path]
        if it.protected or it.state in {"ACTIVE", "PROTECTED"}:
            errors.append(f"BLOCKED {it.state}: {it.path} (never movable)")
            continue
        if not it.removable and not allow_uncertain:
            errors.append(f"SKIPPED {it.state}: {it.path} (requires --allow-uncertain)")
            continue
        if it not in chosen:
            chosen.append(it)
            if it.state in {"REVIEW", "UNKNOWN"}:
                uncertain.append(it)
    if errors:
        print("\nIGNORED / BLOCKED SELECTIONS (no action on these paths):")
        for error in errors:
            print(f"  ! {error}")
    if not chosen:
        print("Nothing eligible selected; no changes.")
        return
    print("\nMOVE PLAN (quarantine only; not permanent deletion):")
    total = sum(it.bytes for it in chosen)
    for it in chosen:
        print(f"  {it.state:10} {human(it.bytes):>9} {it.path}")
        for reason in it.reasons:
            print(f"    evidence: {reason}")
    print(f"SELECTED={len(chosen)} UNCERTAIN={len(uncertain)} SKIPPED={len(errors)} TOTAL={human(total)}")
    print(f"DESTINATION: {quarantine_dir(home, roots)}/<RUN_ID>/")
    print("Close affected apps first. Configurations may include logins and personal settings.")
    if uncertain:
        print("CAUTION: REVIEW/UNKNOWN paths are not verified leftovers.")
        if input("Type UNCERTAIN to acknowledge: ").strip() != "UNCERTAIN":
            print("Cancelled; no changes.")
            return
    if input("Type exactly MOVE to confirm: ").strip() != "MOVE":
        print("Cancelled; no changes.")
        return
    commit_quarantine(chosen, roots, home, allow_uncertain=allow_uncertain,
                      extra_aliases=extra_aliases, keep_names=keep_names)




def _sync_directory(path: Path) -> None:
    """Durably record directory entry changes where filesystem supports fsync."""
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_manifest_atomic(path: Path, data: dict) -> None:
    """Use the same anchored durable writer for MOVE, RESTORE and PURGE."""
    from xdg_quarantine_lifecycle import _open_path, _write_manifest
    if path.name != 'manifest.json' or path.is_symlink():
        raise ValueError('Unsafe manifest name or symlink')
    fd = _open_path(path.parent)
    try:
        _write_manifest(fd, data)
    finally:
        os.close(fd)

def _safe_rename_noreplace(source: Path, destination: Path,
                           expected_identity: tuple[int, int, int] | None = None) -> None:
    """Linux-only anchored, no-overwrite rename for sensitive user files.

    Every ancestor is opened with O_NOFOLLOW relative to its already-checked
    parent (not only the final parent directory). The atomic
    renameat2 RENAME_NOREPLACE prevents clobbering a destination introduced
    between validation and the move. An inode postcheck rejects late swaps.
    """
    import ctypes
    import errno
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError(errno.ENOTSUP, "Missing safe directory descriptor support")
    libc = ctypes.CDLL(None, use_errno=True)
    func = getattr(libc, "renameat2", None)
    if func is None:
        raise OSError(errno.ENOTSUP, "Kernel/libc lacks renameat2; refusing unsafe move")
    func.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    func.restype = ctypes.c_int
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    def checked_parent_fd(path: Path) -> int:
        # O_NOFOLLOW on an absolute path alone does not reject symlink ancestors.
        if not path.is_absolute() or path.name in ('', '.', '..'):
            raise ValueError('Rename requires an absolute, normal filename')
        fd = os.open('/', flags)
        try:
            for component in path.parent.parts[1:]:
                if component in ('', '.', '..'):
                    raise ValueError('Unsafe path component')
                nxt = os.open(component, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
            return fd
        except BaseException:
            os.close(fd)
            raise
    src_fd = checked_parent_fd(source)
    try:
        dst_fd = checked_parent_fd(destination)
        try:
            before = os.stat(source.name, dir_fd=src_fd, follow_symlinks=False)
            identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode))
            if stat.S_ISLNK(before.st_mode) or (expected_identity is not None and identity != expected_identity):
                raise ValueError("Source changed or became a symlink")
            if func(src_fd, os.fsencode(source.name), dst_fd, os.fsencode(destination.name), 1) != 0:
                err = ctypes.get_errno()
                raise OSError(err, os.strerror(err), str(destination))
            after = os.stat(destination.name, dir_fd=dst_fd, follow_symlinks=False)
            final_identity = (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode))
            if final_identity != identity:
                # A concurrent rename must not become a silent successful move.
                # Never overwrite a re-created original during recovery.
                if func(dst_fd, os.fsencode(destination.name), src_fd, os.fsencode(source.name), 1) != 0:
                    raise OSError(errno.EBUSY, "Destination inode changed; manual recovery required")
                raise ValueError("Entry changed during rename; rolled back")
        finally:
            os.close(dst_fd)
    finally:
        os.close(src_fd)


def commit_quarantine(chosen: list[Item], roots: dict[str, Path], home: Path,
                      allow_uncertain: bool = False, emit=print, extra_aliases=None, keep_names=()):
    """Share the same checked move implementation between CLI and GTK.

    Call ONLY after explicit user confirmation. No recursive deletion occurs.
    Does not trust frontend eligibility; verifies category and paths again.
    """
    if not chosen:
        raise ValueError("No entries selected")
    if len({str(it.path) for it in chosen}) != len(chosen):
        raise ValueError("Duplicate selected path")
    for it in chosen:
        if (it.protected or it.state in {"ACTIVE", "PROTECTED"}
                or (not it.removable and not (allow_uncertain and it.state in {"REVIEW", "UNKNOWN"}))):
            raise ValueError(f"Blocked entry: {it.path} [{it.state}]")
        if (it.scope not in roots or it.path.parent != roots[it.scope]
                or it.path == home or it.identity is None):
            raise ValueError(f"Invalid scan entry: {it.path}")
    # Revalidate installation evidence immediately before any filesystem move:
    # the application might have been installed after the scan completed.
    # Require the actual OS database; optional foreign tools cannot replace it.
    current_inventory = read_active_names(home, roots)
    (current_packages, current_flatpaks, current_snaps, current_appimages,
     current_units, current_processes, _desktops, _active) = current_inventory
    current_health = getattr(current_inventory, "status", None)
    from xdg_sources import verified_native_source
    verified_native_source(current_inventory)
    if current_health:
        failures = sorted(name for name, state in current_health.items()
                          if name != "pacman_foreign" and state not in ("ok", "absent"))
        if failures:
            raise ValueError("Installed-app evidence providers failed: " +
                             ",".join(failures) + "; refusing quarantine")
    # Preferences can change after the original scan; do not trust stale GUI
    # eligibility, even when the user has explicitly selected the entry.
    from xdg_prefs import load as load_preferences
    latest_prefs, preferences_error = load_preferences(home, roots)
    if preferences_error:
        raise ValueError(f'Cannot verify saved protection rules: {preferences_error}')
    protected_names = {normalize(name) for name in (*latest_prefs['keep'], *keep_names)}
    alias_map = {**ALIASES, **latest_prefs['aliases'], **(extra_aliases or {})}
    for it in chosen:
        if normalize(it.path.name) in protected_names:
            raise ValueError(f'Entry is explicitly protected in current settings: {it.path}')
        if it.scope in ('snap', 'flatpak'):
            provider = it.scope
            canonical = getattr(current_inventory, provider + '_ids', None)
            if canonical is None:
                canonical = current_snaps if provider == 'snap' else current_flatpaks
            if current_health is not None and current_health.get(provider) != 'ok':
                raise ValueError(f'Cannot verify current {provider} inventory before quarantine; no changes')
            if it.path.name.casefold() in canonical:
                raise ValueError(f'Application is present now; refusing quarantine: {it.path}')
            if nonpacman_matches(it.path.name, current_processes, alias_map):
                raise ValueError(f'Application is running now; refusing quarantine: {it.path}')
            continue  # native package names do not own Snap/Flatpak namespaces
        installed, _helpers = match_installed_packages(it.path.name, current_packages, alias_map)
        live_distro = any(match_installed_packages(it.path.name, names, alias_map)[0]
                          for names in getattr(current_inventory, "distro", {}).values())
        live_other = any(nonpacman_matches(it.path.name, source, alias_map) for source in (
            current_flatpaks, current_snaps, current_appimages, current_units,
            current_processes, getattr(current_inventory, "manual", ()),
            getattr(current_inventory, "npm_global", ()),
            getattr(current_inventory, "pipx", ())))
        if installed or live_distro or live_other:
            raise ValueError(f"Application is present now; refusing quarantine: {it.path} ({installed[:3]})")
    root = quarantine_dir(home, roots)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run = root / stamp
    moved = []
    # Reject unexpected symlink/override in the quarantine destination.
    if root.is_symlink() or home not in root.resolve(strict=False).parents:
        raise SystemExit("ERROR: quarantine destination is a symlink or outside HOME; no changes.")
    # Write intent first; interrupted runs remain recoverable.
    run.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = run / "manifest.json"
    # Bind future restores to the entry actually moved into quarantine.
    # Older journals lack an identity field and retain their legacy behavior.
    plan = [{"source": str(it.path), "destination": str(run / it.scope / it.path.name),
             "scope": it.scope, "state": it.state, "size_bytes_before": it.bytes,
             "identity": list(it.identity),
             "reasons": it.reasons, "move_status": "planned"} for it in chosen]
    payload = {"version": VERSION, "created": stamp, "items": plan,
               "format": "intent-journal-v3"}
    _write_manifest_atomic(manifest, payload)
    _sync_directory(run.parent)
    for it in chosen:
        base = roots[it.scope]
        source = it.path
        try:
            info = source.lstat()
            now_identity = (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))
            if (it.identity != now_identity or not source.exists() or source.is_symlink()
                    or source.is_mount() or source.parent != base or source == base
                    or source == home or base.is_symlink() or info.st_uid != os.getuid()
                    or not (source.is_file() or source.is_dir())):
                emit(f"SKIPPED (unsafe/changed): {source}")
                continue
            if base.resolve() == root.resolve() or root in source.parents:
                emit(f"SKIPPED (quarantine path): {source}")
                continue
            if source.is_dir():
                mount_status = nested_mounts_status(source)
                if mount_status is not False:
                    emit(f"SKIPPED (nested mounts or cannot verify mount table): {source}")
                    continue
            destination = run / it.scope / source.name
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if info.st_dev != destination.parent.stat().st_dev:
                emit(f"SKIPPED (different devices): {source}")
                continue
            if destination.exists() or destination.is_symlink():
                emit(f"SKIPPED (collision): {source}")
                continue
            row = next(row for row in plan if row['source'] == str(source))
            # The intent survives a crash before or during the rename.
            row['move_status'] = 'moving'
            _write_manifest_atomic(manifest, payload)
            _safe_rename_noreplace(source, destination, it.identity)
            moved.append(str(source))
            _sync_directory(source.parent)
            _sync_directory(destination.parent)
            from xdg_quarantine_lifecycle import capture_inventory
            try:
                row['tree_inventory'] = capture_inventory(destination)
            except (OSError, ValueError) as exc:
                # The move already happened. Preserve a restorable journal but
                # never make an unverified tree eligible for purge.
                _write_manifest_atomic(manifest, payload)
                emit(f"MOVED, but purge inventory unavailable (restore-only): {destination}: {exc}")
                continue
            row['move_status'] = 'moved'
            _write_manifest_atomic(manifest, payload)
            emit(f"MOVED {source} -> {destination}")
        except (OSError, ValueError) as exc:
            emit(f"ERROR moving {source}: {exc}")
    emit(f"Moved {len(moved)}/{len(chosen)} entries to quarantine.")
    emit(f"Restore with: python3 {Path(__file__).name} --restore {stamp}")
    emit(f"Manifest: {manifest}")

    return {"run_id": stamp, "moved": moved, "planned": len(chosen), "manifest": str(manifest)}



def quarantine_runs(home: Path, roots: dict[str, Path]) -> list[dict]:
    """Read-only list of completed or interrupted operations (no trust in manifests)."""
    base = quarantine_dir(home, roots)
    result = []
    if not base.is_dir() or base.is_symlink():
        return result
    for run in sorted(base.iterdir(), reverse=True):
        if not re.fullmatch(r"\d{8}-\d{6}-\d{6}", run.name) or run.is_symlink():
            continue
        manifest = run / "manifest.json"
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            rows = data.get("items", [])
            if not isinstance(rows, list):
                continue
            reconciled = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                view = row.copy()
                # Interrupted write: destination exists although manifest says planned.
                # Reconcile display only; never implicitly move/restore any data.
                scope = view.get('scope')
                if scope in roots:
                    original = Path(str(view.get('source', '')))
                    moved_path = Path(str(view.get('destination', '')))
                    if (original.parent == roots[scope] and moved_path.parent == run / scope
                            and moved_path.name == original.name and not moved_path.is_symlink()
                            and moved_path.exists() and not original.exists()):
                        view['move_status'] = 'moved'
                        view['recovered_from_interrupted_manifest'] = row.get('move_status') != 'moved'
                    elif (original.parent == roots[scope] and moved_path.parent == run / scope
                            and moved_path.name == original.name and not original.is_symlink()
                            and original.exists() and not moved_path.exists()):
                        if row.get('move_status') in ('moved', 'moving', 'restoring'):
                            view['move_status'] = 'restored'
                reconciled.append(view)
            states = [x.get("move_status") for x in reconciled]
            terminal = bool(states) and all(x in ("purged", "restored") for x in states)
            if terminal:
                from xdg_quarantine_history import history_info
                try:
                    state = history_info(home, roots, run.name)["status"]
                except (ValueError, OSError):
                    state = "ERROR"
            elif states and all(x == "moved" for x in states):
                state = "QUARANTINED"
            else:
                state = "INCOMPLETE"
            result.append({"run_id": run.name, "items": reconciled,
                           "status": state, "purged_at": data.get("purged_at"),
                           "moved": sum(r.get("move_status") == "moved" for r in reconciled)})
        except (ValueError, OSError, UnicodeError):
            continue
    return result


def restore_quarantine_run(home: Path, roots: dict[str, Path], run_id: str, emit=print) -> dict:
    """GUI-safe restore of an explicitly confirmed whole run. Never overwrite."""
    if not re.fullmatch(r"\d{8}-\d{6}-\d{6}", run_id):
        raise ValueError("Invalid quarantine ID")
    base = quarantine_dir(home, roots)
    run = base / run_id
    if base.is_symlink() or run.is_symlink() or not run.is_dir():
        raise ValueError("Unsafe or missing quarantine run")
    manifest = run / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Missing or unsafe manifest")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid manifest")
    # V3 journals bind restore to the original inode/device/file type.
    # Legacy manifests predate identity tracking; maintain restore support.
    identity_required = payload.get('format') == 'intent-journal-v3'
    count = 0
    skipped = 0
    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue
        scope = row.get("scope")
        if scope not in roots:
            skipped += 1
            continue
        src = Path(str(row.get("source", "")))
        dest = Path(str(row.get("destination", "")))
        root = roots[scope]
        expected_identity = None
        if identity_required:
            raw_identity = row.get('identity')
            if (not isinstance(raw_identity, list) or len(raw_identity) != 3
                    or any(type(value) is not int or value < 0 for value in raw_identity)
                    or raw_identity[2] not in (stat.S_IFREG, stat.S_IFDIR)):
                skipped += 1
                emit(f"SKIPPED missing/invalid quarantine identity: {src}")
                continue
            expected_identity = tuple(raw_identity)
        if (identity_required and row.get('move_status') in ('moving', 'moved', 'restoring')
                and src.parent == root and dest.parent == run / scope and dest.name == src.name
                and src != home and src != root and not dest.exists() and not dest.is_symlink()):
            # A crash can leave an already-returned object and a stale intent.
            # Only the original inode can complete this explicitly requested
            # restore; a newly created collision must never complete a journal.
            from xdg_quarantine_lifecycle import _open_path, _identity
            try:
                originalfd = _open_path(root)
                try:
                    original = os.stat(src.name, dir_fd=originalfd, follow_symlinks=False)
                finally:
                    os.close(originalfd)
                scopefd = _open_path(dest.parent)
                try:
                    try:
                        os.stat(dest.name, dir_fd=scopefd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        raise ValueError('Quarantine object reappeared during restore recovery')
                finally:
                    os.close(scopefd)
                if _identity(original) != expected_identity or original.st_uid != os.getuid():
                    raise ValueError('Original path contains a different object')
                row['move_status'] = 'restored'
                _write_manifest_atomic(manifest, payload)
                count += 1
                emit(f'RESTORED {src}')
                continue
            except (OSError, ValueError) as exc:
                skipped += 1
                emit(f'ERROR reconciling restore {src}: {exc}')
                continue
        if (src.parent != root or dest.parent != run / scope or dest.name != src.name
                or src == home or src == root or dest.is_symlink() or root.is_symlink()
                or not (dest.is_dir() or dest.is_file()) or src.exists() or src.is_symlink()
                or dest.is_mount() or dest.lstat().st_uid != os.getuid()
                or (dest.is_dir() and nested_mounts_status(dest) is not False)):
            skipped += 1
            emit(f"SKIPPED unsafe/conflict: {src}")
            continue
        did_restore = False
        try:
            row['move_status'] = 'restoring'
            _write_manifest_atomic(manifest, payload)
            _safe_rename_noreplace(dest, src, expected_identity)
            did_restore = True
            count += 1
            _sync_directory(dest.parent)
            _sync_directory(src.parent)
            row['move_status'] = 'restored'
            _write_manifest_atomic(manifest, payload)
            emit(f"RESTORED {src}")
        except (OSError, ValueError) as exc:
            if not did_restore:
                skipped += 1
            emit(f"ERROR restoring {src}: {exc}")
    return {"restored": count, "skipped": skipped, "run_id": run_id}

def inspect_quarantine_run(home: Path, roots: dict[str, Path], run_id: str) -> dict:
    from xdg_quarantine_lifecycle import inspect_run
    return inspect_run(home, roots, run_id, nested_mounts_status, allow_unsealed=True)


def purge_quarantine_run(home: Path, roots: dict[str, Path], run_id: str,
                         dry_run: bool = True, emit=print) -> dict:
    from xdg_quarantine_lifecycle import purge_run
    return purge_run(home, roots, run_id, nested_mounts_status, dry_run=dry_run, emit=emit)


def expired_quarantine_runs(home: Path, roots: dict[str, Path]) -> list[str]:
    from xdg_quarantine_lifecycle import expired_run_ids
    from xdg_retention import load
    return expired_run_ids(quarantine_runs(home, roots), load(home, roots)["days"])


def cleanup_quarantine_history(home: Path, roots: dict[str, Path], run_id: str,
                               dry_run: bool = True) -> dict:
    from xdg_quarantine_history import cleanup_history
    return cleanup_history(home, roots, run_id, dry_run=dry_run)


def completed_quarantine_history(home: Path, roots: dict[str, Path]) -> list[str]:
    from xdg_quarantine_history import completed_history_candidates
    return completed_history_candidates(home, roots)


def expired_quarantine_history(home: Path, roots: dict[str, Path]) -> list[str]:
    from xdg_quarantine_history import history_candidates
    return history_candidates(home, roots,
                              [x["run_id"] for x in quarantine_runs(home, roots)])


def adopt_quarantine_inventory(home: Path, roots: dict[str, Path], run_id: str) -> dict:
    """User-confirmed snapshot of current contents after access recovery."""
    from xdg_quarantine_lifecycle import adopt_legacy_run
    return adopt_legacy_run(home, roots, run_id, nested_mounts_status)


def quarantine_access_recoverable_error(error: BaseException) -> bool:
    from xdg_access import needs_access_recovery
    return needs_access_recovery(error)


def diagnose_quarantine_access(home: Path, roots: dict[str, Path], run_id: str) -> dict:
    from xdg_access import diagnose_access
    return diagnose_access(home, roots, run_id)


def repair_quarantine_access(home: Path, roots: dict[str, Path],
                             run_id: str, relative: str) -> dict:
    from xdg_access import repair_owner_directory
    return repair_owner_directory(home, roots, run_id, relative)


def list_quarantine(home: Path, roots: dict[str, Path]):
    base = quarantine_dir(home, roots)
    if not base.is_dir():
        print("No quarantine runs.")
        return
    for path in sorted(base.iterdir()):
        if path.is_dir() and (path / "manifest.json").is_file():
            print(path.name)


def restore(home: Path, roots: dict[str, Path], run_id: str):
    if not sys.stdin.isatty():
        raise SystemExit("ERROR: --restore requires a TTY.")
    if not re.fullmatch(r"\d{8}-\d{6}-\d{6}", run_id):
        raise SystemExit("ERROR: invalid run ID.")
    run = quarantine_dir(home, roots) / run_id
    if run.is_symlink() or quarantine_dir(home, roots).is_symlink():
        raise SystemExit("ERROR: unsafe quarantine link.")
    manifest = run / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise SystemExit("ERROR: manifest not found.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    pending = []
    for i in data["items"]:
        src, dest, scope = Path(i["source"]), Path(i["destination"]), i["scope"]
        base = roots.get(scope)
        if (base is not None and dest.parent == run / scope and src.parent == base
                and dest.name == src.name and dest.exists() and not dest.is_symlink()
                and not src.exists() and not src.is_symlink() and not base.is_symlink()):
            pending.append((src, dest))
        else:
            print(f"SKIPPED unsafe/conflict: {src}")
    for src, dest in pending:
        print(f"RESTORE {dest} -> {src}")
    if input("Type exactly RESTORE to confirm: ").strip() != "RESTORE":
        print("Cancelled.")
        return
    result = restore_quarantine_run(home, roots, run_id)
    print(f"RESTORED={result['restored']} SKIPPED={result['skipped']}")
    print("Manifest retained as a durable journal of the operation.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only XDG orphan audit. --remove quarantines selected entries.")
    parser.add_argument("--version", action="version", version=f"xdg-audit v{VERSION}")
    parser.add_argument("--home", type=Path, default=Path.home(), help="Override HOME (useful for testing)")
    parser.add_argument("--gui", action="store_true", help="Launch native GUI using available system toolkit (GTK/Qt/Tk)")
    parser.add_argument("--theme-info", action="store_true", help="Print detected desktop theme source (read-only)")
    parser.add_argument("--installed-sources", action="store_true",
                        help="Show read-only installed-application provider health and package counts")
    parser.add_argument("--polkit-test-status", action="store_true",
                        help="Check installed system Polkit helper (read-only)")
    parser.add_argument("--polkit-test-create", action="store_true",
                        help="Create user-owned restricted ~/.config fixture (TEST), no administrator required")
    parser.add_argument("--polkit-test-delete", action="store_true",
                        help="Remove only user-owned ~/.config test fixture (DELETE TEST)")
    parser.add_argument("--polkit-test-auth", action="store_true",
                        help="Request system Polkit authorization for trusted read-only id -u")
    parser.add_argument("--polkit-test-repair", action="store_true",
                        help="Repair only two fixed user-owned ~/.config test objects")
    parser.add_argument("--scope", choices=(*SCOPES, "all"), default="all", help="Scan one scope; default all")
    parser.add_argument("--all", action="store_true", help="Also show ACTIVE and PROTECTED entries")
    parser.add_argument("--quick", action="store_true", help="Skip disk usage calculation")
    parser.add_argument("--json", action="store_true", help="JSON report to stdout; read-only")
    parser.add_argument("--compare", type=Path, metavar="PREVIOUS.json",
                        help="Compare with a previous --json report; read-only")
    parser.add_argument("--keep", action="append", default=[], metavar="NAME", help="Protect an entry by basename")
    parser.add_argument("--alias", action="append", default=[], metavar="FOLDER=PKG", help="Add installed alias")
    parser.add_argument("--remove", action="store_true", help="Interactive move to user quarantine (no permanent delete)")
    parser.add_argument("--select", action="append", default=[], metavar="ABS_PATH", help="Exact path to move with --remove")
    parser.add_argument("--allow-uncertain", action="store_true", help="Allow manually selected REVIEW/UNKNOWN; still prompts")
    parser.add_argument("--list-quarantine", action="store_true", help="List previous quarantine runs")
    parser.add_argument("--restore", metavar="RUN_ID", help="Restore one quarantine run")
    parser.add_argument("--quarantine-info", metavar="RUN_ID", help="Inspect a v3 quarantine run")
    parser.add_argument("--diagnose-access", metavar="RUN_ID",
                        help="Inspect inaccessible quarantine files without changing permissions")
    parser.add_argument("--repair-access", metavar="RUN_ID",
                        help="Explicitly add owner-read permission to one diagnosed user-owned directory")
    parser.add_argument("--repair-target", metavar="SCOPE/RELATIVE_PATH",
                        help="Exact relative directory path from --diagnose-access")
    parser.add_argument("--purge", metavar="RUN_ID", help="Permanently delete quarantined objects")
    parser.add_argument("--purge-expired", action="store_true", help="Preview expired quarantine runs")
    parser.add_argument("--cleanup-history", metavar="RUN_ID", help="Remove a completed run journal (interactive)")
    parser.add_argument("--cleanup-all-history", action="store_true",
                        help="Preview ALL completed history journals, regardless of age")
    parser.add_argument("--cleanup-expired-history", action="store_true",
                        help="Preview fully purged journals older than 30 days")
    parser.add_argument("--retention-days", type=int, default=None, metavar="DAYS")
    parser.add_argument("--adopt-quarantine", metavar="RUN_ID", help="Approve current legacy contents for later purge")
    parser.add_argument("--recover-journal", metavar="RUN_ID", help="Preview or clean abandoned manifest temp files")
    parser.add_argument("--automatic-purge", action="store_true", help="Run opt-in scheduled cleanup without TTY")
    parser.add_argument("--configure-retention", type=int, metavar="DAYS", help="Save retention days")
    parser.add_argument("--enable-retention", action="store_true", help="Enable scheduled purge (requires explicit confirmation)")
    parser.add_argument("--disable-retention", action="store_true", help="Disable scheduled purge")
    parser.add_argument("--execute", action="store_true", help="Execute purge-expired after confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Preview a purge without writes")
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)
    # Explicit CLI flags keep their historical behaviour; no arguments open desktop GUI.
    if not argv:
        args.gui = True
    check_no_root()
    home = args.home.expanduser().resolve()
    if not home.is_dir() or home == Path("/"):
        parser.error("HOME must be an existing directory")
    if args.gui and args.theme_info:
        parser.error("--gui and --theme-info are mutually exclusive")
    if args.installed_sources and (args.gui or args.remove or args.json or args.compare or
                                  args.select or args.repair_target):
        parser.error("--installed-sources is a standalone read-only command")
    if args.gui and (args.json or args.compare or args.select or args.list_quarantine or args.restore):
        parser.error("--gui cannot be combined with --json/--compare/--select/--list-quarantine/--restore")
    if args.remove and args.json:
        parser.error("--remove and --json are mutually exclusive")
    if args.select and not args.remove:
        parser.error("--select requires --remove")
    if args.allow_uncertain and not args.remove:
        parser.error("--allow-uncertain requires --remove")
    operations = (args.restore, args.list_quarantine, args.quarantine_info, args.purge,
                  args.purge_expired, args.diagnose_access, args.repair_access,
                  args.cleanup_history, args.cleanup_expired_history,
                  args.cleanup_all_history,
                  args.polkit_test_status, args.polkit_test_create, args.polkit_test_delete,
                  args.polkit_test_auth, args.polkit_test_repair,
                  args.adopt_quarantine, args.recover_journal, args.automatic_purge,
                  args.configure_retention is not None, args.enable_retention,
                  args.disable_retention)
    if sum(bool(x) for x in operations) > 1:
        parser.error("Select a single quarantine operation")
    if args.retention_days is not None and not 1 <= args.retention_days <= 3650:
        parser.error("--retention-days must be between 1 and 3650")
    if args.repair_target and not args.repair_access:
        parser.error("--repair-target requires --repair-access")
    if args.repair_access and not args.repair_target:
        parser.error("--repair-access requires --repair-target from --diagnose-access")
    if args.execute and not (args.purge_expired or args.cleanup_expired_history or args.cleanup_all_history):
        parser.error("--execute requires --purge-expired or a history cleanup flag")
    lifecycle = any(bool(x) for x in operations[2:])
    if lifecycle and (args.gui or args.remove or args.json or args.compare or args.select):
        parser.error("Lifecycle commands cannot be combined with GUI, scan or move")
    roots = xdg_roots(home)
    if args.installed_sources:
        from xdg_sources import package_name_count
        if any(bool(x) for x in operations) or args.theme_info:
            parser.error("--installed-sources cannot be combined with lifecycle operations")
        inventory = read_active_names(home, roots)
        packages, flatpaks, snaps, appimages, _units, _processes, _desktops, _active = inventory
        native = getattr(inventory, 'native_source', None)
        native_names = (packages if native == 'pacman' else
                        getattr(inventory, 'distro', {}).get(native, ()))
        print(json.dumps({
            'native_package_source': native,
            'native_packages': package_name_count(native, native_names),
            "health": dict(getattr(inventory, "status", {})),
            "counts": {"pacman": len(packages),
                       "foreign_pacman_AUR_or_local": len(getattr(inventory, "foreign", ())),
                       "flatpak_evidence": len(flatpaks),
                       "flatpak_app_ids": (len(inventory.flatpak_ids) if
                          getattr(inventory, "flatpak_ids", None) is not None else None),
                       "npm_global_hints": len(getattr(inventory, "npm_global", ())),
                       "pipx_hints": len(getattr(inventory, "pipx", ())),
                       "dpkg": package_name_count('dpkg', getattr(inventory, "distro", {}).get("dpkg", ())),
                       "rpm": len(getattr(inventory, "distro", {}).get("rpm", ())),
                       "snap": len(snaps),
                       "appimage": len(getattr(inventory, 'appimage_paths', None)
                                       if getattr(inventory, 'appimage_paths', None) is not None else appimages),
                       "manual_binary_hints": len(getattr(inventory, "manual", ()))},
            "notes": dict(getattr(inventory, "provenance", {})),
            "warning": "Provider health and installed hints are not proof that files can be deleted"
        }, ensure_ascii=False, indent=2))
        return 0
    if lifecycle:
        if (args.polkit_test_status or args.polkit_test_create or args.polkit_test_delete
                or args.polkit_test_auth or args.polkit_test_repair):
            from xdg_polkit import status as polkit_status, run_test
            from xdg_config_selftest import create, diagnose, repair, cleanup
            if args.polkit_test_status:
                print(json.dumps(polkit_status(), indent=2, ensure_ascii=False))
                return 0
            if not sys.stdin.isatty():
                raise SystemExit("ERROR: interactive confirmation required for test action")
            if args.polkit_test_create:
                if input("Type TEST to create restricted user-owned files under ~/.config: ").strip() != "TEST":
                    raise SystemExit("ERROR: test fixture creation cancelled")
                result = create(home)
            elif args.polkit_test_auth:
                if input("Type AUTH to request system Polkit authentication (read-only id -u): ").strip() != "AUTH":
                    raise SystemExit("ERROR: authentication test cancelled")
                result = run_test("test-auth")
            elif args.polkit_test_repair:
                print(json.dumps(diagnose(home), indent=2, ensure_ascii=False))
                if input("Type ACCESS TEST to repair ONLY the fixture's owner-read bits: ").strip() != "ACCESS TEST":
                    raise SystemExit("ERROR: test repair cancelled")
                result = repair(home)
            else:
                if input("Type DELETE TEST to clean up ONLY the ~/.config test fixture: ").strip() != "DELETE TEST":
                    raise SystemExit("ERROR: test cleanup cancelled")
                result = cleanup(home)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        from xdg_retention import load as load_retention, save as save_retention
        from xdg_quarantine_lifecycle import (inspect_run, purge_run, expired_run_ids,
                                              adopt_legacy_run, recover_manifest_temps)
        if args.configure_retention is not None or args.enable_retention or args.disable_retention:
            policy = load_retention(home, roots)
            if args.configure_retention is not None:
                if not 1 <= args.configure_retention <= 3650:
                    parser.error("Retention days must be between 1 and 3650")
                policy["days"] = args.configure_retention
            elif args.enable_retention:
                if not sys.stdin.isatty() or input("Type ENABLE to permit scheduled purge: ").strip() != "ENABLE":
                    raise SystemExit("ERROR: scheduled purge not enabled")
                policy["automatic"] = True
            elif args.disable_retention:
                policy["automatic"] = False
            save_retention(home, roots, policy)
            print(json.dumps(policy))
            return 0
        if args.diagnose_access:
            print(json.dumps(diagnose_quarantine_access(home, roots, args.diagnose_access),
                             indent=2, ensure_ascii=False))
            return 0
        if args.repair_access:
            from xdg_access import diagnose_access
            report = diagnose_access(home, roots, args.repair_access)
            issue = next((i for i in report["issues"]
                          if i["relative"] == args.repair_target
                          and i["repairable"]), None)
            if issue is None:
                raise SystemExit("ERROR: target not eligible for owner-only repair")
            print("ACCESS REPAIR:", issue["path"], issue["mode"], "->",
                  issue["suggested_mode"])
            if not sys.stdin.isatty() or input("Type ACCESS to change only this directory's owner-read bit: ").strip() != "ACCESS":
                raise SystemExit("ERROR: access repair cancelled")
            result = repair_quarantine_access(home, roots, args.repair_access,
                                              args.repair_target)
            print(json.dumps(result, ensure_ascii=False))
            print("Re-run --diagnose-access. PURGE requires separate verification and confirmation.")
            return 0
        if args.cleanup_history or args.cleanup_expired_history or args.cleanup_all_history:
            from xdg_quarantine_history import (cleanup_history, history_candidates,
                                                completed_history_candidates)
            if args.cleanup_history:
                ids = [args.cleanup_history]
            elif args.cleanup_all_history:
                ids = completed_history_candidates(home, roots)
            else:
                ids = history_candidates(home, roots,
                                        [x["run_id"] for x in quarantine_runs(home, roots)])
            previews = []
            for run_id in ids:
                try:
                    previews.append(cleanup_history(home, roots, run_id, dry_run=True))
                except (ValueError, OSError) as exc:
                    print(f"BLOCKED {run_id}: {exc}", file=sys.stderr)
                    return 1
            for plan in previews:
                print(f"HISTORY PLAN {plan['run_id']}: {plan['items']} terminal entries ({plan['status']})")
            if not previews:
                print("No completed history eligible for cleanup.")
                return 0
            if args.dry_run or ((args.cleanup_expired_history or args.cleanup_all_history)
                                and not args.execute):
                return 0
            if not sys.stdin.isatty() or input("Type HISTORY to erase these journal records: ").strip() != "HISTORY":
                raise SystemExit("ERROR: history cleanup cancelled")
            for plan in previews:
                cleanup_history(home, roots, plan["run_id"], dry_run=False)
                print("HISTORY REMOVED:", plan["run_id"])
            return 0
        if args.recover_journal:
            preview = recover_manifest_temps(home, roots, args.recover_journal, dry_run=True)
            print("RECOVERY PLAN: %d abandoned temporary journals" % preview["temporary_files"])
            if args.dry_run or not preview["temporary_files"]:
                return 0
            if not sys.stdin.isatty() or input("Type RECOVER to delete only abandoned temp journals: ").strip() != "RECOVER":
                raise SystemExit("ERROR: journal recovery cancelled")
            print(recover_manifest_temps(home, roots, args.recover_journal, dry_run=False))
            return 0
        if args.adopt_quarantine:
            report = inspect_run(home, roots, args.adopt_quarantine, nested_mounts_status,
                                 allow_unsealed=True)
            print("LEGACY ADOPTION PLAN: %d entries, %s. Current contents may differ from original." %
                  (report["present"], human(report["bytes"])))
            if not sys.stdin.isatty() or input("Type ADOPT to bind CURRENT contents: ").strip() != "ADOPT":
                raise SystemExit("ERROR: adoption cancelled")
            print(adopt_legacy_run(home, roots, args.adopt_quarantine, nested_mounts_status))
            return 0
        if args.quarantine_info:
            report = inspect_run(home, roots, args.quarantine_info, nested_mounts_status,
                                 allow_unsealed=True)
            print(json.dumps({"run_id": report["run_id"], "objects": report["present"],
                              "bytes": report["bytes"], "entries": [
                                  {"source": str(e["source"]), "status": e["status"],
                                   "present": e["present"], "bytes": e["bytes"],
                                   "requires_adoption": e.get("unsealed", False)}
                                  for e in report["entries"]]}, indent=2))
            return 0
        policy = load_retention(home, roots)
        if args.automatic_purge and not policy["automatic"]:
            raise SystemExit("ERROR: automatic deletion not enabled in retention settings")
        days = args.retention_days if args.retention_days is not None else policy["days"]
        # Retention may purge only healthy runs that still contain quarantined
        # objects. Finished RESTORED/PURGED and interrupted runs are excluded.
        ids = ([args.purge] if args.purge else expired_run_ids(
            [run for run in quarantine_runs(home, roots)
             if run["status"] == "QUARANTINED"], days))
        previews = []
        failed = []
        for run_id in ids:
            try:
                previews.append(purge_run(home, roots, run_id, nested_mounts_status, dry_run=True))
            except (ValueError, OSError) as exc:
                failed.append((run_id, str(exc)))
                print(f"BLOCKED {run_id}: {exc}", file=sys.stderr)
        if not previews and not args.automatic_purge:
            print("No eligible quarantine runs.")
            return 1 if failed else 0
        for preview in previews:
            print("PURGE PLAN: %s: %d entries, %s" %
                  (preview["run_id"], preview["objects"], human(preview["bytes"])))
        if args.dry_run or (args.purge_expired and not args.execute):
            return 1 if failed else 0
        if not args.automatic_purge and previews:
            if not sys.stdin.isatty():
                raise SystemExit("ERROR: purge requires an interactive TTY")
            if input("Type PURGE to permanently delete these objects: ").strip() != "PURGE":
                print("Cancelled.")
                return 0
        for preview in previews:
            try:
                print(purge_run(home, roots, preview["run_id"], nested_mounts_status, dry_run=False))
            except (ValueError, OSError) as exc:
                failed.append((preview["run_id"], str(exc)))
                print(f"BLOCKED {preview['run_id']}: {exc}", file=sys.stderr)
        if args.automatic_purge:
            from xdg_quarantine_history import history_candidates, cleanup_history
            old_history = history_candidates(
                home, roots, [x["run_id"] for x in quarantine_runs(home, roots)])
            for run_id in old_history:
                try:
                    cleanup_history(home, roots, run_id, dry_run=False)
                    print("EXPIRED HISTORY REMOVED:", run_id)
                except (OSError, ValueError) as exc:
                    failed.append((run_id, str(exc)))
                    print(f"BLOCKED HISTORY {run_id}: {exc}", file=sys.stderr)
        return 1 if failed else 0
    if args.theme_info:
        from xdg_theme import detect_appearance
        from xdg_gui import detect_gui_runtime
        appearance = detect_appearance(home)
        print("Desktop: " + appearance.desktop)
        print("Source: " + appearance.source)
        print("Scheme: " + appearance.scheme)
        print("Accent: " + (str(appearance.accent) if appearance.accent else "Qt system palette"))
        runtime = detect_gui_runtime()
        print("OS: " + runtime["os"])
        print("Session: " + runtime["session"])
        print("DE: " + runtime["desktop"])
        print("WM/Compositor: " + runtime["wm"])
        print("Display manager: " + runtime["display_manager"])
        print("Detected toolkits: " + ", ".join(runtime["available"]))
        print("Selected native backend: " + (runtime["selected"] or "none"))
        print("Qt platform theme: " + os.environ.get("QT_QPA_PLATFORMTHEME", "auto"))
        return 0
    if args.list_quarantine:
        list_quarantine(home, roots)
        return 0
    if args.restore:
        restore(home, roots, args.restore)
        return 0
    from xdg_prefs import load as load_preferences
    prefs, prefs_error = load_preferences(home, roots)
    if prefs_error:
        print(f"WARNING: {prefs_error}", file=sys.stderr)
    if prefs['keep']:
        args.keep.extend(prefs['keep'])
    if prefs['quick_scan']:
        args.quick = True
    if prefs['show_active']:
        args.all = True
    if args.gui and '--scope' not in argv and prefs['startup_scope'] in (*SCOPES, 'all'):
        args.scope = prefs['startup_scope']
    args.saved_prefs = prefs
    aliases = {k: list(v) for k, v in prefs['aliases'].items()}
    for val in args.alias:
        if "=" not in val or not all(s.strip() for s in val.split("=", 1)):
            parser.error("--alias expects FOLDER=PACKAGE")
        k, v = val.split("=", 1)
        aliases.setdefault(k.strip().casefold(), []).append(v.strip())
    scopes = list(SCOPES) if args.scope == "all" else [args.scope]
    if args.gui:
        try:
            from xdg_gui import launch_gui
        except ImportError as exc:
            parser.error(f"GUI unavailable: {exc}. Use the complete v1.4.0 directory.")
        try:
            return launch_gui(sys.modules[__name__], home, args, aliases)
        except RuntimeError as exc:
            parser.error(str(exc))
    items, roots, stats = scan(home, scopes, {normalize(x) for x in args.keep}, aliases, args.quick)
    changes = compare_report(items, args.compare, scopes) if args.compare else None
    if args.json:
        report = {"version": VERSION, "scopes": scopes, "stats": stats,
                  "entries": [x.json() for x in items]}
        if changes is not None:
            report["changes"] = changes
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(items, stats, args.all, args.remove)
        if changes is not None:
            print_comparison(changes)
        if args.remove:
            move_items(items, roots, home, args.select, args.allow_uncertain,
                       extra_aliases=aliases, keep_names=args.keep)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)
