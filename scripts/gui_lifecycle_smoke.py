#!/usr/bin/env python3
"""Drive real GUI controls through a lifecycle on an internally created HOME.

Installed-application inventory is synthetic. The optional device-revalidation
case also supplies explicit Btrfs metadata and a renumbered disposable journal;
real Btrfs remounts are covered separately by smoke_btrfs_device.py. Scanning, confirmation
dialogs, MOVE, hashes, manifests, RESTORE and PURGE use production code.
Never accepts an existing HOME, patches a confirmation or bypasses root checks.
"""
from collections import deque
from hashlib import sha256
import argparse
import faulthandler
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import xdg_audit as engine


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def send_x11_key(title, key):
    """Send a real XTest key to the exact visible fixture dialog."""
    windows = subprocess.check_output(
        ['xdotool', 'search', '--onlyvisible', '--name', '^' + re.escape(title) + '$'],
        text=True, timeout=5).splitlines()
    require(len(windows) == 1, 'Expected exactly one keyboard target: ' + title)
    subprocess.run(['xdotool', 'windowfocus', '--sync', windows[0]], check=True, timeout=5)
    subprocess.run(['xdotool', 'key', '--clearmodifiers', key], check=True, timeout=5)


def next_enter(ui):
    key = 'Return' if sum(ui.key_events.values()) % 2 == 0 else 'KP_Enter'
    ui.key_events[key] = ui.key_events.get(key, 0) + 1
    return key


def snapshot(root):
    require(root.is_dir() and not root.is_symlink(), 'fixture directory missing or replaced')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'unexpected fixture symlink')
        result[str(path.relative_to(root))] = ('directory' if path.is_dir() else
                                              sha256(path.read_bytes()).hexdigest())
    return result


