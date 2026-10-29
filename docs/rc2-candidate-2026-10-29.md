# RC2 application baseline proposal — 2026-10-29

[Release checklist](release-readiness.md) · [Roadmap](project-roadmap.md)

**Status: proposed; awaiting explicit owner acceptance of this application
baseline.** This document records completed verification and the exact proposed
release pin. It is not a new owner approval, independent security review or
manual desktop report. The owner's latest statement confirmed green CI.

## Proposed application target

- Commit: `ed7129f41c5270cfcd195e05b607d3ce9ccf4c81`.
- Tree: `3a40f650e376e1e3c23250b27af6e81f12845f07`.
- Source version: `1.7.0-rc2`; no RC2 tag/release has been published.
- Packaged runtime changes since the previously accepted baseline:
  `xdg_sources.py`, `xdg_gui_gtk.py`, `xdg_gui_qt.py` and `xdg_i18n.py`.

PR #45 limits the broad AppImage probe's handling of unreadable root-owned
service directories under `/opt`. Explicit launcher targets retain their
existing validation. PR #46 moves GTK/Qt MOVE work onto their existing
quarantine worker helpers, adds activity presentation and fixes Qt newline
formatting/translations. The quarantine engine, journal formats, PURGE/RESTORE
authorization and confirmation tokens are unchanged by these PRs.

The [roadmap](project-roadmap.md) records the owner's AppImage and new progress
UI acceptance. The earlier [P0 owner confirmation](owner-acceptance-2026-10-28.md)
remains recorded and does not need repeating. Neither that earlier acceptance
nor the latest green-CI acknowledgement is represented here as fresh approval
of a different complete release baseline.

## Completed verification of this exact commit

[Main CI 40898330611](https://github.com/ultherego/xdg-audit/actions/runs/40898330611)
passed all 22 build/test jobs. Python regressions pass with 460 tests, including
the actual GnuPG probes. Native DEB/RPM/Arch install/upgrade/removal and trust
checks, native-provider/live-snapd tests, Btrfs remounts, desktop/GUI lifecycles
and the disposable publication rehearsal passed.

Nine downloaded source/native/GUI/desktop artifact ZIPs passed their API
SHA-256 and ZIP-integrity checks; source/native inner `SHA256SUMS` also passed.
Both source archives contain exactly 164 allowlisted files, matching this
commit byte for byte. All 28 DEB runtime/icon/helper files and 46 documentation
files match the checkout. Nine GUI combinations each passed 13 lifecycle
assertions; all three desktop session and teardown reports passed.

The [main source artifact](https://github.com/ultherego/xdg-audit/actions/runs/40898330611/artifacts/12907288665)
has outer ZIP SHA-256
`340b4005b35b5d856385c4437cbfa34c9c18790fd24a49da200342062a63ef3c`.
These are application/build fixture results, not production signing or manual
desktop checks performed by release automation.

## Proposed release-request change

Update `accepted_application_sha` from
`6f86e1994515febf1722befcf96c9e61bd858357` to the full target SHA above and
point `owner_acceptance` to this record. The accompanying PR changes only
release records and documentation; its packaged application must remain
identical to the proposed target.

The [latest tag attempt](https://github.com/ultherego/xdg-audit/actions/runs/40898867902)
correctly refused the old pin before reaching the signer. Its result does not
establish the current availability of production signing credentials.

Before merging this proposal, record the owner's explicit acceptance of the
proposed application baseline in this document. Keep the runtime comparison,
production signing preflight and final artifact checks enabled. Stable
publication still follows actual RC publication and acceptance.
