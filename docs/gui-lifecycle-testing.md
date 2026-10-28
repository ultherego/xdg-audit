# Automated GUI lifecycle verification

`scripts/gui_lifecycle_smoke.py` drives the actual GTK4, GTK3, Qt6 or Tk
application using native row controls, action buttons and confirmation dialogs.
It creates its own temporary HOME and never accepts a path to existing user
data. Run as a regular user; the normal root guard remains active.

By default, only installed-application inventory is synthetic. The scan, fresh pre-MOVE
inventory check, MOVE, journal writes, SHA-256 inventory, RESTORE and PURGE use
the production implementation. Native pacman/dpkg/RPM and snapd inventories
remain covered by separate real-provider CI jobs.

CI additionally enables `--device-revalidation`. That mode supplies explicit
synthetic Btrfs metadata and renumbers a disposable sealed legacy journal.
It drives cancelled `REVALIDATE`, confirmed `REVALIDATE`, cancellation of the
independent subsequent PURGE, and final explicit PURGE. The report identifies
the filesystem evidence as synthetic; actual unmocked Btrfs mount/UUID behavior
is required in a separate job. See [device identity verification](quarantine-device-identity.md).

Each run verifies:

1. The disposable application is UNKNOWN and requires separate UNCERTAIN and
   MOVE confirmations. The initial scan creates no quarantine.
2. Typing MOVE and pressing Cancel changes no source bytes and creates no journal.
3. Confirming MOVE creates exactly one journal for the selected fixture and
   preserves every nested path and file hash. RESTORE returns identical data
   and changes that run's history to RESTORED.
4. A second MOVE creates a distinct run. Typing PURGE and pressing Cancel
   leaves its payload and journal bytes unchanged after the real preview.
5. Confirming PURGE deletes only the selected payload and records PURGED,
   retaining the earlier RESTORED history. Protected session data and an
   unrelated sentinel retain their original bytes throughout the run.

The harness never replaces a dialog with an automatically accepted result.
It enters tokens and presses buttons on the real widgets. Unexpected dialogs,
missing controls, failed operations and timeouts fail the test. No existing
installation is removed, and automatic retention is not enabled.

## X11

With the selected toolkit and Xvfb already installed:

```fish
xvfb-run -a -s '-screen 0 1600x1000x24' python3 scripts/gui_lifecycle_smoke.py --backend gtk4
xvfb-run -a -s '-screen 0 1600x1000x24' python3 scripts/gui_lifecycle_smoke.py --backend gtk3
xvfb-run -a -s '-screen 0 1600x1000x24' python3 scripts/gui_lifecycle_smoke.py --backend qt6
xvfb-run -a -s '-screen 0 1600x1000x24' python3 scripts/gui_lifecycle_smoke.py --backend tk
```

## Native Wayland

With Weston and the selected toolkit's Wayland support already installed:

```fish
python3 scripts/gui_wayland_smoke.py --backend gtk4 --lifecycle
python3 scripts/gui_wayland_smoke.py --backend qt6 --lifecycle
```

The wrapper creates a private runtime directory and starts headless Weston
without XWayland. It removes DISPLAY, forces native toolkit backends and
requires both a Wayland surface trace and successful lifecycle completion.
The child also verifies the toolkit's actual display backend.
Qt uses its compose input context inside this harness because headless Weston
has no keyboard seat; Qt 6.4's compositor input context can otherwise crash
while drawing a text cursor. Native Wayland rendering and real confirmation
widgets remain required. The installed application's input settings are untouched.

The lifecycle check also verifies that the Tk quarantine actions are mapped and
clickable. They wrap into three columns so Restore remains visible in its pane.

## CI evidence and scope

CI requires four X11 cycles and two native Wayland cycles before source
archives can build. JSON artifacts identify the backend, actual session,
synthetic inventory, tested commit, passed checks and disposable file hashes.
They contain no user HOME paths. The source archive uses an explicit manifest
and excludes generated reports.

These automated checks cover the product workflow on Xvfb/Weston. They do not
establish independent security review or complete GNOME, KDE Plasma or Xfce
desktop-session acceptance. The owner's previously completed GUI acceptance
remains recorded in the release checklist and does not need repeating.
