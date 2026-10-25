# xdg-audit 1.7.0-rc1

**Release candidate — not a stable release.** Scanning is read-only by default; quarantine and restore require explicit confirmation.

## Changes

- Protect user game saves, developer workspaces and custom icon themes from being suggested as removable.
- Additional application aliases for KDE Connect, Zen Browser, GitKraken CLI, Stormshield, pip, GStreamer and Tracker.
- Classification JSON identifies more evidence sources and distinguishes strong, weak, medium, historical and policy evidence.
- Linux directory-descriptor-based no-overwrite rename now opens **each ancestor** with `O_NOFOLLOW`, avoiding linked parent directories.
- New regression tests for mistaken identity, symlink parents, modified restore manifests and helper-package misidentification.
- GTK4, Qt6 and Tk widget checks and real application startup checks under Xvfb; repeatable synthetic scan benchmarking in CI.
- No visual redesign or new installation procedure.

## Known limitations

- `CANDIDATE` is never proof of a safe orphan. Manual review and backups still matter.
- Quarantine authorization currently requires a working pacman installed-package inventory; other distributions can use read-only scanning.
- Xvfb GUI startup tests do not replace real Niri or KDE Plasma testing on Wayland.
- Active process names and desktop launcher files are hints, not authoritative ownership proof.
- An in-progress `du` command may continue briefly after scan cancellation.
- Multi-item quarantine is journaled but not an ACID transaction; manual recovery can be needed.
- `renameat2(RENAME_NOREPLACE)` is Linux-specific and fails closed if unsupported; cross-device moves are refused.
- Desktop entry installation, AUR and automatic updates are deliberately postponed.

## Local verification

```sh
python3 -m unittest discover -s tests -q
python3 scripts/benchmark_scan.py --count 500
python3 scripts/build_archives.py --output-dir dist
(cd dist && sha256sum -c SHA256SUMS)
```

To enforce the CI checks as merge requirements, configure a GitHub repository ruleset under **Settings → Rules → Rulesets**. The current GitHub connection does not expose an administration action to enable or change branch protection.
