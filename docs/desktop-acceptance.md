# Full desktop-session acceptance

[Release checklist](release-readiness.md) · [Automated GUI scope](gui-lifecycle-testing.md)

**Current status: GNOME, KDE Plasma and Xfce accepted by the owner (2026-10-28).**
The owner confirmed all additional keyboard/theme checks were satisfactory.
The [acceptance record](owner-acceptance-2026-10-28.md) records that report
without inventing desktop versions or raw per-session results. The previously
accepted GUI environment also remains accepted. The protocol below is reusable
for future application changes and does not require repeating accepted tests.

| Session | Backend | Required evidence |
|---|---|---|
| GNOME / Wayland | GTK4 | Full workflow, native display, theme, keyboard and error UI |
| KDE Plasma / Wayland | Qt6 | The same workflow, including system-palette integration |
| Xfce / X11 | GTK or Tk, identify which | Startup, workflow, visible controls and keyboard |

## Complete-session integration in CI

The `Full gnome/plasma/xfce session` Actions jobs start the installed session
managers and desktop components on Ubuntu 24.04. GNOME Shell/Mutter uses its
headless virtual monitor, KWin uses its virtual framebuffer, and Xfce runs on
Xvfb. These are complete software-rendered sessions, not physical displays.

`scripts/gui_desktop_session_smoke.py` creates a new profile, runtime directory
and private D-Bus session. An ordinary desktop autostart entry launches the
fixture inside that session. The check requires the session manager, desktop
shell/window manager and settings services, verifies their actual D-Bus owner
PIDs/executables/profile, and checks they survive the entire GUI lifecycle.
Xfce also requires its panel, desktop and settings daemon. The existing GUI
harness then verifies GTK4/Qt6 native Wayland or Tk native X11, explicit token
confirmation/cancellation, hashes, sentinels, REVALIDATE and selected history
removal. The application cannot fall back to XWayland in Wayland cases.

Only temporary desktop settings are changed: GNOME's shell launcher adds the
virtual monitor flags; Plasma uses classic startup on its private bus and a
private PATH wrapper adds KWin's virtual-display flags. KWin also runs with
`no-new-privs` to support same-user process/profile verification without file
capability gains. Installed inventory and
the optional Btrfs device metadata in the GUI harness remain synthetic; native
provider and actual-remount CI are separate. The launcher rejects root and
does not inherit a real profile, display, bus or publication credentials.

Each job retains `session.json`, `lifecycle.json` and diagnostic logs, including
the exact desktop package versions and commit. A failed session cannot produce
release archives. This provides automated desktop integration coverage, while
physical keyboard input, system-theme/palette inspection and the acceptance
record below are separate from CI. The current manual closure follows the
owner's explicit confirmation, not a CI pass alone. All three session jobs passed in
[PR #42 validation](https://github.com/ultherego/xdg-audit/actions/runs/40711792031).
The [retained original reports](verification-data/2026-10-28/desktop-sessions.md)
pin exact versions, service identities, ten lifecycle assertions per session,
keyboard-event scope and SHA-256 evidence. Calendar, audio, networking, portals
and other optional desktop features are outside this check; diagnostic
warnings remain in the original log artifacts.

## Record the environment

Record UTC timestamp, full commit SHA, clean/dirty checkout, distribution and
version, desktop/compositor version, X11/Wayland, backend/bindings, Python and
the exact commands. Record expected and actual results and attach redacted
logs/screenshots. Leave failed or untested cases explicit rather than marking
them PASS.

## Automated fixture precheck inside the actual session

Run as a regular user in the named desktop session, with the relevant toolkit
already installed. GTK X11 keyboard injection also needs `xdotool`; Qt tests
need that binding's QtTest module. These commands create their own temporary
HOME and use production lifecycle code with synthetic installed inventory.

```fish
python3 scripts/gui_lifecycle_smoke.py --backend gtk4 --expect-session wayland --output /tmp/xdg-gnome-lifecycle.json
python3 scripts/gui_lifecycle_smoke.py --backend qt6 --expect-session wayland --output /tmp/xdg-plasma-lifecycle.json
python3 scripts/gui_lifecycle_smoke.py --backend tk --expect-session x11 --output /tmp/xdg-xfce-lifecycle.json
```

Run only the command matching the session under test. Preserve its JSON plus
the separately recorded environment/SHA. The script checks the actual display
backend; XWayland does not count as native Wayland. GTK Wayland activation is
signal-based in this harness, so manually verify physical keyboard behavior
below. A script pass alone does not establish visual desktop acceptance.

## Manual fixture for visual and keyboard acceptance

Create a separate, disposable profile in fish:

```fish
set acceptance_home (mktemp -d -t xdg-audit-desktop.XXXXXX)
mkdir -p "$acceptance_home/.config/xdg-desktop-fixture" "$acceptance_home/.config/niri"
printf 'desktop acceptance fixture\n' > "$acceptance_home/.config/xdg-desktop-fixture/settings.txt"
printf 'protected fixture\n' > "$acceptance_home/.config/niri/settings.txt"
printf 'outside sentinel\n' > "$acceptance_home/outside-sentinel"
sha256sum "$acceptance_home/.config/xdg-desktop-fixture/settings.txt" "$acceptance_home/.config/niri/settings.txt" "$acceptance_home/outside-sentinel"
python3 xdg_audit.py --home "$acceptance_home" --gui --scope config --quick
```

Keep the desktop's environment for theme integration; the explicit `--home`
selects only the disposable audited profile. Confirm the displayed paths belong
to that generated directory before selecting the fixture. Preserve the initial
hashes and the generated path in the test record. No application under test is
uninstalled and no personal configuration is selected.

1. Complete quick and size-measuring scans. Check source health, filters,
   details and visible actions. The protected `niri` fixture must stay blocked.
2. Inspect Settings with empty and populated multiline fields. Check all four
   editor frames/corners, focus outlines and scrolling in light/dark themes
   supported by the session. Enter inserts a newline; Cancel saves nothing.
   Save a language change inside this fixture profile and verify EN/PL labels.
3. Select only `xdg-desktop-fixture`. Exercise uncertain consent where required.
   Cancel a typed MOVE, then confirm MOVE using the keyboard. Verify exact
   fixture bytes and the resulting journal.
4. Confirm RESTORE and compare original paths and hashes. MOVE the fixture
   again to create a distinct run; retain the first restored history entry.
5. Try empty and incorrect PURGE with Enter. Cancel a correctly typed token.
   Verify the quarantined bytes/journal remain unchanged. Then explicitly
   confirm PURGE and verify only the selected fixture payload disappears.
6. Repeat empty/incorrect input and cancellation for HISTORY. Confirm HISTORY
   for the purged run only and verify the other restored history survives.
7. Use physical Return and keypad Enter in the token fields. Confirm each
   operation occurs once, and each subsequent operation still requires its
   own token. If the keyboard lacks a keypad, record that case as untested
   with the separate automated coverage, rather than inventing a manual pass.
8. Exercise a permission refusal using only disposable fixture data and check
   that the message is readable and the operation stops. Preserve outside and
   protected sentinel hashes throughout. Disk-full injection remains covered
   by the dedicated bounded CI fixture; never exhaust the desktop host disk.

Record the actual backend selected by the application. Retain the generated
profile until evidence is accepted; afterwards remove only that disposable
directory. Do not reuse this protocol with an existing user HOME/quarantine.

## Completion record

For future acceptance runs, attach the environment record, automated report,
manual case results, before/after hashes and screenshots. Keep skipped
keyboard/theme/backend cases visible as limitations. The current accepted
application baseline is covered by the owner's linked confirmation above.
