"""Opt-in XDG quarantine retention settings (never enabled by default)."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile

DEFAULT = {"days": 30, "automatic": False}


def _path(home: Path, roots: dict) -> Path:
    return roots.get("config", home / ".config") / "xdg-audit" / "retention.json"


def validate(value) -> dict:
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise ValueError("Invalid retention configuration")
    if type(value["days"]) is not int or not 1 <= value["days"] <= 3650:
        raise ValueError("Retention days must be 1-3650")
    if type(value["automatic"]) is not bool:
        raise ValueError("Automatic deletion must be explicitly enabled")
    return dict(value)


def load(home: Path, roots: dict) -> dict:
    path = _path(home, roots)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Unsafe retention configuration path")
    if not path.exists():
        return dict(DEFAULT)
    if path.stat().st_size > 4096:
        raise ValueError("Retention configuration too large")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def save(home: Path, roots: dict, value: dict) -> None:
    value = validate(value)
    path = _path(home, roots)
    if not path.is_absolute() or home not in path.parents:
        raise ValueError("Retention configuration must be within HOME")
    if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError("Unsafe retention configuration path")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("Unsafe retention symlink")
    fd, temporary = tempfile.mkstemp(prefix=".retention-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