class Cycle:
    def __init__(self, ui, home, device_revalidation=False):
        self.ui, self.home = ui, home
        self.roots = engine.xdg_roots(home)
        self.source = self.roots['config'] / 'xdg-gui-lifecycle-fixture'
        self.source.mkdir(parents=True)
        (self.source / 'nested').mkdir()
        (self.source / 'settings').write_bytes(b'GUI lifecycle settings\x00\xff\n')
        (self.source / 'nested/payload').write_bytes(bytes(range(256)) * 3)
        self.expected = snapshot(self.source)
        self.protected = self.roots['config'] / 'niri'
        self.protected.mkdir()
        (self.protected / 'settings').write_bytes(b'protected session data')
        self.sentinel = home / 'unrelated-sentinel'
        self.sentinel.write_bytes(b'unrelated data')
        self.expected_protected = snapshot(self.protected)
        self.phase, self.pending, self.events = 'scan', deque(), []
        self.in_action, self.done, self.errors = False, False, []
        self.deadline = time.monotonic() + 75
        self.run_id = self.restored_id = None
        self.device_revalidation = device_revalidation

    def start_device_revalidation(self, cancel):
        click = self.ui.action('purge', self.source, self.run_id)
        if click is None:
            return
        responses = [] if self.ui.backend.startswith('gtk') else [('ok', ''), ('yes', '')]
        responses.append(('cancel' if cancel else 'token', 'REVALIDATE'))
        if not cancel:
            if not self.ui.backend.startswith('gtk'):
                responses.append(('yes', ''))
            responses.append(('cancel', 'PURGE'))
        self.pending.extend(responses)
        self.phase = 'device_cancelled' if cancel else 'device_revalidated'
        self.in_action = True
        try:
            click()
        finally:
            self.in_action = False

    def guard(self):
        require(snapshot(self.protected) == self.expected_protected, 'protected data changed')
        require(self.sentinel.read_bytes() == b'unrelated data', 'unrelated sentinel changed')

    def record(self, event):
        if event in self.events:
            return
        self.events.append(event)
        print(self.ui.backend + ': PASS ' + event, flush=True)

    def start(self, operation, phase, *, cancel=False, reject=None):
        click = self.ui.action(operation, self.source, self.run_id)
        if click is None:
            return
        token = {'move': 'MOVE', 'restore': 'RESTORE', 'purge': 'PURGE', 'history': 'HISTORY',
                 'all_history': 'HISTORY', 'adopt': 'ADOPT'}[operation]
        responses = [] if self.ui.backend.startswith('gtk') else [('yes', '')]
        if operation == 'move':
            responses.append(('token', 'UNCERTAIN'))
        responses.append((reject or ('cancel' if cancel else 'token'), token))
        if reject and self.ui.backend.startswith('gtk'):
            responses.append(('cancel', token))
        if not cancel and not reject and operation not in ('history', 'all_history') and not self.ui.backend.startswith('gtk'):
            responses.append(('ok', ''))
        if operation == 'adopt' and not cancel and self.ui.backend.startswith('gtk'):
            responses.append(('ok', ''))
        self.pending.extend(responses)
        self.phase = phase
        self.in_action = True
        try:
            click()
        finally:
            self.in_action = False

    def active_run(self):
        runs = engine.quarantine_runs(self.home, self.roots)
        active = [run for run in runs if run['status'] not in ('PURGED', 'RESTORED', 'COMPLETED')]
        require(len(active) == 1, 'expected exactly one active fixture run')
        require(active[0]['moved'] == 1, 'wrong number of moved objects')
        return active[0]

    def verify_moved(self):
        run = self.active_run()
        self.run_id = run['run_id']
        folder = engine.quarantine_dir(self.home, self.roots) / self.run_id
        manifest = folder / 'manifest.json'
        data = json.loads(manifest.read_text())
        require(data.get('format') == 'intent-journal-v3', 'MOVE did not produce a v3 journal')
        require(len(data['items']) == 1, 'MOVE selected unrelated data')
        item = data['items'][0]
        require(item['source'] == str(self.source), 'MOVE journal has the wrong source')
        self.destination = Path(item['destination'])
        require(snapshot(self.destination) == self.expected, 'MOVE changed paths or file hashes')
        self.manifest = manifest
        self.manifest_before_cancel = manifest.read_bytes()

    def tick(self):
        if self.done:
            return False
        try:
            require(time.monotonic() < self.deadline,
                    'GUI lifecycle timed out in ' + self.phase + ': ' + self.ui.status())
            self.guard()
            dialog = self.ui.dialog()
            if dialog is not None:
                require(self.pending, 'unexpected dialog in ' + self.phase + ': ' + self.ui.title(dialog))
                response, token = self.pending.popleft()
                print(f'{self.ui.backend}: DRIVE {self.phase} {response} {token}', flush=True)
                self.ui.respond(dialog, response, token)
                return True
            if self.in_action or self.pending or not self.ui.ready():
                return True
            if self.phase == 'scan':
                row = next(row for row in self.ui.controller.items if row.path == self.source)
                require(row.state == 'UNKNOWN' and not row.removable, 'fixture must require uncertain consent')
                require(not engine.quarantine_dir(self.home, self.roots).exists(), 'read-only scan wrote quarantine')
                self.start('move', 'cancelled_move', cancel=True)
            elif self.phase == 'cancelled_move':
                require(snapshot(self.source) == self.expected, 'cancelled MOVE changed source bytes')
                require(not engine.quarantine_dir(self.home, self.roots).exists(), 'cancelled MOVE wrote a journal')
                self.record('typed MOVE then Cancel preserves data and creates no quarantine')
                self.start('move', 'first_move')
            elif self.phase == 'first_move':
                require(not self.source.exists(), 'confirmed MOVE did not remove original entry')
                self.verify_moved()
                self.record('UNKNOWN requires UNCERTAIN then MOVE; actual files and v3 journal verified')
                self.restored_id = self.run_id
                self.start('restore', 'restored')
            elif self.phase == 'restored':
                require(snapshot(self.source) == self.expected, 'RESTORE changed paths or file hashes')
                run = next(run for run in engine.quarantine_runs(self.home, self.roots)
                           if run['run_id'] == self.restored_id)
                require(run['status'] == 'RESTORED', 'RESTORE history did not update')
                self.record('RESTORE returns exact original paths and hashes and updates visible history')
                self.start('move', 'second_move')
            elif self.phase == 'second_move':
                require(not self.source.exists(), 'second MOVE did not complete')
                self.verify_moved()
                require(self.run_id != self.restored_id, 'second MOVE reused a completed run')
                data = json.loads(self.manifest.read_text())
                data['format'] = 'intent-journal-v2'
                for row in data['items']:
                    for key in ('identity', 'tree_inventory', 'filesystem_identity'):
                        row.pop(key, None)
                # Model partial legacy MOVE; protected original data stays put.
                data['items'].append({'scope': 'config', 'source': str(self.protected),
                    'destination': str(self.manifest.parent / 'config' / self.protected.name),
                    'move_status': 'planned'})
                self.manifest.write_text(json.dumps(data))
                self.legacy_manifest_before = self.manifest.read_bytes()
                self.phase = 'legacy_ready'
                self.start('adopt', 'cancelled_adoption', cancel=True)
            elif self.phase == 'legacy_ready':
                self.start('adopt', 'cancelled_adoption', cancel=True)
            elif self.phase == 'cancelled_adoption':
                require(self.manifest.read_bytes() == self.legacy_manifest_before, 'cancelled ADOPT changed legacy journal')
                require(snapshot(self.destination) == self.expected, 'cancelled ADOPT changed payload')
                self.record('typed ADOPT then Cancel preserves the legacy v2 journal and payload')
                self.start('adopt', 'adopted')
            elif self.phase == 'adopted':
                data = json.loads(self.manifest.read_text())
                require(data['format'] == 'intent-journal-v3' and len(data['items']) == 1,
                        'ADOPT did not bind only the remaining legacy payload')
                require(data['legacy_adoption']['original_journal'] == json.loads(self.legacy_manifest_before),
                        'ADOPT lost original legacy intent history')
                require(snapshot(self.destination) == self.expected, 'ADOPT deleted or changed payload')
                require(not data['legacy_adoption']['historical_identity_verified'], 'ADOPT invented historical proof')
                self.record('confirmed ADOPT preserves original v2 history and binds current bytes without deleting data')
                self.manifest_before_cancel = self.manifest.read_bytes()
                if self.device_revalidation:
                    data = json.loads(self.manifest.read_text())
                    row = data['items'][0]
                    row.pop('filesystem_identity', None)  # Model an older sealed v3 journal.
                    row['identity'][0] += 1
                    for node in row['tree_inventory']:
                        node['identity'][0] += 1
                    self.manifest.write_text(json.dumps(data))
                    self.manifest_before_cancel = self.manifest.read_bytes()
                    self.phase = 'device_ready'
                    self.start_device_revalidation(cancel=True)
                else:
                    self.start('purge', 'cancelled_purge', cancel=True)
            elif self.phase == 'device_ready':
                self.start_device_revalidation(cancel=True)
            elif self.phase == 'device_cancelled':
                require(self.manifest.read_bytes() == self.manifest_before_cancel,
                        'cancelled REVALIDATE changed the original journal')
                require(snapshot(self.destination) == self.expected, 'cancelled REVALIDATE changed data')
                self.record('typed REVALIDATE then Cancel preserves exact journal and payload')
                self.start_device_revalidation(cancel=False)
            elif self.phase == 'device_revalidated':
                data = json.loads(self.manifest.read_text())
                require(data['items'][0]['identity'][0] == self.destination.stat().st_dev,
                        'REVALIDATE did not update the device binding')
                require(data['items'][0]['move_status'] == 'moved', 'REVALIDATE authorized deletion')
                require(not data['device_revalidations'][0]['historical_binding_verified'],
                        'legacy revalidation falsely claimed historical filesystem proof')
                require(snapshot(self.destination) == self.expected, 'REVALIDATE changed data')
                self.manifest_before_cancel = self.manifest.read_bytes()
                self.record('confirmed REVALIDATE binds verified current contents; independent PURGE cancellation preserves data')
                self.phase = 'cancelled_purge'
            elif self.phase == 'cancelled_purge':
                require(snapshot(self.destination) == self.expected, 'cancelled PURGE changed quarantined data')
                require(self.manifest.read_bytes() == self.manifest_before_cancel,
                        'cancelled PURGE preview modified its journal')
                self.record('typed PURGE then Cancel preserves quarantined bytes and journal')
                self.start('purge', 'empty_purge', reject='empty')
            elif self.phase == 'empty_purge':
                require(snapshot(self.destination) == self.expected, 'empty PURGE token deleted data')
                require(self.manifest.read_bytes() == self.manifest_before_cancel, 'empty PURGE token changed journal')
                self.start('purge', 'invalid_purge', reject='invalid')
            elif self.phase == 'invalid_purge':
                require(snapshot(self.destination) == self.expected, 'invalid PURGE token deleted data')
                require(self.manifest.read_bytes() == self.manifest_before_cancel, 'invalid PURGE token changed journal')
                self.record('Enter with empty or incorrect PURGE token preserves exact bytes and journal')
                self.start('purge', 'purged')
            elif self.phase == 'purged':
                runs = {run['run_id']: run for run in engine.quarantine_runs(self.home, self.roots)}
                require(runs[self.run_id]['status'] == 'PURGED', 'PURGE history did not update')
                require(runs[self.restored_id]['status'] == 'RESTORED', 'PURGE changed a different run')
                require(not self.destination.exists() and not self.source.exists(), 'PURGE retained fixture payload')
                self.guard()
                self.record('PURGE removes only the selected payload; completed history and sentinels preserved')
                self.manifest_before_cancel = self.manifest.read_bytes()
                self.other_manifest = engine.quarantine_dir(self.home, self.roots) / self.restored_id / 'manifest.json'
                self.other_manifest_before = self.other_manifest.read_bytes()
                self.start('history', 'empty_history', reject='empty')
            elif self.phase in ('empty_history', 'invalid_history', 'cancelled_history'):
                require(self.manifest.read_bytes() == self.manifest_before_cancel,
                        'empty/incorrect/cancelled HISTORY changed the journal')
                require(self.other_manifest.read_bytes() == self.other_manifest_before,
                        'history preflight changed a different run')
                if self.phase == 'empty_history':
                    self.start('history', 'invalid_history', reject='invalid')
                elif self.phase == 'invalid_history':
                    self.start('history', 'cancelled_history', cancel=True)
                else:
                    self.record('empty/incorrect HISTORY plus Enter and typed HISTORY plus Cancel preserve history')
                    self.start('history', 'history_removed')
            elif self.phase == 'history_removed':
                require(not self.manifest.parent.exists(), 'confirmed HISTORY retained selected journal')
                require(self.other_manifest.read_bytes() == self.other_manifest_before,
                        'HISTORY changed a different run')
                require(not self.source.exists() and not self.destination.exists(), 'HISTORY recreated deleted payload')
                self.guard()
                self.record('HISTORY plus Enter removes only the selected completed journal')
                empty_id = '20000101-010101-123456'
                empty = engine.quarantine_dir(self.home, self.roots) / empty_id
                (empty / 'config').mkdir(parents=True)
                empty_payload = {'format': 'intent-journal-v2', 'created': empty_id, 'items': [
                    {'scope': 'config', 'source': str(self.roots['config'] / 'empty-legacy-fixture'),
                     'destination': str(empty / 'config/empty-legacy-fixture'), 'move_status': 'moved'}]}
                (empty / 'manifest.json').write_text(json.dumps(empty_payload))
                self.phase = 'all_history_ready'
                self.start('all_history', 'history_all_clear')
            elif self.phase == 'all_history_ready':
                self.start('all_history', 'history_all_clear')
            elif self.phase == 'history_all_clear':
                require(not engine.quarantine_runs(self.home, self.roots), 'Bulk history retained eligible records')
                self.guard()
                self.record('bulk HISTORY clears completed history and verified empty v2 records without touching original data')
                self.done = True
                self.ui.quit()
                return False
        except BaseException:
            self.errors.append(traceback.format_exc())
            self.done = True
            self.ui.quit()
            return False
        return True


