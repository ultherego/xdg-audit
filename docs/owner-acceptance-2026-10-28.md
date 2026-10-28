# Owner acceptance — 2026-10-28

[Release checklist](release-readiness.md) · [Roadmap](project-roadmap.md)

The repository owner confirmed completion and acceptance of the three remaining
P0 items, then instructed the maintainer to proceed with the remaining release
work. This records the owner's report; it is not a new independent review or
manual desktop test performed by release automation.

The application baseline in that conversation was merged main commit
`6f86e1994515febf1722befcf96c9e61bd858357` (PR #43), tree
`de4828012de5da7bc472ec1d1fa44653367cac13`. The owner did not separately state
a reviewed SHA, reviewer identity or desktop versions, and no external review
report or raw machine diagnostics were uploaded. Those details are not invented
here. The P0 checklist is closed on the authority of the owner's confirmation.

| Gate | Owner-reported outcome |
|---|---|
| P0-01: affected quarantine operations and device-identity issue | Completed and working correctly; resolution accepted |
| P0-02: independent security review by another person | Completed and accepted |
| P0-03: keyboard/theme acceptance in GNOME/Wayland, Plasma/Wayland and Xfce/X11 | All accepted |

The previously accepted owner GUI environment remains accepted. The new report
also covers the additional named desktop-session checks; no repeat is required
for the accepted application baseline.

## Release authorization and boundaries

The owner authorized the remaining release work. The next requested version is
`1.7.0-rc2`, followed by RC acceptance and stable publication. Signing setup,
actual signed assets/repositories and successful publication still require
their own operational results; the owner confirmation does not assert that
credentials are already configured or that a release has been published.

The committed release request pins the accepted application baseline. The tag
workflow verifies that packaged application files are unchanged from it, checks
successful main CI and tests an existing configured signing key before creating
an immutable tag. Documentation/release preparation may advance the release
commit; it must not silently replace the accepted application runtime.

For the accepted baseline, [PR CI](https://github.com/ultherego/xdg-audit/actions/runs/40734824714)
and [merged-main CI](https://github.com/ultherego/xdg-audit/actions/runs/40736967093)
passed all 22 build/test jobs with 440 regressions on every supported Python.
Both 160-file source archives and native-package/report checksums were verified;
the nine GUI combinations passed all 13 lifecycle assertions. These automated
results retain their documented fixture/input limits and are separate from
the owner's manual and independent-review acceptance above.
