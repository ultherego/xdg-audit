# Native packages and tagged releases

GitHub Actions is the release builder. Local scripts are the same build entry
points used for development and troubleshooting; local builds do not publish.

Production package hosting and AUR publication require the owner setup below.
The URLs in this document become available after the first signed publication.
The existence of this document does not establish that a package repository or
an AUR package has already been published.

## Artifacts and versions

| Source/tag | DEB | RPM | Arch |
|---|---|---|---|
| `v1.7.0-rc2` | `1.7.0~rc2-1`, `all` | `1.7.0~rc2-1`, `noarch` (with Fedora dist suffix) | `1.7.0rc2-1`, `any` |
| `v1.7.0` | `1.7.0-1`, `all` | `1.7.0-1`, `noarch` | `1.7.0-1`, `any` |

The tag must equal `v` plus `VERSION` in `xdg_audit.py`. Prereleases publish to
`candidate`; final versions publish to `stable`. Their APT package pools are
separate, so an RC cannot leak into the stable index. Published package versions
and tag receipts are immutable. Correct an already published build with a new
application version/tag rather than replacing its bytes.

Every PR and main commit builds and tests:

- Ubuntu 24.04: DEB installation/upgrade through a signed APT repository.
- Fedora 43: RPM installation/upgrade through DNF with package signatures and
  signed repository metadata both required.
- Arch Linux: checksum-pinned PKGBUILD, `makepkg`, package installation/upgrade,
  and a generated AUR recipe containing `PKGBUILD`, `.SRCINFO` and `LICENSE`.
- Installed CLI, imports and a mapped GUI outside the source checkout as an
  unprivileged user; exact runtime bytes and desktop-file validation.
- Removal preserving unrelated user files. APT/DNF must reject altered packages
  and repository metadata. No production credentials are used by these tests.
- The production publisher against a temporary local Git remote: initial
  publication, repeat publication, metadata renewal and corruption refusal.

These packages use a system Python interpreter and system GUI libraries. They
do not install a virtual environment, pip dependencies, an autostart or a daemon.
Tk provides an X11/XWayland fallback. GTK4 or Qt6 is needed for native Wayland;
the DEB/RPM recommend GTK and the PKGBUILD lists the toolkit alternatives.
The initial compatibility matrix above does not certify every DEB/RPM distro.

## Installed paths

| Path | Purpose |
|---|---|
| `/usr/bin/xdg-audit` | Launcher forwarding quoted arguments to system Python |
| `/usr/lib/xdg-audit/` | Explicitly reviewed Python runtime and local icons |
| `/usr/share/applications/io.github.xdgaudit.desktop` | System desktop launcher |
| `/usr/share/icons/hicolor/` | 128px and 512px icons |
| `/usr/share/licenses/xdg-audit/LICENSE` | MIT license |
| `/usr/share/doc/xdg-audit/` | Readme, release notes, changelog and copyright |

Package installation and removal never touch user configuration or quarantine.
The application still refuses to perform its normal operations as root. Run
`xdg-audit` as your regular user after installing the package with the OS manager.
The optional retention helper is installed at
`/usr/lib/xdg-audit/scripts/install_retention_timer.py`; it remains opt-in and is
never invoked by a package install/update/remove hook.
Remove an earlier checkout-based desktop registration using the
[desktop installer](desktop-installation.md) if it shadows the system launcher.

## One-time owner setup

Before creating the first new release tag, configure these in GitHub repository
**Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Secret | `PACKAGES_SIGNING_KEY` | Armored private dedicated CI signing key or signing subkey |
| Variable | `PACKAGES_SIGNING_FINGERPRINT` | Full fingerprint of its public primary key |
| Secret, optional | `AUR_SSH_PRIVATE_KEY` | Dedicated AUR account SSH private key |
| Variable, optional | `AUR_KNOWN_HOSTS` | AUR SSH host-key entry verified independently against Arch's published fingerprints |
| Variable, optional | `AUR_PUBLISH_ENABLED` | `true` after the AUR account/key/host pin are configured |

The `package-signing` and `aur` Actions environments can be given owner approval
rules. The workflows declare their required permissions; publishing needs
`contents: write`, and the optional tag-creation workflow also needs `actions: write`.
No separate hosting account, GitHub Pages configuration or PAT is required.
Public APT/RPM snapshots live on the `packages` branch and are served over HTTPS
by `raw.githubusercontent.com`.

The current unattended signer expects a dedicated key/subkey without a
passphrase, stored as an encrypted Actions secret. Keep an offline backup and
revocation material. Do not remove protection from a personal signing key.
Hardware/external signing and automatic key rotation require a separate setup;
the publisher rejects an unexpected signing fingerprint.

For a new, dedicated CI key, the following example uses fish and GnuPG on the
owner's trusted computer. Replace the fingerprint after checking the listing:

```fish
gpg --batch --pinentry-mode loopback --passphrase '' --quick-generate-key 'xdg-audit CI package signing' rsa3072 sign 1y
gpg --list-secret-keys --with-fingerprint
set signing_fingerprint REPLACE_WITH_THE_FULL_FINGERPRINT
gpg --armor --export-secret-keys $signing_fingerprint | gh secret set PACKAGES_SIGNING_KEY --repo ultherego/xdg-audit
gh variable set PACKAGES_SIGNING_FINGERPRINT --body $signing_fingerprint --repo ultherego/xdg-audit
```

