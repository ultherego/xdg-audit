"""Automatic Linux desktop appearance discovery for xdg-audit v1.3.

Standard library only. Qt/PySide6 is imported only by the GUI. Querying
settings does not write files, change the user environment or launch a portal.
"""
from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Appearance:
    desktop: str
    source: str
    scheme: str = "unknown"  # unknown | light | dark
    accent: tuple[int, int, int] | None = None
    kde_colors: dict[str, tuple[int, int, int]] = field(default_factory=dict)


def desktop_name(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else os.environ
    fields = ":".join((env.get("XDG_CURRENT_DESKTOP", ""), env.get("XDG_SESSION_DESKTOP", ""),
                       env.get("DESKTOP_SESSION", ""), env.get("GDMSESSION", ""))).casefold()
    if "kde" in fields or "plasma" in fields or env.get("KDE_FULL_SESSION") == "true":
        return "KDE Plasma"
    for needle, label in (("gnome", "GNOME"), ("cinnamon", "Cinnamon"),
                          ("xfce", "XFCE"), ("mate", "MATE"), ("budgie", "Budgie"),
                          ("niri", "Niri"), ("hyprland", "Hyprland"),
                          ("sway", "Sway"), ("lxqt", "LXQt")):
        if needle in fields:
            return label
    return "Inne / nieznane"


def _run(args: list[str]) -> str:
    if not shutil.which(args[0]):
        return ""
    try:
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=1.7, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _rgb(text: str) -> tuple[int, int, int] | None:
    text = text.strip().strip("'").strip('"')
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return tuple(int(text[i:i+2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    match = re.fullmatch(r"\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*", text)
    if not match:
        return None
    colors = tuple(int(v) for v in match.groups())
    return colors if all(0 <= v <= 255 for v in colors) else None


def kde_palette(config_home: Path) -> dict[str, tuple[int, int, int]]:
    conf = config_home / "kdeglobals"
    if not conf.is_file() or conf.is_symlink():
        return {}
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(conf, encoding="utf-8")
    except (configparser.Error, UnicodeError, OSError):
        return {}
    result = {}
    mapping = {
        "window": ("Colors:Window", "BackgroundNormal"),
        "window_text": ("Colors:Window", "ForegroundNormal"),
        "base": ("Colors:View", "BackgroundNormal"),
        "text": ("Colors:View", "ForegroundNormal"),
        "button": ("Colors:Button", "BackgroundNormal"),
        "button_text": ("Colors:Button", "ForegroundNormal"),
        "highlight": ("Colors:Selection", "BackgroundNormal"),
        "highlight_text": ("Colors:Selection", "ForegroundNormal"),
        "tooltip_base": ("Colors:Tooltip", "BackgroundNormal"),
        "tooltip_text": ("Colors:Tooltip", "ForegroundNormal"),
        "accent": ("General", "AccentColor"),
    }
    for label, (section, key) in mapping.items():
        if parser.has_option(section, key):
            color = _rgb(parser.get(section, key))
            if color is not None:
                result[label] = color
    return result


def portal_appearance() -> tuple[str, tuple[int, int, int] | None]:
    args = ["gdbus", "call", "--session", "--dest", "org.freedesktop.portal.Desktop",
            "--object-path", "/org/freedesktop/portal/desktop",
            "--method", "org.freedesktop.portal.Settings.Read", "org.freedesktop.appearance"]
    scheme_out = _run(args + ["color-scheme"])
    match = re.search(r"uint32\s+([012])\b", scheme_out)
    scheme = {"1": "dark", "2": "light"}.get(match.group(1), "unknown") if match else "unknown"
    accent_out = _run(args + ["accent-color"])
    # The portal returns an sRGB triple of doubles within a D-Bus variant.
    triple = re.search(r"\(\s*([0-9.eE+-]+)\s*,\s*([0-9.eE+-]+)\s*,\s*([0-9.eE+-]+)\s*\)", accent_out)
    accent = None
    if triple:
        try:
            vals = [float(v) for v in triple.groups()]
            if all(0 <= v <= 1 for v in vals):
                accent = tuple(round(v * 255) for v in vals)  # type: ignore[assignment]
        except ValueError:
            pass
    return scheme, accent


def gtk_preference(config_home: Path) -> tuple[str, str]:
    raw = _run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    if "prefer-dark" in raw:
        return "dark", "gsettings (GNOME color-scheme)"
    if "prefer-light" in raw:
        return "light", "gsettings (GNOME color-scheme)"
    for gtk in ("gtk-4.0", "gtk-3.0"):
        path = config_home / gtk / "settings.ini"
        if not path.is_file() or path.is_symlink():
            continue
        ini = configparser.ConfigParser(interpolation=None)
        try:
            ini.read(path, encoding="utf-8")
            if ini.get("Settings", "gtk-application-prefer-dark-theme", fallback="").strip() == "1":
                return "dark", f"{gtk}/settings.ini"
            name = ini.get("Settings", "gtk-theme-name", fallback="")
            if name.lower().endswith("-dark") or name.lower().endswith(":dark"):
                return "dark", f"{gtk}/settings.ini"
        except (configparser.Error, UnicodeError, OSError):
            continue
    return "unknown", ""


def detect_appearance(home: Path | None = None, env: dict[str, str] | None = None) -> Appearance:
    home = home or Path.home()
    env = env if env is not None else os.environ
    config_root = Path(env.get("XDG_CONFIG_HOME") or (home / ".config"))
    desk = desktop_name(env)
    # Plasma's kdeglobals carries the full palette, unlike the portal's preference.
    if desk == "KDE Plasma":
        colors = kde_palette(config_root)
        scheme, accent = portal_appearance()
        if "window" in colors and "window_text" in colors:
            bg = colors["window"]
            fg = colors["window_text"]
            # Infer scheme using luminance ordering, not an assumed palette name.
            brightness = lambda c: 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]
            scheme = "dark" if brightness(bg) < brightness(fg) else "light"
        return Appearance(desk, "kdeglobals + Qt platform theme" if colors else "Qt platform theme + XDG portal",
                          scheme, colors.get("accent") or accent, colors)
    portal_scheme, accent = portal_appearance()
    if desk in {"GNOME", "Cinnamon", "XFCE", "MATE", "Budgie"}:
        gtk_scheme, gtk_source = gtk_preference(config_root)
        scheme = portal_scheme if portal_scheme != "unknown" else gtk_scheme
        source = "XDG portal" if portal_scheme != "unknown" else (gtk_source or "Qt platform theme")
        return Appearance(desk, source, scheme, accent)
    # Niri, Sway, Hyprland and unknown: xdg portal first, configured GTK second.
    if portal_scheme == "unknown":
        gtk_scheme, gtk_source = gtk_preference(config_root)
        return Appearance(desk, gtk_source or "Qt platform theme", gtk_scheme, accent)
    return Appearance(desk, "XDG portal", portal_scheme, accent)
