"""Read-only quarantine access diagnosis and narrow owner-only remediation.

No subprocess/sudo/pkexec is used for mutation. Repair changes the user-read
bit on exactly one *user-owned* quarantined directory after opt-in approval.
A missing or corrupt inventory is NEVER fabricated by this module.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import re
import shutil
import stat

from xdg_quarantine_lifecycle import (
    RUN_ID, FLAGS, ALLOWED_STATUSES, _directory, _identity, _load_manifest,
    _open_path,
)

MAX_ITEMS = 100000
MAX_DEPTH = 64
MAX_ISSUES = 30


def needs_access_recovery(exc: BaseException) -> bool:
    """Only trigger guided ACCESS/ADOPT for known recoverable preflight errors.

    Other manifest/inode/hash failures must remain blocked without adoption.
    """
    return (isinstance(exc, PermissionError) or
            (isinstance(exc, ValueError) and str(exc) in {
                "Missing recursive inventory; legacy run requires adoption",
                "Foreign owner or filesystem inside quarantine",
            }))


def authority_context() -> dict:
    """Describe the invoking identity; never guess Polkit authorization."""
    uid = os.getuid()
    return {
        "uid": uid, "user": pwd.getpwuid(uid).pw_name,
        "groups": list(os.getgroups()),
        "session": os.environ.get("XDG_SESSION_ID") or None,
        "session_type": os.environ.get("XDG_SESSION_TYPE") or None,
        "pkexec_installed": shutil.which("pkexec") is not None,
        "authorization": "not_requested",
    }


def _journal(home: Path, roots: dict[str, Path], run_id: str):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid quarantine run ID")
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    if home not in base.parents or base.is_symlink():
        raise ValueError("Unsafe quarantine root")
    fd = _open_path(base)
    try:
        runfd = _directory(fd, run_id)
        try:
            rs = os.fstat(runfd)
            if rs.st_uid != os.getuid():
                raise ValueError("Quarantine run is not user-owned")
            payload = _load_manifest(runfd, rs.st_dev)
            if payload.get("format") != "intent-journal-v3" or payload.get("created") != run_id:
                raise ValueError("Invalid or unsupported quarantine journal")
            rows = payload.get("items")
            if not isinstance(rows, list) or not rows or len(rows) > 10000:
                raise ValueError("Invalid quarantine entries")
            scopes = set()
            seen = set()
            targets = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Malformed quarantine entry")
                scope = row.get("scope")
                if scope not in roots or not isinstance(scope, str):
                    raise ValueError("Untrusted quarantine scope")
                src, dest = row.get("source"), row.get("destination")
                if not isinstance(src, str) or not isinstance(dest, str):
                    raise ValueError("Invalid entry path")
                s, d = Path(src), Path(dest)
                if (".." in s.parts or ".." in d.parts or
                    s.parent != roots[scope] or d.parent != base / run_id / scope or
                    s.name != d.name or s.name in ("", ".", "..") or
                    dest in seen):
                    raise ValueError("Entry escapes the quarantine journal")
                raw_id = row.get("identity")
                if (not isinstance(raw_id, list) or len(raw_id) != 3 or
                    any(type(x) is not int or x < 0 for x in raw_id) or
                    raw_id[2] not in (stat.S_IFDIR, stat.S_IFREG) or
                    row.get("move_status") not in ALLOWED_STATUSES):
                    raise ValueError("Malformed quarantine identity or status")
                scopes.add(scope)
                seen.add(dest)
                targets.append((scope, d.name, tuple(raw_id), row))
            if set(os.listdir(runfd)) != {"manifest.json", *scopes}:
                raise ValueError("Untracked content in quarantine run")
            return base, targets, rs.st_dev
        finally:
            os.close(runfd)
    finally:
        os.close(fd)


def diagnose_access(home: Path, roots: dict[str, Path], run_id: str) -> dict:
    """Identify inaccessible descendants without crossing mounts or links."""
    base, targets, device = _journal(home, roots, run_id)
    uid = os.getuid()
    findings = []
    seen_nodes = 0
    unsealed = False

    def problem(code, path, info=None, repairable=False, add_bits=stat.S_IRUSR):
        if len(findings) >= MAX_ISSUES:
            return
        findings.append({
            "code": code, "path": str(path),
            "relative": str(path.relative_to(base / run_id)),
            "mode": format(stat.S_IMODE(info.st_mode), "03o") if info else None,
            "owner_uid": info.st_uid if info else None,
            "repairable": bool(repairable),
            "suggested_mode": (format(stat.S_IMODE(info.st_mode) | add_bits, "03o")
                               if repairable else None),
        })

    def walk(parentfd, name, path, depth):
        nonlocal seen_nodes
        seen_nodes += 1
        if seen_nodes > MAX_ITEMS or depth > MAX_DEPTH:
            raise ValueError("Quarantine access scan limit exceeded")
        info = os.stat(name, dir_fd=parentfd, follow_symlinks=False)
        kind = stat.S_IFMT(info.st_mode)
        if info.st_dev != device or info.st_uid != uid:
            problem("FOREIGN_OWNER_OR_DEVICE", path, info)
            return
        if kind == stat.S_IFDIR:
            try:
                fd = _directory(parentfd, name)
            except PermissionError:
                problem("DIRECTORY_UNREADABLE", path, info,
                        repairable=(stat.S_IMODE(info.st_mode) & stat.S_IRUSR == 0))
                return
            try:
                if _identity(os.fstat(fd)) != _identity(info):
                    raise ValueError("Quarantine directory substituted")
                try:
                    names = sorted(os.listdir(fd))
                except PermissionError:
                    problem("DIRECTORY_UNREADABLE", path, info,
                            repairable=(stat.S_IMODE(info.st_mode) & stat.S_IRUSR == 0))
                    return
                if names and not stat.S_IMODE(info.st_mode) & stat.S_IWUSR:
                    # Empty dirs can be rmdir'd by their parent. Non-empty
                    # dirs require owner-write to unlink verified children.
                    problem("DIRECTORY_NOT_WRITABLE", path, info, repairable=True,
                            add_bits=stat.S_IWUSR)
                for part in names:
                    if len(findings) >= MAX_ISSUES:
                        break
                    walk(fd, part, path / part, depth + 1)
            finally:
                os.close(fd)
        elif kind == stat.S_IFREG:
            if info.st_nlink != 1:
                problem("HARDLINK_UNSAFE", path, info)
                return
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parentfd)
            except PermissionError:
                problem("FILE_UNREADABLE", path, info,
                        repairable=(stat.S_IMODE(info.st_mode) & stat.S_IRUSR == 0))
            else:
                try:
                    if _identity(os.fstat(fd)) != _identity(info):
                        raise ValueError("Quarantine file substituted")
                finally:
                    os.close(fd)
        elif kind != stat.S_IFLNK:
            problem("SPECIAL_FILE_UNSAFE", path, info)

    for scope, name, identity, row in targets:
        if row.get("move_status") in ("purged", "restored"):
            continue
        if row.get("tree_inventory") is None:
            unsealed = True
        scope_path = base / run_id / scope
        scopefd = _open_path(scope_path)
        try:
            actual = os.stat(name, dir_fd=scopefd, follow_symlinks=False)
            if _identity(actual) != identity:
                problem("ENTRY_IDENTITY_CHANGED", scope_path / name, actual)
                continue
            walk(scopefd, name, scope_path / name, 0)
        except FileNotFoundError:
            problem("ENTRY_MISSING", scope_path / name)
        finally:
            os.close(scopefd)
    return {"run_id": run_id, "identity": authority_context(),
            "issues": findings, "truncated": len(findings) >= MAX_ISSUES,
            "unsealed": unsealed,
            "note": "Diagnosis never authorizes purge or changes data."}


def repair_owner_directory(home: Path, roots: dict[str, Path], run_id: str,
                           relative: str) -> dict:
    """Owner-only, exact-path chmod u+r after fresh trusted-journal diagnosis.

    Callers must obtain a distinct user confirmation before invoking this.
    This never invokes sudo or follows a symlink, and never changes ownership.
    """
    if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError("Invalid repair target")
    report = diagnose_access(home, roots, run_id)
    match = next((item for item in report["issues"]
                  if item["relative"] == relative and item["repairable"]
                  and item["code"] in ("DIRECTORY_UNREADABLE", "FILE_UNREADABLE",
                                       "DIRECTORY_NOT_WRITABLE")), None)
    if match is None:
        raise ValueError("Target is no longer eligible for owner-only repair")
    base = roots.get("data", home / ".local/share") / "xdg-audit-quarantine"
    target = base / run_id / relative
    parentfd = _open_path(target.parent)
    try:
        before = os.stat(target.name, dir_fd=parentfd, follow_symlinks=False)
        expected_kind = (stat.S_IFREG if match["code"] == "FILE_UNREADABLE"
                         else stat.S_IFDIR)
        if (stat.S_IFMT(before.st_mode) != expected_kind or before.st_uid != os.getuid()
                or (expected_kind == stat.S_IFREG and before.st_nlink != 1)):
            raise ValueError("Target is not a safely repairable user-owned object")
        missing_bit = (stat.S_IWUSR if match["code"] == "DIRECTORY_NOT_WRITABLE"
                       else stat.S_IRUSR)
        if (stat.S_IMODE(before.st_mode) != int(match["mode"], 8) or
                stat.S_IMODE(before.st_mode) & missing_bit):
            raise ValueError("Target permissions changed after diagnosis")
        os.chmod(target.name, stat.S_IMODE(before.st_mode) | missing_bit,
                 dir_fd=parentfd, follow_symlinks=False)
        after = os.stat(target.name, dir_fd=parentfd, follow_symlinks=False)
        if _identity(before) != _identity(after):
            raise ValueError("Target changed during repair; inspect manually")
        return {"path": str(target), "old_mode": match["mode"],
                "new_mode": format(stat.S_IMODE(after.st_mode), "03o"),
                "purge_authorized": False}
    finally:
        os.close(parentfd)
