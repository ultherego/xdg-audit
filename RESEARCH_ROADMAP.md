# xdg-audit — architecture review and roadmap after v1.4.8

> **Historical document (2026-10-25).** This describes the period after
> v1.4.8; several proposals are already implemented in current main.
> Current priorities: [1.7.0 release readiness](docs/release-readiness.md).
> The current [application installation-source contract](docs/installation-source-support.md)
> describes detection and protection of audited applications.

Date: 2026-10-25. Review of local xdg-audit v1.4.7 code and online sources.
The proposals below were not implemented in v1.4.8, apart from two appearance
fixes documented in the README at that time.

## Code findings at the time

- `xdg_audit.py:scan()` listed immediate entries in six scopes and classified
  them using packages, Flatpak, Snap, AppImage, services, processes, PATH,
  desktop entries and pacman history.
- `read_active_names()` queried `pacman`, `flatpak`, `snap`, `ps` and `systemctl`
  on every call and searched for AppImage files.
- `references()` read small text files for suspected directory names in
  selected Niri/DMS/Fish/systemd configurations.
- `disk_sizes()` ran `du -s -B1 -0` in batches of 100 paths, with a 120-second
  timeout per batch. Deep cache/profile trees could dominate elapsed time.
- The GTK4 table used `Gtk.ListBox` and manually constructed `Gtk.Grid` rows;
  `refresh()` rebuilt every visible row.
- `commit_quarantine()` rechecked installations, ownership, inodes, symlinks,
  mounts and the manifest, then used `Path.rename()` on the same device.

## Findings from code and documentation

1. **Native GTK4 table model.** `Gtk.ColumnView` offers visible-cell factories,
   headers, native sorting, resizing and separators, making it a useful
   replacement for manually constructed rows as the list grows.
   [ColumnView](https://docs.gtk.org/gtk4/class.ColumnView.html),
   [list widgets](https://docs.gtk.org/gtk4/section-list-widget.html).
2. **Progress reporting.** GTK distinguishes `ProgressBar.pulse()` for unknown
   work totals from `set_fraction()` for measured progress. The existing pulse
   was appropriate; v1.4.8 did not promise percentages.
   [ProgressBar](https://docs.gtk.org/gtk4/class.ProgressBar.html).
3. **Application-to-XDG knowledge base.** xdg-unused-data stores JSON mappings
   between executables and user paths and intentionally avoids automatic deletion.
   [xdg-unused-data](https://github.com/pawel-0/xdg-unused-data).
4. **OrphyCleaner** combines installed packages, Flatpaks and desktop entries;
   name heuristics alone cannot establish ownership.
   [source](https://github.com/dodog/orphycleaner/blob/main/orphycleaner.py).
5. **pacrid** combines known paths with name variants, supporting separation
   of strong evidence from heuristics.
   [source](https://github.com/ParkerrDev/pacrid).
6. **XDG specification.** Respect absolute `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`,
   `$XDG_STATE_HOME` and `$XDG_CACHE_HOME` values. Configuration, data, state
   and cache have different roles and deletion risks.
   [specification](https://specifications.freedesktop.org/basedir-spec/latest/).
7. **Safe moves.** Same-filesystem `os.rename` is atomic, but still requires
   TOCTOU, collision, symlink and manifest-transaction checks.
   [Python documentation](https://docs.python.org/3/library/os.html#os.rename).

## Historical priorities

### P0 — before extending removal features

- **Classification evidence:** rows and details must show a precise
  *(data source, result)* pair, such as `pacman: brave-browser (brave*)` or
  `desktop: opera.desktop (hint only)`. A matching name does not prove installation.
- **Protection and conflicts:** browser profiles, games, VMs, session state,
  password managers and credentials must not become automatic deletion
  candidates. Shared names and patterns require an ambiguity warning.
- **Quarantine transactions:** test process interruption between `rename()`
  and journal updates, recovery when a planned file has already moved,
  collisions, simulated remounts and symlink replacement. Support safe recovery.
- **Representative datasets:** record expected classifications for `brave`,
  `opera`, `go`, `gh`, `dms`, `solaar`, `wayland-sessions`, Flatpak and manual
  AppImage installations; measure false positives/negatives by installation source.

### P1 — scan performance and usability

- **Phase profiling:** measure package queries, desktop inspection, dependency
  analysis, references and `du` in milliseconds on a real user HOME.
  Identify the slowest phase from measurements.
- **Two-stage scanning:** show initial classifications quickly, then measure
  sizes later or on request and update only changed rows.
- **Progress phases:** show phases such as Packages, Flatpak, Configuration
  and Sizes; show percentages only when a phase has a known work total.
- **Cancellation:** provide a Cancel button, interruption checks between
  phases and subprocess handling. The worker thread then in use lacked this.
- **Gtk.ColumnView:** move GTK4 to a virtualized model with `Gtk.SortListModel`
  and `Gtk.FilterListModel`, retaining optional Qt/Tk backends.

### P2 — product usefulness

- **Persistent `KEEP` and aliases:** user TOML/JSON under
  `$XDG_CONFIG_HOME/xdg-audit`, with preview and export. Explicit keep decisions
  should survive rescanning; no automatic deletion.
- **Scan history:** save only on explicit request, comparing classifications,
  explanations, sizes and current packages.
- **Sorting and filters:** size, risk, evidence source, age, new entries and
  previously uninstalled applications.
- **Content inspection:** show metadata and safe immediate-child names;
  do not execute scripts or open secret contents without a request.
- **Interoperable reports:** versioned JSON with `evidence`, `confidence`,
  `risk_flags`, `scan_errors` and `source_health`, plus compatibility tests.

## Acceptance criteria for subsequent versions

- ACTIVE classification does not rely solely on a `foo*` match to an unrelated library.
- Failed database reads cannot produce a confident CANDIDATE; source errors are visible.
- Rescanning keeps the GTK main loop responsive and blocks quarantine moves during scanning.
- Interrupted transactions recover without manual JSON repair.
- GTK4 retains visible headers, single-click details, system themes and keyboard access.
- CI tests GTK4 with a real display server; Tk tests do not establish GTK4 appearance.
