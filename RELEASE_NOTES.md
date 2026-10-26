# xdg-audit 1.7.0-rc2 — release preparation

**Unreleased candidate (main).** The latest published release remains
`v1.7.0-rc1`. These notes describe the current code and do not announce a new tag.

## New since v1.7.0-rc1

- Hide unavailable Flatpak/Snap tabs only when no leftover data exists, with
  stable scope selection and automatic fallback after a completed scan.
- Content-sized GTK/Qt/Tk dialogs with 20 px internal padding, bounded long
  messages, accessible actions and unchanged confirmation/cancellation semantics.
- Healthy empty foreign-package filters distinguished from failures, with a
  live pacman query check in native CI.
- Strict raw Flatpak/native identifiers and complete dpkg architecture qualifiers;
  malformed fresh query results block MOVE and preserve selected data.
- Native database name, unique package-name count and health in CLI reports,
  plus compatible JSON statistics without double-counting dpkg aliases.
- Real Arch/pacman inventory and lifecycle coverage alongside Ubuntu and Fedora,
  including ACTIVE protection of installed-package data before MOVE.
- MIT license, included in source archives.
- Native MOVE authorization on APT/dpkg and RPM systems, `ID`/`ID_LIKE`
  selection, dpkg removal history, and refusal when package configuration is incomplete.
- The `~/snap` scope in the CLI and all GUIs, exact instance identifiers,
  fresh installation checks before MOVE, and shared RESTORE/PURGE handling.
- Static AppImage detection using versioned filenames, architecture suffixes
  and safe launchers referencing existing images, without executing code.
- Required native-database and quarantine lifecycle tests on Ubuntu and Fedora in CI.
- Eight real `SIGKILL` recovery tests for MOVE/RESTORE/PURGE and journal-write
  fault tests for ENOSPC/EACCES.
- Retrying a completed RESTORE reconciles the journal using the original inode.
  Counts include completed renames even when a later synchronization fails.
- Source archives contain only an explicit list of project files. Desktop
  registration uses atomic writes without following symlinked parent directories.
- Real native dpkg/RPM lifecycle tests without pacman. CI also tests launching
  from a path containing special characters and displaying a full-disk error in GTK.
- Complete quarantine lifecycle with separately confirmed `PURGE`, recursive
  SHA-256 inventory, file identity checks and v3 journals.
- Safe recovery after interruption and a separate `ADOPT` action for current
  contents when inventory creation failed during MOVE.
- Limited current-user permission repair: `ACCESS` on an exactly verified
  quarantined object, followed by a fresh preflight and separate `PURGE`.
- Historical `PURGED` / `RESTORED` entries, manual cleanup of completed history
  and optional retention through a systemd user timer. Automatic deletion is
  disabled by default.
- Explanations in GTK/Qt/Tk and worker-thread operations that keep the main
  interface responsive while calculating SHA-256 inventories.
- English and Polish UI localization, native GTK/Qt testing on Wayland
  (Weston), and a complete synthetic E2E test. Repository documentation is English.
- Provider health for pacman, foreign packages (AUR **or** local), Flatpak,
  Snap, AppImage, manual binaries, `/opt`, dpkg and rpm.
  `--installed-sources` exposes read-only diagnostics.
- Protective, read-only npm global and pipx inspection in selected directories,
  without executing package code. These sources protect matching `CANDIDATE`
  data from MOVE; missing hints do not prove uninstallation.
- Canonical Flatpak application IDs separated from display names;
  `flatpak_app_ids` counts actual IDs.
- Unmeasured sizes represented by `null` in `--quick --json`, with explicit
  `evidence_level` and `orphan_ownership_verified` fields.
- Installed dpkg/rpm packages protect data as ACTIVE. MOVE uses the native
  database selected through `os-release`.
- Additional regressions for interruption before/after deletion, inaccessible
  directories, unreadable files, symlinks, hardlinks, replaced inodes and invalid manifests.

## Product limits

- Scanning is read-only. `CANDIDATE` does not establish verified orphan
  ownership; inspect the data before MOVE.
- MOVE requires a healthy, current native `pacman`, `dpkg-query` or `rpm`
  inventory selected by OS family. Unknown systems, failed providers and
  incomplete dpkg configuration block the operation.
- AUR packages installed through pacman appear in `pacman -Qq`. AUR origin
  is not distinguished from other foreign packages.
- Flatpak and Snap provide installation evidence. AppImage and manual-binary
  discovery do not cover every possible location.
- The system `pkexec` self-test does not authorize deleting root-owned data.
  Actual quarantine permission repair is restricted to verified objects owned
  by the current user.
- `PURGE` does not securely overwrite storage. Internal limits and access
  failures block the operation.
- This remains a release candidate. The owner confirmed the tested GUI works
  on 2026-10-26; separate GNOME/KDE/Xfce sessions were not documented.
  Independent security review, additional desktop coverage and final release
  artifact acceptance remain open.

## Verification

```sh
python3 -m unittest discover -s tests -q
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
python3 scripts/build_archives.py --output-dir dist
cd dist
sha256sum -c SHA256SUMS
cd ..
```

See the [release checklist](docs/release-readiness.md),
[installation-source contract](docs/installation-source-support.md), and
[desktop installation, update and removal guide](docs/desktop-installation.md).
