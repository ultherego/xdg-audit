#!/usr/bin/env python3
"""Initialize and exercise GTK4, Qt6 or Tk widgets under a virtual display."""
import argparse


def tk_smoke():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.withdraw()
    table = ttk.Treeview(root, columns=('status', 'size'), show='headings')
    table.heading('status', text='Status')
    table.heading('size', text='Size')
    entry = table.insert('', 'end', values=('UNKNOWN', '42B'))
    table.selection_set(entry)
    assert table.item(entry)['values'] == ['UNKNOWN', '42B']
    table.destroy()
    root.destroy()


def gtk4_smoke():
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gio
    Gtk.init()
    store = Gio.ListStore.new(Gtk.StringObject)
    store.append(Gtk.StringObject.new('candidate'))
    model = Gtk.SingleSelection.new(store)
    view = Gtk.ColumnView.new(model)
    factory = Gtk.SignalListItemFactory()
    factory.connect('setup', lambda _factory, row: row.set_child(Gtk.Label(xalign=0)))
    factory.connect('bind', lambda _factory, row: row.get_child().set_text(row.get_item().get_string()))
    column = Gtk.ColumnViewColumn.new('Name', factory)
    column.set_expand(True)
    view.append_column(column)
    window = Gtk.Window()
    window.set_child(view)
    window.present()
    assert store.get_n_items() == 1
    window.close()


def qt6_smoke():
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PyQt6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    table = QtWidgets.QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(['Status', 'Size'])
    table.setItem(0, 0, QtWidgets.QTableWidgetItem('UNKNOWN'))
    table.setItem(0, 1, QtWidgets.QTableWidgetItem('42B'))
    table.show()
    app.processEvents()
    assert table.item(0, 0).text() == 'UNKNOWN'
    table.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', required=True, choices=['gtk4', 'qt6', 'tk'])
    args = parser.parse_args()
    {'gtk4': gtk4_smoke, 'qt6': qt6_smoke, 'tk': tk_smoke}[args.backend]()
    print(f'{args.backend}: widget smoke passed')
