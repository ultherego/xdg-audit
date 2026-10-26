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


def capture_inventory(path: Path) -> list[dict]:
    """Capture complete inode/hash inventory without following symlinks."""
    import hashlib
    parent = _open_path(path.parent)
    try:
        initial = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        device = initial.st_dev
        result = []

        def visit(fd, name, relative, depth):
            if depth > 64 or len(result) >= 100000:
                raise ValueError("Quarantine inventory limit exceeded")
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            _check_owner(before, device)
            kind = stat.S_IFMT(before.st_mode)
            if kind not in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK):
                raise ValueError("Unsafe special file in quarantine")
            row = {"path": relative, "identity": list(_identity(before))}
            if kind == stat.S_IFDIR:
                child = _directory(fd, name)
                try:
                    if _identity(os.fstat(child)) != _identity(before):
                        raise ValueError("Directory replaced during inventory")
                    result.append(row)
                    for part in sorted(os.listdir(child)):
                        visit(child, part, part if relative == "." else relative + "/" + part, depth + 1)
                finally:
                    os.close(child)
            elif kind == stat.S_IFREG:
                if before.st_nlink != 1:
                    raise ValueError("Hard linked file in quarantine")
                filefd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=fd)
                try:
                    start = os.fstat(filefd)
                    if _identity(start) != _identity(before):
                        raise ValueError("File replaced during inventory")
                    sha = hashlib.sha256()
                    with os.fdopen(os.dup(filefd), "rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            sha.update(block)
                    after = os.fstat(filefd)
                    if (_identity(after) != _identity(start) or
                            after.st_mtime_ns != start.st_mtime_ns or after.st_size != start.st_size):
                        raise ValueError("File modified during hashing")
                    row.update({"size": after.st_size, "sha256": sha.hexdigest()})
                    result.append(row)
                finally:
                    os.close(filefd)
            else:
                row["link"] = os.readlink(name, dir_fd=fd)
                if _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(before):
                    raise ValueError("Symlink replaced during inventory")
                result.append(row)

        visit(parent, path.name, ".", 0)
        if _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _identity(initial):
            raise ValueError("Quarantine entry changed during inventory")
        return result
    finally:
        os.close(parent)


def _validated_inventory(value, root_identity):
    if not isinstance(value, list) or not value or len(value) > 100000:
        raise ValueError("Missing recursive inventory; legacy run requires adoption")
    nodes = {}
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("Invalid inventory row")
        name = row["path"]
        if (name != "." and (name.startswith("/") or
                any(part in ("", ".", "..") for part in name.split("/")))):
            raise ValueError("Unsafe inventory relative path")
        ident = row.get("identity")
        if (not isinstance(ident, list) or len(ident) != 3 or
                any(type(n) is not int or n < 0 for n in ident) or
                ident[2] not in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK)):
            raise ValueError("Invalid nested identity")
        if name in nodes:
            raise ValueError("Duplicate inventory entry")
        nodes[name] = row
        if ident[2] == stat.S_IFREG:
            if (type(row.get("size")) is not int or row["size"] < 0 or
                    not isinstance(row.get("sha256"), str) or
                    re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
                raise ValueError("Missing SHA-256 in inventory")
        if ident[2] == stat.S_IFLNK and not isinstance(row.get("link"), str):
            raise ValueError("Missing symlink target")
    if "." not in nodes or tuple(nodes["."]["identity"]) != root_identity:
        raise ValueError("Quarantine root identity differs from inventory")
    for name in nodes:
        if name != ".":
            parent = name.rpartition("/")[0] or "."
            if parent not in nodes or nodes[parent]["identity"][2] != stat.S_IFDIR:
                raise ValueError("Orphan inventory path")
    return nodes


def _match_inventory(expected, current, *, partial=False):
    found = {row["path"]: row for row in current}
    if not set(found).issubset(expected):
        raise ValueError("Unexpected new file in quarantine")
    if not partial and set(found) != set(expected):
        raise ValueError("Quarantined content missing or changed")
    for name, actual in found.items():
        if actual != expected[name]:
            raise ValueError("Quarantined contents or inode changed: " + name)


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


def _delete_children(fd: int, device: int, expected: dict, prefix: str = ".") -> None:
    """Delete exactly inventoried names, anchored to verified directory fds."""
    for name in sorted(os.listdir(fd)):
        relative = name if prefix == "." else prefix + "/" + name
        if relative not in expected:
            raise ValueError("New untracked object appeared while purging")
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        _check_owner(info, device)
        if list(_identity(info)) != expected[relative]["identity"]:
            raise ValueError("Object replaced while purging")
        mode = stat.S_IFMT(info.st_mode)
        if mode == stat.S_IFDIR:
            child = _directory(fd, name)
            try:
                if _identity(os.fstat(child)) != _identity(info):
                    raise ValueError("Directory replaced during deletion")
                _delete_children(child, device, expected, relative)
            finally:
                os.close(child)
            info2 = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if _identity(info2) != _identity(info):
                raise ValueError("Directory changed before rmdir")
            os.rmdir(name, dir_fd=fd)
        elif mode in (stat.S_IFREG, stat.S_IFLNK):
            if mode == stat.S_IFREG and info.st_nlink != 1:
                raise ValueError("Unexpected hard link")
            info2 = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if _identity(info2) != _identity(info):
                raise ValueError("File changed before unlink")
            os.unlink(name, dir_fd=fd)
        else:
            raise ValueError("Special file inside quarantine")
    os.fsync(fd)


def _delete_entry(scopefd: int, name: str, expected_identity: tuple[int, int, int],
                  device: int, inventory: dict) -> None:
    info = os.stat(name, dir_fd=scopefd, follow_symlinks=False)
    _check_owner(info, device)
    if _identity(info) != expected_identity:
        raise ValueError("Quarantined object identity changed; refusing purge")
    if stat.S_ISDIR(info.st_mode):
        child = _directory(scopefd, name)
        try:
            if _identity(os.fstat(child)) != expected_identity:
                raise ValueError("Object changed during purge")
            _delete_children(child, device, inventory)
        finally:
            os.close(child)
        current = os.stat(name, dir_fd=scopefd, follow_symlinks=False)
        if _identity(current) != expected_identity:
            raise ValueError("Quarantine entry changed before rmdir")
        os.rmdir(name, dir_fd=scopefd)
    elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
        os.unlink(name, dir_fd=scopefd)
    else:
        raise ValueError("Unsafe quarantined object")
    os.fsync(scopefd)


def inspect_run(home: Path, roots: dict[str, Path], run_id: str, mounts_checker, *, allow_unsealed=False) -> dict:
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
                row = entry["row"]
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
                        if stat.S_ISDIR(info.st_mode) and mounts_checker(entry["destination"]) is not False:
                            raise ValueError("Nested mounts or unavailable mount inventory")
                        current = capture_inventory(entry["destination"])
                        if allow_unsealed and row.get("tree_inventory") is None:
                            if entry["status"] not in ("moved", "moving"):
                                raise ValueError("Cannot adopt an interrupted destructive operation")
                            entry["unsealed"] = True
                        else:
                            expected = _validated_inventory(row.get("tree_inventory"), entry["identity"])
                            _match_inventory(expected, current, partial=(entry["status"] == "purging"))
                            entry["unsealed"] = False
                        entry["inventory"] = current
                        size = sum(node.get("size", 0) for node in current)
                        entry["present"] = True
                        entry["bytes"] = size
                        total += size
                finally:
                    os.close(scopefd)
            return {"run_id": run_id, "payload": payload, "entries": entries,
                    "run_identity": _identity(run_stat),
                    "bytes": total, "present": sum(e["present"] for e in entries)}
        finally:
            os.close(runfd)
    finally:
        os.close(basefd)


def adopt_legacy_run(home: Path, roots: dict[str, Path], run_id: str, mounts_checker) -> dict:
    """After explicit user confirmation, bind CURRENT legacy data for future purge.

    Adoption does not prove contents match the day of quarantine; it only
    guarantees a subsequent purge cannot silently include later additions.
    """
    report = inspect_run(home, roots, run_id, mounts_checker, allow_unsealed=True)
    entries = [entry for entry in report["entries"] if entry.get("unsealed")]
    if not entries:
        return {"run_id": run_id, "adopted": 0}
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            device = os.fstat(runfd).st_dev
            if _identity(os.fstat(runfd)) != report["run_identity"]:
                raise ValueError("Quarantine run swapped while adopting")
            payload = report["payload"]
            if _load_manifest(runfd, device) != payload:
                raise ValueError("Journal changed while adopting")
            for entry in entries:
                current = capture_inventory(entry["destination"])
                if current != entry["inventory"]:
                    raise ValueError("Data changed while adopting")
                entry["row"]["tree_inventory"] = current
            _write_manifest(runfd, payload)
            return {"run_id": run_id, "adopted": len(entries)}
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
            if _identity(os.fstat(runfd)) != report["run_identity"]:
                raise ValueError("Quarantine run substituted")
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
                    expected = _validated_inventory(row.get("tree_inventory"), entry["identity"])
                    current = capture_inventory(entry["destination"])
                    _match_inventory(expected, current, partial=(row["move_status"] == "purging"))
                    row["move_status"] = "purging"
                    _write_manifest(runfd, payload)
                    _delete_entry(scopefd, entry["name"], entry["identity"], device, expected)
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


def recover_manifest_temps(home: Path, roots: dict[str, Path], run_id: str,
                           *, dry_run: bool = True) -> dict:
    """Recover crash-leftover journal temp files after strict run preflight.

    Never touch the journal, any scope subtree, or arbitrary untracked names.
    No recursive removal. The caller must obtain explicit user confirmation.
    """
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid quarantine run ID")
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    if home not in base.parents or base.is_symlink():
        raise ValueError("Unsafe quarantine path")
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            info = os.fstat(runfd)
            _check_owner(info, info.st_dev)
            payload = _load_manifest(runfd, info.st_dev)
            if payload.get("created") != run_id or payload.get("format") != "intent-journal-v3":
                raise ValueError("Unsupported journal cannot be recovered")
            rows = payload.get("items")
            if not isinstance(rows, list) or not rows:
                raise ValueError("Invalid journal")
            scopes = set()
            for row in rows:
                if not isinstance(row, dict) or row.get("scope") not in roots:
                    raise ValueError("Invalid journal scope")
                scopes.add(row["scope"])
            names = set(os.listdir(runfd))
            temps = sorted(name for name in names if
                           re.fullmatch(r"\.manifest-[a-zA-Z0-9_-]{6,40}\.tmp", name))
            if names - set(temps) - {"manifest.json"} - scopes:
                raise ValueError("Unexpected files outside scope directories")
            for name in temps:
                entry = os.stat(name, dir_fd=runfd, follow_symlinks=False)
                _check_owner(entry, info.st_dev)
                if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or entry.st_mode & 0o077:
                    raise ValueError("Unsafe journal temporary file")
            if not dry_run:
                for name in temps:
                    entry = os.stat(name, dir_fd=runfd, follow_symlinks=False)
                    _check_owner(entry, info.st_dev)
                    if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or entry.st_mode & 0o077:
                        raise ValueError("Journal temp substituted")
                    os.unlink(name, dir_fd=runfd)
                os.fsync(runfd)
            return {"run_id": run_id, "temporary_files": len(temps), "dry_run": dry_run}
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
