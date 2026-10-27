<p align="center">
  <img src="assets/xdg-audit-128.png" alt="xdg-audit icon" width="88">
</p>

<h1 align="center">xdg-audit</h1>
<p align="center"><strong>Find leftover Linux application files. Keep control of your data.</strong></p>
<p align="center">Read-only by default · Recoverable quarantine · Native GTK / Qt / Tk desktop UI</p>

<p align="center">
  <a href="https://github.com/ultherego/xdg-audit/actions/workflows/tests.yml"><img alt="Build and tests" src="https://github.com/ultherego/xdg-audit/actions/workflows/tests.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/ultherego/xdg-audit/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/ultherego/xdg-audit?include_prereleases&style=flat-square&color=fab387&labelColor=1e1e2e"></a>
  <img alt="Python 3.10 and newer" src="https://img.shields.io/badge/Python-3.10%2B-fab387?style=flat-square&labelColor=1e1e2e">
  <img alt="Linux" src="https://img.shields.io/badge/platform-Linux-89b4fa?style=flat-square&labelColor=1e1e2e">
  <img alt="No automatic deletion" src="https://img.shields.io/badge/deletion-manual%20only-a6e3a1?style=flat-square&labelColor=1e1e2e">
</p>

xdg-audit scans user-scoped configuration, data, state, cache, Flatpak/Snap directories and selected dotfiles. It highlights **possible leftovers** while distinguishing active, protected and uncertain application data. **Nothing is deleted automatically.**

## 🖥️ Preview

<details>
<summary><strong>🔎 Overview</strong> — click the screenshot to expand inside this README

<img src="docs/screenshots/overview.webp" alt="xdg-audit overview screenshot; click to expand" width="760">
</summary>

<img src="docs/screenshots/overview.webp" alt="Full-size xdg-audit overview screenshot" width="100%">

</details>

<details>
<summary><strong>📸 Browse all 8 other screenshots</strong> — click any thumbnail to expand it below</summary>

<details>
<summary><strong>Configuration</strong> — View configuration leftovers · click to enlarge

<img src="docs/screenshots/configuration.webp" alt="xdg-audit Configuration screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/configuration.webp" alt="xdg-audit Configuration full-size screenshot" width="100%">

</details>

<details>
<summary><strong>Data</strong> — Review application data · click to enlarge

<img src="docs/screenshots/data.webp" alt="xdg-audit Data screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/data.webp" alt="xdg-audit Data full-size screenshot" width="100%">

</details>

<details>
<summary><strong>State</strong> — Inspect state directories · click to enlarge

<img src="docs/screenshots/state.webp" alt="xdg-audit State screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/state.webp" alt="xdg-audit State full-size screenshot" width="100%">

</details>

<details>
<summary><strong>Cache</strong> — Inspect caches · click to enlarge

<img src="docs/screenshots/cache.webp" alt="xdg-audit Cache screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/cache.webp" alt="xdg-audit Cache full-size screenshot" width="100%">

</details>

<details>
<summary><strong>Flatpak</strong> — Review Flatpak application data · click to enlarge

<img src="docs/screenshots/flatpak.webp" alt="xdg-audit Flatpak screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/flatpak.webp" alt="xdg-audit Flatpak full-size screenshot" width="100%">

</details>

<details>
<summary><strong>Dotfiles</strong> — Inspect selected home-level entries · click to enlarge

<img src="docs/screenshots/dotfiles.webp" alt="xdg-audit Dotfiles screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/dotfiles.webp" alt="xdg-audit Dotfiles full-size screenshot" width="100%">

</details>

<details>
<summary><strong>Quarantine</strong> — Preview and restore quarantined entries · click to enlarge

<img src="docs/screenshots/quarantine.webp" alt="xdg-audit Quarantine screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/quarantine.webp" alt="xdg-audit Quarantine full-size screenshot" width="100%">

</details>

<details>
<summary><strong>Settings</strong> — Choose scan scope, language and keep rules · click to enlarge

<img src="docs/screenshots/settings.webp" alt="xdg-audit Settings screenshot thumbnail" width="480">
</summary>

<img src="docs/screenshots/settings.webp" alt="xdg-audit Settings full-size screenshot" width="100%">

</details>

</details>

<sub>Screenshots: GTK4 on Niri / Wayland, captured before the final RC2 safety fixes. Counts, classifications and quarantine actions may differ in the current version. User paths are replaced with neutral, illustrative paths; pointer and individual quarantine run identifiers have been removed. These are real application screens, not UI mock-ups.</sub>

## ✨ Features

| | Capability | Details |
|:--:|---|---|
| 🔍 | **Evidence-based audit** | `CANDIDATE`, `REVIEW`, `UNKNOWN`, `ACTIVE`, `PROTECTED` with explanations and package/process evidence |
| 🛡️ | **Safety-first cleanup** | Explicit selection, protected data, fail-closed inventory checks, no-overwrite moves |
| ♻️ | **Recoverable quarantine** | Manifest-backed moves and restores, inode/device/type verification for new manifests |
| 🖥️ | **Native interfaces** | GTK4/GTK3, Qt6 and Tk; automatically chooses an already installed backend |
| 🌐 | **English & Polish** | Change UI language without rescanning |
| 📂 | **Focused workflow** | Scope tabs, search, sorting, quick scan, progress, cancellation and directory sizes |
| 📊 | **Portable reports** | JSON export and comparison against a prior audit |
| 🧩 | **Personal controls** | Keep rules and app/package aliases |

