# Desktop installation, update and removal (per user)

xdg-audit does not require packaging, root privileges, a system service or
automatic startup. Python 3.10+ and an installed graphical backend are needed
for desktop use. See [README](../README.md) for supported backends.

## Install from a local checkout

```fish
git clone https://github.com/ultherego/xdg-audit.git
cd xdg-audit
python3 -m unittest discover -s tests -q
python3 install_desktop.py
```

Registration creates exactly two conventional per-user desktop assets,
relative to `XDG_DATA_HOME` (default `~/.local/share`):

- `applications/io.github.xdgaudit.desktop`
- `icons/hicolor/256x256/apps/io.github.xdgaudit.png`

The desktop entry's `Exec` refers to the **absolute current checkout path**.
Do not relocate or delete the checkout and expect the shortcut to continue
working. The installer does not copy source code, install dependencies, or
register a user service. Never run it with `sudo`.

## Update

In the checkout whose path the launcher uses:

```fish
git status --short
git pull --ff-only
python3 -m unittest discover -s tests -q
python3 install_desktop.py
```

Restart any running GUI instance to load new code. If the checkout has moved,
run `python3 install_desktop.py` in the new location to refresh the launcher.
Inspect local changes before pulling. Prefer a verified release tag over a
moving branch for stable deployments.

## Remove desktop registration

Review the exact entries before removing them. These paths are the
registration created by `install_desktop.py`; do **not** remove the surrounding
directories or other desktop entries.

```fish
set -l data_home ~/.local/share
if set -q XDG_DATA_HOME
    set data_home $XDG_DATA_HOME
end
printf '%s\n' $data_home/applications/io.github.xdgaudit.desktop $data_home/icons/hicolor/256x256/apps/io.github.xdgaudit.png
```

After confirming both displayed paths belong to your installation, remove
those **two exact files** using your file manager. Then optionally remove the
checkout itself after reviewing its contents.

Do **not** remove `~/.config`, `~/.cache`, `~/.local/share`, or any
directory belonging to applications discovered by xdg-audit. Audit exports,
keep rules, and quarantine runs may contain valuable user data: they are
**not** automatically deleted by desktop unregistration. Quarantined data
must be managed separately through documented restore or PURGE flows.

## Release acceptance evidence

Run install → launch → update → relaunch → unregister on a disposable
HOME and verify that no user or system autostart was installed, unrelated
desktop entries were not overwritten, and quarantine history remained intact.
Record exact commands, resulting paths, before/after fixture hashes,
environment and a redacted run log in the
[release verification ledger](release-verification-evidence.md).
Documenting the procedure does not mean a real desktop acceptance test passed.

Automated evidence: `tests/test_install_desktop.py` exercises install, update,
exact-file unregistration, preservation of quarantine data and failure paths.
`scripts/desktop_entry_smoke.py` additionally uses Gio to launch an installed
fixture whose checkout path contains spaces, quotes, percent, backslash and
shell metacharacters. This smoke runs under the native GUI CI job.
