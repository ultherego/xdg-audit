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
Architecture-qualified identifiers are validated in full; malformed qualifiers
discard the listing instead of leaving a partial native inventory labelled healthy.

Bounded dpkg removal history is read from plain and gzip-rotated logs.
Missing logs or access permissions do not establish uninstallation.
Historical records never override current installation. RPM does not have
an unverified parser for changing DNF/Zypper history formats: ambiguous data
remains UNKNOWN/REVIEW and requires additional explicit consent before MOVE.

**CANDIDATE is not verified orphan ownership.** REVIEW/UNKNOWN entries are
not moved by default. The CLI requires `--allow-uncertain` and the separate
`UNCERTAIN` and `MOVE` confirmations. The GUI preserves corresponding
independent confirmations.

## Flatpak inventory integrity

The complete three-column listing validates each application ID using Flatpak's
ASCII, segment and 255-character limit rules before normalizing names for matching.
A single malformed ID discards the partial inventory and blocks MOVE.
Display names may contain Unicode and remain protective aliases; they do not
establish installation of a Flatpak namespace. A healthy empty list is distinct
from a failed or malformed query and still does not verify orphan ownership.

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
`~/.local/share/applications`, plus `~/apps`, `~/Apps`, `~/opt`, `~/.local/opt`,
`/opt` and `$XDG_DATA_HOME/{AppImages,appimages,applications}`. Application
folders under these app roots are inspected one level deep, with at most 64
child directories per root. Launchers in `$XDG_DATA_HOME/applications` can
reference an existing image elsewhere.

Settings in GTK, Qt and Tk accept additional AppImage and binary directories,
one absolute or `~/` path per line. The JSON preference keys are `appimage_dirs`
and `binary_dirs`, each limited to 32 paths. Additional folders are inspected
directly, without recursion. `~/` uses the selected audit HOME; environment
variables and shell expressions are never expanded. Changes trigger a fresh scan
and are reloaded before MOVE. Cancelling Settings writes nothing.

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
Each AppImage/manual-binary probe also has a shared 12,000-entry scan budget;
exceeding a budget reports failed health and blocks MOVE.

## Foreign pacman packages and AUR availability

**foreign ≠ AUR**: foreign pacman records include locally built packages and
packages removed from repositories. AUR origin cannot be proven from the
installed package name. Neither yay nor paru is required.

For a healthy native pacman inventory, scans and `--installed-sources` compare
foreign names against the public `https://aur.archlinux.org/packages.gz` index:

- **AUR name listed:** the same name currently exists in AUR; the installed
  binary's build origin remains unverified.
- **Not listed in AUR:** possibly local, renamed or removed; this is not proof
  of a local build or an uninstalled application.
- **Origin unverified:** metadata failed, timed out or was not queried.

The application downloads the complete public index and sends no installed
package names. Downloads, decompression and elapsed network time are bounded.
Successful metadata is cached in memory for one hour, failures for one minute;
there is no disk cache and scanning does not write preferences.
JSON `foreign_provenance` reports these counts separately from provider health.
AUR metadata is weak explanatory evidence: installed pacman packages remain
ACTIVE regardless of index membership or network errors. MOVE never performs
the AUR request and never uses its result to authorize quarantine.

## Other sources and limits

- A quiet `pacman -Qmq` exit 1 with no output or diagnostics means no filter
  matches and is reported as a healthy empty foreign list. Errors, partial output,
  timeouts and missing tools remain separate states. This informational exception
  never authorizes MOVE or applies to the native `pacman -Qq` query.
- Manual binaries in `~/.local/bin`, `~/bin`, `~/Applications`, `~/.cargo/bin`,
  `~/go/bin`, `~/apps/bin`, `~/Apps/bin`, `~/Applications/bin`, `~/opt/bin`,
  `~/.local/opt/bin`, `/usr/local/bin` and configured extra
  folders provide protective filename hints. Files must be regular and executable;
  they are never run. `/opt` directory names, npm global and pipx add weak hints.
  Missing hints do not prove absence.
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
A separate Ubuntu VM runs actual snapd and `scripts/smoke_snapd.py` as an
unprivileged user. CI builds a local metadata-only snap (`base: none`, no apps
or hooks), installs the base and a disabled parallel instance, and verifies
ACTIVE protection and stale-row MOVE refusal. After removing only the base
fixture, it verifies REVIEW, explicit MOVE/RESTORE/PURGE, exact bytes, idempotence
and preservation of the installed parallel namespace and an unrelated sentinel.
CI removes only its two exact fixture names; it downloads no application from
the Snap Store. The application never installs or removes snaps.
AppImage tests use static fixture files, matching the non-execution contract.

## Sources

- [os-release and ID_LIKE](https://www.freedesktop.org/software/systemd/man/latest/os-release.html)
- [pacman query filters](https://man.archlinux.org/man/pacman.8)
- [AUR bulk metadata and public package index](https://wiki.archlinux.org/title/Aurweb_RPC_interface)
- [dpkg-query and package states](https://manpages.debian.org/bookworm/dpkg/dpkg-query.1.en.html)
- [Flatpak application ID validation](https://github.com/flatpak/flatpak/blob/main/common/flatpak-ref-utils.c)
- [RPM query formats](https://rpm.org/docs/latest/man/rpm-queryformat.7)
- [Snap data locations](https://snapcraft.io/docs/reference/administration/data-locations/)
- [Install modes and snap list columns](https://snapcraft.io/docs/explanation/snap-development/install-modes/)
- [Parallel Snap instances](https://canonical.com/blog/parallel-installs-test-and-run-multiple-instances-of-snaps)
- [AppImage portable data](https://docs.appimage.org/user-guide/portable-mode.html)
