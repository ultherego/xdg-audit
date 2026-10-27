# Changelog

## 1.7.0-rc2 (unreleased)

- Exercise the real GUI MOVE/RESTORE/PURGE workflow through native controls and
  dialogs on GTK4/GTK3/Qt6/Tk under X11 and GTK4/Qt6 on native Wayland. Verify
  cancelled tokens, exact hashes, separate journals and untouched sentinels.
- Distinguish current AUR name matches from unlisted and unverified foreign
  packages using a bounded public index; never infer verified build origin.
- Add one-level AppImage discovery in apps/opt/XDG data roots, Cargo/Go/manual
  binary locations and configurable extra source directories in every GUI.
- Gate source archives on a real snapd VM lifecycle, including disabled parallel
  instances, fresh MOVE refusal and exact-namespace RESTORE/PURGE checks.
- Hide unavailable Flatpak/Snap tabs only when no leftover data was found;
  retain failed-source visibility and stable scope selection after rescanning.
- Fit GTK/Qt/Tk dialogs to content with 20 px internal padding, screen bounds,
  scrollable long messages and visible actions; preserve cancellation and tokens.
- Distinguish a healthy empty pacman foreign filter from failed queries while
  keeping native package database authorization strict.
- Validate raw package/Flatpak identifiers before case folding and reject
  malformed dpkg architecture qualifiers without retaining partial results.
- Report the native package database, unique installed package-name count and
  provider health in CLI/JSON, preserving the existing pacman JSON statistic.
- Require real Arch/pacman protection and quarantine lifecycle checks alongside
  Ubuntu/dpkg and Fedora/RPM, including refusal to MOVE installed-package data.
- Adopt the MIT License and include it in both source archive formats.
- Authorize native DEB/RPM quarantine using the OS-selected fresh installed
  database; APT uses dpkg. Incomplete dpkg states block mutation.
- Read bounded dpkg removal history, including compressed rotation, without
  overriding currently installed applications.
- Add the Snap user-data scope to CLI/GTK/Qt/Tk with exact instance IDs,
  strict complete inventory parsing and fresh namespace checks before MOVE.
- Recognize version/architecture AppImage aliases, portable-data names and
  safe direct launcher targets without running images or desktop commands.
- Gate archives and releases on native Ubuntu/dpkg and Fedora/RPM lifecycle CI.

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
- Keep fully installed dpkg packages protective even when their desired
  selection is deinstall/purge; the requested action is not proof of removal.

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
  applications ACTIVE on Debian/Fedora-derived systems. MOVE now uses the
  actual native database, with the same quarantine safety checks.

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
