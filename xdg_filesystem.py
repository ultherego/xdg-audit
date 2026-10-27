"""Read-only, descriptor-bound filesystem evidence; never change mounts or files."""
from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
import platform
import re
import stat
import struct
import uuid


# Linux UAPI <linux/btrfs.h>, asm-generic ioctl encoding. Other architectures
# retain strict device/inode checks without offering device revalidation.
IOCTL_ARCHES = {"x86_64", "aarch64", "riscv64", "loongarch64"}
BTRFS_FS_INFO = 0x8400941F
BTRFS_GET_SUBVOL_INFO = 0x81F8943C
MAX_PROC = 4 * 1024 * 1024


@contextmanager
def object_fd(path, expected=None):
    from xdg_quarantine_lifecycle import _identity, _open_path
    path = Path(path)
    parent = _open_path(path.parent)
    try:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (stat.S_IFMT(before.st_mode) not in (stat.S_IFREG, stat.S_IFDIR) or
                (expected is not None and _identity(before) != tuple(expected))):
            raise ValueError("Filesystem evidence target changed or is not a regular file/directory")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0), dir_fd=parent)
        try:
            if _identity(os.fstat(fd)) != _identity(before):
                raise ValueError("Filesystem evidence target replaced while opening")
            yield fd, before
            if _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _identity(before):
                raise ValueError("Filesystem evidence target replaced while reading")
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def btrfs_identity(fd):
    """Read FSID and subvolume identity from this exact object's descriptor."""
    if platform.machine() not in IOCTL_ARCHES:
        return None
    fs = bytearray(1024)
    sub = bytearray(504)
    try:
        fcntl.ioctl(fd, BTRFS_FS_INFO, fs, True)
        fcntl.ioctl(fd, BTRFS_GET_SUBVOL_INFO, sub, True)
    except OSError as error:
        if error.errno in (errno.ENOTTY, errno.EOPNOTSUPP, errno.ENOSYS):
            return None
        raise
    identity = {"kind": "btrfs", "fsid": str(uuid.UUID(bytes=bytes(fs[16:32]))),
                "subvolume_id": struct.unpack_from("=Q", sub)[0],
                "subvolume_uuid": str(uuid.UUID(bytes=bytes(sub[296:312])))}
    validate_identity(identity)
    return identity


def validate_identity(value):
    fields = {"kind", "fsid", "subvolume_id", "subvolume_uuid"}
    if (not isinstance(value, dict) or set(value) != fields or value.get("kind") != "btrfs" or
            type(value.get("subvolume_id")) is not int or value["subvolume_id"] < 5):
        raise ValueError("Invalid persistent filesystem identity")
    for field in ("fsid", "subvolume_uuid"):
        if not isinstance(value[field], str) or re.fullmatch(
                r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value[field]) is None:
            raise ValueError("Invalid persistent filesystem UUID")
    if uuid.UUID(value["fsid"]).int == 0 or (
            value["subvolume_id"] != 5 and uuid.UUID(value["subvolume_uuid"]).int == 0):
        raise ValueError("Missing persistent filesystem UUID")
    return value


def filesystem_identity(path, expected=None):
    with object_fd(path, expected) as (fd, _):
        return btrfs_identity(fd)


def verify_identity(path, recorded, expected=None):
    validate_identity(recorded)
    current = filesystem_identity(path, expected)
    if current != recorded:
        raise ValueError("Persistent filesystem/subvolume identity differs from the journal")
    return current


def _proc_text(path):
    with Path(path).open("r", encoding="utf-8", errors="strict") as stream:
        text = stream.read(MAX_PROC + 1)
    if len(text) > MAX_PROC:
        raise ValueError("Filesystem evidence exceeds proc read limit")
    return text


def mount_context(fd, info):
    fdinfo = _proc_text(f"/proc/self/fdinfo/{fd}")
    match = re.search(r"^mnt_id:\s*([0-9]+)\s*$", fdinfo, re.MULTILINE)
    if match is None:
        raise ValueError("No descriptor mount ID")
    mount_id = int(match.group(1))
    for line in _proc_text("/proc/self/mountinfo").splitlines():
        fields = line.split()
        if not fields or fields[0] != str(mount_id):
            continue
        split = fields.index("-")
        if split < 6 or len(fields) < split + 4:
            raise ValueError("Malformed descriptor mount record")
        decode = lambda value: re.sub(r"\\(040|011|012|134)",
                                     lambda m: chr(int(m.group(1), 8)), value)
        # Sources and mount options may contain network credentials. Retain
        # only the selected mount's non-secret structural fields.
        return {"mount_id": mount_id, "device_major_minor": fields[2],
                "stat_major_minor": f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}",
                "filesystem_type": fields[split + 1],
                "root": decode(fields[3]), "mountpoint": decode(fields[4]),
                "read_only": "ro" in fields[5].split(","),
                "persistent": False}
    raise ValueError("Descriptor mount record is unavailable")


def filesystem_context(path, expected=None):
    from xdg_quarantine_lifecycle import _identity
    with object_fd(path, expected) as (fd, info):
        result = {"stat_identity": list(_identity(info)), "mount": None,
                  "filesystem_identity": None}
        for key, operation in (("mount", lambda: mount_context(fd, info)),
                               ("filesystem_identity", lambda: btrfs_identity(fd))):
            try:
                result[key] = operation()
            except (OSError, ValueError, UnicodeError) as error:
                result[key + "_error"] = str(error)
        return result
