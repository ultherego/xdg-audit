# P0/P1 verification — 2026-10-26

> Historical results for PRs #27/#28. The owner's subsequent request covers
> MIT licensing, native APT/dpkg and RPM MOVE, the Snap scope and expanded
> AppImage detection. Current behavior is defined by the
> [installation-source contract](installation-source-support.md).
> References below to blocked RPM/MOVE and pending license selection describe
> those earlier commits, rather than the current specification.

Changes: [PR #27](https://github.com/ultherego/xdg-audit/pull/27) and
[PR #28](https://github.com/ultherego/xdg-audit/pull/28).
Exact commits, Python matrix results and native smoke tests are available in
[PR #28 checks](https://github.com/ultherego/xdg-audit/pull/28/checks).
No new RC or stable release was published during this verification.

## Completed checks

Local environment: Ubuntu 24.04.3 LTS, Python 3.12.14, without pacman.
Tests used temporary directories only. The execution container maps only
UID 0; product CLI and installer root guards were not disabled.
Installer unit tests use a controlled UID-check stub; the native launcher
smoke test in CI requires a regular user.

| Check | Result and scope |
| --- | --- |
| `python3 -m unittest discover -s tests -q` | PASS: 297 tests locally and a green Python 3.10–3.14 CI matrix; detailed cases below |
| Eight real SIGKILL checkpoints | PASS: before/after MOVE rename, before/after RESTORE rename, before deletion, after the first unlink, after deletion before final journal write, and during journal replacement |
| Restart recovery | PASS: identical restored bytes, resumed partial PURGE, explicit recovery from a temporary-only journal, and an untouched outside-operation sentinel |
| ENOSPC / EACCES / EIO | PASS: original error codes and previous journal preserved; no unapproved changes; accurate counts after rename; retry after fault removal |
| Real dpkg without pacman | PASS at these historical commits: read the dpkg database, scanned fixtures and explicitly refused MOVE; fixture bytes unchanged |
| Desktop registration installation/update/removal | PASS: nine regressions; unrelated registrations and quarantine unchanged; symlink/hardlink refusal; previous entry preserved after write failure |
| ZIP and tar.gz archives | PASS locally and in CI: build, integrity, reproducibility and identical rebuilding from extracted sources without Git; explicit `scripts/archive-files.json` contents only |
| Archive input privacy | PASS: incidental `.env`, JSON report, private Python and PEM files excluded; a declared symlink or path outside the project blocks building |
| Native Gio / GTK ENOSPC message | PASS in [GUI job 121701281841](https://github.com/ultherego/xdg-audit/actions/runs/40359634579/job/121701281841): launch from a path containing special characters, responsive GTK, visible ENOSPC error and no PURGE confirmation |

PR #27, commit `8d7a70535134fce903f470fca7a8a9098af78999`, passed
Python 3.10–3.14, Xvfb, Weston, E2E, benchmark and archive checks:
[run 40356697307](https://github.com/ultherego/xdg-audit/actions/runs/40356697307).
The PR was merged after those results.

PR #28 code, commit `9b389f6776d69eabc71b0c673d83a2667e31c222`, passed
the Python matrix, Xvfb (including Gio/ENOSPC), Weston, E2E, benchmark and archives:
[run 40359634579](https://github.com/ultherego/xdg-audit/actions/runs/40359634579).
Xvfb dependency installation has time limits, bounded retries and
noninteractive mode, preventing indefinite package-installation waits.

The actual CI artifact `12666463359` from that run was also downloaded.
Verification covered the digest in GitHub metadata, internal SHA256SUMS,
the exact 93-file inventory, ZIP/tar.gz content parity and byte-for-byte
agreement of all Python files with locally tested sources. No files outside
the explicit manifest were found.

## Fixed defects

1. dpkg fixtures contained literal backslash-t/backslash-n sequences, so the
   valid-record test did not exercise the actual format. Fixtures now use
   real tabs and newlines.
2. Journal writes closed a descriptor twice after flush/fsync failure,
   masking ENOSPC with EBADF. Descriptor ownership is now unambiguous.
3. MOVE and RESTORE wrote journals through paths with potentially symlinked
   ancestors. They now use the same anchored writer as PURGE.
4. RESTORE interrupted after rename left data restored but did not finish
   the journal on retry. Reconciliation requires the original inode;
   a new collision remains untouched and is not accepted as restored data.
5. Synchronization errors after rename undercounted objects already moved.
6. The desktop installer did not check every ancestor, wrote directly and
   mishandled percent signs in Exec.
7. Archive building collected arbitrary checkout files. It now requires an
   explicit manifest, including when building outside a Git repository.
8. dpkg can return `deinstall ok installed` or `purge ok installed`: these
   request a future action while the package remains installed. Such records
   protect data just like `install ok installed`, verified by real dpkg queries
   against an isolated fixture status database.

## Screenshot and project-file review

All nine `docs/screenshots/*.webp` images were inspected visually and with OCR.
Image metadata contained no EXIF/XMP fields. No password/token values, complete
personal HOME paths or hostnames were observed. Application names and neutral
`~/…` paths remain visible. The OCR `@` match was a Settings icon, not an email
address. This was a content review, not proof that every possible secret is absent.

The README identifies these screenshots as historical: classifications and
controls may differ from current code. Archives are additionally limited to
reviewed project files; scan reports and local logs are not published.
Binary attachments from the last published RC1 were outside this review.
New release artifacts still require acceptance before publication.

## Decisions and external evidence pending at that time

- License selection belonged to the owner; no default license had been added
  in PR #28. The subsequent owner-authorized change selects MIT.
- Independent security review requires a reviewer other than the change author.
- The owner's GUI confirmation was accepted. Separate GNOME/KDE/Xfce sessions
  were not marked complete on that basis.
- A new RC/stable release requires a release decision and successful required checks.
- RPM/MOVE expansion was deferred under the earlier P0/P1 sequence. The current
  installation-source contract supersedes that historical hold.

## Reproducing the checks

```fish
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p test_process_recovery.py -v
python3 -m unittest discover -s tests -p test_journal_errors.py -v
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
python3 scripts/build_archives.py --output-dir dist
cd dist
sha256sum -c SHA256SUMS
cd ..
```

CI runs native Gio and GTK tests with the required dependencies.
Run the CLI and desktop installer as a regular user.
