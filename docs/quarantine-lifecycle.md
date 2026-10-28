# Quarantine lifecycle

For a device-number-only refusal, see
[filesystem diagnosis and separately confirmed revalidation](quarantine-device-identity.md).

Journal reads and payload probes use nonblocking opens followed by descriptor
validation. A FIFO manifest or a regular file replaced by a FIFO is rejected
without waiting for a pipe writer. Listing and legacy restore share the same
bounded, user-owned regular-file journal reader; this does not authorize any
operation or relax inode, filesystem, ownership or content checks.

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
is the same as when the item was first quarantined.

Known `intent-journal-v2` runs can also be explicitly adopted, including
partial runs containing both moved and never-moved intents. A read-only
preview validates all original paths and the complete remaining quarantine
namespace. Its approval token binds that journal, current inodes, recursive
hashes and filesystem binding. Confirmation rechecks the evidence before an
atomic v3 conversion. The original v2 journal is retained as an unchanged JSON
object in the `legacy_adoption` receipt; only remaining quarantine objects
become live v3 items. Original source paths are never changed by adoption.
Unused empty scope directories may be removed with `rmdir` only.

The receipt explicitly records no historical identity proof and no PURGE
authorization. Adopted v2 runs remain blocked from automatic deletion.
Manual PURGE needs a fresh preflight and its own token; RESTORE also remains
available. Unknown formats, mismatched run IDs, identity-bearing downgraded
journals, untracked content, nested mounts and unsafe objects remain blocked.

```fish
python3 xdg_audit.py --adopt-quarantine RUN_ID --dry-run
python3 xdg_audit.py --adopt-quarantine RUN_ID  # ADOPT; does not delete payloads
python3 xdg_audit.py --purge RUN_ID             # Separate PURGE
python3 xdg_audit.py --cleanup-history RUN_ID   # Separate HISTORY after completion
```

## Explaining blocked PURGE and safe access recovery

A failure such as `[Errno 13] Permission denied: 'pkg'` means Linux refused
a read while xdg-audit was inventorying quarantine data. The path may refer
to a directory with mode `111`: it can be entered but not listed.
Failure to inspect **blocks deletion**, not restoration.

The normal GUI path starts at **Delete permanently…**. When the verified
PURGE preview finds an inaccessible user-owned object, GTK/Qt/Tk run
**Check access…** automatically and explain its exact path, owner,
current permissions and proposed change. No test buttons are shown in
the application.

After each approved `ACCESS` change, the GUI diagnoses the run again,
offering another individually approved correction if a different object
still blocks access. This includes:

- directories without owner-read (`111 → 511`),
- directories without owner-search/execute permission (`400 → 500`, or
  `000 → 500` if both owner read and search are absent),
- user-owned, single-linked regular files without owner-read (`000 → 400`),
- **nonempty** directories that can be read but lack owner-write, required
  to unlink their children (`511 → 711`).

The last case is checked **before permanent deletion**, so a readable
but undeletable tree never silently proceeds into a partially completed
PURGE. All changes apply only to the exact diagnosed inode inside a
validated quarantine journal, never arbitrarily chosen paths. Every
change requires a separate `ACCESS` confirmation.

If the original post-MOVE SHA-256 inventory was unavailable, the same GUI
flow next asks for a separate `ADOPT` confirmation. This binds **current**
contents, which might differ from the original snapshot. The GUI then
repeats the PURGE preflight and requests its original, independent `PURGE`
confirmation before deleting anything. Rejecting any confirmation stops
the sequence without continuing on its own.

Equivalent CLI actions remain available:

```fish
python3 xdg_audit.py --diagnose-access RUN_ID
python3 xdg_audit.py --repair-access RUN_ID --repair-target cache/Shelly/lib32-gstreamer/pkg
python3 xdg_audit.py --adopt-quarantine RUN_ID  # Only if inventory is unsealed
python3 xdg_audit.py --purge RUN_ID --dry-run
python3 xdg_audit.py --purge RUN_ID
```

The diagnostic identity comes from `os.getuid()` and the OS account
database; it also reports `XDG_SESSION_ID`, session type, user groups and
whether `pkexec` exists. This does *not* predict which account a Polkit
agent will require to authorize privileged actions: only the system's
Polkit policy/agent decides that at authentication time. **This release
does not ship a privileged helper** and never performs a root-backed repair.
Foreign-owner data and integrity violations remain protected. A future
privileged repair implementation must use an audited, system-installed,
root-owned helper with narrowly scoped actions; running scripts directly
from a user-writable clone through `pkexec` is unsafe.

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
Runs with a device-revalidation receipt remain blocked from automatic
deletion. Remove them only through a separately confirmed manual PURGE.

To turn it off:

```fish
python3 xdg_audit.py --disable-retention
python3 scripts/install_retention_timer.py --disable
```

The installer writes user units at `~/.config/systemd/user/` (or under the
configured XDG_CONFIG_HOME). It uses the absolute script path at installation
time; reinstall if the repository is moved.

## Completed history and privacy

The controls have different purposes:

| Control | What it removes | Eligibility / confirmation |
|---|---|---|
| Purge permanently | Remaining data in the selected quarantine run | Verified inventory and explicit `PURGE` |
| Purge expired data | Data in runs older than the configured retention threshold (30 days by default) | The same fresh safety preflight and `PURGE`; age never bypasses validation |
| Clear all completed history | Journals and empty scope/run directories | Completed, empty v3 runs or independently verified empty v2 records; `HISTORY` |
| Approve current state | No payload data; records the current inventory | Explicit `ADOPT`; separate PURGE remains required |

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
python3 xdg_audit.py --cleanup-all-history               # Preview ALL terminal runs
python3 xdg_audit.py --cleanup-all-history --execute      # Requires HISTORY
python3 xdg_audit.py --cleanup-expired-history            # Only PURGED 30+ days ago
python3 xdg_audit.py --cleanup-expired-history --execute
```

In GTK, Qt and Tk you can see a distinct status for purged runs, remove
an individually completed operation's history, or use **Clear all completed
history…** for *all* verified `PURGED`, `RESTORED` and `COMPLETED` runs,
regardless of age. Each destructive GUI history operation requires the exact
`HISTORY` confirmation.

This manual all-history operation intentionally differs from the scheduled
30-day retention task. It does not alter the timer or enable automation.
If no history is eligible, the GUI explicitly explains that active and
incomplete runs are protected. Restored operations can have their histories
removed **manually**, but never through age-based automatic cleanup.

Known v2 records with no remaining quarantine objects are shown as `EMPTY`.
Their old moved/planned counters may be stale; manual history cleanup verifies
the actual empty namespace independently. It does not assert how missing data
was removed, touch original source paths, or make them eligible for automatic
history expiry. An unknown/corrupt journal remains blocked even when a folder
appears empty.

Incomplete v3, corrupted, inconsistent, or nonempty runs remain protected.
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
