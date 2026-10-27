# Quarantine device identity changes

[CLI](cli.md) · [Quarantine lifecycle](quarantine-lifecycle.md) · [Current roadmap](project-roadmap.md)

## What the refusal establishes

The v3 journal records the device number, inode and file type of every moved
root and every inventoried descendant. A different device number blocks
ordinary PURGE and RESTORE even if the inode and type still match.

On Btrfs, the kernel reports an anonymously allocated device number for each
subvolume. That number is not a persistent filesystem identifier and may be
different after unmounting and mounting again. Snapshots also preserve inode
numbers and initially preserve file contents, while having different
subvolume identities. Therefore, ignoring `st_dev` or accepting matching
inode numbers alone would be unsafe.

This explains a reproducible class of failures; it does not establish the
filesystem or exact cause of a particular owner's report without diagnostics.

## Read-only diagnosis

Run as the normal user, with the affected run ID:

```fish
python3 xdg_audit.py --diagnose-access RUN_ID
python3 xdg_audit.py --revalidate-device RUN_ID --dry-run
```

Diagnosis reports the changed identity fields and only the selected object's
mount information. It obtains the mount ID from the opened descriptor's
`fdinfo`, and reads Btrfs FSID/subvolume ID/UUID through read-only ioctls on
that same object. Mount IDs and major/minor numbers are explicitly transient.
Mount sources and options are omitted because they may contain credentials.
No mount, permission, ownership or manifest is changed by diagnosis.

The revalidation preview requires all of the following:

- Only the root device number differs; inode and type are unchanged.
- A completed MOVE and the original sealed recursive inventory exist.
- The complete set of paths, inodes, file types, sizes, symlink targets and
  SHA-256 file hashes matches when remapping only the recorded device number.
- The current tree remains user-owned, without nested mounts, hard-linked
  regular files, special files, extra or missing objects.
- The complete run has one consistent device-number transition.
- The current Btrfs persistent identity is readable. If the journal recorded
  a persistent binding, FSID, subvolume ID and subvolume UUID must all match.

An unavailable inventory or changed content remains blocked. `ACCESS` repairs
only eligible owner permissions; `ADOPT` cannot reconstruct historical content
for a device-mismatched, unsealed journal. This recovery path currently uses
the asm-generic ioctl ABI on x86_64, aarch64, riscv64 and loongarch64; other
architectures and filesystems retain strict refusal.

## Separate confirmation

```fish
python3 xdg_audit.py --revalidate-device RUN_ID
```

Execution requires an interactive TTY and the exact word `REVALIDATE`. The
approval is bound to the displayed manifest, current filesystem identity and
complete inventory. Changed evidence invalidates the approval. The operation
repeats verification, atomically updates only the device binding and records
an audit receipt. It does not delete files or authorize automatic deletion.

For **older sealed v3 journals**, historical filesystem UUIDs were never
recorded. The confirmation explicitly says that matching hashes and inodes
do not prove the historical filesystem identity. The user is approving the
fully verified **current** binding. No historical UUID is inferred or invented.
Do not confirm if that approval is inappropriate for the data being inspected.

New successful Btrfs MOVEs record persistent filesystem/subvolume identity.
Normal PURGE and RESTORE also enforce that binding; a different snapshot UUID
cannot become eligible merely because its hashes and inode numbers match.

After successful revalidation, use a separate command:

```fish
python3 xdg_audit.py --purge RUN_ID --dry-run
python3 xdg_audit.py --purge RUN_ID
```

GTK, Qt and Tk offer the same path after a device-only PURGE refusal or through
**Check access…**. Cancelling `REVALIDATE` preserves the original journal.
After approval, a fresh PURGE preflight and its independent `PURGE` confirmation
remain mandatory. Restoring instead remains a separate `RESTORE` action.

## Validation scope and references

The mandatory Actions Btrfs job creates two new image files in the disposable
runner, mounts them, and holds another filesystem/subvolumes open to reproduce
a real device-number change. Application operations run as a regular user.
It checks snapshot refusal, unchanged persistent identity after remount,
changed-hash refusal, exact-byte revalidation, legacy limitations, separate
PURGE/RESTORE and an untouched outside sentinel. No filesystem syscall or
ioctl is mocked. The installed-app inventory is synthetic and native provider
coverage remains in separate mandatory jobs.

The GUI lifecycle harness uses explicit synthetic Btrfs metadata and a
renumbered disposable journal to drive cancelled `REVALIDATE`, confirmed
`REVALIDATE`, cancelled subsequent PURGE, and final explicit PURGE in all
supported toolkit/display combinations. It does not claim to mount Btrfs.

Primary references:

- [Btrfs subvolumes and inode namespaces](https://btrfs.readthedocs.io/en/latest/Subvolumes.html).
- [Read-only filesystem/subvolume ioctls](https://btrfs.readthedocs.io/en/latest/btrfs-ioctl.html).
- [Linux Btrfs device allocation](https://github.com/torvalds/linux/blob/v6.17/fs/btrfs/disk-io.c)
  and [stat device reporting](https://github.com/torvalds/linux/blob/v6.17/fs/btrfs/inode.c).
- [Linux mountinfo and fdinfo](https://docs.kernel.org/filesystems/proc.html).
