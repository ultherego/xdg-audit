#!/usr/bin/env python3
"""Exercise real adaptive tabs and dialogs under Xvfb with disposable scan data.

Cancels all prompts; never moves, restores or deletes user data. Optional
screenshots capture only synthetic HOME contents and public test messages.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import os
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xdg_gui_layout import DIALOG_PADDING

LONG_TEXT = ('Review the selected disposable application data before confirming.\n' * 100
             + '/temporary/' + 'long-path-component-' * 60 + '\nThe action still requires its own token.')
PATH_TEXT = '/temporary/' + 'long-component-' * 300


def capture(output, name):
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        subprocess.run(['scrot', '-o', str(output / (name + '.png'))], check=True, timeout=10)


def run(backend, output):
    import xdg_audit as engine
    from xdg_prefs import defaults
    with tempfile.TemporaryDirectory(prefix='xdg-layout-fixture-') as temporary:
        home = Path(temporary)
        env = {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
               'XDG_DATA_HOME': str(home / '.local/share'),
               'XDG_STATE_HOME': str(home / '.local/state'),
               'XDG_CACHE_HOME': str(home / '.cache')}
        with patch.dict(os.environ, env):
            roots = engine.xdg_roots(home)
            absent = {'installed_sources': {'flatpak': 'absent', 'snap': 'absent'}, 'phase_times_ms': {}}
            prefs = {**defaults(), 'language': 'en'}
            args = SimpleNamespace(saved_prefs=prefs, keep=[], quick=True, scope='snap', all=True)
            runtime = {'desktop': 'Fixture', 'session': 'x11', 'selected': backend,
                       'available': [backend], 'wm': 'test'}
            errors = []

            def tabs(controller):
                row = engine.Item('snap', roots['snap'] / 'layout-fixture', state='REVIEW')
                if backend.startswith('gtk'):
                    apply = lambda rows, stats: controller.finish((rows, roots, stats))
                    def shown(scope):
                        switcher = controller.scope_switcher
                        if backend == 'gtk4':
                            buttons = []
                            child = switcher.get_first_child()
                            while child is not None:
                                buttons.append(child)
                                child = child.get_next_sibling()
                        else:
                            buttons = switcher.get_children()
                        def labels(widget):
                            if isinstance(widget, Gtk.Label):
                                return [widget.get_text()]
                            if backend == 'gtk4':
                                nested = []
                                child = widget.get_first_child()
                                while child is not None:
                                    nested.append(child)
                                    child = child.get_next_sibling()
                            else:
                                nested = widget.get_children() if hasattr(widget, 'get_children') else []
                            return [text for child in nested for text in labels(child)]
                        matches = [w for w in buttons if scope.title() in labels(w)]
                        return any(button.get_visible() for button in matches)
                    select = lambda scope: controller.stack.set_visible_child_name(scope)
                    current = lambda: controller.stack.get_visible_child_name()
                elif backend == 'qt6':
                    apply = lambda rows, stats: controller.scan_done(rows, roots, stats)
                    shown = lambda scope: controller.scope_tabs.isTabVisible(controller.scope_values.index(scope))
                    select = lambda scope: controller.scope_tabs.setCurrentIndex(controller.scope_values.index(scope))
                    current = lambda: controller.scope_values[controller.scope_tabs.currentIndex()]
                else:
                    def apply(rows, stats):
                        controller.items, controller.stats = rows, stats
                        controller._update_optional_tabs()
                        controller._refresh_tables()
                    shown = lambda scope: controller.tabs.tab(controller.scope_frames[scope], 'state') != 'hidden'
                    select = lambda scope: controller.tabs.select(controller.scope_frames[scope])
                    current = lambda: next(scope for scope, frame in controller.scope_frames.items()
                                           if str(frame) == controller.tabs.select())
                apply([], absent)
                assert not shown('flatpak') and not shown('snap')
                assert current() == 'all', 'hidden startup scope did not fall back to all'
                apply([row], absent)
                assert shown('snap') and not shown('flatpak'), 'uninstalled-source leftovers were hidden'
                select('snap')
                assert current() == 'snap', 'hidden neighboring tab shifted the scope identity'
                apply([], absent)
                assert current() == 'all'
                apply([], {'installed_sources': {'flatpak': 'failed', 'snap': 'absent'}})
                assert shown('flatpak'), 'failed source was hidden as if absent'
                print(backend + ': PASS optional tabs, leftovers, fallback and stable scope IDs')

            with patch.object(engine, 'scan', return_value=([], roots, absent)):
                if backend.startswith('gtk'):
                    import gi
                    gi.require_version('Gtk', '4.0' if backend == 'gtk4' else '3.0')
                    from gi.repository import Gtk, GLib, Gio
                    from xdg_gui_gtk import launch_gui
                    heights = []
                    controller = []

                    def windows():
                        if backend == 'gtk4':
                            model = Gtk.Window.get_toplevels()
                            return [model.get_item(i) for i in range(model.get_n_items())]
                        return Gtk.Window.list_toplevels()

                    def walk(widget):
                        yield widget
                        if backend == 'gtk4':
                            nested = []
                            child = widget.get_first_child()
                            while child is not None:
                                nested.append(child)
                                child = child.get_next_sibling()
                        else:
                            nested = widget.get_children() if hasattr(widget, 'get_children') else []
                        for child in nested:
                            yield from walk(child)

                    def inspect(title, close=True):
                        window = next(w for w in windows() if w.get_title() == title)
                        body = window.get_child() if backend == 'gtk4' else window.get_children()[0]
                        assert all(getattr(body, 'get_margin_' + side)() == DIALOG_PADDING
                                   for side in ('top', 'bottom', 'start', 'end'))
                        width = window.get_width() if backend == 'gtk4' else window.get_size()[0]
                        height = window.get_height() if backend == 'gtk4' else window.get_size()[1]
                        assert width <= 1552 and height <= 952, (title, width, height)
                        heights.append(height)
                        capture(output, backend + '-' + title.lower().replace(' ', '-'))
                        if close:
                            window.destroy()
                        return window

                    def first():
                        try:
                            app = Gio.Application.get_default()
                            window = app.get_active_window()
                            current = getattr(window, '_xdg_controller', None)
                            if current is None or not current.scan_complete:
                                return True
                            controller.append(current)
                            tabs(current)
                            current.prompt('Short prompt', 'Saved.', 'MOVE', lambda: errors.append('unexpected MOVE'))
                            GLib.timeout_add(200, short)
                        except BaseException:
                            errors.append(traceback.format_exc()); Gio.Application.get_default().quit()
                        return False

                    def short():
                        try:
                            inspect('Short prompt')
                            controller[0].prompt('Long prompt', LONG_TEXT, 'PURGE',
                                lambda: errors.append('unexpected PURGE'))
                            GLib.timeout_add(250, long)
                        except BaseException:
                            errors.append(traceback.format_exc()); Gio.Application.get_default().quit()
                        return False

                    def long():
                        try:
                            inspect('Long prompt')
                            assert heights[1] > heights[0], heights
                            controller[0].prompt('Long path', PATH_TEXT, 'MOVE',
                                lambda: errors.append('unexpected MOVE'))
                            GLib.timeout_add(200, path)
                        except BaseException:
                            errors.append(traceback.format_exc()); Gio.Application.get_default().quit()
                        return False

                    def path():
                        try:
                            inspect('Long path')
                            controller[0].open_settings()
                            GLib.timeout_add(200, settings)
                        except BaseException:
                            errors.append(traceback.format_exc()); Gio.Application.get_default().quit()
                        return False

                    def settings():
                        try:
                            window = inspect('xdg-audit settings', close=False)
                            editor = next(w for w in walk(window) if isinstance(w, Gtk.TextView))
                            editor.grab_focus()
                            from gui_lifecycle_smoke import send_x11_key
                            send_x11_key(window.get_title(), 'Return')
                            GLib.timeout_add(150, lambda: settings_focused(window, editor))
                        except BaseException:
                            errors.append(traceback.format_exc())
                            Gio.Application.get_default().quit()
                        return False

                    def settings_focused(window, editor):
                        try:
                            buffer = editor.get_buffer()
                            assert '\n' in buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
                            assert window.get_visible(), 'Enter in a multiline editor closed Settings'
                            capture(output, backend + '-settings-focused')
                            buffer.set_text('\n'.join('Scrollable fixture line ' + str(i) for i in range(40)))
                            GLib.timeout_add(150, lambda: settings_scrolled(window, editor))
                        except BaseException:
                            errors.append(traceback.format_exc()); Gio.Application.get_default().quit()
                        return False

                    def settings_scrolled(window, editor):
                        try:
                            buffer = editor.get_buffer()
                            editor.scroll_to_iter(buffer.get_end_iter(), 0.0, False, 0.0, 0.0)
                            GLib.timeout_add(150, lambda: settings_finish(window))
                        except BaseException:
                            errors.append(traceback.format_exc()); Gio.Application.get_default().quit()
                        return False

                    def settings_finish(window):
                        try:
                            capture(output, backend + '-settings-scrolled')
                            window.destroy()
                            print(backend + ': PASS multiline Enter, focused and scrolled settings frames')
                        except BaseException:
                            errors.append(traceback.format_exc())
                        Gio.Application.get_default().quit()
                        return False

                    GLib.timeout_add(100, first)
                    GLib.timeout_add_seconds(15, lambda: (errors.append('GTK layout timeout'),
                        Gio.Application.get_default().quit(), False)[-1])
                    launch_gui(engine, home, args, {}, runtime, backend)
                elif backend == 'qt6':
                    from xdg_gui_qt import launch_gui, import_qt
                    from xdg_gui_dialogs import qt_dialog_helpers
                    QtCore, _, QtWidgets, _ = import_qt()
                    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
                    messages, inputs = qt_dialog_helpers(QtWidgets, QtCore, lambda value: {
                        'Tak': 'Yes', 'Nie': 'No', 'Anuluj': 'Cancel'}.get(value, value))
                    heights = []

                    def inspect(title):
                        dialog = app.activeModalWidget()
                        assert dialog is not None and dialog.windowTitle() == title
                        margins = dialog.layout().contentsMargins()
                        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (20,) * 4
                        assert dialog.width() <= 1552 and dialog.height() <= 952
                        heights.append(dialog.height())
                        if output is not None:
                            output.mkdir(parents=True, exist_ok=True)
                            dialog.grab().save(str(output / ('qt6-' + title.lower().replace(' ', '-') + '.png')))
                        return dialog

                    def dismiss(title, token=False):
                        try:
                            dialog = inspect(title)
                            if token:
                                dialog.findChild(QtWidgets.QLineEdit).setText('MOVE')
                            if title == 'xdg-audit settings':
                                import importlib
                                test = importlib.import_module(QtWidgets.__name__.split('.')[0] + '.QtTest').QTest
                                editor = dialog.findChild(QtWidgets.QPlainTextEdit)
                                editor.setPlainText('line one')
                                editor.setFocus()
                                test.keyClick(editor, QtCore.Qt.Key.Key_Return)
                                assert '\n' in editor.toPlainText() and dialog.isVisible()
                            dialog.reject()
                        except BaseException:
                            errors.append(traceback.format_exc()); app.quit()

                    def drive():
                        try:
                            window = next(w for w in app.topLevelWidgets() if hasattr(w, 'scope_tabs'))
                            if window.thread is not None or not window.scan_complete:
                                QtCore.QTimer.singleShot(50, drive); return
                            tabs(window)
                            QtCore.QTimer.singleShot(150, lambda: dismiss('Short prompt'))
                            messages.information(window, 'Short prompt', 'Saved.')
                            QtCore.QTimer.singleShot(150, lambda: dismiss('Long prompt'))
                            result = messages.question(window, 'Long prompt', LONG_TEXT)
                            assert result == QtWidgets.QMessageBox.StandardButton.No
                            assert heights[1] > heights[0], heights
                            QtCore.QTimer.singleShot(150, lambda: dismiss('Long path'))
                            messages.information(window, 'Long path', PATH_TEXT)
                            QtCore.QTimer.singleShot(150, lambda: dismiss('Token prompt', True))
                            token, accepted = inputs.getText(window, 'Token prompt', 'Type MOVE:')
                            assert token == 'MOVE' and not accepted, 'cancel accepted a typed token'
                            QtCore.QTimer.singleShot(150, lambda: dismiss('xdg-audit settings'))
                            window.open_settings()
                        except BaseException:
                            errors.append(traceback.format_exc())
                        app.quit()

                    QtCore.QTimer.singleShot(100, drive)
                    QtCore.QTimer.singleShot(15000, lambda: (errors.append('Qt layout timeout'), app.quit()))
                    launch_gui(engine, home, args, {}, runtime, backend)
                else:
                    import tkinter as tk
                    from tkinter import ttk
                    from xdg_gui_tk import launch_gui
                    from xdg_gui_dialogs import tk_dialog_helpers
                    original_tk = tk.Tk
                    active_root = []
                    heights = []

                    def inspect(title):
                        root = active_root[0]
                        dialog = next(w for w in root.winfo_children()
                                      if isinstance(w, tk.Toplevel) and w.title() == title)
                        assert dialog._xdg_padding == 20
                        assert dialog.winfo_width() <= 1552 and dialog.winfo_height() <= 952
                        heights.append(dialog.winfo_height())
                        capture(output, 'tk-' + title.lower().replace(' ', '-'))
                        return dialog

                    def dismiss(title, token=False):
                        try:
                            dialog = inspect(title)
                            if token:
                                actions = dialog._xdg_layout[2]
                                next(w for w in actions.winfo_children() if isinstance(w, ttk.Entry)).insert(0, 'MOVE')
                            if title == 'xdg-audit settings':
                                def walk(widget):
                                    yield widget
                                    for child in widget.winfo_children():
                                        yield from walk(child)
                                editor = next(w for w in walk(dialog) if isinstance(w, tk.Text))
                                editor.delete('1.0', 'end')
                                editor.insert('1.0', 'line one')
                                editor.focus_force()
                                editor.event_generate('<KeyPress-Return>')
                                assert '\n' in editor.get('1.0', 'end-1c') and dialog.winfo_exists()
                            dialog.destroy()
                        except BaseException:
                            errors.append(traceback.format_exc()); active_root[0].destroy()

                    def drive():
                        root = active_root[0]
                        try:
                            controller = root._xdg_controller
                            if controller.busy or not controller.scan_complete:
                                root.after(50, drive); return
                            tabs(controller)
                            messages, inputs = tk_dialog_helpers(tk, ttk, root, lambda value: {
                                'Tak': 'Yes', 'Nie': 'No', 'Anuluj': 'Cancel'}.get(value, value))
                            root.after(150, lambda: dismiss('Short prompt'))
                            messages.showinfo('Short prompt', 'Saved.', parent=root)
                            root.after(150, lambda: dismiss('Long prompt'))
                            assert not messages.askyesno('Long prompt', LONG_TEXT, parent=root)
                            assert heights[1] > heights[0], heights
                            root.after(150, lambda: dismiss('Long path'))
                            messages.showinfo('Long path', PATH_TEXT, parent=root)
                            root.after(150, lambda: dismiss('Token prompt', True))
                            assert inputs.askstring('Token prompt', 'Type MOVE:', parent=root) is None
                            controller.open_settings()
                            root.after(150, lambda: (dismiss('xdg-audit settings'), root.destroy()))
                            return
                        except BaseException:
                            errors.append(traceback.format_exc())
                        root.destroy()

                    def create_root(*values, **keywords):
                        root = original_tk(*values, **keywords)
                        active_root.append(root)
                        root.after(100, drive)
                        root.after(15000, lambda: (errors.append('Tk layout timeout'), root.destroy()))
                        return root

                    with patch.object(tk, 'Tk', create_root):
                        launch_gui(engine, home, args, {}, runtime, backend)
            if errors:
                raise AssertionError('\n'.join(errors))
            assert not (home / '.config/xdg-audit/settings.json').exists(), 'cancel wrote settings'
            print(backend + ': PASS content sizing, 20 px padding, screen limits and cancelled confirmations')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('gtk4', 'gtk3', 'qt6', 'tk'), required=True)
    parser.add_argument('--output-dir', type=Path)
    arguments = parser.parse_args()
    run(arguments.backend, arguments.output_dir)
