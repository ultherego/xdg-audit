"""Release readiness contract: source version, archive gate and honest docs."""
from pathlib import Path
import re
import unittest

import xdg_audit


ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_version_is_documented_but_rc2_is_not_misrepresented_as_released(self):
        version = xdg_audit.VERSION
        self.assertTrue(version.startswith("1.7.0-rc"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        self.assertIn(version, changelog)
        self.assertIn(version, release_notes)
        self.assertIn("Niewydany", release_notes)

    def test_archive_build_is_gated_by_all_safety_and_gui_jobs(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        archives = workflow.split("\n  archives:", 1)[1].split("\n  release:", 1)[0]
        match = re.search(r"needs:\s*\[([^]]+)\]", archives)
        self.assertIsNotNone(match, "Release archive must depend on safety jobs")
        required = {"test", "gui-smoke", "wayland-smoke", "benchmark", "quarantine-cycle"}
        actual = {name.strip() for name in match.group(1).split(",")}
        self.assertTrue(required.issubset(actual), f"Missing release safety gates: {required-actual}")

    def test_future_distro_support_is_explicitly_not_a_current_delete_backend(self):
        roadmap = (ROOT / "docs/installation-source-support.md").read_text(encoding="utf-8")
        self.assertIn("dpkg", roadmap)
        self.assertIn("rpm", roadmap)
        self.assertIn("foreign ≠ AUR", roadmap)
        self.assertIn("MOVE pozostaje zablokowany", roadmap)
        self.assertTrue((ROOT / "docs/release-readiness.md").is_file())


if __name__ == "__main__":
    unittest.main()
