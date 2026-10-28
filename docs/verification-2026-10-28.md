# Verification record — 2026-10-28

[Release checklist](release-readiness.md) · [Roadmap](project-roadmap.md) · [Evidence protocol](release-verification-evidence.md)

This is an author-run automated and visual verification record. It does not
claim independent security approval, diagnosis of the owner's affected run,
full GNOME/Plasma/Xfce acceptance or production publication.

## Exact target and CI

[PR #40](https://github.com/ultherego/xdg-audit/pull/40) fixes Settings editor
corners and typed-token confirmation with Enter.

- PR head: `0e4d11a23f361c498c7aefbee58667fa37fc8c64`.
- Tested PR merge: `c27474a3f0bc521330816851677e2c6f8f4e9251`.
- Merged main: `62194aeb7f4981d95cb65a47babf1e3f363c0c57`.
- Identical reviewed tree: `840bef5d11b2c153b6e6fd5eaadcf3525bda07ac`.
- [PR CI](https://github.com/ultherego/xdg-audit/actions/runs/40650051326)
  and [main CI](https://github.com/ultherego/xdg-audit/actions/runs/40650695607)
  both completed successfully: 19 build/test jobs each. The three production
  release/repository/AUR jobs were skipped, as expected for these events.

## Results and boundaries

| Check | Result and scope |
|---|---|
| Python 3.10–3.14 | 415 regressions pass on each supported interpreter |
| GUI lifecycle | GTK4, GTK3, Qt6 and Tk on X11; GTK4 and Qt6 on native headless Wayland pass with production lifecycle operations and synthetic inventory |
| Keyboard confirmations | Each X11 backend and Qt6 Wayland reports Return ×7 and keypad Enter ×6; GTK4 Wayland reports 13 Entry activations, not physical keyboard injection |
| Refusal and history | Empty/incorrect PURGE/HISTORY, typed-token cancellation, separate positive confirmations and selected completed-history removal pass; another restored journal survives |
| Data boundaries | Exact payload hashes, protected fixture and outside sentinels survive the expected stages; only explicitly selected payload/history is removed |
| Settings layout/input | Empty/focused/scrolled GTK frames, light/dark presentation, bounded dialogs and multiline Return are checked; Qt/Tk multiline input also passes |
| Filesystem identity | Disposable real Btrfs remounts, device-number changes, persistent UUID binding, snapshot refusal and separately confirmed recovery/PURGE/RESTORE pass |
| Native sources | Actual pacman/dpkg/RPM inventories and live snapd lifecycle pass; this is separate from synthetic GUI inventory |
| Packages and trust | DEB/RPM/Arch build/install/upgrade/removal and authenticated repository/tamper checks pass |
| Publication rehearsal | Actual signing tools and disposable credentials/local remote exercise first publication, retries, renewal and tamper refusal; no production key or repository is claimed |
| Source contents | PR source ZIP and tar.gz each contain exactly the 142 allowlisted files at this target, matching the reviewed checkout byte for byte |

Downloaded GUI, source and three native-package artifact ZIPs passed their
published outer SHA-256 and ZIP integrity checks. Source/native-package inner
`SHA256SUMS` also passed. These results apply to PR #40's tree, not to future
release artifacts or the documentation changes recording this evidence.

## Visual inspection

All nine Settings images were inspected: GTK4 light, GTK4 dark and GTK3 light,
each empty, focused and scrolled. Editor borders have complete corners; opaque
TextView backgrounds stay inset within the frames, focus outlines are visible
and scroll controls remain inside the bounds. The layout harness additionally
verifies Return inserts a newline without accepting/closing Settings or saving
cancelled edits. This is screenshot inspection, not full-desktop acceptance.

The [GUI harness documentation](gui-lifecycle-testing.md) specifies how X11
uses actual XTest key events, Qt uses its QtTest binding, Tk uses widget events,
and GTK headless Wayland uses Entry activation. Physical keyboard/theme checks
remain in the [desktop protocol](desktop-acceptance.md).

## Downloaded evidence

Artifacts belong to [PR CI run 40650051326](https://github.com/ultherego/xdg-audit/actions/runs/40650051326).
The following hashes cover the downloaded GitHub artifact ZIPs, rather than
individual files inside them.

| Artifact | SHA-256 |
|---|---|
| [gui-layout](https://github.com/ultherego/xdg-audit/actions/runs/40650051326/artifacts/12799695428) | `d23cae7705c277a1aed7a12303ff7f2b159aa34852685b558657cb37b2265680` |
| [gui-lifecycle-x11](https://github.com/ultherego/xdg-audit/actions/runs/40650051326/artifacts/12799601261) | `555edb1104f4259bfebff7138dd004792bcd81570c0e686f18a48bc99c3c0ccd` |
| [gui-lifecycle-wayland](https://github.com/ultherego/xdg-audit/actions/runs/40650051326/artifacts/12799137438) | `9b363cd367b51d9e5b1a0614acc8208e377040c68cd8bcde7674e6f5b17bac55` |
| [xdg-audit-source](https://github.com/ultherego/xdg-audit/actions/runs/40650051326/artifacts/12798509133) | `1c2f1ef82ddc21c983fb24098e2a79120531ad5cf8f8380c7758700b73d649e1` |

GUI artifacts have a configured 14-day retention. The nine inspected original
PNGs and six verbatim lifecycle reports are also retained in the repository,
with original-member hashes in the [retained evidence](verification-data/2026-10-28/gui-lifecycle.md).
The images are unedited copies from the verified `gui-layout` ZIP:

| Theme/backend | Empty | Focused | Scrolled |
|---|---|---|---|
| GTK4 light | [PNG](screenshots/verification-2026-10-28/gtk4-light-empty.png) | [PNG](screenshots/verification-2026-10-28/gtk4-light-focused.png) | [PNG](screenshots/verification-2026-10-28/gtk4-light-scrolled.png) |
| GTK4 dark | [PNG](screenshots/verification-2026-10-28/gtk4-dark-empty.png) | [PNG](screenshots/verification-2026-10-28/gtk4-dark-focused.png) | [PNG](screenshots/verification-2026-10-28/gtk4-dark-scrolled.png) |
| GTK3 light | [PNG](screenshots/verification-2026-10-28/gtk3-light-empty.png) | [PNG](screenshots/verification-2026-10-28/gtk3-light-focused.png) | [PNG](screenshots/verification-2026-10-28/gtk3-light-scrolled.png) |

Only these explicitly reviewed evidence files are added to the source manifest;
incidental generated reports remain excluded. Retention does not expand the
scope of what the fixtures demonstrate.

## Earlier safety work in this target

- [PR #37](https://github.com/ultherego/xdg-audit/pull/37),
  [CI](https://github.com/ultherego/xdg-audit/actions/runs/40644225721): exact
  device revalidation, Btrfs binding and refusal to reuse recovery consent for
  automatic retention.
- [PR #38](https://github.com/ultherego/xdg-audit/pull/38),
  [CI](https://github.com/ultherego/xdg-audit/actions/runs/40644732636): live Git
  verification after leased branch cleanup, preserving recreated heads.
- [PR #39](https://github.com/ultherego/xdg-audit/pull/39),
  [PR CI](https://github.com/ultherego/xdg-audit/actions/runs/40646071789),
  [main CI](https://github.com/ultherego/xdg-audit/actions/runs/40646428649):
  nine real FIFO substitutions that previously timed out now refuse without
  blocking journal, hashing and permission inspection paths.

Real Btrfs CI concerns disposable filesystems. It does not diagnose the owner's
existing quarantine or infer filesystem UUIDs absent from older journals.

## Open evidence

Complete software-rendered desktop integration was subsequently added in
[PR #42](https://github.com/ultherego/xdg-audit/pull/42): GNOME 46/GTK4 and
Plasma 5.27/Qt6 on native Wayland, plus Xfce 4.18/Tk on native X11.
[Its exact target, verified artifacts and retained original reports](verification-data/2026-10-28/desktop-sessions.md)
are separate from the PR #40 results above. This does not close manual
theme/palette or physical-keyboard acceptance.

The owner's read-only device diagnostics, [independent reviewer report](security-review-guide.md),
[additional desktop sessions](desktop-acceptance.md), production signing setup
and RC/stable release decisions remain open. The latest published prerelease
is still `v1.7.0-rc1`; `1.7.0-rc2` is the development source version.
