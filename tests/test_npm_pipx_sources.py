"""Read-only npm/pipx source hints never prove XDG data ownership."""
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import xdg_audit as audit
import xdg_sources as sources


class NativePackageHintsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / ".cache").mkdir()

    def test_npm_detects_regular_and_scoped_global_packages(self):
        root = self.home / ".npm-global/lib/node_modules"
        (root / "opencode").mkdir(parents=True)
        (root / "@example" / "terminal").mkdir(parents=True)
        (root / "evil").symlink_to("/etc", target_is_directory=True)
        with patch.object(sources.subprocess, "run") as run:
            evidence = sources.npm_global_packages(self.home)
        run.assert_not_called()
        self.assertEqual(evidence.status, "ok")
        self.assertIn("opencode", evidence.names)
        self.assertIn("terminal", evidence.names)
        self.assertIn("@example/terminal", evidence.names)
        self.assertNotIn("evil", evidence.names)

    def test_nvm_versioned_global_packages(self):
        (self.home / ".nvm/versions/node/v22.1.0/lib/node_modules/pnpm").mkdir(parents=True)
        evidence = sources.npm_global_packages(self.home)
        self.assertIn("pnpm", evidence.names)

    def test_pipx_virtualenv_names_are_protective_hints(self):
        (self.home / ".local/share/pipx/venvs/ansible-lint").mkdir(parents=True)
        (self.home / ".local/share/pipx/venvs/suspicious").symlink_to(
            "/etc", target_is_directory=True)
        with patch.object(sources.subprocess, "run") as run:
            probe = sources.pipx_environments(self.home)
        run.assert_not_called()
        self.assertIn("ansible-lint", probe.names)
        self.assertNotIn("suspicious", probe.names)

    def test_symlinked_provider_root_fails_closed(self):
        base = self.home / ".npm-global/lib"
        base.mkdir(parents=True)
        (base / "node_modules").symlink_to("/tmp", target_is_directory=True)
        self.assertEqual(sources.npm_global_packages(self.home).status, "failed")

    def test_symlinked_npm_parent_is_not_traversed(self):
        target = self.home / "external-node-modules"
        (target / "lib/node_modules/private-package").mkdir(parents=True)
        (self.home / ".npm-global").symlink_to(target, target_is_directory=True)
        with patch.object(sources.subprocess, "run") as run:
            result = sources.npm_global_packages(self.home)
        run.assert_not_called()
        self.assertEqual(result.status, "failed")
        self.assertNotIn("private-package", result.names)

    def test_symlinked_pipx_parent_is_not_traversed(self):
        outside = self.home / "external-pipx"
        (outside / "venvs/private-tool").mkdir(parents=True)
        (self.home / ".local").symlink_to(outside, target_is_directory=True)
        with patch.object(sources.subprocess, "run") as run:
            result = sources.pipx_environments(self.home)
        run.assert_not_called()
        self.assertEqual(result.status, "failed")
        self.assertNotIn("private-tool", result.names)

    def test_symlinked_nvm_ancestor_and_version_are_rejected(self):
        outside = self.home / "external-nvm"
        (outside / "node").mkdir(parents=True)
        (self.home / ".nvm").mkdir()
        (self.home / ".nvm/versions").symlink_to(outside, target_is_directory=True)
        self.assertEqual(sources.npm_global_packages(self.home).status, "failed")
        (self.home / ".nvm/versions").unlink()
        (self.home / ".nvm/versions/node").mkdir(parents=True)
        (self.home / ".nvm/versions/node/v999").symlink_to(
            outside, target_is_directory=True)
        self.assertEqual(sources.npm_global_packages(self.home).status, "failed")

    def test_npm_package_enumeration_is_bounded_before_inspection(self):
        root = self.home / ".npm-global/lib/node_modules"
        root.mkdir(parents=True)
        seen = []
        def many(_):
            for idx in range(100_000):
                seen.append(idx)
                yield root / f"entry-{idx}"
        with patch.object(Path, "iterdir", many):
            _, status = sources._package_directories(root, home=self.home)
        self.assertEqual(status, "failed")
        self.assertEqual(len(seen), 2001)

    def test_npm_prevents_historical_candidate(self):
        (self.home / ".cache/opencode").mkdir()
        inv = sources.ActiveInventory(
            ({"python"}, set(), set(), set(), set(), set(), set(), set()),
            status={"pacman": "ok", "npm_global": "ok", "pipx": "ok"},
            npm_global={"opencode"})
        with patch.object(audit, "read_active_names", return_value=inv), \
             patch.object(audit, "parse_removals",
                          return_value={"opencode": ["[old]"]}), \
             patch.object(audit, "references", return_value={}):
            items, *_ = audit.scan(self.home, ["cache"], set(), {}, True)
        self.assertEqual(items[0].state, "REVIEW")
        self.assertFalse(items[0].removable)
        self.assertIn("npm_global",
                      [e["source"] for e in items[0].json()["evidence"]])

    def test_pipx_hint_refuses_move_even_if_scan_was_outdated(self):
        folder = self.home / ".cache" / "ansible-lint"
        folder.mkdir()
        info = folder.lstat()
        candidate = audit.Item("cache", folder, state="CANDIDATE", removable=True,
                               identity=(info.st_dev, info.st_ino, stat.S_IFDIR))
        inv = sources.ActiveInventory(
            ({"python"}, set(), set(), set(), set(), set(), set(), set()),
            status={"pacman": "ok", "npm_global": "ok", "pipx": "ok"},
            pipx={"ansible-lint"})
        with patch.object(audit, "read_active_names", return_value=inv):
            with self.assertRaisesRegex(ValueError, "present now"):
                audit.commit_quarantine([candidate], audit.xdg_roots(self.home),
                                        self.home, emit=lambda *_: None)
        self.assertTrue(folder.exists())

    def test_installed_flatpak_ids_separate_from_display_names(self):
        listing = "com.example.App\tFriendly Application\tuser\n"
        with patch.object(sources, "_run", return_value=(
            sources.Probe("flatpak", "ok"), listing)):
            probe = sources.flatpak_apps()
        self.assertEqual(probe.app_ids, {"com.example.app"})
        self.assertIn("friendly application", probe.names)
        self.assertNotIn("friendly application", probe.app_ids)

    def test_scope_does_not_trust_flatpak_display_name_as_appid(self):
        folder = self.home / ".var/app/Friendly Application"
        folder.mkdir(parents=True)
        inv = sources.ActiveInventory(
            ({"python"}, {"com.example.app", "friendly application"},
             set(), set(), set(), set(), set(), set()),
            status={"pacman": "ok", "flatpak": "ok"},
            flatpak_ids={"com.example.app"})
        with patch.object(audit, "read_active_names", return_value=inv), \
             patch.object(audit, "parse_removals", return_value={}):
            items, *_ = audit.scan(self.home, ["flatpak"], set(), {}, True)
        self.assertEqual(items[0].state, "REVIEW")


if __name__ == "__main__":
    unittest.main()
