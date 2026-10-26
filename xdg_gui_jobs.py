"""Run filesystem GUI jobs off the UI thread, returning via the UI dispatcher.

No toolkit imports: GTK supplies GLib.idle_add, and callbacks must touch
widgets only when invoked on the UI thread by the dispatcher.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


def run_gui_job(
    operation: Callable[[], Any],
    complete: Callable[[bool, Any], Any],
    dispatch: Callable[..., Any],
) -> threading.Thread:
    """Start a daemon worker; deliver either a result or exception via dispatch.

    The caller must provide a main-loop dispatcher, not call `complete`
    directly from the background thread. Never suppress a failed operation.
    """
    def worker() -> None:
        try:
            result = operation()
        except Exception as exc:
            dispatch(complete, False, exc)
        else:
            dispatch(complete, True, result)

    thread = threading.Thread(target=worker, name="xdg-audit-quarantine", daemon=True)
    thread.start()
    return thread
