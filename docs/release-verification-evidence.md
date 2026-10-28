# v1.7.0 release verification — P0/P1 evidence ledger

This document separates the reusable **verification protocol** from linked
results. The owner accepted all three remaining P0 gates on 2026-10-28:
[confirmation and scope](owner-acceptance-2026-10-28.md).
Use only disposable fixture data. Do not run xdg-audit under `sudo` or test
destructive actions against your real XDG directories.

## Evidence requirements

For every manual run, record: UTC timestamp, commit SHA, distribution/version,
session type, GUI backend, Python version, exact command, expected/actual result,
and a redacted log or screenshot. A checked box in the readiness checklist needs
a linked result (CI run, test output, peer review or explicit owner attestation).
Owner-reported acceptance is identified as such; it does not imply that raw
reports were uploaded or that release automation performed those checks.
A failed or skipped test is **not** a pass.

## P0 — reproducible checks

### Automated baseline (all platforms)

```fish
python3 -m unittest discover -s tests -q
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
python3 scripts/build_archives.py --output-dir dist
```

Record hashes for generated archives and keep CI workflow URLs. These commands
must not be followed by real-user `--purge` or `--remove`.

### Interrupted journal (isolated fixture only)

1. In a disposable HOME, create a test XDG directory containing several known
   files; record SHA-256 of each file.
2. Run the isolated lifecycle test. Validate interruption cases before and
   after journal writes, and before and after unlink, using its test fixtures.
3. Assert recovery never follows symlinks, never overwrites collisions, rejects
   inode substitution, and never purges untracked bytes.
4. Record the command, the case name, and the recovery/restore result.
5. Repeat an interactive test on a *disposable* fixture HOME only; terminate
   the test process at a known fixture checkpoint. Never intentionally interrupt
   actions against personal data.

`tests/test_process_recovery.py` now executes eight real SIGKILL checkpoints
in child processes, so Python cleanup/finally blocks cannot run. These tests
exercise actual journal writes, renameat2, unlink, hashes and restart recovery
on disposable filesystem fixtures. They provide reproducible process-crash
evidence. They do not establish power-loss, kernel-crash or filesystem-failure
durability. An interactive rehearsal remains optional additional evidence.

### Desktop session matrix

| Environment | Scan | Inspect | Quarantine | Restore | PURGE | Theme / error UI | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GNOME / Wayland / GTK | accepted | accepted | accepted | accepted | accepted | accepted | [Owner report](owner-acceptance-2026-10-28.md) |
| KDE Plasma / Wayland / Qt | accepted | accepted | accepted | accepted | accepted | accepted | [Owner report](owner-acceptance-2026-10-28.md) |
| Xfce / X11 / Tk or GTK | accepted | accepted | accepted | accepted | accepted | accepted | [Owner report](owner-acceptance-2026-10-28.md) |

The owner confirmed all tested GUI functions work on 2026-10-26. This closes
acceptance for the tested owner environment. On 2026-10-28 the owner also
accepted the additional named sessions, including keyboard and themes. The
matrix records that attestation; no separate desktop versions or raw manual
reports were supplied. Do not request the same accepted tests again.

Use the [desktop acceptance protocol](desktop-acceptance.md) for disposable
fixtures, physical keyboard checks and the required per-session record.

Automated complete software-rendered sessions now also pass the native GUI
lifecycle: [exact target and retained reports](verification-data/2026-10-28/desktop-sessions.md).
Their scope remains separate from the manual matrix above.

For each session, launch with a disposable HOME and verify all confirmation
tokens and visible error messages. Recording a successful Xvfb/Weston CI smoke
does not satisfy a real desktop-session validation.

### No pacman

On a disposable Debian/RPM-family VM (or a controlled test environment where
`pacman` cannot be resolved), prove separately:
- a read-only scan completes and reports package-provider health accurately;
- MOVE rechecks the native dpkg/RPM database and completes only after explicit
  confirmation (including uncertain consent for REVIEW/UNKNOWN);
- missing, failed, partial or wrong-family inventories refuse authorization;
- an unavailable optional provider is not confused with a provider that
  failed during execution.

Retain an exact command transcript and a before/after hash of fixture data.

### Disk full / permissions

Use a bounded disposable filesystem or fixture with a controlled ENOSPC
injection, **never** fill the host filesystem. Check journal write, manifest
write, MOVE, RESTORE and PURGE preflight error paths; inspect for remaining
test bytes and unambiguous UI messages. Also exercise unreadable directories
and files owned by a different test user. No elevated automatic repair.

### Independent security review

Reviewer other than the author must examine the package source recheck path,
TOCTOU boundaries, anchored filesystem operations, SHA-256 and inode
validation, interrupted journal recovery, confirmation UX, and retention
policy. Record name/handle, reviewed commit, findings, disposition and link.
Author self-review cannot satisfy this P0 gate.
The owner subsequently confirmed completion and acceptance of this independent
review: [owner report](owner-acceptance-2026-10-28.md). The
[review map and report template](security-review-guide.md) remain available for
future changes; release automation does not claim to be the independent reviewer.

## P1 — publication checks

1. **License:** owner delegated the selection on 2026-10-26; MIT is recorded in LICENSE and included in source archives.
2. **Docs:** compare README, CHANGELOG and RELEASE_NOTES against the exact
   release commit; distinguish shipped functionality from planned features.
3. **Artifact privacy:** inspect screenshots, source archives and release
   attachments for user paths, hostnames, credentials and untracked data.
   Record what was inspected and evidence of successful inspection.
4. **Install lifecycle:** test documented user installation, update and
   uninstallation in disposable environments. Verify no system-wide
   autostart, stale desktop file, or accidental deletion of user data.
5. **RC/stable:** release/tag only after evidence for mandatory P0/P1 gates,
   explicit owner approval, and passing required CI. A released RC precedes
   the stable tag.

## Acceptance authority and remaining external configuration

- Real GNOME/KDE/Xfce sessions, independent second-person review and the affected
  old quarantines were accepted by explicit owner report. Repository tests alone
  do not supply those attestations.
- License selection was authorized and MIT was added. The owner also authorized
  the remaining release work; actual signing/publication results remain separate.
- Production signing keys must be configured from a trusted owner computer.
  Missing configuration blocks the tag workflow before an immutable tag exists.
- GitHub branch ruleset changes require a separate verified admin action;
  direct CI dependencies already provide the current functional gate.

## Acceptance

Only close an item after linking its concrete result or explicit owner
attestation, with the evidence type and limits stated. Production publication
requires real workflow/assets evidence rather than a statement of intent.

Executed checks and findings: [2026-10-26 verification](verification-2026-10-26.md).
Latest safety and GUI evidence: [2026-10-28 verification](verification-2026-10-28.md).
