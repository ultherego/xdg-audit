# Project roadmap

[Back to README](../README.md) · [Release checklist](release-readiness.md) · [Current evidence](verification-2026-10-28.md)

Status checked on **2026-10-28**. Source version is **`1.7.0-rc2`**; the latest
published prerelease remains **`v1.7.0-rc1`**. The owner's previously tested
GUI environment remains accepted. The owner subsequently confirmed all three
remaining P0 gates and authorized the remaining release work; the
[acceptance record](owner-acceptance-2026-10-28.md) records that report and its
limits. This roadmap tracks the remaining publication work.

## Verified foundation

- [PR #43](https://github.com/ultherego/xdg-audit/pull/43) and
  [merged main CI](https://github.com/ultherego/xdg-audit/actions/runs/40736967093)
  passed all 22 build/test jobs with 440 regressions per supported interpreter.
  Both 160-file source archives matched the accepted application tree; native
  package checksums and all nine GUI lifecycle reports were verified.
  Known partial v2 adoption and independently verified empty-history cleanup
  retain separate ADOPT, PURGE and HISTORY consent.
- [PR #42 desktop integration](verification-data/2026-10-28/desktop-sessions.md)
  passed all 22 build/test jobs with 418 regressions per supported interpreter.
  Actual GNOME 46, Plasma 5.27 and Xfce 4.18 software-rendered sessions passed
  the native GUI lifecycle. The owner separately accepted keyboard/theme checks.
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

## Owner-accepted P0 gates

| ID | Work | Status |
|---|---|---|
| P0-01 | Affected old quarantines and device-identity issue | Owner confirmed working and accepted |
| P0-02 | Independent security review by another person | Owner confirmed completed and accepted |
| P0-03 | Keyboard/theme acceptance in GNOME/Wayland, Plasma/Wayland and Xfce/X11 | Owner confirmed all accepted |

These are owner attestations, not additional checks performed by automation.
The [record](owner-acceptance-2026-10-28.md) identifies the conversation's
application baseline without inventing a reviewed SHA, reviewer identity,
desktop versions or a forensic explanation of the old device change.

## 2026-10-29 post-acceptance changes

- [PR #45](https://github.com/ultherego/xdg-audit/pull/45) fixed the broad AppImage probe failing on unrelated root-owned /opt/containerd (mode 0711). The owner reported appimage: ok, zero discovered images and 460 passing local regressions.
- [PR #46](https://github.com/ultherego/xdg-audit/pull/46) moved GTK/Qt quarantine commits off the GUI thread with activity dialogs. [PR CI](https://github.com/ultherego/xdg-audit/actions/runs/40896756722) passed and the owner confirmed the progress UI works.
- The [RC2 tag attempt](https://github.com/ultherego/xdg-audit/actions/runs/40896316642) was correctly rejected because the release request still pins the previously accepted application SHA 6f86e1994515febf1722befcf96c9e61bd858357, while xdg_sources.py changed afterward.
- Successful PR CI and owner testing of one GUI feature do not automatically replace acceptance of the complete release baseline. Verify current main CI, inspect and approve its exact application tree, then update the pinned release request with recorded owner approval before retrying RC2.
- [Main CI and artifact verification](rc2-candidate-2026-10-29.md) now identify
  `ed7129f41c5270cfcd195e05b607d3ce9ccf4c81` as the concrete RC2 proposal:
  22 successful build/test jobs, 460 regressions and exact source/native bytes.
  The draft request update awaits owner acceptance of this baseline.

## Remaining release gates

| ID | Work | Responsible party | Completion evidence |
|---|---|---|---|
| P1-01 | Final release commit and artifact acceptance | Maintainer and owner | Clean pinned SHA, green CI, inspected source/native packages, checksums and privacy record |
| P1-02 | Confirm production signing configuration | Owner with repository secret access | Dedicated key/fingerprint configured and checked through the publication workflow; rehearsal alone is insufficient |
| P1-03 | Publish and accept RC2 | Release work authorized; gated workflows and owner RC acceptance | New version tag, release assets, signed repository results and RC acceptance |
| P1-04 | Stable release after RC acceptance | Owner release decision and gated workflows | Resolved blockers, accepted RC and successful stable publication |

## Execution order

1. Preserve the accepted application bytes while preparing release documentation
   and automation. The committed release request pins that baseline; the tag
   workflow rejects a changed packaged runtime rather than silently extending
   the owner's existing acceptance.
2. Confirm the production secrets and fingerprint described in
   [Native packages](native-packages.md), without exposing private keys in
   issues, logs or source. Optional AUR setup additionally requires its account
   SSH credential and verified host key.
3. Select the exact release commit. Reconcile
   README, CHANGELOG, RELEASE_NOTES and checklist with that commit; inspect its
   own artifacts, hashes, license, paths and package installation lifecycle.
   Earlier successful artifacts do not establish a later release's contents.
4. After green main CI, process the committed RC2 request through the tag
   workflow. It probes an existing signer before creating the immutable tag.
   Check source, DEB/RPM/Arch assets and production
   signed APT/RPM repositories. AUR publication is optional and final-only.
5. Record owner RC acceptance and address any findings. Publish stable only
   after the RC and remaining P0/P1 gates are accepted.
6. Keep the evidence ledger and checklist linked to the actual accepted
   commits, jobs and artifacts. Re-run affected checks after subsequent fixes.

The accepted P0 checks do not need repeating for unchanged application code.
Production keys must be configured from the owner's trusted computer and are
never generated by release automation. Missing or unusable signing configuration
blocks tag creation and produces a public preflight report without key data.

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
