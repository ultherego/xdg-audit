"""Regression tests for asynchronous GUI quarantine operations.

Files and SHA-256 inspection may take seconds on real desktops. The main
window cannot block while awaiting the user-visible PURGE confirmation.
"""
from __future__ import annotations

import queue
import threading
import time
import unittest

from xdg_gui_jobs import run_gui_job


class GUIJobTests(unittest.TestCase):
    def test_operation_does_not_block_caller_or_main_loop(self):
        started = threading.Event()
        release = threading.Event()
        events = queue.Queue()
        main = threading.get_ident()

        def slow_preview():
            started.set()
            if not release.wait(5):
                raise TimeoutError("Preview did not complete")
            return {"objects": 2, "bytes": 100}

        def dispatcher(callback, ok, result):
            events.put((callback, ok, result))

        delivered = []
        begin = time.monotonic()
        thread = run_gui_job(
            slow_preview,
            lambda ok, result: delivered.append((threading.get_ident(), ok, result)),
            dispatcher)
        self.addCleanup(release.set)
        self.assertLess(time.monotonic() - begin, 0.5)
        self.assertTrue(started.wait(2))
        self.assertTrue(events.empty())
        self.assertFalse(delivered)
        self.assertTrue(thread.is_alive())
        # The event dispatcher hands the operation result to the main loop.
        release.set()
        callback, ok, outcome = events.get(timeout=3)
        self.assertEqual(outcome, {"objects": 2, "bytes": 100})
        callback(ok, outcome)
        self.assertEqual(delivered, [(main, True, outcome)])
        thread.join(timeout=2)

    def test_failed_preview_reaches_gui_instead_of_swallowing_error(self):
        events = queue.Queue()

        def bad_preview():
            raise ValueError("Quarantine inode substituted")

        thread = run_gui_job(bad_preview, lambda ok, result: None,
                             lambda fn, ok, result: events.put((fn, ok, result)))
        _, ok, error = events.get(timeout=3)
        self.assertFalse(ok)
        self.assertIsInstance(error, ValueError)
        self.assertIn("inode", str(error))
        thread.join(timeout=2)

    def test_worker_never_calls_widget_callback_itself(self):
        events = queue.Queue()
        callback_called = threading.Event()
        thread = run_gui_job(lambda: 3,
                             lambda *_: callback_called.set(),
                             lambda fn, ok, res: events.put((fn, ok, res)))
        thread.join(timeout=2)
        self.assertFalse(callback_called.is_set())
        callback, ok, result = events.get(timeout=2)
        callback(ok, result)
        self.assertTrue(callback_called.is_set())


if __name__ == "__main__":
    unittest.main()
