# Retained GUI fixture reports — 2026-10-28

[Verification record](../../verification-2026-10-28.md)

These six JSON reports are copied verbatim into code fences from the PR #40
X11/Wayland artifacts. They describe disposable synthetic inventory, not
owner data, a real Btrfs remount or full desktop-session acceptance.
Their commit is the tested PR merge; the verification record identifies
the resulting identical main tree and the original artifact ZIP digests.

## Original member SHA-256

| Artifact | Original member | SHA-256 |
|---|---|---|
| `gui-lifecycle-x11` | `gtk3-x11.json` | `38ad6a8257f2e4ab546511ae0b61d729d6146ff2f1bd57fb439181f24ea0a856` |
| `gui-lifecycle-x11` | `gtk4-x11.json` | `ad7bd9d3e14a326879bcb477149d37b67102cba044d5f95cd02e41c76d87973e` |
| `gui-lifecycle-x11` | `qt6-x11.json` | `130c1d11d2464c1f2733f6bdfce095aee2f107328064fdeccfd6bd55c15bedf5` |
| `gui-lifecycle-x11` | `tk-x11.json` | `e4112ebe7905ae2ac18dba1a4a5d36ddbe62bc9d41b35725c1bfa292aec21f8f` |
| `gui-lifecycle-wayland` | `gtk4-wayland.json` | `ca1f9f3bc93a5d71f9749308288500447fb6359b93c58a4736ef0cc1c7aaac9a` |
| `gui-lifecycle-wayland` | `qt6-wayland.json` | `fba57ba8f42e4288839dd6012fc4136f1639df98cef80ca8a7d5c8eb04fb2c46` |

## Retained original screenshots

PNG bytes are copied without cropping, editing or conversion. Names below
map retained files to members of the original `gui-layout` artifact.

| Original member | Retained file | SHA-256 |
|---|---|---|
| `gtk4-xdg-audit-settings.png` | [gtk4-light-empty.png](../../screenshots/verification-2026-10-28/gtk4-light-empty.png) | `de7d3aa80cbb7a1eb10abcc2b4106913f5835fabd8c2305336da68791c0da0fe` |
| `gtk4-settings-focused.png` | [gtk4-light-focused.png](../../screenshots/verification-2026-10-28/gtk4-light-focused.png) | `5c20c5e6a7c1d37bb83efbf89d5febb635a56d25a672046e8c8593a8ebc4b324` |
| `gtk4-settings-scrolled.png` | [gtk4-light-scrolled.png](../../screenshots/verification-2026-10-28/gtk4-light-scrolled.png) | `bdd0ae138d626b09c2840f0aa7af4e9ce0c3410422f37b1414c6caa47ebdd8dc` |
| `dark/gtk4-xdg-audit-settings.png` | [gtk4-dark-empty.png](../../screenshots/verification-2026-10-28/gtk4-dark-empty.png) | `9eca4addba6abee8e40c293db1b8114be8cd488ad3f2d58964ac21628331e7ab` |
| `dark/gtk4-settings-focused.png` | [gtk4-dark-focused.png](../../screenshots/verification-2026-10-28/gtk4-dark-focused.png) | `d2d71ae76bcef1692f674078f1dfdb6f5720ee60363589d2357ff8242f4b9947` |
| `dark/gtk4-settings-scrolled.png` | [gtk4-dark-scrolled.png](../../screenshots/verification-2026-10-28/gtk4-dark-scrolled.png) | `56fd6928c459160e94f9e6aa91c6280a0b76810dfe5f655c4ee1d086dfedc0e0` |
| `gtk3-xdg-audit-settings.png` | [gtk3-light-empty.png](../../screenshots/verification-2026-10-28/gtk3-light-empty.png) | `9c480146bb527022cc7e367c98e2a78394083fe3f8f0583030628c2a253c9a61` |
| `gtk3-settings-focused.png` | [gtk3-light-focused.png](../../screenshots/verification-2026-10-28/gtk3-light-focused.png) | `ce1e587f67c53dd3d7b90f345a7993123d065aac877aeeee6f544a37ecbecea7` |
| `gtk3-settings-scrolled.png` | [gtk3-light-scrolled.png](../../screenshots/verification-2026-10-28/gtk3-light-scrolled.png) | `bde70dafabd0fa07fcc090dfd2b3139a150a7d3154f275a0200be98ad871a052` |

## gtk3-x11.json

Original artifact: `gui-lifecycle-x11`.

```json
{
  "backend": "gtk3",
  "native_session": "x11",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "c27474a3f0bc521330816851677e2c6f8f4e9251",
  "checks": [
    "typed MOVE then Cancel preserves data and creates no quarantine",
    "UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified",
    "RESTORE returns exact original paths and hashes and updates visible history",
    "typed REVALIDATE then Cancel preserves exact journal and payload",
    "confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data",
    "typed PURGE then Cancel preserves quarantined bytes and journal",
    "Enter with empty or incorrect PURGE token preserves exact bytes and journal",
    "PURGE removes only the selected payload; completed history and sentinels preserved",
    "empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history",
    "HISTORY plus Enter removes only the selected completed journal"
  ],
  "confirmation_key_events": {
    "Return": 7,
    "KP_Enter": 6
  },
  "result": "PASS",
  "fixture_hashes": {
    "nested": "directory",
    "nested/payload": "f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363",
    "settings": "d9affc1bb624e0eba64e377e4273b88d9578310f07b698c724ab2578bdd9cff6"
  }
}
```

## gtk4-x11.json

Original artifact: `gui-lifecycle-x11`.