class GtkUI:
    def __init__(self, backend, session):
        import gi
        gi.require_version('Gtk', '4.0' if backend == 'gtk4' else '3.0')
        from gi.repository import Gtk, GLib, Gio, Gdk
        self.Gtk, self.GLib, self.Gio, self.Gdk = Gtk, GLib, Gio, Gdk
        self.backend, self.session, self.controller = backend, session, None
        self.key_events = {}

    def walk(self, widget):
        yield widget
        children = widget.get_children() if self.backend == 'gtk3' and hasattr(widget, 'get_children') else []
        if self.backend == 'gtk4':
            child = widget.get_first_child()
            while child is not None:
                children.append(child)
                child = child.get_next_sibling()
        for child in children:
            yield from self.walk(child)

    def ready(self):
        app = self.Gio.Application.get_default()
        window = app.get_active_window() if app else None
        if self.controller is None:
            self.controller = getattr(window, '_xdg_controller', None)
        current = self.controller
        if current is None:
            return False
        display = type(current.win.get_display()).__name__.lower()
        require('wayland' in display or 'x11' in display, 'GTK did not use a native Wayland/X11 display')
        actual = 'wayland' if 'wayland' in display else 'x11'
        require(actual == self.session, 'GTK used the wrong display backend: ' + actual)
        return current.scan_complete and not current.busy and not current._quarantine_job_busy

    def dialog(self):
        if self.backend == 'gtk4':
            model = self.Gtk.Window.get_toplevels()
            windows = [model.get_item(i) for i in range(model.get_n_items())]
        else:
            windows = self.Gtk.Window.list_toplevels()
        for window in windows:
            if window.get_visible() and window.get_modal() and any(
                    isinstance(widget, self.Gtk.Button) and widget.get_label() in ('Confirm', 'OK', 'Yes', 'Close')
                    for widget in self.walk(window)):
                return window
        return None

    def title(self, dialog):
        return dialog.get_title()

    def respond(self, dialog, response, token):
        widgets = list(self.walk(dialog))
        entries = [widget for widget in widgets if isinstance(widget, self.Gtk.Entry)]
        if response == 'ok':
            require(not entries, 'Expected a GTK notification without token input')
            next(widget for widget in widgets if isinstance(widget, self.Gtk.Button)
                 and widget.get_label() == 'Close').emit('clicked')
            return
        require(response in ('token', 'cancel', 'empty', 'invalid') and len(entries) == 1, 'unexpected GTK confirmation shape')
        require(token in entries[0].get_placeholder_text(), 'GTK confirmation token differs from expected')
        entries[0].set_text('' if response == 'empty' else 'WRONG' if response == 'invalid' else token)
        if response != 'cancel':
            entries[0].grab_focus()
            if self.session == 'x11':
                send_x11_key(self.title(dialog), next_enter(self))
            else:
                # Headless Weston has no physical keyboard seat. X11 covers
                # actual Return/KP_Enter delivery; Wayland covers its GTK signal.
                self.key_events['gtk_entry_activate'] = self.key_events.get('gtk_entry_activate', 0) + 1
                entries[0].emit('activate')
            return
        button = next(widget for widget in widgets if isinstance(widget, self.Gtk.Button)
                      and widget.get_label() == ('Cancel' if response == 'cancel' else 'Confirm'))
        button.emit('clicked')

    def action(self, operation, source, run_id):
        current = self.controller
        if operation == 'move':
            current.stack.set_visible_child_name('config')
            current.uncertain.set_active(True)
            view = current.lists['config']
            if str(source) not in current.checked:
                for checkbox in self.walk(view):
                    if not isinstance(checkbox, self.Gtk.CheckButton) or not checkbox.get_mapped():
                        continue
                    ancestor = checkbox.get_parent()
                    while ancestor is not None and ancestor is not view:
                        if any(isinstance(widget, self.Gtk.Label) and widget.get_text() == source.name
                               for widget in self.walk(ancestor)):
                            checkbox.set_active(True)
                            break
                        ancestor = ancestor.get_parent()
            if str(source) not in current.checked or not current.move_button.get_sensitive():
                return None
            return lambda: current.move_button.emit('clicked')
        current.stack.set_visible_child_name('quarantine')
        if operation == 'all_history':
            button = next(widget for widget in self.walk(current.qlist) if isinstance(widget, self.Gtk.Button)
                          and widget.get_label() == 'Clear all completed history…')
            return (lambda: button.emit('clicked')) if button.get_mapped() else None
        rows = [widget for widget in self.walk(current.qlist) if isinstance(widget, self.Gtk.ListBoxRow)]
        for row in rows:
            widgets = list(self.walk(row))
            if not any(isinstance(widget, self.Gtk.Label) and run_id in widget.get_text() for widget in widgets):
                continue
            caption = {'restore': 'Restore…', 'purge': 'Purge permanently…', 'history': 'Clear history…', 'adopt': 'Approve current state…'}[operation]
            for widget in widgets:
                if isinstance(widget, self.Gtk.Button) and widget.get_label() == caption and widget.get_mapped():
                    return lambda button=widget: button.emit('clicked')
        return None

    def status(self):
        return self.controller.status.get_text() if self.controller else 'no controller'

    def quit(self):
        app = self.Gio.Application.get_default()
        if app:
            app.quit()

    def run(self, cycle, home, args, runtime):
        from xdg_gui_gtk import launch_gui
        self.GLib.timeout_add(60, cycle.tick)
        launch_gui(engine, home, args, {}, runtime, self.backend)


