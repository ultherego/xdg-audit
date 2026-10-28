# v1.7.0 — Release readiness checklist

**Status:** stabilization on `main` (source version `1.7.0-rc2`).
The latest published tag/release is `v1.7.0-rc1`.
Publishing a new release or stable tag requires a separate release decision.

Evidence needed to close open items is defined in the
[P0/P1 validation protocol](release-verification-evidence.md).
A checked item requires a linked result; adding a script or test alone does
not demonstrate that it ran.

Results from 2026-10-26: [verification record](verification-2026-10-26.md).
Latest safety/GUI results: [2026-10-28 verification](verification-2026-10-28.md).
Current priorities: [project roadmap](project-roadmap.md).

## 1. Safety (P0)

- [x] Descriptor-based access to quarantine, manifests and child directories,
  without following symlinks.
- [x] Recursive SHA-256 inventory and inode verification before PURGE.
- [x] Refusal of automatic changes with unknown ownership/device identity,
  with separate `ACCESS`, `ADOPT` and `PURGE` confirmations.
- [x] Journal-write, partial-deletion recovery, path replacement, collision
  and outside-quarantine sentinel tests.
- [x] Regressions for directories without read, write or search permission.
- [x] Real process interruption at eight MOVE/RESTORE/PURGE checkpoints using
  `SIGKILL`, with synthetic data only, followed by restart recovery —
  [results and scope](verification-2026-10-26.md).
  This covers process termination, not power loss or kernel failure.
- [ ] Independent security review of the latest changes by a second person —
  [review map and required report](security-review-guide.md).
- [ ] Investigate the reported device-number change in an existing quarantine
  run. The inode and type match, but identity verification still refuses PURGE.
  Read-only filesystem diagnostics, persistent Btrfs bindings and explicit
  exact-inventory `REVALIDATE` are implemented with an actual-remount CI gate.
  The owner's specific filesystem/cause and affected run remain unverified.
  [Recovery contract](quarantine-device-identity.md); independent review remains open.

## 2. CI and main protection (P0)

The active `Protect main` ruleset requires a PR, blocks force-push and deletion
of `main`, and requires Python, Xvfb GUI, benchmark and source-archive checks.

The source archive job depends on Python, GUI, Wayland, full desktop sessions, benchmark, quarantine,
native-source, live-snapd, native-package and actual-Btrfs jobs. Archive success therefore
also requires Wayland, isolated quarantine E2E, native Arch/Ubuntu/Fedora,
actual snapd, Btrfs remount/revalidation and DEB/RPM/Arch package tests, even when those contexts are not
listed directly in the ruleset. Release publication additionally requires
the disposable repository-publication rehearsal.

- [x] Python 3.10–3.14 and native GUI checks (Xvfb/Weston).
- [x] Complete software-rendered GNOME 46/Wayland, Plasma 5.27/Wayland and
  Xfce 4.18/X11 integration with actual session/shell/settings processes,
  native GUI lifecycle and unchanged hashes/sentinels —
  [exact target and retained reports](verification-data/2026-10-28/desktop-sessions.md).
  This does not close the physical-keyboard/manual-theme acceptance below.
- [x] Isolated MOVE → RESTORE lifecycle and safety-failure tests.
- GUI lifecycle automation also exercises real row controls, confirmation
  dialogs and production file operations with synthetic installed inventory:
  [commands, assertions and scope](gui-lifecycle-testing.md). CI results must
  pass before this supplies evidence for the exact commit; real desktop-session
  acceptance below remains separate.
- [x] Archive and release gates depend on Wayland, E2E, native-source,
  live-snapd and native-package checks; release also requires publication
  rehearsal — [PR #35 results](https://github.com/ultherego/xdg-audit/actions/runs/40515908169).
- [ ] **Optional:** list Wayland and E2E directly in the ruleset so administrators
  can see them individually as required checks. This requires GitHub
  administrative permission; do not bypass access controls.

## 3. Linux and GUI compatibility (P0)

**Owner confirmation (2026-10-26):** the owner tested the GUI and confirmed all
functions checked in that environment worked. Acceptance of that environment
is complete and does not require repeating the same tests.
The following matrix concerns additional, separately identified environments.

- [x] Functional GUI tests in the owner's environment — owner confirmation.
- [x] Requested dialog polish: complete Settings editor corners in light/dark
  themes, including focus/scroll states; Return/keypad Enter token confirmation,
  rejection of empty/incorrect PURGE/HISTORY and unchanged multiline newlines.
  [Exact-commit CI and visual screenshot results](verification-2026-10-28.md);
  the [automated scope](gui-lifecycle-testing.md) retains the separate physical
  keyboard/full-desktop limits.
- [ ] GNOME/Wayland — complete scan, restore and PURGE workflow.
- [ ] KDE Plasma/Wayland — the same workflow with system-theme integration.
- [ ] Xfce/X11 — startup and workflow through Tk/GTK.
  [Prepared session protocol and evidence requirements](desktop-acceptance.md).
- [x] Native pacman, APT/dpkg and RPM: MOVE verifies the OS's own database.
  Arch/Ubuntu/Fedora native protection and lifecycle tests are mandatory before
  CI can build archives. Arch validates the package-manager family used by
  CachyOS, with real regular-user inventories rather than synthetic package lists.
- [x] Real snapd inventory and lifecycle with local metadata-only fixtures,
  a disabled parallel instance, stale-row MOVE refusal and exact-namespace
  MOVE/RESTORE/PURGE with unchanged bytes and sentinel —
  [snapd 2.77.1 results](https://github.com/ultherego/xdg-audit/actions/runs/40414152100/job/121892105511).
- [x] Full-disk and permission-error handling: engine ENOSPC/EACCES tests,
  no data overwrites, and a native GTK ENOSPC message smoke test —
  [results](verification-2026-10-26.md). Physical storage exhaustion and
  separate error acceptance on every desktop remain outside this evidence.

## 4. Publication (P1)

- [x] **MIT license:** the owner delegated license selection on 2026-10-26.
  Full text in [LICENSE](../LICENSE), also included in source archives.
- [x] README, CHANGELOG and RELEASE_NOTES describe RC2. All repository
  documentation is English; Polish is application localization only.
- [x] Review existing screenshots, neutral paths and source-archive inputs;
  exclude incidental checkout files —
  [scope and results](verification-2026-10-26.md). Final published artifacts
  still require acceptance before release.
- [x] Document and test user installation, update and desktop-registration
  removal (`install_desktop.py` currently points to the existing checkout) —
  [instructions and tests](desktop-installation.md).
- [x] Native package and tag pipelines are implemented:
  [builds, trust tests and owner setup](native-packages.md),
  [validated results](https://github.com/ultherego/xdg-audit/actions/runs/40515908169).
  Production publication requires the dedicated signing key/fingerprint; AUR
  additionally needs its account key and verified SSH host key.
- [ ] Configure production package signing and optionally AUR publication.
- [ ] Publish a **new RC** after acceptance, then consider a stable release.

## 5. Application installation sources

Application inventory covers Arch/AUR/foreign, Flatpak, Snap, AppImage,
manual binaries, APT/dpkg and RPM. MOVE requires explicit consent and a
healthy native package database.
AUR name availability is informational; build origin remains unverified.
AppImage/manual-binary discovery includes additional conventional directories
and validated user-configured source paths in all GUI backends.
Adapter behavior and safety conditions:
[installation-source-support.md](installation-source-support.md).
