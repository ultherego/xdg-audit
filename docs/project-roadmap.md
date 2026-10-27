# Project roadmap

[Back to README](../README.md) · [Testing and release status](testing-and-release-status.md)

The current priority is stabilizing **1.7.0**, with source version
`1.7.0-rc2`. This is the current work list as of **2026-10-27**; the detailed
acceptance criteria live in the [release-readiness checklist](release-readiness.md).

## Remaining work, in order

1. **Investigate the reported quarantine device-identity change.** An existing
   run records a different device number from the current object, while its
   inode and file type match. Detailed errors now expose those values, but
   PURGE remains blocked. Collect read-only filesystem/mount evidence and
   reproduce the change before choosing a recovery design. Matching inode
   numbers alone cannot prove that the object is unchanged; do not edit the
   journal or bypass identity checks.
2. **Obtain an independent security review** of the latest quarantine and
   publication changes by a second person. Automated regression results do
   not close this item.
3. **Complete additional desktop-session acceptance** on GNOME/Wayland,
   KDE Plasma/Wayland and Xfce/X11. The owner's already accepted environment
   does not need to repeat its completed tests. Headless CI coverage has a
   separate scope from full desktop-session acceptance.
4. **Configure production publication credentials.** The build, tag and signed
   repository pipelines are implemented and rehearsed. The owner must supply
   the dedicated package-signing key and fingerprint; AUR publication is
   optional and requires its own SSH credential and verified host key.
   Follow [Native packages](native-packages.md).
5. **Publish and accept a new release candidate**, then decide on the stable
   release. The latest published prerelease is still `v1.7.0-rc1`; current CI
   artifacts are not a newly published RC or production package repository.

Listing Wayland and end-to-end contexts individually in the main protection
ruleset is optional: the required archive gate already depends on them.

## Implemented foundation

- Installed-application inventory covers pacman/foreign, Flatpak, Snap,
  AppImage, manual binaries, npm/pipx, dpkg and RPM. MOVE rechecks native
  package evidence immediately before changes. AUR availability is
  informational and does not prove build provenance. See the
  [source support contract](installation-source-support.md).
- GTK, Qt and Tk provide quarantine lifecycle controls, configurable source
  directories, visible settings editors and detailed refusal messages.
  See [CLI usage](cli.md) and [Quarantine lifecycle](quarantine-lifecycle.md).
- Actions builds native DEB/RPM/Arch packages and source archives after
  application and GUI gates. Disposable repository tests cover signing,
  installation, upgrade, removal, tamper refusal and publication retries.
  See the [validated scope and results](testing-and-release-status.md).

Merged PR branches are maintained by the
[branch-cleanup workflow](https://github.com/ultherego/xdg-audit/actions/workflows/branch-cleanup.yml). It runs only
on `main`, preserves open-PR dependencies and changed branch heads, and uses
an atomic Git push with per-ref leases. Closed but unmerged PRs are retained
apart from the explicitly reviewed, commit-pinned PR #24 → #25 supersession.

The older [research roadmap](../RESEARCH_ROADMAP.md) is a historical review
after 1.4.8, not the current release checklist.