class QtUI:
    def __init__(self, backend, session):
        from xdg_gui_qt import import_qt
        self.Core, _, self.Widgets, _ = import_qt()
        self.backend, self.session, self.controller = backend, session, None
        self.key_events = {}
        import importlib
        self.Test = importlib.import_module(self.Widgets.__name__.split('.')[0] + '.QtTest').QTest
        self.app = self.Widgets.QApplication.instance() or self.Widgets.QApplication([])

    def ready(self):
        if self.controller is None:
            self.controller = next((window for window in self.app.topLevelWidgets()
                                    if hasattr(window, 'audit_model')), None)
        if self.controller is None:
            return False
        surface = self.controller.windowHandle()
        if surface is None or not surface.isExposed():
            return False
        platform = self.app.platformName()
        require(platform == 'xcb' or platform.startswith('wayland'), 'Qt did not use a native display: ' + platform)
        actual = 'wayland' if platform.startswith('wayland') else 'x11'
        require(actual == self.session,
                'Qt used the wrong display backend: ' + self.app.platformName())
        return (self.controller.scan_complete and self.controller.thread is None
                and not self.controller._quarantine_job_busy)

    def dialog(self):
        return self.app.activeModalWidget()

    def title(self, dialog):
        return dialog.windowTitle()

    def respond(self, dialog, response, token):
        entries = dialog.findChildren(self.Widgets.QLineEdit)
        if response in ('token', 'cancel', 'empty', 'invalid'):
            require(len(entries) == 1, 'expected one Qt token input')
            require(any(token in label.text() for label in dialog.findChildren(self.Widgets.QLabel)),
                    'Qt confirmation token differs from expected')
            entries[0].setText('' if response == 'empty' else 'WRONG' if response == 'invalid' else token)
            if response != 'cancel':
                key = self.Core.Qt.Key.Key_Return if next_enter(self) == 'Return' else self.Core.Qt.Key.Key_Enter
                entries[0].setFocus()
                self.Test.keyClick(entries[0], key)
                return
        else:
            require(not entries, 'expected a Qt question/notification, found a token input')
        caption = {'yes': 'Yes', 'ok': 'OK', 'token': 'OK', 'cancel': 'Cancel'}[response]
        button = next(widget for widget in dialog.findChildren(self.Widgets.QPushButton)
                      if widget.text().replace('&', '') == caption)
        button.click()

    def action(self, operation, source, run_id):
        current = self.controller
        if operation == 'move':
            current.scope_tabs.setCurrentIndex(current.scope_values.index('config'))
            current.allow_uncertain_box.setChecked(True)
            model = current.audit_model
            row = next((i for i, item in enumerate(model.rows) if item.path == source), None)
            if row is None:
                return None
            require(model.setData(model.index(row, 0), self.Core.Qt.CheckState.Checked,
                                  self.Core.Qt.ItemDataRole.CheckStateRole), 'Qt row was not checkable')
            return current.move_button.click if current.move_button.isEnabled() else None
        current.scope_tabs.setCurrentIndex(current.scope_tabs.count() - 1)
        if operation == 'all_history':
            button = next(widget for widget in current.findChildren(self.Widgets.QPushButton)
                          if widget.text() == 'Clear all completed history…')
            return button.click if button.isVisible() and button.isEnabled() else None
        for index in range(current.qtree.topLevelItemCount()):
            item = current.qtree.topLevelItem(index)
            if item.text(0) == run_id:
                current.qtree.setCurrentItem(item)
                break
        else:
            return None
        caption = {'restore': 'Restore selected…', 'purge': 'Purge selected…', 'history': 'Clear history…', 'adopt': 'Approve current state…'}[operation]
        button = next(widget for widget in current.findChildren(self.Widgets.QPushButton)
                      if widget.text() == caption)
        return button.click if button.isVisible() and button.isEnabled() else None

    def status(self):
        return self.controller.statusBar().currentMessage() if self.controller else 'no controller'

    def quit(self):
        self.app.quit()

    def run(self, cycle, home, args, runtime):
        from xdg_gui_qt import launch_gui
        # Schedule independent callbacks before clicking: Qt input dialogs
        # execute nested loops while the action's original callback is active.
        def tick():
            if not cycle.done:
                self.Core.QTimer.singleShot(60, tick)
                cycle.tick()
        self.Core.QTimer.singleShot(60, tick)
        launch_gui(engine, home, args, {}, runtime, self.backend)


