# Retained desktop integration reports — 2026-10-28

[Desktop acceptance protocol](../../desktop-acceptance.md) · [Roadmap](../../project-roadmap.md)

These are original author-run CI reports from disposable, complete software-rendered desktop sessions. They are not manual theme/palette acceptance, physical keyboard evidence or independent security approval. Inventory and the Btrfs device metadata in the GUI lifecycle remain explicitly synthetic; filesystem actions, hashes and native displays are real.

The reports cover PR #42 head `6363b49c5d81fe2b69296f59f5731c6400e57dc9`, tested PR merge `79fb097bd697ad02a518abebb1402877bc45ddb7`, identical tree `5f6dc243403d5de6e5752313ade2f036d4feca0c`. [CI run 40711792031](https://github.com/ultherego/xdg-audit/actions/runs/40711792031) passed all 22 build/test jobs and 418 regressions per supported Python version. Production publication jobs were skipped. Later bookkeeping/cleanup changes require their own CI and are not retroactively included in these reports.

GNOME 46/GTK4 and Plasma 5.27/Qt6 used native Wayland; Xfce 4.18/Tk used X11. Each session passed ten lifecycle assertions, including cancellation, separate REVALIDATE/PURGE, invalid tokens, RESTORE, selected HISTORY removal and outside/protected sentinels. GTK Wayland reports 13 Entry activations; Qt/Tk report Return ×7 and keypad Enter ×6. These are the harness mechanisms documented in the desktop protocol, not physical keyboard input.

Downloaded ZIPs passed their published SHA-256 and ZIP integrity checks. The six JSON reports below are copied verbatim, including their exact versions, PIDs and synthetic fixture hashes. Diagnostic logs contain disposable fixture and CI/system paths; no owner profile or credentials were included. Optional calendar/audio/network/portal features were not acceptance requirements; warnings remain in the original log artifacts.

## Original artifact ZIPs

Artifacts retain `session.json`, `lifecycle.json`, `desktop.log` and `application.log` for 14 days. The JSON copies here remain with the source after that retention expires.

