"""Read-only source probes and fail-closed quarantine source rechecks."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import xdg_audit as audit
import xdg_sources as sources


class SourceProviderTests(unittest.TestCase):
    def test_pacman_foreign_is_provenance_not_separate_aur_package_manager(self):
        with patch.object(sources, "_run", return_value=(
            sources.Probe("pacman_foreign", "ok"), "hello-aur-git\nlocal-tool\n")) as call:
            probe = sources.pacman_foreign()
        self.assertEqual(probe.names, {"hello-aur-git", "local-tool"})
        self.assertEqual(call.call_args.args[1], ["pacman", "-Qmq"])

    def test_empty_success_not_same_as_failed_package_query(self):
        with patch.object(sources, "_run", side_effect=[
            (sources.Probe("pacman", "ok"), ""),
            (sources.Probe("pacman", "failed"), ""),
        ]):
            empty = sources.pacman_packages()
            error = sources.pacman_packages()
        self.assertEqual(empty.status, "ok")
        self.assertFalse(empty.names)
        self.assertEqual(error.status, "failed")

    def test_dpkg_rejects_malformed_status_without_partial_results(self):
        for output in (
            "safe-package\\tinstall ok installed\\n"
            "broken-package\\tgarbled\\n",
            "safe-package\\tinstall ok installed\\n"
            "broken-package\\tinstall invalid installed\\n",
            "safe-package\\tinstall ok installed\\n"
            "broken-package\\tinstall ok installed extra\\n",
        ):
            with self.subTest(output=output), patch.object(sources, "_run", return_value=(
                sources.Probe("dpkg", "ok"), output)):
                probe = sources.dpkg_packages()
            self.assertEqual(probe.status, "parse_error")
            self.assertFalse(probe.names)

    def test_dpkg_installed_and_residual_config_are_distinct(self):
        output = ("active:amd64\\tinstall ok installed\\n"
                  "retired\\tdeinstall ok config-files\\n"
                  "waiting\\tinstall ok unpacked\\n")
        with patch.object(sources, "_run", return_value=(
            sources.Probe("dpkg", "ok"), output)):
            probe = sources.dpkg_packages()
        self.assertEqual(probe.status, "ok")
        self.assertEqual(probe.names, {"active", "active:amd64"})

    def test_flatpak_lists_apps_not_runtimes(self):
        output = ("org.mozilla.Firefox\tFirefox\tuser\n"
                  "com.valvesoftware.Steam\tSteam\tsystem\n")
        with patch.object(sources, "_run", return_value=(
            sources.Probe("flatpak", "ok"), output)) as call:
            result = sources.flatpak_apps()
        self.assertIn("org.mozilla.firefox", result.names)
        self.assertIn("steam", result.names)
        self.assertEqual(call.call_args.args[1][2], "--app")

    def test_flatpak_malformed_output_is_not_silent_empty_inventory(self):
        with patch.object(sources, "_run", return_value=(
            sources.Probe("flatpak", "ok"), "broken-single-column")):
            self.assertEqual(sources.flatpak_apps().status, "parse_error")

    def test_flatpak_incomplete_installation_column_fails_closed(self):
        # A truncated successful command must not masquerade as a complete list.
        for output in (
            "org.example.App\tExample\n",
            "org.example.App\tExample\t\n",
            "org.example.App\tExample\tuser\textra\n",
        ):
            with self.subTest(output=output), patch.object(sources, "_run", return_value=(
                sources.Probe("flatpak", "ok"), output)):
                probe = sources.flatpak_apps()
            self.assertEqual(probe.status, "parse_error")
            self.assertFalse(probe.names)
            self.assertFalse(probe.app_ids)

    def test_snap_list_parses_name_not_untrusted_header(self):
        content = "Name Version Rev Tracking Publisher Notes\nopera 4.1 42 stable somebody -\n"
        with patch.object(sources, "_run", return_value=(
            sources.Probe("snap", "ok"), content)):
            self.assertEqual(sources.snap_apps().names, {"opera"})

    def test_installed_appimages_are_not_executed_or_followed_through_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            folder = home / "Applications"
            folder.mkdir()
            (folder / "MyApp.AppImage").write_bytes(b"not executed")
            outside = home / "important"
            outside.write_bytes(b"preserve")
            (folder / "Evil.AppImage").symlink_to(outside)
            with patch.object(sources.subprocess, "run") as run:
                found = sources.user_appimages(home)
            self.assertIn("myapp", found.names)
            self.assertNotIn("evil", found.names)
            run.assert_not_called()
            self.assertEqual(outside.read_bytes(), b"preserve")

    def test_manual_bin_is_protective_hints_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            local = home / ".local/bin"
            local.mkdir(parents=True)
            binary = local / "mytool"
            binary.write_text("#!/bin/sh\nexit 1")
            binary.chmod(0o700)
            with patch.object(sources.subprocess, "run") as run:
                found = sources.manual_binaries(home)
            run.assert_not_called()
            self.assertIn("mytool", found.names)

    def test_manual_and_appimage_do_not_follow_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            outside = home / "external"
            (outside / "bin").mkdir(parents=True)
            (outside / "share/applications").mkdir(parents=True)
            tool = outside / "bin/private-binary"
            tool.write_text("#!/bin/sh\\nexit 0\\n")
            tool.chmod(0o700)
            (outside / "share/applications/private.AppImage").write_bytes(b"not executed")
            (home / ".local").symlink_to(outside, target_is_directory=True)
            with patch.object(sources.subprocess, "run") as execute:
                manual = sources.manual_binaries(home)
                image = sources.user_appimages(home)
            execute.assert_not_called()
            self.assertEqual(manual.status, "failed")
            self.assertEqual(image.status, "failed")
            self.assertNotIn("private-binary", manual.names)
            self.assertNotIn("private", image.names)

    def test_manual_probe_rejects_symlinked_opt_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            external = home / "external"
            (external / "tool").mkdir(parents=True)
            (home / ".local").symlink_to(external, target_is_directory=True)
            names, state = sources._app_directories(
                home / ".local/opt", anchor=home)
            self.assertEqual(state, "unsafe")
            self.assertFalse(names)

    def test_appimage_probe_stops_after_directory_entry_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            folder = home / "Applications"
            folder.mkdir()
            seen = []
            def many(_):
                for idx in range(100_000):
                    seen.append(idx)
                    yield folder / f"item-{idx}.AppImage"
            original_lstat = Path.lstat
            def fake_lstat(path):
                if path.name.startswith("item-"):
                    return original_lstat(folder)  # Simulate harmless non-regular entries.
                return original_lstat(path)
            with patch.object(Path, "iterdir", many), patch.object(Path, "lstat", fake_lstat):
                names, status = sources._safe_direct_children(
                    folder, extensions=(".appimage",), anchor=home)
            self.assertEqual(status, "failed")
            self.assertFalse(names)
            self.assertEqual(len(seen), 2001)

    def test_opt_style_dirs_are_shallow_protective_only(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "opt"
            base.mkdir()
            (base / "brave-bin").mkdir()
            (base / "not-an-app.txt").write_text("content")
            (base / "symlink").symlink_to("/etc", target_is_directory=True)
            names, state = sources._app_directories(base)
            self.assertEqual(state, "ok")
            self.assertEqual(names, {"brave-bin"})

    def test_source_health_cli_report_contains_no_user_files(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(audit, "read_active_names",
                          return_value=sources.ActiveInventory((
                              {"python"}, {"org.example.App"}, set(), set(),
                              set(), set(), set(), set()),
                              status={"pacman": "ok", "flatpak": "ok"},
                              foreign={"python"})):
            import contextlib
            import io
            import json
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = audit.main(["--home", str(Path(temp)), "--installed-sources"])
            self.assertEqual(result, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["health"]["pacman"], "ok")
            self.assertEqual(report["counts"]["foreign_pacman_AUR_or_local"], 1)
            self.assertNotIn("test-only.txt", output.getvalue())

    def test_manual_bin_symlink_cannot_count_as_bundled_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            local = home / "bin"
            local.mkdir()
            (local / "example").symlink_to("/usr/bin/true")
            result = sources.manual_binaries(home)
            self.assertNotIn("example", result.names)

    def test_pacman_foreign_hint_surfaces_without_claiming_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / ".config" / "brave").mkdir(parents=True)
            packages = sources.ActiveInventory((
                {"brave-bin"}, set(), set(), set(), set(), set(), set(), set()),
                status={"pacman": "ok", "flatpak": "absent",
                        "snap": "absent", "appimage": "ok", "manual_binary": "ok"},
                foreign={"brave-bin"})
            with patch.object(audit, "read_active_names", return_value=packages), \
                 patch.object(audit, "parse_removals", return_value={}):
                items, *_ = audit.scan(home, ["config"], set(), {}, True)
            self.assertEqual(items[0].state, "ACTIVE")
            self.assertIn("foreign: AUR or local", " ".join(items[0].reasons))

    def test_provider_failure_is_not_health_ok(self):
        probes = {
            "flatpak": sources.Probe("flatpak", "failed"),
            "snap": sources.Probe("snap", "absent"),
            "pacman": sources.Probe("pacman", "ok", frozenset({"python"})),
        }
        self.assertEqual(sources.health_failed(probes), ("flatpak",))


class EvidenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / ".config"
        self.config.mkdir()
        self.item = self.config / "mytool"
        self.item.mkdir()
        self.item.joinpath("keep").write_text("safe")

    def fixture_inventory(self, *, manual=(), flatpak_state="ok"):
        return sources.ActiveInventory((
            {"python"}, set(), set(), set(), set(), set(), set(), {"python"}),
            status={"pacman": "ok", "flatpak": flatpak_state, "snap": "absent",
                    "appimage": "ok", "manual_binary": "ok"},
            manual=manual, foreign={"python"})

    def test_manual_binary_prevents_candidate_from_stale_pacman_history(self):
        with patch.object(audit, "read_active_names", return_value=self.fixture_inventory(manual={"mytool"})), \
             patch.object(audit, "parse_removals", return_value={"mytool": ["[old]"]}), \
             patch.object(audit, "references", return_value={}):
            items, *_ = audit.scan(self.home, ["config"], set(), {}, True)
        row = next(x for x in items if x.path.name == "mytool")
        self.assertEqual(row.state, "REVIEW")
        self.assertFalse(row.removable)
        self.assertIn("manual executable", " ".join(row.reasons))

    def test_failed_installed_source_blocks_stale_removal_candidate(self):
        with patch.object(audit, "read_active_names", return_value=self.fixture_inventory(flatpak_state="failed")), \
             patch.object(audit, "parse_removals", return_value={"mytool": ["[old]"]}), \
             patch.object(audit, "references", return_value={}):
            rows, *_ = audit.scan(self.home, ["config"], set(), {}, True)
        self.assertEqual(rows[0].state, "REVIEW")
        self.assertIn("installed-app inventory failed", " ".join(rows[0].reasons))

    def test_move_refuses_changed_manual_binary_or_failed_provider(self):
        st = self.item.lstat()
        row = audit.Item("config", self.item, state="CANDIDATE", removable=True,
                         identity=(st.st_dev, st.st_ino, st.st_mode & 0o170000))
        roots = audit.xdg_roots(self.home)
        for inv in (self.fixture_inventory(manual={"mytool"}),
                    self.fixture_inventory(flatpak_state="failed")):
            with self.subTest(source_status=inv.status, manual=inv.manual), \
                 patch.object(audit, "read_active_names", return_value=inv):
                with self.assertRaisesRegex(ValueError, "(present now|providers failed)"):
                    audit.commit_quarantine([row], roots, self.home,
                                            emit=lambda _: None)
            self.assertTrue(self.item.exists())


if __name__ == "__main__":
    unittest.main()
