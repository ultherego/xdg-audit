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
