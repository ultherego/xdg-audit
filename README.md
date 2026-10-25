# xdg-audit

**xdg-audit** is a conservative, native Linux utility for auditing leftover per-user application configuration, data, state, caches, and related files. It is developed primarily with Arch Linux and CachyOS in mind, but it can run on other Linux distributions.

> **Development version: 1.7.0-dev.** This is not yet a stable release. Review every item before taking action, and keep backups of important data.

- **Read-only by default.** Scanning does not remove or relocate files.
- **Recoverable quarantine.** Explicitly selected items are moved to a quarantine directory rather than permanently deleted.
- **Native interfaces.** GTK4/GTK3, Qt6, and Tk are supported, with automatic backend detection; the CLI works independently.
- **No mandatory GUI installation.** The program uses GUI bindings already available on the system and does not install dependencies, change desktop settings, or require `sudo`.
- **English and Polish UI.** Change languages from Settings without restarting the app or triggering another scan.
- **Python 3.10+.** No browser-based interface.

## Quick start

Download a source archive from a successful [GitHub Actions run](https://github.com/ultherego/xdg-audit/actions) or clone the repository:

```sh
git clone https://github.com/ultherego/xdg-audit.git
cd xdg-audit
python3 xdg_audit.py
```

Running without arguments opens the native GUI when a compatible backend is available. The command-line interface remains usable if no GUI backend can be initialized.

### Command-line examples

```sh
python3 xdg_audit.py --theme-info       # Inspect GUI/theme detection
python3 xdg_audit.py --scope all        # Read-only CLI audit
python3 xdg_audit.py --scope config --json > before.json
python3 xdg_audit.py --scope config --compare before.json
python3 xdg_audit.py --list-quarantine
python3 xdg_audit.py --restore RUN_ID   # Explicit RESTORE confirmation required
python3 xdg_audit.py --help
```

The available audit scopes include `config`, `data`, `state`, `cache`, `flatpak`, `dotfiles`, and `all`.

## Desktop environments and GUI backends

The application automatically selects a suitable **already installed** backend:

| Environment | Preferred interface |
| --- | --- |
| KDE Plasma / LXQt | Qt6 |
| GNOME / Niri and other GTK-friendly sessions | GTK4, with GTK3 fallback |
| Other supported graphical sessions | An available compatible native backend |
| X11 / XWayland fallback | Tk |
| No suitable GUI | CLI |

The application follows the available system theme integration. GTK CSS does not necessarily have an identical counterpart in Qt or Tk.

The GUI has an adaptive results table, sortable columns where supported, scan-stage feedback, incremental results, cancellation, an item inspector, and quarantine/history views. The inspector can open an item's parent folder in the system file manager.

### Changing the language

Open **Settings → Language → English / Polski → Save**.

The visible interface is updated immediately: there is no application restart, full window rebuild, or filesystem rescan just for changing the language. Existing results, selections, and the active tab are preserved.

File and directory names, technical state identifiers such as `ACTIVE` and `UNKNOWN`, and some diagnostics provided by external tools remain unchanged.

## Classification and audit reports

xdg-audit distinguishes between the following states:

| State | Meaning |
| --- | --- |
| `CANDIDATE` | Potential leftover; **not proof** that an application has been uninstalled |
| `REVIEW` | Requires manual investigation |
| `UNKNOWN` | Insufficient evidence for a confident classification |
| `ACTIVE` | Evidence indicates that the item belongs to an active application |
| `PROTECTED` | Deliberately excluded from relocation |

Classification uses available package/application signals, user-defined aliases and exceptions, and references found in configuration files. The JSON report includes structured `evidence`, `risk_flags`, and `schema_version` fields while preserving earlier `state` and `reasons` fields.

Results can be exported to JSON and compared with an earlier report. Export is user-initiated; the application does not silently overwrite an earlier report.

Scanning is incremental: classification results can appear before directory sizes finish computing. Progress is reported by stage and by countable batches, not as an invented percentage of the whole scan. A running `du` subprocess can take additional time to finish after cancellation is requested. Quarantine actions are disabled while a scan is incomplete or cancelled.

## Quarantine and safety

**There is no automatic, irreversible deletion.**

- All moves require explicit `MOVE` confirmation.
- Moving `REVIEW` and `UNKNOWN` items additionally requires `UNCERTAIN` confirmation.
- `ACTIVE` and `PROTECTED` items cannot be moved.
- Before moving an item, the application checks current package information, user exceptions, file identity, symlinks, mount points, and related safety conditions again.
- A cancelled or incomplete scan cannot be used as the basis for a move.

Quarantined items are stored under:

```text
~/.local/share/xdg-audit-quarantine/<RUN_ID>/
```

Restoring an item requires a separate, explicitly confirmed action. Older quarantine manifests from releases 1.1–1.5 remain readable.

The quarantine journal records steps such as `moving`, `moved`, `restoring`, and `restored`. Manifest updates use a temporary file, atomic replacement, and filesystem synchronization where supported. Interrupted operations can be reconciled against the file's physical location.

In **1.7.0-dev**, quarantine and restore are further hardened using directory-file-descriptor-anchored Linux `renameat2(RENAME_NOREPLACE)` to avoid overwriting a destination or following unsafe parent-directory substitutions. If this operation is unavailable, the move fails closed rather than silently falling back to a less safe mechanism. Cross-filesystem moves are refused rather than converted to copy-and-delete operations.

**Safety limit:** a multi-item move is not a single ACID transaction. Journaling and recovery improve crash handling but do not replace backups, filesystem reliability, or independent verification before removing application data.

## Settings

Settings are saved only when **Save** is selected, in:

```text
${XDG_CONFIG_HOME:-~/.config}/xdg-audit/settings.json
```

The settings file is written with `0600` permissions. Supported keys include:

| Setting | Purpose |
| --- | --- |
| `language` | UI language (`en` or `pl`) |
| `keep` | Paths to preserve |
| `aliases` | Additional application/directory matching patterns |
| `quick_scan` | Skip expensive size calculations |
| `startup_scope` | Default audit scope on launch |
| `show_active` | Show or hide active items |

Example alias entries:

```text
BraveSoftware=brave*
opera=opera*
```

Changing only the language, startup scope, or visibility filter does not rescan the filesystem. Changes to `keep`, `aliases`, or `quick_scan` can affect audit results and therefore require a fresh scan.

## Development, testing, and archives

Run the standard-library test suite:

```sh
python3 -m unittest discover -s tests -v
```

If `pytest` is installed:

```sh
python3 -m pytest -q
```

Build source archives locally:

```sh
python3 scripts/build_archives.py --output-dir dist
cd dist && sha256sum -c SHA256SUMS
```

The builder produces versioned `.zip` and `.tar.gz` archives plus a `SHA256SUMS` file. It does **not** install the application or its dependencies.

[GitHub Actions](https://github.com/ultherego/xdg-audit/actions) runs the Python test matrix (3.10–3.14), performs a CLI smoke test, and builds downloadable archive artifacts when checks pass. A matching `v*` tag can initiate a GitHub Release; development/prerelease tags are marked accordingly.

**GUI validation status:** automated source/model tests and Tk/X11 smoke tests do not establish full visual or interaction coverage for GTK4 on Niri or Qt6 on KDE Plasma. Those combinations still require real-session integration testing before a stable release. The current stable-use baseline prior to this development series was v1.6.3.

## Source layout

| Path | Responsibility |
| --- | --- |
| `xdg_audit.py` | Core audit logic and CLI |
| `xdg_gui.py` | GUI backend selection |
| `xdg_gui_gtk.py` | GTK4 / GTK3 interface |
| `xdg_gui_qt.py` | Qt6 interface |
| `xdg_gui_tk.py` | Tk fallback interface |
| `xdg_prefs.py` | Persistent settings |
| `xdg_i18n.py` | English/Polish translations |
| `xdg_inspector.py` | Shared item detail text |
| `xdg_history.py` | Report comparison |
| `assets/` | Application icons |
| `tests/` | Unit and regression tests |
| `scripts/build_archives.py` | Reproducible source archives |
| `.github/workflows/tests.yml` | CI and release workflow |
| `install_desktop.py` | Optional desktop integration helper; **not automatically run** |

Desktop-menu installation, AUR/system packaging, and automatic updates are intentionally postponed while the application is being refined.

## Requirements

**The CLI does not require any third-party Python packages.** Only one GUI backend is needed; xdg-audit automatically uses a compatible backend already installed on your system.

### Core

| Package / component | Purpose |
| --- | --- |
| **Linux** | Required operating system |
| **Python 3.10+** (`python` on Arch/CachyOS) | Required to run the application |
| `pacman` | Package inventory on Arch/CachyOS; **required for moving items into quarantine** (moves fail closed if the package inventory cannot be verified) |
| `coreutils` (`du`) | Directory size calculation; not needed for a quick scan without size calculation |
| `procps-ng` (`ps`) | Running-process detection; scanning still works with reduced evidence if unavailable |

### Native GUI — choose one backend

| Backend | Arch Linux / CachyOS packages | Notes |
| --- | --- | --- |
| **GTK4** | `python-gobject gtk4` | Preferred on GTK-oriented desktops such as GNOME and Niri |
| **GTK3** | `python-gobject gtk3` | GTK fallback |
| **Qt6** | `pyside6` **or** `python-pyqt6` | Preferred on KDE Plasma and LXQt |
| **Tk** | `tk` | Fallback; requires X11 or XWayland |

For example, to install the **GTK4 dependencies** on Arch Linux / CachyOS:

```sh
sudo pacman -S --needed python coreutils procps-ng python-gobject gtk4
```

For **Qt6**, install `pyside6` or `python-pyqt6` instead of `python-gobject gtk4`. For **Tk**, install `tk` instead. You do **not** need to install all GUI backends.

### Optional integrations

- `xdg-utils` (`xdg-open`) — opens an item's location in your file manager.
- `flatpak` — detects installed Flatpak applications.
- `snapd` (`snap`) — detects installed Snap applications.
- `systemd` (`systemctl --user`) — provides additional user-service evidence when available.

No `pip install` step or `requirements.txt` is needed for the core application. The app does not install packages automatically or require root privileges to run.

For version-by-version changes, see [CHANGELOG.md](CHANGELOG.md).
