<p align="center">
  <img src="assets/xdg-audit-128.png" alt="xdg-audit icon" width="76">
</p>
<h1 align="center">xdg-audit</h1>
<p align="center"><strong>Review leftover Linux application files without blindly deleting your data.</strong></p>
<p align="center">Native GTK, Qt and Tk interfaces · Python 3.10+ · Read-only by default</p>

<p align="center">
  <img src="docs/screenshots/overview.webp" alt="xdg-audit showing the All audit results view" width="100%">
</p>
<p align="center"><sub>GTK4 on Niri · Representative screenshot with anonymized user paths</sub></p>

<details>
<summary>More screenshots — Data and State views</summary>
<p><strong>Data</strong></p>
<p><img src="docs/screenshots/data.webp" alt="xdg-audit Data scope"></p>
<p><strong>State</strong></p>
<p><img src="docs/screenshots/state.webp" alt="xdg-audit State scope"></p>
</details>

xdg-audit scans per-user Linux configuration, data, state, cache, Flatpak data and selected dotfiles. It helps identify files that **may** belong to removed applications while keeping uncertain or active application data out of automatic cleanup.

## Features

- **Review before changing anything.** Entries are classified as `CANDIDATE`, `REVIEW`, `UNKNOWN`, `ACTIVE` or `PROTECTED`, with reasons available in the inspector.
- **Recoverable quarantine.** Selected files are moved, never permanently deleted by the app; restore is available with explicit confirmation.
- **Native desktop GUI.** Automatically detects available GTK4/GTK3, Qt6 or Tk support, follows the system theme where possible, and keeps the CLI independent.
- **Useful audit workflow.** Scope tabs, search, filtering, sorting, incremental scan results, progress, cancellation and directory-size reporting.
- **Personal preferences.** Keep rules, package aliases and instant English/Polish language switching without rescanning.
- **Reports.** Export an audit to JSON and compare it with a previous scan.

## Quick start

```sh
git clone https://github.com/ultherego/xdg-audit.git
cd xdg-audit
python3 xdg_audit.py
```

Running without arguments launches the first compatible **already installed** GUI backend. Nothing is installed automatically. To run a read-only CLI scan:

```sh
python3 xdg_audit.py --scope all
```

## Requirements

**Core:** Linux and **Python 3.10+**. The CLI uses Python’s standard library; no `pip install` is required.

Choose **one** available GUI backend (Arch Linux / CachyOS package names):

| Backend | Packages |
| --- | --- |
| GTK4 (GNOME, Niri) | `python-gobject gtk4` |
| GTK3 fallback | `python-gobject gtk3` |
| Qt6 (KDE, LXQt) | `pyside6` **or** `python-pyqt6` |
| Tk fallback (X11/XWayland) | `tk` |

For example, on Arch Linux or CachyOS:

```sh
# GTK4
sudo pacman -S --needed python python-gobject gtk4

# Or Qt6
sudo pacman -S --needed python pyside6
```

**Additional system tools:** `coreutils` (`du`) supplies directory sizes; `procps-ng` (`ps`) supplies process evidence. `pacman` is used to verify installed packages and is **required before quarantine moves**, which fail closed without a verifiable inventory. Optional integrations: `flatpak`, `snapd` (`snap`), `systemd` (`systemctl --user`) and `xdg-utils` (`xdg-open`, to open folders).

## Safety first

| Classification | What it means |
| --- | --- |
| `CANDIDATE` | Possible leftover — **not a guarantee** that removal is safe |
| `REVIEW` / `UNKNOWN` | Requires manual inspection and additional confirmation |
| `ACTIVE` / `PROTECTED` | Cannot be moved to quarantine |

- A scan is **read-only**. Moving any entry requires an explicit user action and confirmation.
- Quarantined items live under `~/.local/share/xdg-audit-quarantine/` and can be restored.
- The app rechecks relevant filesystem and package information before moving, refuses cross-filesystem relocation and uses no-overwrite operations.
- Cancelled or unfinished scans cannot be used to move files.

> **Important:** Application ownership cannot always be determined reliably. Review every selection and keep backups of important files. Quarantine reduces risk; it does not replace a backup.

## Command-line usage

```sh
python3 xdg_audit.py --help
python3 xdg_audit.py --scope config --json > audit.json
python3 xdg_audit.py --scope config --compare audit.json
python3 xdg_audit.py --scope config --remove   # Interactive confirmation
python3 xdg_audit.py --list-quarantine
python3 xdg_audit.py --restore RUN_ID          # Interactive confirmation
```

Scopes: `all`, `config`, `data`, `state`, `cache`, `flatpak`, `dotfiles`.

## Development status

**v1.7.0-dev — development preview.** Automated tests cover Python 3.10–3.14 and build source ZIP/tar.gz archives in [GitHub Actions](https://github.com/ultherego/xdg-audit/actions). GTK4/Niri and Qt6/KDE still need broader real-session integration testing before a stable release.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_archives.py --output-dir dist
```

Desktop-menu installation and distribution packaging are intentionally deferred. See [CHANGELOG.md](CHANGELOG.md) for release history.