Flatpak and Snap tabs are hidden after a complete scan when their integration
is unavailable and no leftover data was found. Existing data and failed probes
keep the corresponding tab accessible. Dialogs fit their contents with 20 px
internal padding and scroll long messages within the available screen area.

## 🚀 Get started

**Linux + Python 3.10+**. The command-line engine uses the Python standard library. There is no `pip install` step or automatic dependency installer.

```bash
git clone https://github.com/ultherego/xdg-audit.git
cd xdg-audit
python3 xdg_audit.py
```

The command launches an available GUI backend. To scan read-only in a terminal:

```bash
python3 xdg_audit.py --scope all
```

### 🧰 Native GUI backends

Install **one** backend using your distribution's package manager (Arch Linux / CachyOS names):

| GUI | Packages |
|---|---|
| GTK4 (Niri, GNOME) | `python-gobject gtk4` |
| GTK3 fallback | `python-gobject gtk3` |
| Qt6 (KDE Plasma, LXQt) | `pyside6` **or** `python-pyqt6` |
| Tk (X11 / XWayland fallback) | `tk` |

```bash
# GTK4
sudo pacman -S --needed python python-gobject gtk4

# Or Qt6
sudo pacman -S --needed python pyside6
```

**System tools:** `coreutils` (`du`) for directory sizes, `procps-ng` (`ps`) for process evidence. The native database (`pacman`, `dpkg-query` or `rpm`, selected using `os-release`) must be verified before quarantine moves. Missing, incomplete or failed inventories block MOVE. Optional integrations: `flatpak`, `snap`, `systemctl --user`, and `xdg-open`.

### Installed-application sources

The `npm_global` and `pipx` providers inspect selected directory names without
executing package code. Their presence protects matching data from MOVE;
their absence does not establish that an application was uninstalled.
`flatpak_app_ids` counts canonical application IDs separately from display aliases.

These sources describe how **audited applications** were installed. They are
independent of how xdg-audit itself is distributed.

```fish
python3 xdg_audit.py --installed-sources
```

Text scan reports identify the native database, unique installed package-name
count and source health. JSON reports expose `native_package_source` and
`native_packages` while retaining the existing pacman statistics.

The read-only diagnostic reports provider health for pacman, foreign packages,
Flatpak, Snap, AppImage, installed DEB/RPM packages, and protective hints for
manual binaries, including Cargo/Go bins and `/opt` directory hints.
Foreign pacman packages are compared with the public AUR name index: names
currently listed in AUR, unlisted names (possibly local, renamed or removed),
and unavailable metadata are reported separately. This does not verify build
origin. No installed names are sent, no disk cache is written, and AUR metadata
cannot authorize MOVE.

On Debian/Ubuntu and RPM-family systems, MOVE verifies the actual native
package database without requiring pacman. Inventories are read again before
each operation. Failed queries, timeouts, partial dpkg configuration and unknown
OS families block MOVE. REVIEW/UNKNOWN entries still require separate
acknowledgement of uncertain ownership.

The **Snap** scope covers `~/snap`, distinguishes exact instance IDs such as
`firefox` and `firefox_work`, and requires a healthy Snap inventory before MOVE.
**AppImage** detection recognizes versioned filenames, apps/opt/XDG data
locations, one application-directory level and safe launchers pointing to existing
images elsewhere. **Settings** in every GUI accepts extra AppImage and binary
folders, one absolute or `~/` path per line (`appimage_dirs` / `binary_dirs` in
the saved JSON preferences). Custom folders are inspected directly.
Images, `Exec` commands and wrapper scripts are never executed.

```fish
python3 xdg_audit.py --scope snap --quick --json
```

## 🛡️ Safety model

| Status | Meaning |
|---|---|
| `CANDIDATE` | Possible leftover — **not a guarantee of safe removal** |
| `REVIEW` / `UNKNOWN` | Uncertain ownership; additional manual confirmation is required |
| `ACTIVE` / `PROTECTED` | Cannot be moved to quarantine |

- Scans do not modify data. The user must explicitly select and confirm every move.
- With `--remove`, selected entries are **moved, not permanently deleted**, into `~/.local/share/xdg-audit-quarantine/`.
- Before a move the application revalidates filesystem and package evidence, refuses cross-filesystem moves, and never overwrites the destination.
- New v3 manifests bind restores to the original device, inode and file type and include a recursive SHA-256 inventory for later verified purge. Earlier manifests remain restore-capable; old v3 runs require explicit inventory adoption before purge.
- Cancelled and unfinished scans cannot authorize quarantine operations.
- Permanent deletion (`PURGE`) requires its own explicit confirmation and strict recursive verification; automatic retention is disabled unless opted into.

> [!CAUTION]
> File ownership is inherently ambiguous. Inspect each candidate and keep backups of anything important. Quarantine is **not** a replacement for a backup.

## ⌨️ CLI

[CLI usage and JSON evidence](docs/cli.md)

## 🧭 Project roadmap

[Project roadmap and remaining work](docs/project-roadmap.md)

## 🧪 Testing & release status

[Testing and release status](docs/testing-and-release-status.md)

## License

xdg-audit is available under the [MIT License](LICENSE), copyright 2026 Ulther Ego (ultherego).
Optional GTK/Qt/Tk dependencies retain their own licenses and are not bundled
with the source archives.

## Repository language

Repository documentation, comments and developer-facing text are written in
English. Polish is reserved for the application localization and its tests.
Documentation refers to interface controls by their English labels.