class TkUI:
    def __init__(self, backend, session):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.backend, self.session, self.controller, self.root = backend, session, None, None
        self.key_events = {}

    def walk(self, widget):
        yield widget
        for child in widget.winfo_children():
            yield from self.walk(child)

    def ready(self):
        self.controller = getattr(self.root, '_xdg_controller', None)
        if self.controller is None:
            return False
        require(self.root.tk.call('tk', 'windowingsystem') == 'x11' and self.session == 'x11',
                'Tk lifecycle requires an actual X11 display')
        return self.controller.scan_complete and not self.controller.busy and not self.controller._quarantine_job_busy

    def dialog(self):
        if self.root is not None:
            return next((widget for widget in self.walk(self.root)
                         if isinstance(widget, self.tk.Toplevel) and widget.winfo_viewable()), None)

    def title(self, dialog):
        return dialog.title()

    def respond(self, dialog, response, token):
        widgets = list(self.walk(dialog))
        entries = [widget for widget in widgets if isinstance(widget, self.ttk.Entry)]
        if response in ('token', 'cancel', 'empty', 'invalid'):
            require(len(entries) == 1, 'expected one Tk token input')
            require(any(token in str(widget.cget('text')) for widget in widgets
                        if isinstance(widget, self.ttk.Label)), 'Tk confirmation token differs from expected')
            entries[0].delete(0, 'end')
            entries[0].insert(0, '' if response == 'empty' else 'WRONG' if response == 'invalid' else token)
            if response != 'cancel':
                entries[0].focus_force()
                entries[0].event_generate('<KeyPress-' + next_enter(self) + '>')
                return
        else:
            require(not entries, 'expected a Tk question/notification, found a token input')
        caption = {'yes': 'Yes', 'ok': 'OK', 'token': 'OK', 'cancel': 'Cancel'}[response]
        button = next(widget for widget in widgets if isinstance(widget, self.ttk.Button)
                      and widget.cget('text') == caption)
        button.invoke()

    def action(self, operation, source, run_id):
        current = self.controller
        if operation == 'move':
            current.tabs.select(current.scope_frames['config'])
            current.allow_uncertain.set(True)
            tree = current.views['config']
            if str(source) not in current.checked:
                bounds = tree.bbox(str(source), '#1')
                if not bounds:
                    return None
                x, y, width, height = bounds
                tree.event_generate('<ButtonRelease-1>', x=x + width // 2, y=y + height // 2)
            if str(source) not in current.checked or current.move_button.instate(['disabled']):
                return None
            return current.move_button.invoke
        current.tabs.select(current.tabs.tabs()[-1])
        if operation != 'all_history' and not current.qtree.exists(run_id):
            return None
        if operation == 'all_history':
            button = next(widget for widget in self.walk(self.root) if isinstance(widget, self.ttk.Button)
                          and widget.cget('text') == 'Clear all completed history…')
            return button.invoke if button.winfo_viewable() else None
        current.qtree.selection_set(run_id)
        current.qtree.focus(run_id)
        caption = {'restore': 'Restore operation…', 'purge': 'Purge permanently…', 'history': 'Clear history…', 'adopt': 'Approve current state…'}[operation]
        button = next(widget for widget in self.walk(self.root) if isinstance(widget, self.ttk.Button)
                      and widget.cget('text') == caption)
        return button.invoke if button.winfo_viewable() else None

    def status(self):
        if self.controller is None:
            return 'no controller'
        buttons = [(widget.cget('text'), widget.winfo_viewable()) for widget in self.walk(self.root)
                   if isinstance(widget, self.ttk.Button) and 'Restore' in str(widget.cget('text'))]
        return (self.controller.status.get() + '; selected tab=' + str(self.controller.tabs.select())
                + '; runs=' + str(self.controller.qtree.get_children()) + '; restore buttons=' + str(buttons))

    def quit(self):
        if self.root is not None:
            self.root.destroy()

    def run(self, cycle, home, args, runtime):
        from xdg_gui_tk import launch_gui
        original = self.tk.Tk

        def create_root(*values, **keywords):
            self.root = original(*values, **keywords)
            def tick():
                if not cycle.done:
                    self.root.after(60, tick)
                    cycle.tick()
            self.root.after(60, tick)
            return self.root

        with patch.object(self.tk, 'Tk', create_root):
            launch_gui(engine, home, args, {}, runtime, self.backend)


def run(backend, session, output=None, device_revalidation=False):
    engine.check_no_root()
    require(session in ('x11', 'wayland'), 'unsupported display session')
    require(bool(os.environ.get('WAYLAND_DISPLAY' if session == 'wayland' else 'DISPLAY')),
            'requested native display is unavailable')
    if session == 'wayland':
        require('DISPLAY' not in os.environ and backend != 'tk', 'Wayland must run without an X11 fallback')
    from xdg_prefs import defaults
    with tempfile.TemporaryDirectory(prefix='xdg-gui-cycle-') as temporary:
        home = Path(temporary)
        env = {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
               'XDG_DATA_HOME': str(home / '.local/share'), 'XDG_STATE_HOME': str(home / '.local/state'),
               'XDG_CACHE_HOME': str(home / '.cache'), 'XDG_AUDIT_PACMAN_LOG': str(home / 'empty.log')}
        # Keep native provider tests separate. Every lifecycle operation below
        # still performs the production fresh-inventory check against this fixture.
        inventory = ({'python', 'coreutils'}, set(), set(), set(), set(), set(), set(), set())
        from contextlib import nullcontext
        import xdg_filesystem
        binding = {'kind': 'btrfs', 'fsid': '11111111-2222-3333-4444-555555555555',
                   'subvolume_id': 256, 'subvolume_uuid': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}
        probe = patch.object(xdg_filesystem, 'btrfs_identity', return_value=binding) if device_revalidation else nullcontext()
        with patch.dict(os.environ, env), patch.object(engine, 'read_active_names', return_value=inventory), probe:
            ui = (GtkUI if backend.startswith('gtk') else QtUI if backend == 'qt6' else TkUI)(backend, session)
            cycle = Cycle(ui, home, device_revalidation)
            args = SimpleNamespace(saved_prefs={**defaults(), 'language': 'en'},
                                   keep=[], quick=True, scope='config', all=False)
            runtime = {'desktop': 'CI', 'session': session, 'selected': backend,
                       'available': [backend], 'wm': 'test'}
            ui.run(cycle, home, args, runtime)
            require(cycle.done and not cycle.errors, '\n'.join(cycle.errors) or 'GUI exited before completing lifecycle')
            require(cycle.phase == 'history_all_clear', 'GUI did not complete every lifecycle stage')
            if not (backend.startswith('gtk') and session == 'wayland'):
                require(all(ui.key_events.get(key, 0) > 0 for key in ('Return', 'KP_Enter')),
                        'Both Enter keys must be exercised')
            report = {'backend': backend, 'native_session': session, 'inventory': 'synthetic',
                      'legacy_adoption': 'synthetic v2 journal with moved and never-moved entries',
                      'filesystem_evidence': 'synthetic Btrfs metadata and device transition' if device_revalidation else 'native',
                      'version': engine.VERSION, 'commit': os.environ.get('GITHUB_SHA'),
                      'checks': cycle.events, 'confirmation_key_events': ui.key_events,
                      'result': 'PASS', 'fixture_hashes': cycle.expected}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS GUI lifecycle: ' + backend + ' on native ' + session, flush=True)


if __name__ == '__main__':
    faulthandler.enable()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('gtk4', 'gtk3', 'qt6', 'tk'), required=True)
    parser.add_argument('--expect-session', choices=('x11', 'wayland'), default='x11')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--device-revalidation', action='store_true')
    values = parser.parse_args()
    run(values.backend, values.expect_session, values.output, values.device_revalidation)