```json
{
  "backend": "gtk4",
  "native_session": "x11",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "c27474a3f0bc521330816851677e2c6f8f4e9251",
  "checks": [
    "typed MOVE then Cancel preserves data and creates no quarantine",
    "UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified",
    "RESTORE returns exact original paths and hashes and updates visible history",
    "typed REVALIDATE then Cancel preserves exact journal and payload",
    "confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data",
    "typed PURGE then Cancel preserves quarantined bytes and journal",
    "Enter with empty or incorrect PURGE token preserves exact bytes and journal",
    "PURGE removes only the selected payload; completed history and sentinels preserved",
    "empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history",
    "HISTORY plus Enter removes only the selected completed journal"
  ],
  "confirmation_key_events": {
    "Return": 7,
    "KP_Enter": 6
  },
  "result": "PASS",
  "fixture_hashes": {
    "nested": "directory",
    "nested/payload": "f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363",
    "settings": "d9affc1bb624e0eba64e377e4273b88d9578310f07b698c724ab2578bdd9cff6"
  }
}
```

## qt6-x11.json

Original artifact: `gui-lifecycle-x11`.

```json
{
  "backend": "qt6",
  "native_session": "x11",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "c27474a3f0bc521330816851677e2c6f8f4e9251",
  "checks": [
    "typed MOVE then Cancel preserves data and creates no quarantine",
    "UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified",
    "RESTORE returns exact original paths and hashes and updates visible history",
    "typed REVALIDATE then Cancel preserves exact journal and payload",
    "confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data",
    "typed PURGE then Cancel preserves quarantined bytes and journal",
    "Enter with empty or incorrect PURGE token preserves exact bytes and journal",
    "PURGE removes only the selected payload; completed history and sentinels preserved",
    "empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history",
    "HISTORY plus Enter removes only the selected completed journal"
  ],
  "confirmation_key_events": {
    "Return": 7,
    "KP_Enter": 6
  },
  "result": "PASS",
  "fixture_hashes": {
    "nested": "directory",
    "nested/payload": "f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363",
    "settings": "d9affc1bb624e0eba64e377e4273b88d9578310f07b698c724ab2578bdd9cff6"
  }
}
```

## tk-x11.json

Original artifact: `gui-lifecycle-x11`.

```json
{
  "backend": "tk",
  "native_session": "x11",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "c27474a3f0bc521330816851677e2c6f8f4e9251",
  "checks": [
    "typed MOVE then Cancel preserves data and creates no quarantine",
    "UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified",
    "RESTORE returns exact original paths and hashes and updates visible history",
    "typed REVALIDATE then Cancel preserves exact journal and payload",
    "confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data",
    "typed PURGE then Cancel preserves quarantined bytes and journal",
    "Enter with empty or incorrect PURGE token preserves exact bytes and journal",
    "PURGE removes only the selected payload; completed history and sentinels preserved",
    "empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history",
    "HISTORY plus Enter removes only the selected completed journal"
  ],
  "confirmation_key_events": {
    "Return": 7,
    "KP_Enter": 6
  },
  "result": "PASS",
  "fixture_hashes": {
    "nested": "directory",
    "nested/payload": "f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363",
    "settings": "d9affc1bb624e0eba64e377e4273b88d9578310f07b698c724ab2578bdd9cff6"
  }
}
```

## gtk4-wayland.json

Original artifact: `gui-lifecycle-wayland`.

```json
{
  "backend": "gtk4",
  "native_session": "wayland",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "c27474a3f0bc521330816851677e2c6f8f4e9251",
  "checks": [
    "typed MOVE then Cancel preserves data and creates no quarantine",
    "UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified",
    "RESTORE returns exact original paths and hashes and updates visible history",
    "typed REVALIDATE then Cancel preserves exact journal and payload",
    "confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data",
    "typed PURGE then Cancel preserves quarantined bytes and journal",
    "Enter with empty or incorrect PURGE token preserves exact bytes and journal",
    "PURGE removes only the selected payload; completed history and sentinels preserved",
    "empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history",
    "HISTORY plus Enter removes only the selected completed journal"
  ],
  "confirmation_key_events": {
    "gtk_entry_activate": 13
  },
  "result": "PASS",
  "fixture_hashes": {
    "nested": "directory",
    "nested/payload": "f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363",
    "settings": "d9affc1bb624e0eba64e377e4273b88d9578310f07b698c724ab2578bdd9cff6"
  }
}
```

## qt6-wayland.json

Original artifact: `gui-lifecycle-wayland`.

```json
{
  "backend": "qt6",
  "native_session": "wayland",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "c27474a3f0bc521330816851677e2c6f8f4e9251",
  "checks": [
    "typed MOVE then Cancel preserves data and creates no quarantine",
    "UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified",
    "RESTORE returns exact original paths and hashes and updates visible history",
    "typed REVALIDATE then Cancel preserves exact journal and payload",
    "confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data",
    "typed PURGE then Cancel preserves quarantined bytes and journal",
    "Enter with empty or incorrect PURGE token preserves exact bytes and journal",
    "PURGE removes only the selected payload; completed history and sentinels preserved",
    "empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history",
    "HISTORY plus Enter removes only the selected completed journal"
  ],
  "confirmation_key_events": {
    "Return": 7,
    "KP_Enter": 6
  },
  "result": "PASS",
  "fixture_hashes": {
    "nested": "directory",
    "nested/payload": "f3a25aa93aa2fbba28d79260535bbd6a5eb0fc1c24a8b0f04e12b484c1dfe363",
    "settings": "d9affc1bb624e0eba64e377e4273b88d9578310f07b698c724ab2578bdd9cff6"
  }
}
```
