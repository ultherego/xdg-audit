import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("xdg_audit", str(Path(__file__).resolve().parent.parent / "xdg_audit.py"))
app = importlib.util.module_from_spec(spec)
import sys
sys.modules["xdg_audit"] = app
spec.loader.exec_module(app)
ACTUAL_REFERENCES = app.references


def fake_names(*args):
    packages = {"ghostty", "dms-shell-git"}
    return (packages, set(), set(), set(), set(), set(), set(),
            {"ghostty", "dmsshellgit", "dmsshell"})


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.config = self.home / ".config"
        self.config.mkdir()
        for name in ("noctalia", "niri", "solaar", "ghostty", "weirdtool", "dms"):
            (self.config / name).mkdir()
            (self.config / name / "settings.json").write_text("{}")
        (self.config / "external").symlink_to("/etc")
        self.removals = {"noctalia": ["[2026-09-01]"], "solaar": ["[2026-10-21]"]}
        self.patches = [patch.object(app, "read_active_names", side_effect=fake_names),
                        patch.object(app, "parse_removals", return_value=self.removals),
                        patch.object(app, "references", return_value={}),
                        patch.object(app, "disk_sizes", return_value={})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def test_report_without_changes(self):
        old = {str(p): (p.lstat().st_mtime_ns, p.is_symlink()) for p in self.config.iterdir()}
        items, _roots, _stats = app.scan(self.home, ["config"], set(), {}, True)
        lookup = {i.path.name: i for i in items}
        self.assertEqual(lookup["noctalia"].state, "CANDIDATE")
        self.assertEqual(lookup["solaar"].state, "CANDIDATE")
        self.assertEqual(lookup["ghostty"].state, "ACTIVE")
        self.assertEqual(lookup["dms"].state, "PROTECTED")
        self.assertEqual(lookup["niri"].state, "PROTECTED")
        self.assertEqual(lookup["weirdtool"].state, "UNKNOWN")
        self.assertEqual(lookup["external"].state, "PROTECTED")
        self.assertEqual(old, {str(p): (p.lstat().st_mtime_ns, p.is_symlink()) for p in self.config.iterdir()})

    def test_reference_prevents_candidate(self):
        with patch.object(app, "references", return_value={"solaar": {"~/.config/niri/config.kdl"}}):
            items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        lookup = {i.path.name: i for i in items}
        self.assertEqual(lookup["solaar"].state, "REVIEW")
        self.assertFalse(lookup["solaar"].removable)

    def test_missing_package_db_fails_closed(self):
        empty = (set(), set(), set(), set(), set(), set(), set(), set())
        with patch.object(app, "read_active_names", return_value=empty):
            items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        self.assertEqual(next(x for x in items if x.path.name == "noctalia").state, "REVIEW")

    def test_remove_and_restore(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="MOVE"):
            app.move_items(items, roots, self.home, [str(self.config / "noctalia")], False)
        self.assertFalse((self.config / "noctalia").exists())
        qdir = app.quarantine_dir(self.home, roots)
        run = next(p for p in qdir.iterdir() if p.is_dir())
        manifest = json.loads((run / "manifest.json").read_text())
        self.assertEqual(manifest["items"][0]["source"], str(self.config / "noctalia"))
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="RESTORE"):
            app.restore(self.home, roots, run.name)
        self.assertTrue((self.config / "noctalia" / "settings.json").exists())

    def test_refuses_active_item(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True):
            app.move_items(items, roots, self.home, [str(self.config / "ghostty")], True)
        self.assertTrue((self.config / "ghostty").exists())
        self.assertFalse(app.quarantine_dir(self.home, roots).exists())

    def test_refuses_uncertain_without_explicit_override(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True):
            app.move_items(items, roots, self.home, [str(self.config / "weirdtool")], False)
        self.assertTrue((self.config / "weirdtool").exists())
        self.assertFalse(app.quarantine_dir(self.home, roots).exists())

    def test_backup_and_sensitive_protected(self):
        (self.config / "mozilla-backup-crashrecovery-2026").mkdir()
        (self.config / "my-passwords").mkdir()
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        data = {i.path.name: i for i in items}
        self.assertEqual(data["mozilla-backup-crashrecovery-2026"].state, "PROTECTED")
        self.assertEqual(data["my-passwords"].state, "PROTECTED")

    def test_real_workstation_protections(self):
        for name in ("anthropic", "gh", "goa-1.0", "cachyos", "cachyos-hello.json",
                     "unity3d", "7DaysToDie", "StoneShard", "Vortex", "VirtualBox", "niri_back"):
            (self.config / name).mkdir()
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        by_name = {item.path.name: item for item in items}
        for name in ("anthropic", "gh", "goa-1.0", "cachyos", "cachyos-hello.json",
                     "unity3d", "7DaysToDie", "StoneShard", "Vortex", "VirtualBox", "niri_back"):
            self.assertEqual(by_name[name].state, "PROTECTED", name)

    def test_user_software_aliases(self):
        for name in ("BetterDiscord", "Vencord", "easyeffectsrc", "okularrc",
                     "okularpartrc", "logi-ghub-linux"):
            (self.config / name).mkdir()
        packages = {"discord", "easyeffects", "okular"}
        units = {"logi-ghubd"}
        active = {app.normalize(x) for x in packages | units}
        names = (packages, set(), set(), set(), units, set(), set(), active)
        with patch.object(app, "read_active_names", return_value=names):
            items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        by_name = {item.path.name: item for item in items}
        for name in ("BetterDiscord", "Vencord", "easyeffectsrc", "okularrc",
                     "okularpartrc", "logi-ghub-linux"):
            self.assertEqual(by_name[name].state, "ACTIVE", name)

    def test_unknown_session_reference_moves_to_review(self):
        with patch.object(app, "references", return_value={"weirdtool": {"~/.config/niri/config.kdl"}}):
            items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        obj = next(x for x in items if x.path.name == "weirdtool")
        self.assertEqual(obj.state, "REVIEW")
        self.assertFalse(obj.removable)

    def test_checksum_manifest_requires_review(self):
        (self.config / "SHA256SUMS").write_text("abc")
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        self.assertEqual(next(i for i in items if i.path.name == "SHA256SUMS").state, "REVIEW")


    def test_parse_input_formats(self):
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        # Indexing must match the report currently displayed to the user.
        first_three = [str(i.path) for i in items[:3]]
        for value in ("1,2,3", "1 2 3", "1-3", "1, 2 3", "1-2,3"):
            parsed, errors = app.resolve_selection(value, items, self.home)
            self.assertEqual(parsed, first_three)
            self.assertFalse(errors, value)
        parsed, errors = app.resolve_selection("123", items, self.home)
        self.assertEqual(parsed, [])
        self.assertIn("Unknown report ID", errors[0])

    def test_select_by_stable_path_and_quoted_name(self):
        (self.config / "name with spaces").mkdir()
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        for raw in (f'"{self.config / "name with spaces"}"',
                    f'"~/.config/name with spaces"'):
            paths, errs = app.resolve_selection(raw, items, self.home)
            self.assertEqual(paths, [str(self.config / "name with spaces")])
            self.assertEqual(errs, [])

    def test_mixed_candidate_and_unknown_skips_unknown(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="MOVE"):
            app.move_items(items, roots, self.home,
                           [str(self.config / "noctalia"), str(self.config / "weirdtool")], False)
        self.assertFalse((self.config / "noctalia").exists())
        self.assertTrue((self.config / "weirdtool").exists())

    def test_uncertain_double_confirmation(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=["UNCERTAIN", "MOVE"]):
            app.move_items(items, roots, self.home, [str(self.config / "weirdtool")], True)
        self.assertFalse((self.config / "weirdtool").exists())

    def test_uncertain_cancel_at_second_gate(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="MOVE"):
            app.move_items(items, roots, self.home, [str(self.config / "weirdtool")], True)
        self.assertTrue((self.config / "weirdtool").exists())
        self.assertFalse(app.quarantine_dir(self.home, roots).exists())

    def test_comparison_tracks_reason_changes_and_missing_paths(self):
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        report = self.home / "before.json"
        report.write_text(json.dumps({"version": "1.1.0", "entries": [x.json() for x in items]}))
        (self.config / "noctalia").rename(self.config / "newtool")
        later, *_ = app.scan(self.home, ["config"], set(), {}, True)
        changes = app.compare_report(later, report)
        diff = {x["path"]: x for x in changes}
        self.assertEqual(diff[str(self.config / "noctalia")]["new_state"], "NOT_SCANNED")
        self.assertEqual(diff[str(self.config / "newtool")]["old_state"], "NOT_SCANNED")
        self.assertNotIn(str(self.config / "solaar"), diff)

    def test_comparison_rejects_scope_change(self):
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        previous = self.home / "before.json"
        previous.write_text(json.dumps({"scopes": ["config"], "entries": [x.json() for x in items]}))
        with self.assertRaises(SystemExit):
            app.compare_report(items, previous, ["data"])

    def test_comparison_rejects_invalid_report(self):
        bad = self.home / "bad.json"
        bad.write_text('{"entries": ["unexpected"]}')
        with self.assertRaises(SystemExit):
            app.compare_report([], bad)

    def test_reference_ignores_backups_but_not_active_files(self):
        source = self.config / "niri"
        (source / "config.kdl.bak.20260811").write_text("spawn-sh 'shelly'")
        result = ACTUAL_REFERENCES(self.home, app.xdg_roots(self.home), {"shelly"})
        self.assertEqual(result["shelly"], set())
        (source / "config.kdl").write_text("spawn-sh 'shelly'")
        result = ACTUAL_REFERENCES(self.home, app.xdg_roots(self.home), {"shelly"})
        self.assertIn(str(source / "config.kdl"), result["shelly"])

    def test_protection_reasons_descriptive(self):
        self.assertIn("credentials", app.protection_reason("config", "anthropic"))
        self.assertIn("browser", app.protection_reason("config", "mozilla"))
        self.assertIn("desktop/session", app.protection_reason("config", "niri"))

    def test_fails_closed_when_mount_table_unavailable(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="MOVE"), \
             patch.object(app, "nested_mounts_status", return_value=None):
            app.move_items(items, roots, self.home, [str(self.config / "noctalia")], False)
        self.assertTrue((self.config / "noctalia").exists())

    def test_entry_replaced_between_scan_and_remove(self):
        items, roots, _ = app.scan(self.home, ["config"], set(), {}, True)
        (self.config / "noctalia").rename(self.config / "old-noctalia")
        (self.config / "noctalia").mkdir()
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="MOVE"):
            app.move_items(items, roots, self.home, [str(self.config / "noctalia")], False)
        self.assertTrue((self.config / "noctalia").exists())
        self.assertTrue((self.config / "old-noctalia").exists())

    def test_only_config_scope(self):
        (self.home / ".cache").mkdir()
        (self.home / ".cache" / "noctalia").mkdir()
        items, *_ = app.scan(self.home, ["config"], set(), {}, True)
        self.assertTrue(all(x.scope == "config" for x in items))


if __name__ == "__main__":
    unittest.main(verbosity=2)
