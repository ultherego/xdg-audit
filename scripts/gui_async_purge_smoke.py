#!/usr/bin/env python3
"""GTK4 event-loop regression: slow PURGE preview must not freeze the UI.

Run with: xvfb-run -a /usr/bin/python3 scripts/gui_async_purge_smoke.py
Uses fake quarantine metadata: it NEVER deletes real user data.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, GLib, Gio
    import xdg_audit as engine
    from xdg_prefs import defaults
    from xdg_gui_gtk import launch_gui

    main_thread = threading.get_ident()
    errors = []
    ticks = []
    work_threads = []
    preview_started = threading.Event()
    preview_done = threading.Event()
    run_id = "20261026-092717-954140"

    def find_widgets(widget):
        yield widget
        child = widget.get_first_child()
        while child is not None:
            yield from find_widgets(child)
            child = child.get_next_sibling()

    def open_windows():
        model = Gtk.Window.get_toplevels()
        return [model.get_item(i) for i in range(model.get_n_items())]

    with tempfile.TemporaryDirectory(prefix="xdg-audit-async-purge-") as td:
        home = Path(td)
        for p in (".config", ".cache", ".local/share", ".local/state", ".var/app"):
            (home / p).mkdir(parents=True, exist_ok=True)

        engine.scan = lambda *_args, **_kwargs: (
            [], engine.xdg_roots(home), {"phase_times_ms": {}})
        engine.quarantine_runs = lambda *_args: [
            {"run_id": run_id, "status": "QUARANTINED", "moved": 2,
             "items": [{"source": str(home / ".config" / "first")},
                       {"source": str(home / ".config" / "second")}]}
        ]

        def slow_preview(*_args, **kwargs):
            work_threads.append(threading.get_ident())
            preview_started.set()
            time.sleep(0.9)
            preview_done.set()
            return {"run_id": run_id, "objects": 2, "bytes": 123,
                    "dry_run": kwargs.get("dry_run", True)}

        engine.purge_quarantine_run = slow_preview

        def tick():
            ticks.append(time.monotonic())
            return True

        GLib.timeout_add(40, tick)

        def click_purge():
            try:
                app = Gio.Application.get_default()
                window = app.get_active_window()
                if window is None:
                    raise AssertionError("GTK main window not active")
                stack = next((w for w in find_widgets(window)
                              if isinstance(w, Gtk.Stack) and
                              w.get_child_by_name("quarantine") is not None), None)
                if stack is None:
                    raise AssertionError("Quarantine stack not found")
                stack.set_visible_child_name("quarantine")
                button = next((w for w in find_widgets(window)
                               if isinstance(w, Gtk.Button) and
                               w.get_label() == "Usuń trwale…"), None)
                if button is None:
                    raise AssertionError("PURGE button not found")
                print("DEBUG button",button.get_sensitive(),button.get_visible(),
                      button.get_mapped(),flush=True)
                start = time.monotonic()
                button.emit("clicked")
                print("DEBUG clicked",preview_started.is_set(),flush=True)
                if time.monotonic() - start > 0.3:
                    raise AssertionError("PURGE click blocked GTK event loop")
            except BaseException as exc:
                errors.append(str(exc))
                Gio.Application.get_default().quit()
            return False

        def check_progress():
            try:
                if not preview_started.is_set():
                    print("DEBUG windows:",[w.get_title() for w in open_windows()],
                          "ticks:",len(ticks),flush=True)
                    raise AssertionError("PURGE worker never started")
                if preview_done.is_set():
                    raise AssertionError("Preview finished too quickly for test")
                if len(ticks) < 6:
                    raise AssertionError("GTK main-loop heartbeat stopped")
                if not any(w.get_title() == "Weryfikacja kwarantanny"
                           for w in open_windows()):
                    raise AssertionError("Background operation has no progress window")
            except BaseException as exc:
                errors.append(str(exc))
            return False

        def check_confirm():
            try:
                if not preview_done.is_set():
                    raise AssertionError("Slow preview still running")
                if work_threads != [x for x in work_threads if x != main_thread]:
                    raise AssertionError("Slow file inspection ran on UI thread")
                if not any(w.get_title() == "Trwałe usunięcie"
                           for w in open_windows()):
                    raise AssertionError("PURGE confirmation dialog never appeared")
            except BaseException as exc:
                errors.append(str(exc))
            finally:
                Gio.Application.get_default().quit()
            return False

        GLib.timeout_add(300, click_purge)
        GLib.timeout_add(700, check_progress)
        GLib.timeout_add(1700, check_confirm)
        GLib.timeout_add(4000, lambda: (errors.append("GTK smoke timeout"),
                                       Gio.Application.get_default().quit(), False)[-1])
        args = SimpleNamespace(saved_prefs=defaults(), keep=[], quick=True,
                               scope="all", all=False)
        runtime = {"desktop": "Niri", "session": "x11", "selected": "gtk4",
                   "available": ["gtk4"], "wm": "test"}
        launch_gui(engine, home, args, {}, runtime, "gtk4")
        if errors:
            raise AssertionError("; ".join(errors))
        print("PASS: slow PURGE preview leaves GTK responsive and displays confirmation")


if __name__ == "__main__":
    main()
