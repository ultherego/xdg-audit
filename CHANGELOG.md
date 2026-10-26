# Changelog

## 1.7.0-rc2 (unreleased)

- Verify interruption recovery with eight real SIGKILL checkpoints covering
  MOVE, RESTORE, partial PURGE and abandoned journal temporary files.
- Anchor all MOVE/RESTORE journal writes; preserve the original ENOSPC/EACCES
  error instead of masking it with a duplicate descriptor close.
- Reconcile an interrupted completed RESTORE only when the original inode is
  present; keep counts accurate after a rename followed by a sync failure.
- Build source archives from an explicit file manifest, excluding incidental
  reports, credentials, symlink targets and custom output directories.
- Harden per-user desktop registration against symlinked ancestors, linked
  assets and interrupted writes; correctly escape special Exec path characters.
- Add real dpkg scan/MOVE-refusal coverage and a real Gio fixture-launch smoke;
  exercise the GTK disk-full error path without permitting deletion.
- Validate complete Flatpak columns and dpkg status tuples, discarding partial
  results on malformed records.

- Fail closed on symlinked ancestor directories when inspecting manual binaries,
  AppImages, and /opt-style hints; cap large directory listings before relying
  on their evidence, without running any installed application.
- Read-only npm-global and pipx directory-name evidence protects applications
  installed outside pacman. Missing/unsafe source paths never authorize removal.
- Keep canonical Flatpak application IDs separate from display names and report
  the number of unique installed Flatpak IDs without double-counting aliases.

- Introduce health-aware installed-application providers: pacman and foreign
  packages (AUR or local), Flatpak, Snap, AppImage, manual binaries and
  shallow /opt installation hints. Failed probes never imply uninstallation.
- Expose read-only `--installed-sources` health/count diagnostics.
- Add installed-only dpkg-query and RPM probes to keep currently installed
  applications ACTIVE on Debian/Fedora-derived systems. Non-Arch MOVE stays
  blocked pending separate security validation.

- Finalize manual PURGE with v3 SHA-256 inventory, fail-closed preflight,
  inode checking and resumable journal states.
- Add GUI-guided `ACCESS → ADOPT → PURGE` recovery; no demo buttons in GUI
  and no implicit privileged file operations.
- Support explicit owner-only repairs for unreadable files, directories,
  non-writable nonempty directories and missing directory-search permission;
  preserve separate confirmation for each modification.
- Add completed-history cleanup, optional user-scoped retention with default
  auto-delete disabled, and async GTK/Qt/Tk PURGE previews.
- Cover crashes immediately before and after destructive unlink with synthetic
  journal-recovery regressions.
- Document optional native Polkit CLI smoke separately from production file
  authorization, and plan package-source detection beyond pacman.
- Add an explicit release-readiness checklist; no release tag was created.

- Add isolated end-to-end quarantine/restore validation against disposable XDG data, including SHA-256 integrity, collisions, inode substitution and failure-closed checks.
- Require successful end-to-end verification before building release archives.

- Complete Polish/English translations across GTK, Qt6 and Tk confirmation dialogs, quarantine and restore, report export and status messages.
- Translate known classification evidence for display in the inspector and report comparison; keep original evidence untouched in JSON and the core engine.
- Add tests for translation catalog coverage, message placeholders, confirmation tokens, path preservation and language switching.

- Quarantine journal v3 records source file identity (device, inode, type) before moving an entry.
- Restore fails closed if a v3 entry was replaced or its identity is missing/corrupt.
- Older v1/v2 manifests remain restorable under their original no-overwrite safeguards.
- Six new regression tests cover identity substitutions, intact and legacy restores, and interrupted moves.
- Headless Weston smoke tests require GTK4 and Qt6 to create native Wayland surfaces without an X11 fallback.


## 1.7.0-rc1

- More conservative classification and source-specific evidence, including high-value user-data safeguards.
- Symlink-safe traversal of ancestor directories before sensitive quarantine and restore renames.
- Regression tests, synthetic benchmarks and native GUI smoke checks (GTK4, Qt6, Tk).
- No GUI layout changes, installers, permanent deletion, or automatic updates.

## 1.7.0-dev

- Linux renameat2 without destination overwrites.
- Single-pass reference matching in session configuration.
- Inspector open-location action.
- Python version-matrix CI and reproducible source archives.

Earlier changes remain available in Git history.
