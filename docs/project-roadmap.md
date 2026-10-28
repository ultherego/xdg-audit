# Project roadmap

[Back to README](../README.md) · [Release checklist](release-readiness.md) · [Current evidence](verification-2026-10-28.md)

Status checked on **2026-10-28**. Source version is **`1.7.0-rc2`**; the latest
published prerelease remains **`v1.7.0-rc1`**. The owner's previously tested
GUI environment remains accepted. This roadmap tracks the remaining work;
the checklist and linked evidence define completion.

## Verified foundation

- [PR #42 desktop integration](verification-data/2026-10-28/desktop-sessions.md)
  passed all 22 build/test jobs with 418 regressions per supported interpreter.
  Actual GNOME 46, Plasma 5.27 and Xfce 4.18 software-rendered sessions passed
  the native GUI lifecycle; physical keyboard/manual theme acceptance stays open.
- [PR #40 and its merged main commit](verification-2026-10-28.md) passed all
  19 build/test jobs, with 415 regressions on each supported Python version.
  Native provider, package, actual-Btrfs and disposable publication checks
  remain mandatory archive/release dependencies.
- Requested Settings editor corners are complete in the inspected GTK
  light/dark empty, focused and scrolled screenshots. Return/keypad Enter
  confirm tokens through existing validation; negative PURGE/HISTORY,
  cancellation and multiline-newline checks pass across the documented
  [GUI test scope](gui-lifecycle-testing.md).
- Device recovery requires exact inventory and separate REVALIDATE consent.
  Automatic retention cannot inherit that consent. FIFO substitutions in
  journals, hashing and permission inspection are rejected without hanging.
- Installed-application inventory covers pacman/foreign, Flatpak, Snap,
  AppImage, manual binaries, npm/pipx, dpkg and RPM. MOVE refreshes native
  evidence before mutation. AUR name availability does not prove provenance.
  See the [source support contract](installation-source-support.md).
- Source/native packages and signed-repository pipelines are implemented and
  rehearsed with disposable keys. Production publication remains pending.

## Open release gates

| ID | Work | Responsible party | Completion evidence |
|---|---|---|---|
| P0-01 | Diagnose the owner's existing quarantine device mismatch | Owner supplies read-only diagnostics; maintainer investigates | Exact affected run/filesystem, verified recovery or a justified refusal with remaining limits |
| P0-02 | Independent security review | A person other than the author | Named report pinned to a full SHA, findings, disposition and decision |
| P0-03 | GNOME/Wayland, Plasma/Wayland and Xfce/X11 acceptance | Testers with those actual sessions | Environment/SHA, workflow results, hashes, screenshots and reviewed evidence links |
| P1-01 | Final release commit and artifact acceptance | Maintainer and owner | Clean pinned SHA, green CI, inspected source/native packages, checksums and privacy record |
| P1-02 | Confirm production signing configuration | Owner with repository secret access | Dedicated key/fingerprint configured and checked through the publication workflow; rehearsal alone is insufficient |
| P1-03 | Publish and accept a new RC | Owner release decision and gated workflows | New version tag, release assets, signed repository results and RC acceptance |
| P1-04 | Stable release after RC acceptance | Owner release decision and gated workflows | Resolved blockers, accepted RC and successful stable publication |

## Execution order

1. Obtain read-only diagnostics for the affected owner run using the
   [device-identity recovery guide](quarantine-device-identity.md). Compare
   device, inode/type, filesystem/subvolume binding and exact inventory.
   Matching inode numbers alone never authorize recovery. Confirm REVALIDATE
   separately if eligible; PURGE/RESTORE still need their own authorization.
2. Pin a candidate SHA and hand the latest code to an independent reviewer
   using the [review map and required report](security-review-guide.md).
   Resolve findings with focused regressions and re-review changed areas.
3. Run the [desktop acceptance protocol](desktop-acceptance.md) in each named
   session, using disposable data and physical keyboard checks. Retain explicit
   failures/skips. The already accepted owner environment need not repeat its
   completed acceptance. Complete software-rendered GNOME/Plasma/Xfce session
   jobs now extend CI integration coverage; they do not close physical keyboard
   or manual theme/palette acceptance.
4. Confirm the production secrets and fingerprint described in
   [Native packages](native-packages.md), without exposing private keys in
   issues, logs or source. Optional AUR setup additionally requires its account
   SSH credential and verified host key.
5. After fixes and acceptance, select the exact release commit. Reconcile
   README, CHANGELOG, RELEASE_NOTES and checklist with that commit; inspect its
   own artifacts, hashes, license, paths and package installation lifecycle.
   Earlier successful artifacts do not establish a later release's contents.
6. Publish a new RC through the tag workflow after mandatory evidence and the
   owner release decision. Check source, DEB/RPM/Arch assets and production
   signed APT/RPM repositories. AUR publication is optional and final-only.
7. Record owner RC acceptance and address any findings. Publish stable only
   after the RC and remaining P0/P1 gates are accepted.
8. Keep the evidence ledger and checklist linked to the actual accepted
   commits, jobs and artifacts. Re-run affected checks after subsequent fixes.

Independent review, desktop testing and credential preparation can proceed in
parallel once their targets are pinned. Owner filesystem diagnostics, another
reviewer's decision, manual desktop acceptance and production keys cannot be
supplied by author automation.

## After release

- Monitor the weekly repository-metadata renewal workflow, the 30-day APT
  metadata validity window and signing-key expiry. Follow the documented
  renewal/recovery procedure rather than replacing immutable package versions.
- Ship fixes under new versions; retain publication receipts and trust checks.
- Evaluate broader fixture datasets, scan performance, accessibility and
  clearer error reporting as subsequent work. These are proposals rather than
  additional claims of completed acceptance.
- Listing Wayland and E2E contexts individually in the main ruleset is optional:
  the required archive gate already depends on them. A ruleset change needs
  verified GitHub administrative access.

Merged PR branches are maintained by the
[branch-cleanup workflow](https://github.com/ultherego/xdg-audit/actions/workflows/branch-cleanup.yml).
It runs only on `main`, preserves open-PR dependencies and changed heads, and
uses an atomic Git push with per-ref leases. Closed but unmerged PRs are
retained apart from the explicitly reviewed, commit-pinned PR #24 → #25
supersession. Verification queries the live Git remote; deletion is not repeated
when a branch has been recreated or the remote cannot be reached.

The older [research roadmap](../RESEARCH_ROADMAP.md) is a historical review
after 1.4.8, not the current release checklist.
