"""Real-scan regression: evidence quality is not proof of XDG ownership."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import xdg_audit as audit


def inventory(*, units=(), desktops=()):
    return ({"unrelated-package"}, set(), set(), set(), set(units), set(),
            set(desktops), set())


class ConservativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / ".cache").mkdir()

    def test_generic_systemd_app_and_session_do_not_make_active(self):
        for name in ("session", "kdeconnect.app"):
            (self.home / ".cache" / name).mkdir()
        with patch.object(audit, "read_active_names",
                          return_value=inventory(units={"app", "session"},
                                                 desktops={"kdeconnectapp"})), \
             patch.object(audit, "parse_removals", return_value={}), \
             patch.object(audit, "references", return_value={}):
            entries, *_ = audit.scan(self.home, ["cache"], set(), {}, True)
        states = {item.path.name: item.state for item in entries}
        self.assertEqual(states["session"], "UNKNOWN")
        self.assertEqual(states["kdeconnect.app"], "REVIEW")
        self.assertFalse(any(item.removable for item in entries))

    def test_history_only_candidate_explicitly_unverified(self):
        folder = self.home / ".cache" / "old-app"
        folder.mkdir()
        with patch.object(audit, "read_active_names", return_value=inventory()), \
             patch.object(audit, "parse_removals",
                          return_value={"old-app": ["[historical]"]}), \
             patch.object(audit, "references", return_value={}):
            entries, *_ = audit.scan(self.home, ["cache"], set(), {}, True)
        item = entries[0]
        row = item.json()
        self.assertEqual(item.state, "CANDIDATE")
        self.assertEqual(row["evidence_level"], "historical_only")
        self.assertEqual(row["risk_flags"], ["unverified_owner", "history_only"])
        self.assertFalse(row["orphan_ownership_verified"])
        self.assertTrue(item.removable)  # Still requires an explicit MOVE action.
        self.assertIsNone(row["size_bytes"])
        self.assertFalse(row["size_calculated"])

    def test_measured_zero_is_not_unknown(self):
        item = audit.Item("cache", self.home / ".cache" / "empty",
                          state="UNKNOWN", bytes=0, size_known=True)
        result = item.json()
        self.assertEqual(result["size_bytes"], 0)
        self.assertTrue(result["size_calculated"])

    def test_active_process_is_only_protective_hint(self):
        item = audit.Item("cache", self.home / ".cache" / "claude",
                          state="ACTIVE", reasons=["running executable: claude"])
        result = item.json()
        self.assertEqual(result["evidence_level"], "protective_hint")
        self.assertFalse(result["orphan_ownership_verified"])
        self.assertFalse(result["removable"])


if __name__ == "__main__":
    unittest.main()
