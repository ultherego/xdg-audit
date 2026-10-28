# Independent security review handoff

[Release checklist](release-readiness.md) · [Evidence protocol](release-verification-evidence.md)

**Current status: accepted on the owner's report (2026-10-28).** The owner
confirmed that a second person completed the independent review and that it
was satisfactory. The [acceptance record](owner-acceptance-2026-10-28.md)
identifies the application baseline and the details not separately supplied.
This guide is a reusable handoff for future changes; it does not manufacture
a reviewer identity, raw report or additional review by release automation.

## Pin the review target

Record the full commit SHA and a clean checkout before starting. Include all
merged safety changes, including device revalidation, retention consent,
nonblocking journal reads and the latest confirmation-keyboard changes.
If code changes during review, record the replacement SHA and re-review the
affected scope. A report referring only to a moving branch is insufficient.

## Review map

| Area | Source entry points | Questions and evidence |
|---|---|---|
| MOVE authorization | `xdg_audit.py`: `commit_quarantine`, `_safe_rename_noreplace`; `xdg_sources.py` | Are package/provider inventories fresh and complete? Do protection, ownership, exact namespace and uncertain-consent checks precede mutation? Can a path substitution, mount or collision bypass them? |
| Journals and inventory | `xdg_quarantine_lifecycle.py`: `_open_path`, `_load_manifest`, `read_manifest`, `_write_manifest`, `capture_inventory` | Check descriptor anchoring, symlink/hardlink refusal, regular-file/device/owner limits, FIFO opens, bounded reads, hashes and error cleanup. Examine durability claims separately from actual syscall guarantees. |
| PURGE and recovery | `inspect_run`, `purge_run`, `_delete_entry`, `_delete_children`, `recover_manifest_temps` | Inspect complete preflight, untracked/changed content, final identity checks, partial deletion and interrupted journals. Verify outside sentinels and failed journal writes cannot silently authorize further deletion. |
| RESTORE and legacy runs | `xdg_audit.py`: `restore_quarantine_run`; `xdg_quarantine_legacy.py`; `xdg_quarantine_lifecycle.py`: `adopt_legacy_run` | Check no-overwrite behavior, v3 identity enforcement, complete namespace validation, interrupted-rename reconciliation and explicit limits of older formats. Current inventory adoption cannot invent historical proof or grant PURGE consent. |
| Btrfs identity | `xdg_filesystem.py`; `device_revalidation_plan`, `revalidate_device` | Check FSID/subvolume ID/UUID binding, snapshot refusal, exact inventory equality, preview-token freshness, the atomic receipt and explicit legacy limitations. Inode equality alone is insufficient. |
| Permissions and retention | `xdg_access.py`, `xdg_retention.py`, `xdg_quarantine_history.py`; CLI automatic-purge path | Check narrowly scoped owner permission repair, foreign-data refusal, default-off policy, age calculation, completed-history checks and refusal of automatic PURGE after REVALIDATE. |
| Confirmation UI | `xdg_gui_gtk.py`, `xdg_gui_qt.py`, `xdg_gui_tk.py`, `xdg_gui_dialogs.py` | Verify exact tokens, empty/incorrect input, cancellation, Return/keypad Enter and one operation per confirmation. ACCESS/ADOPT/REVALIDATE do not grant subsequent PURGE consent. Multiline Settings Enter must remain a newline. |
| Publication and trust | `packaging/install_payload.py`, `repository.py`, `publish_repository.py`, `publish_aur.py`; release workflows | Inspect explicit artifact inputs, signing fingerprint checks, immutable versions/receipts, APT/RPM authentication, tamper refusal, AUR host verification, credentials/log privacy and workflow permissions. |

## Existing checks to inspect

- `tests/test_process_recovery.py`: eight actual SIGKILL checkpoints. This is
  process-interruption evidence, not a power-loss guarantee.
- `tests/test_quarantine_lifecycle.py`, `test_quarantine_identity.py`,
  `test_journal_errors.py`, `test_quarantine_history.py`: inventory, restore,
  write failures and completed-history boundaries.
- `tests/test_device_revalidation.py`, `test_filesystem.py`,
  `test_quarantine_special_files.py`, `test_access.py`: binding, consent,
  real FIFO refusal and narrow permission recovery.
- `scripts/smoke_btrfs_device.py`: actual remounts and snapshots on disposable
  images, with application operations as a regular user.
- `scripts/gui_lifecycle_smoke.py`: actual toolkit controls, separate
  confirmations, keyboard events, payload hashes and outside sentinels.
- Native-provider/package jobs and `packaging/rehearse_publication.py`:
  actual package tools and a temporary publication remote with disposable keys.

Use disposable fixtures and a regular user. The existing test harnesses create
their own data; do not point destructive test commands at personal XDG data.
Record commands, environment, failures and exact CI job/artifact links.
Synthetic inventory and GTK headless-Wayland activation coverage must retain
their documented limitations.

## Reviewer record for subsequent reviews

| Field | Required content |
|---|---|
| Reviewer | Name/handle and confirmation of independence from the author |
| Target | Full reviewed SHA, dirty state, review date in UTC |
| Scope | Reviewed areas, omitted areas and reasons |
| Findings | Trigger, affected code, impact, reproducible evidence and priority |
| Disposition | Fix/PR/SHA, regression evidence, retest result or explicit unresolved limitation |
| Decision | Approval or remaining blockers, with an accessible report/review link |

For subsequent reviews, retain this record and resolve findings capable of
unapproved data loss or trust bypass. The current P0 closure follows the
owner's explicit acceptance; this future-report template does not reopen it.
Security acceptance does not substitute for successful production signing
and final artifact/publication checks.
