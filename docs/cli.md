# CLI

[Back to README](../README.md)

```fish
python3 xdg_audit.py --help
python3 xdg_audit.py --scope config --json > audit.json
python3 xdg_audit.py --scope config --compare audit.json
python3 xdg_audit.py --scope config --remove  # Interactive confirmation
python3 xdg_audit.py --list-quarantine
python3 xdg_audit.py --restore RUN_ID         # Interactive confirmation
python3 xdg_audit.py --quarantine-info RUN_ID
python3 xdg_audit.py --purge RUN_ID --dry-run
python3 xdg_audit.py --purge RUN_ID           # Explicit PURGE confirmation
python3 xdg_audit.py --purge-expired          # Retention preview
python3 xdg_audit.py --cleanup-history RUN_ID --dry-run
python3 xdg_audit.py --cleanup-expired-history # 30 days after PURGE
python3 xdg_audit.py --cleanup-all-history    # Preview all completed history
python3 xdg_audit.py --cleanup-all-history --execute # Explicit HISTORY confirmation
python3 xdg_audit.py --polkit-test-status      # Read-only existing Polkit check
python3 xdg_audit.py --polkit-test-auth        # AUTH + native Polkit id -u
python3 xdg_audit.py --polkit-test-create      # TEST: create ~/.config fixture
python3 xdg_audit.py --polkit-test-repair      # ACCESS TEST: owner-only repair
python3 xdg_audit.py --polkit-test-delete      # DELETE TEST: clean test-only fixture
```

Available scopes: `all`, `config`, `data`, `state`, `cache`, `flatpak`, `snap`, `dotfiles`.

Completed PURGE operations remain visible in the GUI as **PURGED** until
their manifest is cleaned up; that history may be automatically removed 30
days after full PURGE, but only with explicit opt-in to automatic retention.
Incomplete or corrupted journals are never auto-removed.

**Normal operation:** In GTK, Qt and Tk, **Delete permanently…** checks the
quarantine and, when needed, automatically opens **Check access…**.
For user-owned files/directories with restricted permissions it offers
an individually confirmed `ACCESS` change. If the original inventory was
unsealed, it then requires separate `ADOPT` confirmation, followed by a
fresh preflight and the usual independent `PURGE` confirmation.

For advanced/manual checks, the **CLI** still offers isolated, optional
Polkit and ~/.config test fixtures (see
[Polkit and access self-tests](polkit-selftest.md)). These test controls
are intentionally **not present in the GUI**. Polkit does not elevate
quarantine operations: root-owned files remain blocked until a separately
audited and packaged privileged helper is available.

See [Quarantine lifecycle](quarantine-lifecycle.md) for recovery,
history-only cleanup, manual/automatic retention, user-scoped systemd
timer, legacy adoption, and safeguards.

## JSON evidence quality

A `--quick --json` scan returns `size_bytes: null` when size has **not been
measured**. This is different from an empty file or directory with size `0`;
`size_calculated` distinguishes these cases.

`evidence_level` distinguishes `installed_evidence`, `protective_hint`,
`historical_only`, `policy_protected` and `unknown`. Package-removal history
is only a hint. `orphan_ownership_verified: false` means the application has
not verified that the data can be removed safely. Every CANDIDATE based only
on history also carries `risk_flags: ["unverified_owner", "history_only"]`
and still requires explicit MOVE consent and fresh verification before PURGE.
