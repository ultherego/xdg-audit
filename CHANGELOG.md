# Changelog

## 1.7.0-rc2 (unreleased)

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
