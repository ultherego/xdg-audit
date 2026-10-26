"""Fail-closed, journaled quarantine purge and inspection (Linux, stdlib only).

Purge removes *only* quarantined objects. It retains the manifest as an audit
tombstone. Legacy journals can be restored, but cannot authorize deletion.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import uuid

RUN_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{6}$")
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
MAX_MANIFEST = 4 * 1024 * 1024
ALLOWED_STATUSES = {"planned", "moving", "moved", "restoring", "restored", "purging", "purged"}


def _open_path(path: Path) -> int:
    """Open every ancestor without following symlinks; caller closes fd."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe non-absolute directory")
    fd = os.open("/", FLAGS)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, FLAGS, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def _directory(fd: int, name: str) -> int:
    return os.open(name, FLAGS, dir_fd=fd)


def _identity(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _check_owner(info: os.stat_result, device: int) -> None:
    if info.st_uid != os.getuid() or info.st_dev != device:
        raise ValueError("Foreign owner or filesystem inside quarantine")


def _load_manifest(fd: int, device: int) -> dict:
    filefd = os.open("manifest.json", os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=fd)
    try:
        info = os.fstat(filefd)
        _check_owner(info, device)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_MANIFEST:
            raise ValueError("Unsafe manifest file")
        with os.fdopen(os.dup(filefd), "rb") as stream:
            raw = stream.read(MAX_MANIFEST + 1)
        if len(raw) > MAX_MANIFEST:
            raise ValueError("Manifest too large")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid manifest object")
        return data
    finally:
        os.close(filefd)


def _write_manifest(fd: int, payload: dict) -> None:
    """Use anchored, no-follow temp creation + durable same-directory replace."""
    name = ".manifest-" + uuid.uuid4().hex + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    tmp = os.open(name, flags, 0o600, dir_fd=fd)
    try:
        with os.fdopen(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        tmp = -1
        os.replace(name, "manifest.json", src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        if tmp != -1:
            os.close(tmp)
        try:
            os.unlink(name, dir_fd=fd)
        except FileNotFoundError:
            pass


def _walk(fd: int, device: int) -> tuple[int, int]:
    """Verify all descendants; never follow links, reject special files/mounts."""
    size = 0
    objects = 0
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _check_owner(info, device)
        mode = stat.S_IFMT(info.st_mode)
        if mode == stat.S_IFDIR:
            child = _directory(fd, name)
            try:
                if _identity(os.fstat(child)) != _identity(info):
                    raise ValueError("Directory changed during inspection")
                child_bytes, child_objects = _walk(child, device)
                size += child_bytes
                objects += child_objects
            finally:
                os.close(child)
        elif mode in (stat.S_IFREG, stat.S_IFLNK):
            if mode == stat.S_IFREG and info.st_nlink != 1:
                raise ValueError("Hard-linked quarantine file; refusing purge")
            size += info.st_size
            objects += 1
        else:
            raise ValueError("Special file inside quarantine")
    return size, objects


def _delete_children(fd: int, device: int) -> None:
    """Delete only names relative to already-open, verified directory FDs."""
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _check_owner(info, device)
        mode = stat.S_IFMT(info.st_mode)
        if mode == stat.S_IFDIR:
            child = _directory(fd, name)
            try:
                if _identity(os.fstat(child)) != _identity(info):
                    raise ValueError("Directory replaced during deletion")
                _delete_children(child, device)
                os.fsync(child)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        elif mode in (stat.S_IFREG, stat.S_IFLNK):
            if mode == stat.S_IFREG and info.st_nlink != 1:
                raise ValueError("Unexpected hard link")
            os.unlink(name, dir_fd=fd)
        else:
            raise ValueError("Special file inside quarantine")
    os.fsync(fd)


def _delete_entry(scopefd: int, name: str, expected: tuple[int, int, int], device: int) -> None:
    info = os.stat(name, dir_fd=scopefd, follow_symlinks=False)
    _check_owner(info, device)
    if _identity(info) != expected:
        raise ValueError("Quarantined object identity changed; refusing purge")
    if stat.S_ISDIR(info.st_mode):
        child = _directory(scopefd, name)
        try:
            if _identity(os.fstat(child)) != expected:
                raise ValueError("Object changed during purge")
            _delete_children(child, device)
        finally:
            os.close(child)
        os.rmdir(name, dir_fd=scopefd)
    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
        os.unlink(name, dir_fd=scopefd)
    else:
        raise ValueError("Unsafe quarantined object")
    os.fsync(scopefd)


def inspect_run(home: Path, roots: dict[str, Path], run_id: str, mounts_checker) -> dict:
    """Strictly preflight the complete run, including untracked files."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid quarantine run ID")
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    if home not in base.parents or base.is_symlink():
        raise ValueError("Unsafe quarantine location")
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            run_stat = os.fstat(runfd)
            _check_owner(run_stat, run_stat.st_dev)
            payload = _load_manifest(runfd, run_stat.st_dev)
            if payload.get("format") != "intent-journal-v3" or payload.get("created") != run_id:
                raise ValueError("Purge requires a valid v3 journal and matching run ID")
            rows = payload.get("items")
            if not isinstance(rows, list) or not rows or len(rows) > 10000:
                raise ValueError("Invalid journal items")
            entries = []
            scopes = set()
            seen_sources, seen_destinations = set(), set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Malformed journal row")
                scope = row.get("scope")
                if not isinstance(scope, str) or scope not in roots:
                    raise ValueError("Invalid journal scope")
                source, destination = row.get("source"), row.get("destination")
                if not isinstance(source, str) or not isinstance(destination, str):
                    raise ValueError("Invalid journal paths")
                src, dest = Path(source), Path(destination)
                if (".." in src.parts or ".." in dest.parts or
                        src.parent != roots[scope] or dest.parent != base / run_id / scope or
                        src.name != dest.name or src.name in ("", ".", "..") or
                        source in seen_sources or destination in seen_destinations):
                    raise ValueError("Foreign, duplicated or manipulated journal path")
                seen_sources.add(source)
                seen_destinations.add(destination)
                raw_id = row.get("identity")
                if (not isinstance(raw_id, list) or len(raw_id) != 3 or
                        any(type(n) is not int or n < 0 for n in raw_id) or
                        raw_id[2] not in (stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError("Missing or invalid v3 inode identity")
                status = row.get("move_status")
                if status not in ALLOWED_STATUSES:
                    raise ValueError("Unknown journal state")
                scopes.add(scope)
                entries.append({"row": row, "scope": scope, "name": src.name,
                                "source": src, "destination": dest,
                                "identity": tuple(raw_id), "status": status})
            if set(os.listdir(runfd)) != {"manifest.json", *scopes}:
                raise ValueError("Untracked content in quarantine run")
            names_by_scope = {scope: set() for scope in scopes}
            total = 0
            for entry in entries:
                names_by_scope[entry["scope"]].add(entry["name"])
            for scope, expected_names in names_by_scope.items():
                scopefd = _directory(runfd, scope)
                try:
                    _check_owner(os.fstat(scopefd), run_stat.st_dev)
                    if not set(os.listdir(scopefd)).issubset(expected_names):
                        raise ValueError("Untracked object in quarantine scope")
                finally:
                    os.close(scopefd)
            for entry in entries:
                scopefd = _directory(runfd, entry["scope"])
                try:
                    try:
                        info = os.stat(entry["name"], dir_fd=scopefd, follow_symlinks=False)
                    except FileNotFoundError:
                        info = None
                    if info is None:
                        if entry["status"] in ("moved", "moving", "restoring") and not entry["source"].exists():
                            raise ValueError("Missing quarantined object without purge intent")
                        if entry["status"] in ("planned", "moving", "restoring", "restored") and not entry["source"].exists():
                            raise ValueError("Missing original and quarantined object")
                        entry["present"] = False
                        entry["bytes"] = 0
                    else:
                        _check_owner(info, run_stat.st_dev)
                        if _identity(info) != entry["identity"]:
                            raise ValueError("Quarantine inode substitution")
                        if entry["status"] in ("purged", "restored"):
                            raise ValueError("Journal claims object absent, but it exists")
                        if stat.S_ISDIR(info.st_mode):
                            if mounts_checker(entry["destination"]) is not False:
                                raise ValueError("Nested mounts or unavailable mount inventory")
                            fd = _directory(scopefd, entry["name"])
                            try:
                                if _identity(os.fstat(fd)) != entry["identity"]:
                                    raise ValueError("Quarantine changed during inspection")
                                size, _ = _walk(fd, run_stat.st_dev)
                            finally:
                                os.close(fd)
                        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                            size = info.st_size
                        else:
                            raise ValueError("Unsafe quarantined object")
                        entry["present"] = True
                        entry["bytes"] = size
                        total += size
                finally:
                    os.close(scopefd)
            return {"run_id": run_id, "payload": payload, "entries": entries,
                    "bytes": total, "present": sum(e["present"] for e in entries)}
        finally:
            os.close(runfd)
    finally:
        os.close(basefd)


def purge_run(home: Path, roots: dict[str, Path], run_id: str, mounts_checker,
              *, dry_run: bool = True, emit=print) -> dict:
    """Full preflight before deleting anything; resume after interrupted purge."""
    report = inspect_run(home, roots, run_id, mounts_checker)
    result = {"run_id": run_id, "objects": report["present"],
              "bytes": report["bytes"], "dry_run": dry_run}
    if dry_run:
        return result
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            device = os.fstat(runfd).st_dev
            payload = report["payload"]
            # Refuse manifest substitutions between inspection and execution.
            if _load_manifest(runfd, device) != payload:
                raise ValueError("Journal changed after preflight")
            for entry in report["entries"]:
                row = entry["row"]
                if not entry["present"]:
                    if row["move_status"] == "purging":
                        row["move_status"] = "purged"
                        _write_manifest(runfd, payload)
                    continue
                scopefd = _directory(runfd, entry["scope"])
                try:
                    if mounts_checker(entry["destination"]) is not False and entry["identity"][2] == stat.S_IFDIR:
                        raise ValueError("Mount inventory changed during purge")
                    row["move_status"] = "purging"
                    _write_manifest(runfd, payload)
                    _delete_entry(scopefd, entry["name"], entry["identity"], device)
                    row["move_status"] = "purged"
                    _write_manifest(runfd, payload)
                    emit("PURGED " + str(entry["destination"]))
                finally:
                    os.close(scopefd)
            return result
        finally:
            os.close(runfd)
    finally:
        os.close(basefd)


def expired_run_ids(runs: list[dict], days: int, now: dt.datetime | None = None) -> list[str]:
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError("Retention days must be between 1 and 3650")
    now = now or dt.datetime.now()
    cutoff = now - dt.timedelta(days=days)
    return [run["run_id"] for run in runs if
            RUN_ID.fullmatch(run.get("run_id", "")) and
            dt.datetime.strptime(run["run_id"], "%Y%m%d-%H%M%S-%f") < cutoff]
