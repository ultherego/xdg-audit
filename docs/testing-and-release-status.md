# Testing and release status

[Back to README](../README.md) · [Remaining work](project-roadmap.md)

Status checked on **2026-10-28**. Latest exact-commit results and artifact
hashes: [verification record](verification-2026-10-28.md).

The [GUI lifecycle harness](gui-lifecycle-testing.md) exercises real
MOVE/RESTORE/PURGE controls and dialogs on disposable data, including cancelled
confirmations, exact file hashes and retained history. Installed inventory is
synthetic in this harness; native provider CI remains separate.

The unreleased development version on `main` is **`1.7.0-rc2`**. The most recent tagged prerelease is **[v1.7.0-rc1](https://github.com/ultherego/xdg-audit/releases/tag/v1.7.0-rc1)**.

GitHub Actions covers:

- Python 3.10–3.14 regressions and a synthetic scan benchmark.
- GTK4/GTK3/Qt6/Tk layout and MOVE/RESTORE/PURGE workflows under Xvfb,
  plus GTK4/Qt6 workflows on native Wayland with headless Weston.
- Isolated quarantine lifecycle, real `SIGKILL` recovery checkpoints,
  permission failures, GTK disk-full handling and Gio desktop launching.
- Actual Btrfs remount/device-number changes, persistent FS/subvolume UUID
  checks, snapshot refusal, explicit revalidation and separate PURGE/RESTORE.
  [Contract and test scope](quarantine-device-identity.md).
- Native Arch/pacman, Ubuntu/dpkg and Fedora/RPM inventory protection and
  lifecycle checks, plus live snapd with a disabled parallel instance.
- DEB/RPM/Arch package installation, upgrade and removal; authenticated
  APT/RPM repositories and rejection of tampered metadata/packages.
- Source ZIP/tar.gz integrity, checksum-pinned AUR recipes and a rehearsal of
  the production repository publisher against a disposable local Git remote.

The latest GUI change passed all 19 build/test jobs, including 415 regressions
on each supported Python version:
[PR #40 validation](https://github.com/ultherego/xdg-audit/actions/runs/40650051326)
and [merged main validation](https://github.com/ultherego/xdg-audit/actions/runs/40650695607).
Keyboard checks include Return/keypad Enter, empty/incorrect PURGE/HISTORY,
cancellation and selected history removal. Settings corners were inspected
in GTK light/dark empty/focused/scrolled screenshots; multiline Enter remains
a newline. GTK headless-Wayland activation and full desktop acceptance have
the separate scopes documented in the verification record.

The earlier package/release change passed all 18 build/test jobs, including 370
regressions on every supported Python version:
[PR #35 validation](https://github.com/ultherego/xdg-audit/actions/runs/40515908169).
The resulting `main` commit also passed:
[main validation](https://github.com/ultherego/xdg-audit/actions/runs/40516685256).
These results concern the commits linked in those runs; later changes need
fresh CI results.

The owner confirmed the tested GUI functionality on 2026-10-26. Additional
GNOME/KDE/Xfce session coverage and independent security review remain open in
the [release-readiness checklist](release-readiness.md). A reported device
identity change initially blocks its existing run; its actual owner environment
remains unverified. Exact-inventory recovery requires separate `REVALIDATE`
confirmation and does not authorize deletion or infer missing historical UUIDs.
The [independent review handoff](security-review-guide.md) and
[desktop acceptance protocol](desktop-acceptance.md) are prepared; neither is
a report of completed acceptance.

```fish
python3 -m unittest discover -s tests -v
python3 scripts/smoke_quarantine_cycle.py
python3 scripts/build_archives.py --output-dir dist
```

The quarantine test creates a disposable `HOME`, performs real moves, restores and purge, verifies file hashes and handles simulated conflicts without writing into your real XDG directories. Details: [Safe integration testing](testing-quarantine.md).

Optional per-user desktop-menu registration, updating and safe unregistration are described in [Desktop installation](desktop-installation.md). Native DEB/RPM/Arch builds, tag-driven releases and signed APT/RPM repository setup are described in [Native packages](native-packages.md). Production publication requires the documented owner credentials. See the [changelog](../CHANGELOG.md) for version history.

Source archives use the explicit allowlist in `scripts/archive-files.json`.
Add intended source files there when extending the project; incidental checkout
files and symbolic links must never enter a release archive.
