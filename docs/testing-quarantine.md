# Quarantine/restore integration test

Run this on **Linux as a regular user**, from the repository root:

```sh
python3 scripts/smoke_quarantine_cycle.py
```

The default uses the machine's actual installed-package inventory (pacman on Arch/CachyOS). It exercises the same `scan()`, `commit_quarantine()` and `restore_quarantine_run()` used by the application. It does **not** make changes to your real XDG files.

**What is tested:** two candidate directories in a newly created disposable HOME; protected `niri` configuration; scanning and moving both candidates; journal v3 recording; SHA-256 comparison of files before/after the move and restore; refused restore when a destination exists; refused restore when the quarantined inode has been replaced; recovery after resolving these artificial conflicts; refusal of a move when the installed-package inventory cannot be verified.

The only writable workspace is an automatically generated `/tmp/xdg-audit-e2e-…` folder (or another location chosen by Python's `tempfile`). `HOME` and all `XDG_*_HOME` paths are overridden **within this test process only**. The test uses a fake pacman removal log **inside that temporary HOME** to create synthetic candidates. It does not modify the system pacman log or installed packages. Temporary files are cleaned automatically, even if the test raises an error.

For CI and non-Arch development environments only:

```sh
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
```

This replaces only installed-application detection with a known, fictional inventory; the scan, moves, journal and restore still perform actual Linux filesystem operations. It is deliberately not the same as verifying your host's real pacman inventory.

**Do not run with `sudo` or as root.** The script refuses root execution. No configuration, system package, real user data or external directory should be manually selected; the script chooses its own temporary paths.

Successful output has six `PASS` checks and a final cleanup confirmation. A failed assertion ends the run with a nonzero exit code.