| Session | Original artifact | ZIP SHA-256 |
|---|---|---|
| gnome | [Artifact 12827310241](https://github.com/ultherego/xdg-audit/actions/runs/40711792031/artifacts/12827310241) | `e1013134c3a69ab7b610670c592a1e87afd8a5814d8d34340c7c96ca5161532d` |
| xfce | [Artifact 12826361802](https://github.com/ultherego/xdg-audit/actions/runs/40711792031/artifacts/12826361802) | `9a1ec20e1b8774231018dab81056297e1f3c0cd29ccc29f6dc0086009468b6f8` |
| plasma | [Artifact 12826053449](https://github.com/ultherego/xdg-audit/actions/runs/40711792031/artifacts/12826053449) | `9c6a462255f16fcade46099380b58d34a11c94a79f349317c323291e7b7de538` |

## Original member SHA-256

| Session | Member | SHA-256 |
|---|---|---|
| gnome | `session.json` | `9489475b7d230b848b4d7cd0e4a6588e203fa5a978badae52a1b1deadafdbbfd` |
| gnome | `lifecycle.json` | `4feca6ad53461df2ad736c2252423248d95f59a2ae3b4c028bb5eef8183a3d75` |
| xfce | `session.json` | `e32041b7a44d108174c6b328d36006f8cce5e23993ac98a0d639f86cdd6cc5ad` |
| xfce | `lifecycle.json` | `048d2768f350f4a1c7f86ee8f7db661a97e1eab0c1b5ed6e6703b1afa50fde10` |
| plasma | `session.json` | `208a89c0a4d31dcce0271f3bfd687569b7cbf0dfe73054f32d0bd00529b47085` |
| plasma | `lifecycle.json` | `b43de02e5ddfa829c61270e2095944f351e7819d7739cd36ab798e64cf4cfc10` |

## gnome / session.json

```json
{
  "desktop": "gnome",
  "commit": "79fb097bd697ad02a518abebb1402877bc45ddb7",
  "result": "PASS",
  "manual_theme_keyboard_acceptance": "pending",
  "inventory": "synthetic",
  "session": {
    "services": {
      "org.gnome.SessionManager": {
        "pid": 4978,
        "executable": "gnome-session-binary",
        "fixture_profile": true
      },
      "org.gnome.Shell": {
        "pid": 4997,
        "executable": "gnome-shell",
        "fixture_profile": true
      },
      "org.gnome.SettingsDaemon.Keyboard": {
        "pid": 5099,
        "executable": "gsd-keyboard",
        "fixture_profile": true
      }
    },
    "processes": [],
    "native_session": "wayland"
  },
  "distribution": {
    "PRETTY_NAME": "Ubuntu 24.04.5 LTS",
    "VERSION_ID": "24.04",
    "ID": "ubuntu"
  },
  "packages": [
    "gnome-session 46.0-1ubuntu4",
    "gnome-settings-daemon 46.0-1ubuntu1.24.04.1",
    "gnome-shell 46.0-0ubuntu6~24.04.16"
  ],
  "session_after": {
    "services": {
      "org.gnome.SessionManager": {
        "pid": 4978,
        "executable": "gnome-session-binary",
        "fixture_profile": true
      },
      "org.gnome.Shell": {
        "pid": 4997,
        "executable": "gnome-shell",
        "fixture_profile": true
      },
      "org.gnome.SettingsDaemon.Keyboard": {
        "pid": 5099,
        "executable": "gsd-keyboard",
        "fixture_profile": true
      }
    },
    "processes": [],
    "native_session": "wayland"
  }
}
```

## gnome / lifecycle.json

```json
{
  "backend": "gtk4",
  "native_session": "wayland",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "79fb097bd697ad02a518abebb1402877bc45ddb7",
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

## xfce / session.json

```json
{
  "desktop": "xfce",
  "commit": "79fb097bd697ad02a518abebb1402877bc45ddb7",
  "result": "PASS",
  "manual_theme_keyboard_acceptance": "pending",
  "inventory": "synthetic",
  "session": {
    "services": {
      "org.xfce.SessionManager": {
        "pid": 3210,
        "executable": "xfce4-session",
        "fixture_profile": true
      },
      "org.xfce.Xfconf": {
        "pid": 3215,
        "executable": "xfconfd",
        "fixture_profile": true
      }
    },
    "processes": [
      {
        "pid": 3236,
        "executable": "xfwm4",
        "fixture_profile": true
      },
      {
        "pid": 3245,
        "executable": "xfce4-panel",
        "fixture_profile": true
      },
      {
        "pid": 3261,
        "executable": "xfdesktop",
        "fixture_profile": true
      },
      {
        "pid": 3241,
        "executable": "xfsettingsd",
        "fixture_profile": true
      }
    ],
    "native_session": "x11"
  },
  "distribution": {
    "PRETTY_NAME": "Ubuntu 24.04.5 LTS",
    "VERSION_ID": "24.04",
    "ID": "ubuntu"
  },
  "packages": [
    "xfce4-session 4.18.3-1build2",
    "xfce4-settings 4.18.4-0ubuntu3",
    "xfdesktop4 4.18.1-1build3",
    "xfwm4 4.18.0-1build3"
  ],
  "session_after": {
    "services": {
      "org.xfce.SessionManager": {
        "pid": 3210,
        "executable": "xfce4-session",
        "fixture_profile": true
      },
      "org.xfce.Xfconf": {
        "pid": 3215,
        "executable": "xfconfd",
        "fixture_profile": true
      }
    },
    "processes": [
      {
        "pid": 3236,
        "executable": "xfwm4",
        "fixture_profile": true
      },
      {
        "pid": 3245,
        "executable": "xfce4-panel",
        "fixture_profile": true
      },
      {
        "pid": 3261,
        "executable": "xfdesktop",
        "fixture_profile": true
      },
      {
        "pid": 3241,
        "executable": "xfsettingsd",
        "fixture_profile": true
      }
    ],
    "native_session": "x11"
  }
}
```

## xfce / lifecycle.json

```json
{
  "backend": "tk",
  "native_session": "x11",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "79fb097bd697ad02a518abebb1402877bc45ddb7",
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

## plasma / session.json

```json
{
  "desktop": "plasma",
  "commit": "79fb097bd697ad02a518abebb1402877bc45ddb7",
  "result": "PASS",
  "manual_theme_keyboard_acceptance": "pending",
  "inventory": "synthetic",
  "session": {
    "services": {
      "org.kde.ksmserver": {
        "pid": 8307,
        "executable": "ksmserver",
        "fixture_profile": true
      },
      "org.kde.plasmashell": {
        "pid": 8334,
        "executable": "plasmashell",
        "fixture_profile": true
      },
      "org.kde.KWin": {
        "pid": 8236,
        "executable": "kwin_wayland",
        "fixture_profile": true
      },
      "org.kde.kded5": {
        "pid": 8294,
        "executable": "kded5",
        "fixture_profile": true
      }
    },
    "processes": [],
    "native_session": "wayland"
  },
  "distribution": {
    "PRETTY_NAME": "Ubuntu 24.04.5 LTS",
    "VERSION_ID": "24.04",
    "ID": "ubuntu"
  },
  "packages": [
    "kwin-wayland 4:5.27.11-0ubuntu3",
    "plasma-desktop 4:5.27.12-0ubuntu0.1",
    "plasma-workspace 4:5.27.12-0ubuntu0.1"
  ],
  "session_after": {
    "services": {
      "org.kde.ksmserver": {
        "pid": 8307,
        "executable": "ksmserver",
        "fixture_profile": true
      },
      "org.kde.plasmashell": {
        "pid": 8334,
        "executable": "plasmashell",
        "fixture_profile": true
      },
      "org.kde.KWin": {
        "pid": 8236,
        "executable": "kwin_wayland",
        "fixture_profile": true
      },
      "org.kde.kded5": {
        "pid": 8294,
        "executable": "kded5",
        "fixture_profile": true
      }
    },
    "processes": [],
    "native_session": "wayland"
  }
}
```

## plasma / lifecycle.json

```json
{
  "backend": "qt6",
  "native_session": "wayland",
  "inventory": "synthetic",
  "filesystem_evidence": "synthetic Btrfs metadata and device transition",
  "version": "1.7.0-rc2",
  "commit": "79fb097bd697ad02a518abebb1402877bc45ddb7",
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
