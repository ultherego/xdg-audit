# Polkit integration: isolated permission test

This optional extension proves **real system Polkit authorization** using a
root-owned, installed helper. It does not allow xdg-audit to delete arbitrary
paths, access unrelated user files, or bypass existing PURGE integrity checks.

The helper supports exactly two actions: create one root-owned test directory
under /var/lib/xdg-audit/polkit-selftest/<UID>/authorization-demo with a fixed
marker; separately authorize and verify deletion of that exact marker and
directory. Its UID comes from PKEXEC_UID, not from a user-supplied argument.

## Install the trusted system helper

Review both files in packaging/polkit/ before installation. These commands
copy the files as root; they never *execute source code from the user's Git
working tree as root*. On Arch/CachyOS, run from the repository root:

    sudo install -d -o root -g root -m 0755 /usr/libexec/xdg-audit
    sudo install -o root -g root -m 0755       packaging/polkit/xdg-audit-polkit-helper       /usr/libexec/xdg-audit/xdg-audit-polkit-helper
    sudo install -o root -g root -m 0644       packaging/polkit/io.github.ultherego.xdg-audit.policy       /usr/share/polkit-1/actions/io.github.ultherego.xdg-audit.policy

Check installation and system registration without requesting authorization:

    python3 xdg_audit.py --polkit-test-status
    pkaction --action-id io.github.ultherego.xdg-audit.polkit-selftest --verbose

The action's defaults are auth_admin only for an active local session; it
explicitly denies inactive sessions. The Polkit agent decides which account
can authenticate. xdg-audit never asks for a password directly.

## Test: create an isolated directory

Use the **Test Polkit…** button in the Quarantine tab. Confirm with TEST;
a system Polkit dialog should request administrative authentication.

Alternatively, in an interactive terminal:

    python3 xdg_audit.py --polkit-test-create

Enter TEST when asked, then complete Polkit authentication. The helper
returns a JSON record with status created or already_exists and the
root-owned test directory. It cannot create a directory outside its
hard-coded test namespace.

## Test: delete only the test directory

The GUI presents a separate DELETE TEST confirmation after the fixture
was created. It makes a second Polkit request.

You can also execute:

    python3 xdg_audit.py --polkit-test-delete

Enter DELETE TEST and authenticate. The helper verifies root ownership,
directory structure, exact marker bytes, regular file type and hardlink
count. It removes only the marker file and the now-empty test directory
using fd-relative unlink and rmdir, never recursive deletion.

The UID-specific parent directory remains for subsequent tests.
If an extra file, symlink or unexpected marker appears, the helper refuses
deletion; it never cleans arbitrary user-specified paths.

## Troubleshooting

- If pkexec or the installed helper/policy is absent, the feature refuses
  to start and reports missing trusted installation.
- If no Polkit session authentication agent is available, the GUI request
  fails rather than prompting invisibly in a terminal.
- Code 126 indicates the user cancelled authorization; code 127 indicates
  authorization failure or unavailable agent.
- Policy and helper must be root-owned, not symlinks and never writable by
  non-root users. xdg-audit checks these conditions before launching pkexec.
- Only installed, root-owned code is executed with elevated permissions.
  Neither the GUI nor any repo script runs as root.

## Intentional scope limitation

This demo validates **Polkit itself**, including the actual system password
dialog and a root-only create/delete operation. It does not change
permissions of real root-owned quarantine objects. Such changes require a
separate audited, narrowly-scoped privileged helper and a security review;
there is no sudo/pkexec fallback that runs user-writable source code.
