"""Fail-closed cleanup of completed quarantine journals.

Unlike purge, history cleanup removes only metadata and empty scope/run
folders. Never recursively delete anything and never touch a live entry.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import stat

from xdg_quarantine_lifecycle import RUN_ID, _open_path, _directory, _identity, _check_owner, _load_manifest

HISTORY_DAYS = 30
TERMINAL = frozenset(("purged", "restored"))


def _timestamp(value: object) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError("Purge completion time is missing")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid purge completion time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("Purge timestamp must include UTC offset")
    return parsed


def history_info(home: Path, roots: dict[str, Path], run_id: str, *, allow_empty_legacy=False) -> dict:
    """Verify *every* manifest item is terminal and all run scopes are empty.

    Strict anchoring means this never trusts the displayed GUI state or a
    caller-supplied path; it confirms there are no quarantined objects.
    """
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    if not base.is_absolute() or home not in base.parents or base.is_symlink():
        raise ValueError("Unsafe quarantine root")
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            run_stat = os.fstat(runfd)
            _check_owner(run_stat, run_stat.st_dev)
            payload = _load_manifest(runfd, run_stat.st_dev)
            if allow_empty_legacy and payload.get('format') == 'intent-journal-v2':
                from xdg_quarantine_legacy import inspect_legacy_run
                from xdg_audit import nested_mounts_status
                report = inspect_legacy_run(home, roots, run_id, nested_mounts_status, empty_only=True)
                if report['run_identity'] != _identity(run_stat) or report['payload'] != payload:
                    raise ValueError('Legacy run changed during empty-history verification')
                return {'run_id': run_id, 'status': 'EMPTY', 'items': len(payload['items']),
                        'purged_at': None, 'payload': payload, 'run_identity': _identity(run_stat),
                        'scopes': report['scopes'], 'existing_scopes': report['existing_scopes']}
            if payload.get("format") != "intent-journal-v3" or payload.get("created") != run_id:
                raise ValueError("Unsupported or mismatched journal")
            rows = payload.get("items")
            if not isinstance(rows, list) or not rows or len(rows) > 10000:
                raise ValueError("Invalid journal items")
            scopes: set[str] = set()
            names: set[tuple[str, str]] = set()
            states: list[str] = []
            for row in rows:
                if not isinstance(row, dict) or row.get("scope") not in roots:
                    raise ValueError("Malformed journal item")
                scope = row["scope"]
                source, destination = row.get("source"), row.get("destination")
                if not isinstance(source, str) or not isinstance(destination, str):
                    raise ValueError("Malformed paths")
                src, dst = Path(source), Path(destination)
                if (".." in src.parts or ".." in dst.parts or
                        src.parent != roots[scope] or dst.parent != base / run_id / scope or
                        src.name != dst.name or src.name in ("", ".", "..") or
                        (scope, src.name) in names):
                    raise ValueError("Untrusted manifest path or duplicate entry")
                identity = row.get("identity")
                if (not isinstance(identity, list) or len(identity) != 3 or
                        any(type(n) is not int or n < 0 for n in identity) or
                        identity[2] not in (stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError("Invalid recorded identity")
                status = row.get("move_status")
                if status not in TERMINAL:
                    raise ValueError("Run is not fully completed")
                names.add((scope, src.name))
                scopes.add(scope)
                states.append(status)
                # A restored entry must not still be present in quarantine.
                # A purged entry must not have been recreated either.
                # Scope directories are independently validated below.
            visible = set(os.listdir(runfd))
            if visible - {"manifest.json"} - scopes:
                raise ValueError("Untracked object in history run")
            existing_scopes = visible & scopes
            for scope in existing_scopes:
                fd = _directory(runfd, scope)
                try:
                    info = os.fstat(fd)
                    _check_owner(info, run_stat.st_dev)
                    if os.listdir(fd):
                        raise ValueError("Scope still contains quarantined or untracked files")
                finally:
                    os.close(fd)
            state = ("PURGED" if all(x == "purged" for x in states) else
                     "RESTORED" if all(x == "restored" for x in states) else "COMPLETED")
            purged_at = payload.get("purged_at")
            if purged_at is not None:
                _timestamp(purged_at)
                if state != "PURGED":
                    raise ValueError("Inconsistent purge completion timestamp")
            return {"run_id": run_id, "status": state, "items": len(rows),
                    "purged_at": purged_at, "payload": payload,
                    "run_identity": _identity(run_stat),
                    "scopes": sorted(scopes), "existing_scopes": sorted(existing_scopes)}
        finally:
            os.close(runfd)
    finally:
        os.close(basefd)


def history_expired(info: dict, *, now: dt.datetime | None = None) -> bool:
    """Automatic history cleanup starts 30 days after completed PURGE.

    Older tombstones without purged_at never expire automatically.
    """
    if info["status"] != "PURGED" or not info["purged_at"]:
        return False
    moment = _timestamp(info["purged_at"])
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Current time must be timezone-aware")
    return now - moment >= dt.timedelta(days=HISTORY_DAYS)


def history_candidates(home: Path, roots: dict[str, Path],
                       run_ids: list[str], *, now: dt.datetime | None = None) -> list[str]:
    result = []
    for run_id in run_ids:
        try:
            info = history_info(home, roots, run_id)
        except (OSError, ValueError, UnicodeError):
            continue  # errors and interrupted operations are intentionally ignored
        if history_expired(info, now=now):
            result.append(run_id)
    return result


def completed_history_candidates(home: Path, roots: dict[str, Path]) -> list[str]:
    """Find verified terminal journals and empty v2 records, regardless of age.

    This is *manual-cleanup only*: automated cleanup must continue to use
    history_candidates() with its 30-day post-PURGE restriction.
    A v2 record may have stale incomplete states, but must have no payload.
    Corrupt, incomplete v3 or non-empty runs are never returned.
    """
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    if not base.is_dir() or base.is_symlink():
        return []
    eligible = []
    for path in sorted(base.iterdir(), key=lambda entry: entry.name):
        if not RUN_ID.fullmatch(path.name) or path.is_symlink():
            continue
        try:
            history_info(home, roots, path.name, allow_empty_legacy=True)
        except (ValueError, OSError, UnicodeError):
            continue
        eligible.append(path.name)
    return eligible


def cleanup_history(home: Path, roots: dict[str, Path], run_id: str, *,
                    dry_run: bool = True) -> dict:
    """Remove only the complete journal and empty run directories.

    Known, independently verified empty v2 records may be manually removed.
    Cannot remove an invalid run or data within any scope.
    Aborted cleanup after empty scopes were removed is safely retryable.
    """
    report = history_info(home, roots, run_id, allow_empty_legacy=True)
    result = {"run_id": run_id, "status": report["status"],
              "items": report["items"], "dry_run": dry_run}
    if dry_run:
        return result
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    basefd = _open_path(base)
    try:
        runfd = _directory(basefd, run_id)
        try:
            device = os.fstat(runfd).st_dev
            if _identity(os.fstat(runfd)) != report["run_identity"]:
                raise ValueError("Run directory changed since preflight")
            if _load_manifest(runfd, device) != report["payload"]:
                raise ValueError("Journal changed since preflight")
            if set(os.listdir(runfd)) - {"manifest.json"} - set(report["scopes"]):
                raise ValueError("Untracked object appeared after preflight")
            # Only rmdir (never rmtree) can remove scope directories.
            for scope in report["existing_scopes"]:
                fd = _directory(runfd, scope)
                try:
                    _check_owner(os.fstat(fd), device)
                    if os.listdir(fd):
                        raise ValueError("Scope changed after preflight")
                finally:
                    os.close(fd)
            for scope in report["existing_scopes"]:
                os.rmdir(scope, dir_fd=runfd)
            # Journal is deleted only after all scoped directories are empty
            # and removed. If interrupted, the remaining manifest is retained.
            if set(os.listdir(runfd)) != {"manifest.json"}:
                raise ValueError("Unexpected files while removing history")
            os.unlink("manifest.json", dir_fd=runfd)
            os.fsync(runfd)
        finally:
            os.close(runfd)
        os.rmdir(run_id, dir_fd=basefd)
        os.fsync(basefd)
    finally:
        os.close(basefd)
    return result