The private key is sent directly to the secret store, never to Git, logs, a
release asset or the public package branch. Production keys are never generated
by the workflow. Ephemeral keys used by CI trust tests are not production keys.

For AUR, register the dedicated SSH public key in the AUR account first. Read the
[AUR submission rules](https://wiki.archlinux.org/title/AUR_submission_guidelines),
check that the package name is available or maintained by this account, and
verify the AUR host keys before setting `AUR_KNOWN_HOSTS`. The publisher never
disables host verification or force-pushes an AUR repository.

## Creating a release

After merging the intended version and confirming green main CI, run **Actions →
Create release tag → Run workflow**, selecting `main` and the exact source
version without `v`. This creates an annotated tag and explicitly starts the
full test/release workflow for that tag. A mismatched version, missing signing
fingerprint, failed main CI or existing tag prevents tag creation.

Alternatively, create and push an annotated tag from a trusted checkout:

```fish
git switch main
git pull --ff-only
git tag -a v1.7.0-rc2 -m 'xdg-audit v1.7.0-rc2'
git push origin refs/tags/v1.7.0-rc2
```

Use `git tag -s` when a maintainer signing key is configured. Never move an
already published tag. An ordinary branch push builds test artifacts only.

The tag pipeline waits for the complete application, GUI, quarantine and native
package checks. It then signs/publishes APT and RPM, uploads signed release
assets, and creates a GitHub Release. RC/dev tags become GitHub prereleases.
AUR submission is opt-in and runs only for final versions; the tested RC recipe
is still available as a release asset for explicit local builds. The separate
development recipe is [packaging/arch/PKGBUILD](../packaging/arch/PKGBUILD) with
checked-in `.SRCINFO`; it follows `main` as `xdg-audit-git`.

Release assets include DEB, signed RPM, an Arch package, the AUR recipe ZIP,
source ZIP/tar.gz, the public key/fingerprint, build receipt and signed SHA-256
checksums. The same signed RPM bytes are served by the RPM repository.
If a later release stage fails, rerun failed jobs for the same tag/artifacts;
the publisher validates its existing receipt before reusing signed packages.

The separate **Signed package repository** workflow refreshes both existing
channels weekly. APT metadata expires after 30 days; monitor workflow failures
and key expiry. Manual runs of that workflow renew existing repositories only.
Keep older packages/by-hash indexes; deleting them can break clients that fetched
an earlier signed index. The public branch contains no executable workflow code.

## Adding the repository after its first publication

The first fingerprint must be obtained from the maintainer through a trusted
channel and checked before installing the key. A downloaded key alone does not
establish its authenticity. The examples below use fish and `candidate` because
the current source is an RC; use `stable` only after its first final release.

```fish
set package_repo https://raw.githubusercontent.com/ultherego/xdg-audit/packages
set channel candidate
curl --fail --location $package_repo/xdg-audit-keyring.gpg --output xdg-audit.gpg
gpg --show-keys --with-fingerprint xdg-audit.gpg
```

After verifying the full fingerprint, on Debian/Ubuntu:

```fish
sudo install -d -m 0755 /etc/apt/keyrings
sudo install -m 0644 xdg-audit.gpg /etc/apt/keyrings/xdg-audit.gpg
curl --fail --location $package_repo/xdg-audit-$channel.sources --output xdg-audit.sources
sudo install -m 0644 xdg-audit.sources /etc/apt/sources.list.d/xdg-audit.sources
sudo apt update
sudo apt install xdg-audit
```

On Fedora, after the same fingerprint verification:

```fish
curl --fail --location $package_repo/xdg-audit-$channel.repo --output xdg-audit.repo
sudo install -m 0644 xdg-audit.repo /etc/yum.repos.d/xdg-audit.repo
sudo dnf install xdg-audit
```

Confirm that DNF's imported-key fingerprint matches the verified fingerprint.
The generated configuration requires both `gpgcheck=1` and `repo_gpgcheck=1`.
APT uses a dedicated `Signed-By` keyring. Neither configuration disables trust
checks or uses the deprecated global `apt-key` trust store.

For Arch/CachyOS, AUR distributes source recipes rather than a pacman binary
repository. After actual AUR publication, use the normal AUR workflow for
`xdg-audit` (release) or submit/use the provided `xdg-audit-git` recipe. No entry
in `/etc/pacman.conf` is needed for AUR. Review the PKGBUILD before building.

## Local troubleshooting

```fish
python3 packaging/build_deb.py --output-dir /tmp/xdg-audit-deb
python3 packaging/build_rpm.py --output-dir /tmp/xdg-audit-rpm
python3 scripts/build_archives.py --output-dir /tmp/xdg-audit-source
```

DEB needs `dpkg-deb`; RPM needs native `rpmbuild`. `repository.py` needs
`apt-ftparchive`, GnuPG, RPM signing tools and `createrepo_c`, with an existing
signing key in a separately supplied `GNUPGHOME`. Its output must be an explicit
staging directory. The destructive native-package test harness refuses to run
outside a disposable GitHub Actions container.

References: [APT trust](https://manpages.debian.org/stable/apt/apt-secure.8.en.html),
[RPM signing](https://rpm.org/docs/6.0.x/man/rpmsign.1),
[Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets),
[GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token).
