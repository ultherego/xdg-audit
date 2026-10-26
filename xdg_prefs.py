"""Explicit user preferences for xdg-audit. No writes during normal scans.

Do not accept arbitrary paths outside the user's XDG config directory. Settings
are data only; entries are never executed or evaluated.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

SCOPES = ('all', 'config', 'data', 'state', 'cache', 'flatpak', 'snap', 'dotfiles')
NAME = re.compile(r'^[A-Za-z0-9.][A-Za-z0-9._+ -]{0,127}$')
PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+*?-]{0,127}$')


def defaults() -> dict:
    return {'keep': [], 'aliases': {}, 'quick_scan': False,
            'startup_scope': 'all', 'show_active': False, 'language': 'pl'}


def settings_path(home: Path, roots: dict | None = None) -> Path:
    base = (roots or {}).get('config', home / '.config')
    return base / 'xdg-audit' / 'settings.json'


def validate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('Ustawienia muszą być obiektem JSON')
    result = defaults()
    keep = payload.get('keep', [])
    if not isinstance(keep, list) or len(keep) > 400 or any(
            not isinstance(x, str) or x in {'.', '..'} or not NAME.fullmatch(x) for x in keep):
        raise ValueError('Niepoprawna lista chronionych katalogów')
    result['keep'] = sorted(set(keep), key=str.casefold)
    aliases = payload.get('aliases', {})
    if not isinstance(aliases, dict) or len(aliases) > 200:
        raise ValueError('Niepoprawne aliasy')
    output = {}
    for name, matches in aliases.items():
        if not isinstance(name, str) or name in {'.', '..'} or not NAME.fullmatch(name):
            raise ValueError('Niepoprawna nazwa aliasu')
        if not isinstance(matches, list) or not matches or len(matches) > 15 or any(
                not isinstance(x, str) or not PATTERN.fullmatch(x) for x in matches):
            raise ValueError(f'Niepoprawny wzorzec dla {name}')
        output[name.casefold()] = sorted(set(matches))
    result['aliases'] = output
    for key in ('quick_scan', 'show_active'):
        val = payload.get(key, False)
        if not isinstance(val, bool):
            raise ValueError(f'Niepoprawny typ {key}')
        result[key] = val
    scope = payload.get('startup_scope', 'all')
    if scope not in SCOPES:
        raise ValueError('Nieznany zakres startowy')
    result['startup_scope'] = scope
    lang = payload.get('language', 'pl')
    if lang not in ('pl', 'en'):
        raise ValueError('Language must be pl or en')
    result['language'] = lang
    return result


def load(home: Path, roots: dict | None = None) -> tuple[dict, str | None]:
    path = settings_path(home, roots)
    if path.is_symlink():
        return defaults(), 'Ustawienia są dowiązaniem symbolicznym; ignoruję je'
    if not path.exists():
        return defaults(), None
    try:
        if path.stat().st_size > 128 * 1024:
            raise ValueError('Plik ustawień przekracza 128 KiB')
        return validate(json.loads(path.read_text(encoding='utf-8'))), None
    except (OSError, ValueError, TypeError) as exc:
        return defaults(), f'Nie można odczytać ustawień: {exc}'


def save(home: Path, settings: dict, roots: dict | None = None) -> Path:
    data = validate(settings)
    path = settings_path(home, roots)
    if path.parent.is_symlink() or path.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError('Niebezpieczna ścieżka ustawień (symlink)')
    # Resolve first, so a configured XDG_CONFIG_HOME cannot redirect to a foreign home.
    if home.resolve() not in path.parent.resolve(strict=False).parents:
        raise ValueError('Ustawienia znajdują się poza katalogiem użytkownika')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Niebezpieczny katalog ustawień')
    fd, temp = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return path


def parse_alias_lines(text: str) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(f'Alias w linii {number}: użyj katalog=wzorzec')
        name, pattern = (x.strip() for x in line.split('=', 1))
        if not name or not pattern:
            raise ValueError(f'Pusty alias w linii {number}')
        output.setdefault(name.casefold(), []).append(pattern)
    validate({'aliases': output})
    return output


def format_aliases(aliases: dict[str, list[str]]) -> str:
    return '\n'.join(f'{name}={pattern}' for name, pats in sorted(aliases.items()) for pattern in pats)


def scan_inputs_changed(previous: dict, updated: dict) -> bool:
    """Only input changes affecting scan/classification require filesystem re-scan.

    Language, show_active and startup_scope alter the GUI only.
    Do not destroy cached scan results or bulk selections when toggling them.
    """
    return any(previous.get(key) != updated.get(key)
               for key in ('keep', 'aliases', 'quick_scan'))
