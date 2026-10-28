"""Fail-closed, journaled quarantine purge and inspection (Linux, stdlib only).

Purge removes *only* quarantined objects. It retains the manifest as an audit
tombstone. Known v2 journals require explicit current-content adoption before
separately confirmed deletion; historical evidence is never invented.
"""
from __future__ import annotations

import datetime as dt
import copy
import hashlib
import errno
import json
import os
from pathlib import Path
import re
import stat
import uuid

RUN_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{6}$")
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
MAX_MANIFEST = 64 * 1024 * 1024
ALLOWED_STATUSES = {"planned", "moving", "moved", "restoring", "restored", "purging", "purged"}


class LegacyQuarantineJournal(ValueError):
    """Known pre-identity journal: explicit adoption is required before purge."""
    def __init__(self, run_id):
        self.run_id = run_id
        super().__init__('Legacy v2 journal requires explicit ADOPT before PURGE: ' + run_id)


class QuarantineIdentityMismatch(ValueError):
    """Preserve exact read-only identity evidence when preflight refuses a run."""
    def __init__(self, run_id, path, expected, actual):
        self.run_id = run_id
        self.path = Path(path)
        self.expected = tuple(expected)
        self.actual = tuple(actual)
        super().__init__(f"Quarantine inode substitution: {self.path}; "
                         f"recorded device/inode/type={self.expected}; "
                         f"current device/inode/type={self.actual}")


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


