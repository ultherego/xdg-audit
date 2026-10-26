# Installation sources: Arch, APT/dpkg, RPM, Flatpak, Snap and AppImage

This document covers application detection and protection of user data.
APT/RPM support does not mean building xdg-audit distribution packages.
The application does not install or uninstall software.

## Native package database and MOVE authorization

| OS family | Currently installed package database | Behavior |
| --- | --- | --- |
| Arch/CachyOS and derivatives | `pacman -Qq`; `pacman -Qmq` for foreign packages | ACTIVE evidence, pacman history and explicitly confirmed quarantine |
| Debian/Ubuntu/APT and derivatives | `dpkg-query -W` with complete package status | ACTIVE evidence, dpkg history including APT operations, and explicitly confirmed quarantine |
| Fedora/RHEL/openSUSE and derivatives | `rpm -qa --qf` | ACTIVE evidence and explicitly confirmed quarantine; no inferred DNF/Zypper removal history |

The native database is selected using `ID`, then `ID_LIKE`, from `os-release`.
Installing a foreign package manager does not replace the native database.
Unknown OS families cannot authorize MOVE. Existing quarantine runs remain
eligible for separately verified RESTORE/PURGE under the journal safeguards.
The Python API retains compatibility with older eight-field pacman inventory tuples.

Text reports identify the selected database as `NATIVE`, show its `PACKAGES`
count and report `SOURCE_HEALTH` separately. JSON statistics add
`native_packages` alongside `native_package_source` and `installed_sources`;
the existing `pacman_packages` field remains available. Counts represent unique
installed package names, so dpkg architecture qualifiers and protective aliases
do not count the same name repeatedly. A count does not establish healthy
inventory or permission to MOVE.

Every MOVE reads the providers again. The native database must be read
successfully and contain package records. Missing, failed, partial and
unknown-family inventories block the operation. Provider health and record
count are separate facts: an empty database may be read successfully but is
not sufficient to authorize moving user data.

APT uses dpkg's installed database; the human-oriented `apt list` output is
not parsed. `deinstall ok installed` and `purge ok installed` still describe
present packages. Residual configuration (`config-files`) is not treated as
an active installation. States such as `unpacked`, `half-configured` or
`reinstreq` produce `partial` health and block MOVE until the user repairs
the package database. xdg-audit does not perform that repair.

Bounded dpkg removal history is read from plain and gzip-rotated logs.
Missing logs or access permissions do not establish uninstallation.
Historical records never override current installation. RPM does not have
an unverified parser for changing DNF/Zypper history formats: ambiguous data
remains UNKNOWN/REVIEW and requires additional explicit consent before MOVE.

**CANDIDATE is not verified orphan ownership.** REVIEW/UNKNOWN entries are
not moved by default. The CLI requires `--allow-uncertain` and the separate
`UNCERTAIN` and `MOVE` confirmations. The GUI preserves corresponding
independent confirmations.

## Snap user-data namespace

The `snap` scope contains only immediate entries under `~/snap` and is
available in the CLI, GTK, Qt and Tk. A read-only scan:

```fish
python3 xdg_audit.py --scope snap --quick --json
```

- `snap list` runs with a fixed C locale. The complete header, six columns,
  revision and instance identifiers are validated. Malformed records discard
  partial inventory results.
- Identifiers are exact: `firefox` and `firefox_work` are different instances.
  A native Firefox package does not establish a Snap installation.
- Installed instances, including disabled instances, remain ACTIVE. An instance
  not verified as installed becomes REVIEW, without automatic deletion eligibility.
- Rechecking before MOVE blocks an instance installed after the scan.
  A failed or absent Snap provider blocks MOVE in the Snap scope.
- RESTORE and PURGE use the same v3 journal, inode checks, SHA-256 inventory
  and explicit confirmations as other scopes.

System data in `/var/snap`, mounts under `/snap` and snapshots under
`/var/lib/snapd` are outside this user-data audit.
The Flatpak scope similarly requires a healthy inventory and exact application
ID; a native package name does not establish ownership of Flatpak data.

## AppImage

Detection is static and bounded. It inspects immediate `*.AppImage` files in
`~/Applications`, `~/AppImages`, `~/Downloads`, `~/.local/bin`, `~/bin` and
`~/.local/share/applications`, plus desktop launchers in
`$XDG_DATA_HOME/applications`.

Launchers can identify images elsewhere, including paths containing spaces.
A safe, existing file must be referenced by direct `Exec` (including a simple
`env` wrapper), `TryExec` or `X-AppImage-Path`. A title or stale launcher
without an existing image is not installed-application evidence.
The detector does not interpret `sh -c` or arbitrary wrapper scripts.

Filename aliases remove common version and architecture suffixes. For example,
`Obsidian-1.8.2-x86_64.AppImage` also protects the name `obsidian`.
Adjacent portable-data names ending in `.AppImage.home` and `.AppImage.config`
are recognized as protective aliases. This does not add a whole-disk scan or
move application binaries. Portable directories outside the supported XDG
scopes are not audited here.

Images are never executed or mounted, and `Exec` commands are never run.
Symlinks and symlinked ancestors are not followed. Launcher size and directory
entry counts are bounded; inspection failures do not masquerade as complete
inventories. Absence is not proof of AppImage uninstallation. An image found
during the fresh pre-MOVE inventory blocks moving matching XDG data.
Image-file counts are kept separate from protective filename/display aliases.

## Other sources and limits

- **foreign ≠ AUR**: pacman foreign records also include local packages and
  packages no longer available from repositories. Neither yay nor paru is required.
- Manual binaries, `/opt` directories, npm global and pipx provide protective
  hints. Missing hints do not prove absence; custom prefixes may not be covered.
- Protection for secrets, profiles, backups, games and session data remains active.
- Installed-application evidence does not verify XDG-directory ownership.
  `orphan_ownership_verified` remains `false`.

## Verification

Tests cover native database selection, incomplete output, timeouts, installation
after scanning, Snap/Flatpak namespace isolation, static AppImage metadata,
non-execution of binaries, and fixture-only MOVE/RESTORE/PURGE.

Before archive building, CI requires regressions and
`scripts/smoke_native_sources.py` to run as an unprivileged user on Arch Linux
(pacman), Ubuntu 24.04 (dpkg) and Fedora 43 (RPM), using real native package
inventories. Each run verifies that installed package data is ACTIVE and refuses
MOVE, then checks explicit MOVE/RESTORE/PURGE on unrelated disposable data,
including exact hashes, idempotence and an untouched sentinel.
Arch coverage exercises the native package-manager family used by CachyOS;
it does not claim a separate CachyOS desktop-session test.
Snap parser and lifecycle coverage uses fixtures; it does not claim a live
snapd installation inside the test container. AppImage tests use static fixture
files, matching the non-execution contract.

## Sources

- [os-release and ID_LIKE](https://www.freedesktop.org/software/systemd/man/latest/os-release.html)
- [dpkg-query and package states](https://manpages.debian.org/bookworm/dpkg/dpkg-query.1.en.html)
- [RPM query formats](https://rpm.org/docs/latest/man/rpm-queryformat.7)
- [Snap data locations](https://snapcraft.io/docs/reference/administration/data-locations/)
- [Install modes and snap list columns](https://snapcraft.io/docs/explanation/snap-development/install-modes/)
- [Parallel Snap instances](https://canonical.com/blog/parallel-installs-test-and-run-multiple-instances-of-snaps)
- [AppImage portable data](https://docs.appimage.org/user-guide/portable-mode.html)
