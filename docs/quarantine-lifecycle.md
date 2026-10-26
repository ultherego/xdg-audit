# Quarantine lifecycle (experimental)

Available on the feature branch only. Existing `--remove` and `--restore`
are unchanged.

## Commands

```sh
python3 xdg_audit.py --list-quarantine
python3 xdg_audit.py --quarantine-info 20261025-103000-123456
python3 xdg_audit.py --purge 20261025-103000-123456 --dry-run
python3 xdg_audit.py --purge-expired --retention-days 30
```

After reviewing the preview, interactive deletion is:

```sh
python3 xdg_audit.py --purge 20261025-103000-123456
python3 xdg_audit.py --purge-expired --retention-days 30 --execute
```

The program requires a TTY and an exact `PURGE` confirmation for
destructive operations. Expired-run deletion is never automatic.
A run's `manifest.json` is retained after its objects are deleted, with
each entry marked `purged`. To test safely, use an isolated disposable
`--home` and data created only for testing.

## Safety rules

- Only v3 journals with valid inode/device/file-type identities are eligible.
- Each source/destination must match the expected XDG root and run path.
- The run may not contain untracked top-level objects.
- Nested mounts, special files, foreign-owner objects and regular files with
  multiple hard links are rejected.
- An object whose inode has been substituted is not deleted.
- The implementation uses Linux directory descriptors and does not traverse
  symbolic links.
- Interrupted `purging` journal states may be resumed after verification.
- A corrupt journal blocks removal. A stale, legacy v2 journal can still be
  restored by the legacy restore mechanism, but cannot be purged here.

## Limitations before release

The current v3 journal records top-level object identity, not a cryptographic
inventory of all nested content. A modified directory with the same top-level
identity can still contain new nested data. Do not treat this feature as
a secure shredder or as protection against concurrent writers modifying a
quarantined directory. Keep the feature in draft until additional adversarial
tests and nested-content protections are complete.

The GTK/Qt/Tk frontends do not expose purge or retention controls yet.
The retention threshold applies to CLI preview and manually triggered cleanup,
not a scheduled background service.
