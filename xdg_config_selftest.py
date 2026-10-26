"""Non-privileged, narrowly scoped access test under ~/.config.

The fixture is user-owned and does NOT require Polkit. Its restrictive modes
reproduce the denied directory/file reads seen in real quarantine scans.
All operations are fd-relative, do not follow symlinks and reject foreign data.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from xdg_quarantine_lifecycle import FLAGS, _open_path, capture_inventory

FOLDER = "xdg-audit-polkit-test"
CHILD = "pkg"
FILE = "test-only.txt"
DATA = b"xdg-audit local access fixture v1\n"


class UnsafeFixture(ValueError):
    pass


def path(home: Path) -> Path:
    return home / ".config" / FOLDER


def _check(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise UnsafeFixture("Foreign or invalid test directory")


def _entry(fd: int, name: str, kind: int):
    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if info.st_uid != os.getuid() or stat.S_IFMT(info.st_mode) != kind:
        raise UnsafeFixture("Untrusted test entry: " + name)
    return info


def _open(fd: int, name: str) -> int:
    child = os.open(name, FLAGS, dir_fd=fd)
    _check(child)
    return child


def _config(home: Path) -> int:
    parent = _open_path(home)
    try:
        _entry(parent, ".config", stat.S_IFDIR)
        return _open(parent, ".config")
    finally:
        os.close(parent)


def _root(home: Path) -> tuple[int, int]:
    config = _config(home)
    try:
        root = _open(config, FOLDER)
        return config, root
    except BaseException:
        os.close(config)
        raise


def _validate(root: int, *, expect_modes: bool = False) -> tuple[os.stat_result, os.stat_result]:
    if set(os.listdir(root)) != {CHILD}:
        raise UnsafeFixture("Unexpected entries in test root")
    item = _entry(root, CHILD, stat.S_IFDIR)
    if expect_modes and stat.S_IMODE(item.st_mode) not in (0o111, 0o511, 0o711):
        raise UnsafeFixture("Unexpected permissions on test directory")
    # O_PATH supports stat without listing a deliberately unreadable directory.
    fd = os.open(CHILD, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
    try:
        _check(fd)
        marker = _entry(fd, FILE, stat.S_IFREG)
        if marker.st_nlink != 1 or marker.st_size != len(DATA):
            raise UnsafeFixture("Unexpected test file")
        if expect_modes and stat.S_IMODE(marker.st_mode) not in (0o000, 0o400, 0o600):
            raise UnsafeFixture("Unexpected permissions on test file")
    finally:
        os.close(fd)
    return item, marker


def create(home: Path) -> dict:
    """Create an isolated fixture; refuse to reuse or overwrite any existing path."""
    config = _config(home)
    try:
        os.mkdir(FOLDER, 0o700, dir_fd=config)  # EEXIST means no changes
        root = _open(config, FOLDER)
        try:
            os.mkdir(CHILD, 0o700, dir_fd=root)
            child = _open(root, CHILD)
            try:
                f = os.open(FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                            os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600,
                            dir_fd=child)
                try:
                    os.write(f, DATA)
                    os.fsync(f)
                    os.fchmod(f, 0o000)
                finally:
                    os.close(f)
                os.fchmod(child, 0o111)
                os.fsync(root)
            finally:
                os.close(child)
        finally:
            os.close(root)
        return {"status": "created", "path": str(path(home)),
                "restricted_directory": str(path(home) / CHILD),
                "restricted_file": str(path(home) / CHILD / FILE)}
    finally:
        os.close(config)


def diagnose(home: Path) -> dict:
    config, root = _root(home)
    try:
        directory, file_info = _validate(root)
        return {
            "path": str(path(home)),
            "directory_mode": format(stat.S_IMODE(directory.st_mode), "03o"),
            "file_mode": format(stat.S_IMODE(file_info.st_mode), "03o"),
            "directory_readable": bool(directory.st_mode & stat.S_IRUSR),
            "file_readable": bool(file_info.st_mode & stat.S_IRUSR),
            "owner_uid": os.getuid(),
            "scope": "LOCAL_ONLY",
            "polkit_required": False
        }
    finally:
        os.close(root)
        os.close(config)


def repair(home: Path) -> dict:
    """Only add read permission to the exact two known user-owned objects."""
    config, root = _root(home)
    try:
        directory, marker = _validate(root, expect_modes=True)
        if stat.S_IMODE(directory.st_mode) != 0o111 or stat.S_IMODE(marker.st_mode) != 0o000:
            raise UnsafeFixture("Test fixture was already changed")
        os.chmod(CHILD, 0o511, dir_fd=root, follow_symlinks=False)
        child = _open(root, CHILD)
        try:
            if set(os.listdir(child)) != {FILE}:
                raise UnsafeFixture("Unexpected extra test files")
            current = _entry(child, FILE, stat.S_IFREG)
            if (current.st_dev, current.st_ino) != (marker.st_dev, marker.st_ino):
                raise UnsafeFixture("Test file substituted")
            os.chmod(FILE, 0o400, dir_fd=child, follow_symlinks=False)
        finally:
            os.close(child)
        inventory = capture_inventory(path(home) / CHILD)
        if len(inventory) != 2 or inventory[-1].get("size") != len(DATA):
            raise UnsafeFixture("Inventory did not match expected fixture")
        return {"status": "repaired", "path": str(path(home)),
                "directory_mode": "511", "file_mode": "400",
                "inventory_objects": len(inventory), "polkit_required": False}
    finally:
        os.close(root)
        os.close(config)


def cleanup(home: Path) -> dict:
    """Delete only a fully verified fixture; reject extra files and symlinks."""
    config, root = _root(home)
    try:
        directory, marker = _validate(root, expect_modes=True)
        if stat.S_IMODE(directory.st_mode) == 0o111:
            os.chmod(CHILD, 0o511, dir_fd=root, follow_symlinks=False)
        child = _open(root, CHILD)
        try:
            if set(os.listdir(child)) != {FILE}:
                raise UnsafeFixture("Unexpected extra test objects")
            current = _entry(child, FILE, stat.S_IFREG)
            if (current.st_dev, current.st_ino) != (marker.st_dev, marker.st_ino):
                raise UnsafeFixture("Test file changed")
            if not current.st_mode & stat.S_IRUSR:
                os.chmod(FILE, stat.S_IMODE(current.st_mode) | stat.S_IRUSR,
                         dir_fd=child, follow_symlinks=False)
            f = os.open(FILE, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=child)
            try:
                current = os.fstat(f)
                if current.st_uid != os.getuid() or current.st_nlink != 1 or os.read(f, len(DATA) + 1) != DATA:
                    raise UnsafeFixture("Test marker changed: cleanup refused")
            finally:
                os.close(f)
            os.unlink(FILE, dir_fd=child)
            os.fsync(child)
        finally:
            os.close(child)
        os.rmdir(CHILD, dir_fd=root)
        os.fsync(root)
        os.rmdir(FOLDER, dir_fd=config)
        os.fsync(config)
        return {"status": "cleaned", "path": str(path(home)), "deleted_test_only": True}
    finally:
        os.close(root)
        os.close(config)
