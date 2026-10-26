# Native Polkit test without installing a helper

The desktop already provides its own authentication agent in many GNOME,
KDE Plasma, Xfce and other sessions. The existence of `pkexec` does not
necessarily prove that an agent is running, so this test checks by requesting
actual system authorization.

**No xdg-audit Polkit policy/helper installation is required.** The previous
root-installed experimental helper was removed from the repository. Neither
part of this test authorizes a real quarantine PURGE as root.

## Test A: system Polkit authorization

The GUI button **Test Polkit…** requests authorization to run the single,
trusted system command `/usr/bin/id -u` through `pkexec`. No paths, file
changes, commands from the repository or arbitrary arguments are supplied.
The GUI passes `--disable-internal-agent` so an absent graphical agent is
reported rather than replaced by an invisible text-based password prompt.

The system agent—not xdg-audit—chooses which administrator may authenticate.
The GUI never reads or stores the password. A successful response must be
exactly UID `0`. It proves *only* this fixed authorization action worked,
not that xdg-audit is authorized to perform arbitrary privileged operations.

From an interactive terminal:

```fish
python3 xdg_audit.py --polkit-test-status
python3 xdg_audit.py --polkit-test-auth
```

Enter `AUTH`, then complete the system's prompt. If Polkit denies the
request or no session agent exists, the action fails without touching
files. The status command reports `pkexec_installed`,
`pkexec_trusted`, `system_id_trusted`, `helper_required: false`,
`ready`, and `scope: auth_smoke_only`.

## Test B: permissions under ~/.config

The independent GUI button **Test uprawnień ~/.config…** creates exactly:

```text
~/.config/xdg-audit-polkit-test/
└── pkg/                       # mode 111 (d--x--x--x)
    └── test-only.txt           # mode 000 (----------)
```

Everything belongs to the calling user; no Polkit authentication or root
permissions are required. This reproduces both a directory that can be
traversed but not listed and a file that cannot be read. The test invokes
the standard recursive inventory after granting explicit owner-read
permissions, verifying that both items are now readable.

In the GUI, independent confirmations are required:
`TEST` creates the objects, `ACCESS TEST` changes only the two test
objects' owner-read bits, and `DELETE TEST` deletes only the fixed verified
fixture. Each change takes place after explicit consent; cancellation
leaves the fixture under the path above for later recovery.

In an interactive shell:

```fish
python3 xdg_audit.py --polkit-test-create
python3 xdg_audit.py --polkit-test-repair
python3 xdg_audit.py --polkit-test-delete
```

If the test was interrupted before repair, the cleanup command can remove
the original restricted fixture without requiring root. It first verifies
the marker content and directory entries, then temporarily restores the
minimum owner-write permission needed to remove the verified file. Unknown
files, symlinks, ownership changes and unexpected contents block cleanup;
the tool never deletes another app's files.

**These are intentionally separate tests.** Permission changes on
user-owned objects don't require Polkit; making real root-owned objects
modifiable by an unprivileged GUI would require a separate audited,
root-owned helper. The general Polkit smoke cannot be reused as an
authorization token to bypass that boundary.
