# Quarantine lifecycle

New quarantine runs keep the v3 intent journal format for compatibility,
with an additional complete `tree_inventory` containing inode identities,
SHA-256 file hashes and symlink destinations. All destructive operations
require valid manifests. No delete operation follows symbolic links.

## Inspect and restore

```fish
python3 xdg_audit.py --list-quarantine
python3 xdg_audit.py --quarantine-info RUN_ID
python3 xdg_audit.py --restore RUN_ID
```

`--quarantine-info` reports the number of objects, recorded bytes, statuses
and which older entries need adoption. Restores remain non-overwriting.

## Manual purge

```fish
python3 xdg_audit.py --purge RUN_ID --dry-run
python3 xdg_audit.py --purge RUN_ID
```

The second command requires an interactive terminal and the exact token
`PURGE`. A preview alone never writes files. The journal is retained as a
`purged` tombstone. Repeating a completed purge does not delete more files.

For older v3 journals without the recursive inventory, purge is blocked.
To explicitly validate and bind what exists **now**, first inspect and then
adopt (current data might differ from the original snapshot):

```fish
python3 xdg_audit.py --quarantine-info RUN_ID
python3 xdg_audit.py --adopt-quarantine RUN_ID
python3 xdg_audit.py --purge RUN_ID --dry-run
```

Adoption requires typing `ADOPT`. It does not prove that the current content
is the same as when the item was first quarantined. Legacy v2 journals remain
restore-only and are not eligible for adoption or purge.

## Recovery after interruption

If a process was interrupted while writing a journal, a leftover
`.manifest-*.tmp` file may block purge until explicitly reviewed. The
recovery command verifies the run and removes only valid abandoned temporary
journal files, never the manifest or quarantined data:

```fish
python3 xdg_audit.py --recover-journal RUN_ID --dry-run
python3 xdg_audit.py --recover-journal RUN_ID
```

The second command requires a TTY and the exact `RECOVER` token.
Interrupted `purging` entries are resumable with the usual `--purge` after
reinspection. Legacy interrupted `moving` entries can be restored or
explicitly adopted if their destination exists.

## Retention

Default retention threshold: 30 days, **automatic cleanup disabled**.
No background process is created or enabled by scanning/quarantining.

```fish
python3 xdg_audit.py --purge-expired --retention-days 30
python3 xdg_audit.py --purge-expired --execute --retention-days 30
python3 xdg_audit.py --configure-retention 30
```

The first command is preview-only. The second asks for `PURGE` on an
interactive terminal. In GTK, Qt and Tk, the Quarantine tab exposes purge
of selected and expired runs and always asks for `PURGE`.

For an optional **user-scoped** systemd timer, enable the policy and install
the timer. Do not use `sudo`:

```fish
python3 xdg_audit.py --enable-retention
python3 scripts/install_retention_timer.py --install-only
python3 scripts/install_retention_timer.py --enable
systemctl --user status xdg-audit-retention.timer
```

`--enable-retention` requires the exact `ENABLE` confirmation.
The timer executes once daily with `Persistent=true` and a 10-minute
randomized delay. It executes `--automatic-purge`, which refuses to delete
unless the persistent automatic setting is true. Changing the setting does
not silently create or activate a timer.

To turn it off:

```fish
python3 xdg_audit.py --disable-retention
python3 scripts/install_retention_timer.py --disable
```

The installer writes user units at `~/.config/systemd/user/` (or under the
configured XDG_CONFIG_HOME). It uses the absolute script path at installation
time; reinstall if the repository is moved.

## Completed history and privacy

A successful full `PURGE` retains its small `manifest.json` audit tombstone
and records a UTC `purged_at` timestamp. The GUI lists such runs explicitly
as `PURGED`, distinct from `QUARANTINED`, `RESTORED` and `INCOMPLETE`.
A run whose metadata cannot be validated is marked `ERROR`; it is never
eligible for history cleanup.

The manifest is eligible for automatic removal **30 days after PURGE**, not
30 days after quarantine. Automatic history cleanup runs in the existing
user-scoped retention timer only when the explicit automatic-retention policy
has been enabled. Old tombstones without `purged_at` are **never** selected
for automatic history removal.

Manual metadata-only cleanup (the separate token is `HISTORY`):

```fish
python3 xdg_audit.py --cleanup-history RUN_ID --dry-run
python3 xdg_audit.py --cleanup-history RUN_ID
python3 xdg_audit.py --cleanup-expired-history
python3 xdg_audit.py --cleanup-expired-history --execute
```

In GTK, Qt and Tk you can see a distinct status for purged runs, remove
an individually completed operation's history, or clean up history past the
30-day cutoff. Each destructive GUI history operation requires the exact
`HISTORY` confirmation. Restored operations can have their histories
removed **manually**, but never through age-based automatic cleanup.

Incomplete, corrupted, inconsistent, or nonempty runs are always protected.
History deletion uses only `rmdir` on empty run/scope directories and removes
the manifest with an anchored `unlink`; it never recursively deletes files.

## GUI responsiveness during PURGE

GTK, Qt and Tk verify each selected quarantine run off the graphical event
loop, including the recursive SHA-256 inventory. The confirmation prompt
appears **after** verification. Slow checks must not freeze window rendering.
For large directories, GTK displays a spinner while verification is running.
The confirmed destructive operation also runs off the UI thread; a second
click is ignored while another quarantine operation is in progress.
All safety preflights are re-run before deletion, and failed operations
surface an explicit error instead of silently deleting anything.

When updating this software, restart the running application: an already
open GTK/Qt/Tk window will not load new Python code dynamically.

## Fail-closed behavior and boundaries

- Deletion is anchored to already-open directory descriptors.
- Before destructive work, inventories and object identity are revalidated;
  untracked files, changed bytes, inode substitutions, special files, nested
  mounts and unexpected hard links block purge.
- Interrupted `purging` states can be resumed with the original journal.
- A corrupt or unsupported journal cannot authorize deletion. If an item
  could not be inventoried immediately after quarantine, it is restore-only
  until explicitly adopted.
- The claimed saved-byte count represents file sizes, not physically freed
  disk blocks. A purge is **not** secure erasure on SSD/CoW filesystems.
- Like any user-scoped cleanup tool, it cannot fully protect against a
  malicious concurrent process running as the same Unix UID mutating the
  filesystem mid-operation. Stop affected applications before purging.

Run the isolated verification suite:

```fish
python3 -m unittest discover -s tests -q
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
```