def capture_inventory(path: Path, *, require_deletable: bool = False) -> list[dict]:
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
                    children = sorted(os.listdir(child))
                    # A readable directory may still refuse unlinking its
                    # descendants. Reject that before any destructive PURGE.
                    if (require_deletable and children and
                            not stat.S_IMODE(before.st_mode) & stat.S_IWUSR):
                        raise PermissionError(errno.EACCES,
                            "Cannot delete children of a non-writable directory", relative)
                    for part in children:
                        visit(child, part, part if relative == "." else relative + "/" + part, depth + 1)
                finally:
                    os.close(child)
            elif kind == stat.S_IFREG:
                if before.st_nlink != 1:
                    raise ValueError("Hard linked file in quarantine")
                filefd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                                 getattr(os, "O_CLOEXEC", 0), dir_fd=fd)
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
    # Reject a FIFO before any read; even opening it can otherwise wait forever.
    filefd = os.open("manifest.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                     getattr(os, "O_CLOEXEC", 0), dir_fd=fd)
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


def read_manifest(run: Path) -> dict:
    """Read a bounded, user-owned regular journal through anchored descriptors.

    Shared by display and legacy restore paths without requiring a v3 schema.
    Opening a substituted FIFO cannot stall before descriptor validation.
    """
    fd = _open_path(run)
    try:
        info = os.fstat(fd)
        _check_owner(info, info.st_dev)
        return _load_manifest(fd, info.st_dev)
    finally:
        os.close(fd)


def _write_manifest(fd: int, payload: dict) -> None:
    """Use anchored, no-follow temp creation + durable same-directory replace."""
    name = ".manifest-" + uuid.uuid4().hex + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    tmp = os.open(name, flags, 0o600, dir_fd=fd)
    try:
        handle = os.fdopen(tmp, "w", encoding="utf-8")
        # fdopen owns the descriptor even if dump/flush/fsync later fails.
        # A second close would mask ENOSPC/EACCES with EBADF.
        tmp = -1
        with handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
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


def inspect_run(home: Path, roots: dict[str, Path], run_id: str, mounts_checker, *,
                allow_unsealed=False, require_deletable=False,
                device_revalidation=False) -> dict:
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
            if payload.get('format') == 'intent-journal-v2' and payload.get('created') == run_id:
                raise LegacyQuarantineJournal(run_id)
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
                if device_revalidation and status not in {"moved", "purged", "restored"}:
                    raise ValueError("Device revalidation requires completed MOVE entries")
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
                        actual_identity = _identity(info)
                        device_only = (actual_identity[0] != entry["identity"][0] and
                                       actual_identity[1:] == entry["identity"][1:])
                        if actual_identity != entry["identity"] and not (device_revalidation and device_only):
                            raise QuarantineIdentityMismatch(run_id, entry["destination"],
                                                             entry["identity"], actual_identity)
                        from xdg_filesystem import filesystem_identity, verify_identity
                        binding = None
                        if "filesystem_identity" in row:
                            binding = verify_identity(entry["destination"], row["filesystem_identity"], actual_identity)
                        if device_revalidation:
                            binding = binding or filesystem_identity(entry["destination"], actual_identity)
                            if binding is None:
                                raise ValueError("Device revalidation currently requires readable Btrfs filesystem identity")
                            entry["current_identity"] = actual_identity
                            entry["filesystem_identity"] = binding
                            entry["historical_binding_verified"] = "filesystem_identity" in row
                            entry["device_changed"] = device_only
                        if entry["status"] in ("purged", "restored"):
                            raise ValueError("Journal claims object absent, but it exists")
                        if stat.S_ISDIR(info.st_mode) and mounts_checker(entry["destination"]) is not False:
                            raise ValueError("Nested mounts or unavailable mount inventory")
                        current = capture_inventory(entry["destination"],
                                                    require_deletable=require_deletable)
                        if allow_unsealed and row.get("tree_inventory") is None:
                            if entry["status"] not in ("moved", "moving"):
                                raise ValueError("Cannot adopt an interrupted destructive operation")
                            entry["unsealed"] = True
                        else:
                            if device_revalidation and row.get("tree_inventory") is None:
                                raise ValueError("Device revalidation requires the original sealed recursive inventory; ADOPT cannot reconstruct historical content")
                            expected = _validated_inventory(row.get("tree_inventory"), entry["identity"])
                            if device_revalidation:
                                if any(node["identity"][0] != entry["identity"][0] for node in expected.values()):
                                    raise ValueError("Recorded inventory contains inconsistent devices")
                                expected = {name: {**node, "identity": [actual_identity[0], *node["identity"][1:]]}
                                            for name, node in expected.items()}
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


def device_revalidation_plan(home, roots, run_id, mounts_checker):
    """Read-only proof of exact inventory equality with only st_dev remapped.

    Legacy journals lack historical FSID evidence. Confirmation must explicitly
    approve the verified CURRENT binding, never claim historical identity proof.
    """
    report = inspect_run(home, roots, run_id, mounts_checker, device_revalidation=True)
    changed = [entry for entry in report["entries"] if entry.get("device_changed")]
    if not changed:
        raise ValueError("No device-only identity change requires revalidation")
    old = {entry["identity"][0] for entry in changed}
    new = {entry["current_identity"][0] for entry in changed}
    if len(old) != 1 or len(new) != 1:
        raise ValueError("Device revalidation requires one consistent device-number transition")
    return report


def device_revalidation_summary(report):
    entries = [entry for entry in report["entries"] if entry.get("device_changed")]
    if not entries:
        raise ValueError("No device change in revalidation report")
    approval = {"payload": report["payload"], "run_identity": report["run_identity"],
                "current": [{"identity": entry.get("current_identity"),
                             "filesystem": entry.get("filesystem_identity"),
                             "inventory": entry.get("inventory")}
                            for entry in report["entries"]]}
    token = hashlib.sha256(json.dumps(approval, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {"run_id": report["run_id"], "entries": len(entries), "bytes": report["bytes"],
            "old_device": entries[0]["identity"][0], "new_device": entries[0]["current_identity"][0],
            "historical_binding_verified": all(entry["historical_binding_verified"] for entry in entries),
            "filesystem_identity": entries[0]["filesystem_identity"], "purge_authorized": False,
            "approval_token": token}


def revalidate_device(home, roots, run_id, mounts_checker, *, approval_token):
    """After distinct REVALIDATE consent, journal the verified current binding.

    Never delete data or change expected names, inode numbers, types or hashes.
    PURGE always performs another independent preflight and confirmation.
    """
    report = device_revalidation_plan(home, roots, run_id, mounts_checker)
    summary = device_revalidation_summary(report)
    if not isinstance(approval_token, str) or approval_token != summary['approval_token']:
        raise ValueError("Device revalidation evidence changed after confirmation; review a fresh preview")
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    with_fd = _open_path(base / run_id)
    try:
        device = os.fstat(with_fd).st_dev
        if (_identity(os.fstat(with_fd)) != report["run_identity"] or
                _load_manifest(with_fd, device) != report["payload"]):
            raise ValueError("Journal or run changed during device revalidation")
        from xdg_filesystem import verify_identity
        for entry in report["entries"]:
            if not entry.get("present"):
                continue
            if (mounts_checker(entry["destination"]) is not False and
                    entry["current_identity"][2] == stat.S_IFDIR):
                raise ValueError("Mount inventory changed during device revalidation")
            verify_identity(entry["destination"], entry["filesystem_identity"], entry["current_identity"])
            if capture_inventory(entry["destination"]) != entry["inventory"]:
                raise ValueError("Contents changed during device revalidation")
            verify_identity(entry["destination"], entry["filesystem_identity"], entry["current_identity"])
        original_payload = report["payload"]
        payload = copy.deepcopy(original_payload)
        history = payload.get("device_revalidations", [])
        if not isinstance(history, list) or len(history) >= 100:
            raise ValueError("Invalid or excessive device revalidation history")
        rows = {row["destination"]: row for row in payload["items"]}
        for entry in report["entries"]:
            if entry.get("device_changed"):
                row = rows[str(entry["destination"])]
                row["identity"] = list(entry["current_identity"])
                row["tree_inventory"] = entry["inventory"]
                row["filesystem_identity"] = entry["filesystem_identity"]
        payload["device_revalidations"] = history + [{**summary,
            "confirmed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "reason": "explicit_current_binding_revalidation"}]
        if _load_manifest(with_fd, device) != original_payload:
            raise ValueError("Journal changed before device revalidation commit")
        _write_manifest(with_fd, payload)
        return summary
    finally:
        os.close(with_fd)


def adopt_legacy_run(home: Path, roots: dict[str, Path], run_id: str, mounts_checker, *, approval_token=None) -> dict:
    """After explicit user confirmation, bind CURRENT legacy data for future purge.

    Adoption does not prove contents match the day of quarantine; it only
    guarantees a subsequent purge cannot silently include later additions.
    """
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError('Invalid quarantine run ID')
    base = roots.get('data', home / '.local/share') / 'xdg-audit-quarantine'
    if read_manifest(base / run_id).get('format') == 'intent-journal-v2':
        from xdg_quarantine_legacy import adopt_v2_run
        return adopt_v2_run(home, roots, run_id, mounts_checker, approval_token)
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
              *, dry_run: bool = True, automatic: bool = False, emit=print) -> dict:
    """Full preflight before deleting anything; resume after interrupted purge."""
    report = inspect_run(home, roots, run_id, mounts_checker, require_deletable=True)
    # Rebinding an identity never inherits a previously enabled timer's consent.
    # Enforce this on both preview and execution, using the fresh journal.
    if automatic and 'device_revalidations' in report['payload']:
        raise ValueError('Revalidated runs require a separate explicit PURGE confirmation; automatic deletion is blocked')
    if automatic and 'legacy_adoption' in report['payload']:
        raise ValueError('Adopted v2 runs require a separate explicit PURGE confirmation; automatic deletion is blocked')
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
                    if "filesystem_identity" in row:
                        from xdg_filesystem import verify_identity
                        verify_identity(entry["destination"], row["filesystem_identity"], entry["identity"])
                    current = capture_inventory(entry["destination"], require_deletable=True)
                    _match_inventory(expected, current, partial=(row["move_status"] == "purging"))
                    row["move_status"] = "purging"
                    _write_manifest(runfd, payload)
                    _delete_entry(scopefd, entry["name"], entry["identity"], device, expected)
                    row["move_status"] = "purged"
                    _write_manifest(runfd, payload)
                    emit("PURGED " + str(entry["destination"]))
                finally:
                    os.close(scopefd)
            # Retention starts at successful PURGE completion, never run creation.
            # Old journals lacking purged_at are not auto-expired by history GC.
            if (all(row["move_status"] == "purged" for row in payload["items"])
                    and "purged_at" not in payload):
                payload["purged_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
                _write_manifest(runfd, payload)
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
