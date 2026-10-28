"""Content-sized, bounded dialogs for optional GTK, Qt and Tk backends.

No toolkit is imported until a backend is already running. Confirmations keep
their original return values and tokens; closing a dialog always cancels.
"""
from math import ceil
from types import SimpleNamespace

from xdg_gui_layout import DIALOG_PADDING, SCREEN_MARGIN, dialog_limits


def configure_gtk_dialog(dialog, content, Gtk, Gdk, Pango):
    """Fit natural content with scrolling, fixed padding and a pinned footer."""
    parent = dialog.get_transient_for()
    display = dialog.get_display()
    gtk4 = hasattr(Gtk, 'ColumnView')
    monitor = None
    if gtk4:
        surface = parent.get_surface() if parent else None
        if surface is not None:
            monitor = display.get_monitor_at_surface(surface)
        if monitor is None:
            monitor = display.get_monitors().get_item(0)
    else:
        window = parent.get_window() if parent else None
        monitor = display.get_monitor_at_window(window) if window else display.get_primary_monitor()
    area = (monitor.get_workarea() if hasattr(monitor, 'get_workarea') else monitor.get_geometry())
    max_width, max_height = dialog_limits(area.width, area.height)
    inner_width = max_width - 2 * DIALOG_PADDING - 20
    children = []
    child = content.get_first_child() if gtk4 else None
    if gtk4:
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
    else:
        children = list(content.get_children())

    def child_list(widget):
        if not gtk4:
            return list(widget.get_children()) if hasattr(widget, 'get_children') else []
        result = []
        child = widget.get_first_child()
        while child is not None:
            result.append(child)
            child = child.get_next_sibling()
        return result

    def append(box, widget):
        box.append(widget) if gtk4 else box.pack_start(widget, False, False, 0)

    footer = []
    if children:
        last = children[-1]
        buttons = isinstance(last, Gtk.Button) or (
            isinstance(last, Gtk.Box) and any(isinstance(w, Gtk.Button) for w in child_list(last)))
        if buttons:
            footer.insert(0, children.pop())
            if children and isinstance(children[-1], (Gtk.Entry, Gtk.SpinButton)):
                footer.insert(0, children.pop())
    for widget in children + footer:
        content.remove(widget)
    body = Gtk.Box(orientation=content.get_orientation(), spacing=content.get_spacing())
    max_body_height = max(60, max_height - 2 * DIALOG_PADDING - (90 if footer else 0))

    def prepare(widget):
        if isinstance(widget, Gtk.Label):
            if hasattr(widget, 'set_wrap'):
                widget.set_wrap(True)
                widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            else:
                widget.set_line_wrap(True)
                widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            unit = max(1, widget.create_pango_layout('M').get_pixel_size()[0])
            widget.set_max_width_chars(max(12, min(80, inner_width // unit)))
        if isinstance(widget, Gtk.ScrolledWindow):
            widget.set_propagate_natural_width(True)
            widget.set_propagate_natural_height(True)
            widget.set_max_content_width(inner_width)
            widget.set_max_content_height(max(widget.get_min_content_height(), 60, max_body_height // 2))
        for child in child_list(widget):
            prepare(child)

    for widget in children:
        prepare(widget)
        append(body, widget)
    if not gtk4:
        body.show_all()
    natural_width = (body.measure(Gtk.Orientation.HORIZONTAL, -1)[1] if gtk4
                     else body.get_preferred_width()[1])
    measured_width = max(1, min(inner_width, natural_width))
    natural_height = (body.measure(Gtk.Orientation.VERTICAL, measured_width)[1] if gtk4
                      else body.get_preferred_height_for_width(measured_width)[1])
    # Unparented GTK3 form measurements can undercount themed field heights.
    # Always bound forms containing editors, while keeping simple prompts compact.
    def contains_editor(widget):
        return (isinstance(widget, Gtk.ScrolledWindow) or
                any(contains_editor(child) for child in child_list(widget)))
    has_editors = any(contains_editor(widget) for widget in children)
    if natural_height > max_body_height or has_editors:
        scrolling = Gtk.ScrolledWindow()
        scrolling.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolling.set_propagate_natural_width(True)
        scrolling.set_propagate_natural_height(True)
        scrolling.set_max_content_width(inner_width)
        scrolling.set_min_content_height(0)
        scrolling.set_max_content_height(max_body_height)
        scrolling.set_child(body) if gtk4 else scrolling.add(body)
        append(content, scrolling)
    else:
        append(content, body)
    for widget in footer:
        append(content, widget)
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(content, 'set_margin_' + side)(DIALOG_PADDING)
    dialog.set_default_size(-1, -1)
    dialog.set_resizable(True)
    dialog.set_child(content) if gtk4 else dialog.add(content)
    dialog._xdg_padding = DIALOG_PADDING


def _qt_bounds(dialog, QtWidgets):
    parent = dialog.parentWidget()
    screen = parent.screen() if parent else QtWidgets.QApplication.primaryScreen()
    area = screen.availableGeometry()
    return area, dialog_limits(area.width(), area.height())


def _qt_show_size(dialog, QtWidgets):
    area, (width, height) = _qt_bounds(dialog, QtWidgets)
    dialog.setMaximumSize(width, height)
    dialog.adjustSize()
    dialog.resize(min(dialog.width(), width), min(dialog.height(), height))
    parent = dialog.parentWidget()
    center = parent.frameGeometry().center() if parent else area.center()
    x = max(area.left() + SCREEN_MARGIN, min(center.x() - dialog.width() // 2,
            area.right() - SCREEN_MARGIN - dialog.width()))
    y = max(area.top() + SCREEN_MARGIN, min(center.y() - dialog.height() // 2,
            area.bottom() - SCREEN_MARGIN - dialog.height()))
    dialog.move(x, y)


def fit_qt_dialog(dialog, QtWidgets, QtCore, tr=lambda value: value):
    """Bound existing settings/report forms while keeping their actions visible."""
    layout = dialog.layout()
    _, (max_width, max_height) = _qt_bounds(dialog, QtWidgets)
    width = min(720, max_width - 2 * DIALOG_PADDING - 24)
    body = QtWidgets.QWidget()
    contents = QtWidgets.QVBoxLayout(body)
    contents.setContentsMargins(0, 0, 0, 0)
    footer = None
    if layout.count():
        last = layout.itemAt(layout.count() - 1).widget()
        if isinstance(last, (QtWidgets.QDialogButtonBox, QtWidgets.QPushButton)):
            footer = layout.takeAt(layout.count() - 1).widget()
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            if isinstance(widget, QtWidgets.QLabel):
                widget.setWordWrap(True)
                widget.setMaximumWidth(width)
            if isinstance(widget, QtWidgets.QPlainTextEdit):
                text = widget.toPlainText()
                metrics = widget.fontMetrics()
                lines = sum(max(1, ceil(metrics.horizontalAdvance(line) / max(1, width)))
                            for line in text.split('\n'))
                widget.setFixedHeight(min(260 if widget.isReadOnly() else 140,
                    max(55, lines * metrics.lineSpacing() + 18)))
            contents.addWidget(widget)
        elif item.layout() is not None:
            contents.addLayout(item.layout())
        else:
            contents.addItem(item)
    scrolling = QtWidgets.QScrollArea()
    scrolling.setWidgetResizable(True)
    scrolling.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scrolling.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scrolling.setWidget(body)
    scrolling.setMinimumWidth(min(width, body.sizeHint().width() + 20))
    scrolling.setFixedHeight(min(max(60, max_height - 2 * DIALOG_PADDING - 65),
                                 body.sizeHint().height() + 4))
    layout.setContentsMargins(*([DIALOG_PADDING] * 4))
    layout.addWidget(scrolling)
    if footer is not None:
        if isinstance(footer, QtWidgets.QDialogButtonBox):
            for flag, text in ((QtWidgets.QDialogButtonBox.StandardButton.Save, 'Zapisz'),
                               (QtWidgets.QDialogButtonBox.StandardButton.Cancel, 'Anuluj')):
                button = footer.button(flag)
                if button is not None:
                    button.setText(tr(text))
        layout.addWidget(footer)
    _qt_show_size(dialog, QtWidgets)
    dialog._xdg_padding = DIALOG_PADDING


def qt_dialog_helpers(QtWidgets, QtCore, tr):
    """Create native-looking bounded message/input dialogs without global patches."""
    def shell(parent, title, text, icon=None):
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle(title)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(*([DIALOG_PADDING] * 4))
        _, (max_width, max_height) = _qt_bounds(dialog, QtWidgets)
        label = QtWidgets.QLabel(str(text))
        label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse |
                                      QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard)
        label.setWordWrap(True)
        metrics = label.fontMetrics()
        natural = max((metrics.horizontalAdvance(line) for line in str(text).split('\n')), default=0)
        width = min(720, max_width - 2 * DIALOG_PADDING - (70 if icon else 24), max(140, natural))
        label.setFixedWidth(width)
        label.setMinimumHeight(max(metrics.lineSpacing(), label.heightForWidth(width)))
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(label)
        scroll.setFixedWidth(width + 22)
        scroll.setFixedHeight(min(label.minimumHeight() + 4,
            max(55, max_height - 2 * DIALOG_PADDING - 125)))
        if icon is not None:
            row = QtWidgets.QHBoxLayout()
            emblem = QtWidgets.QLabel()
            emblem.setPixmap(QtWidgets.QApplication.style().standardIcon(icon).pixmap(32, 32))
            row.addWidget(emblem, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            row.addWidget(scroll)
            layout.addLayout(row)
        else:
            layout.addWidget(scroll)
        dialog._xdg_padding = DIALOG_PADDING
        return dialog, layout

    def message(parent, title, text, buttons=None, default=None, question=False, icon=None):
        flags = QtWidgets.QMessageBox.StandardButton
        wanted = buttons if buttons is not None else (flags.Yes | flags.No if question else flags.Ok)
        dialog, layout = shell(parent, title, text, icon)
        box = QtWidgets.QDialogButtonBox()
        response = [flags.No if question else flags.Cancel]
        default_button = None
        for flag in (flags.Ok, flags.Yes, flags.No, flags.Cancel):
            if wanted & flag:
                button = box.addButton(QtWidgets.QDialogButtonBox.StandardButton(flag.value))
                button.setText(tr({flags.Ok: 'OK', flags.Yes: 'Tak', flags.No: 'Nie', flags.Cancel: 'Anuluj'}[flag]))
                button.clicked.connect(lambda _=False, value=flag: (response.__setitem__(0, value), dialog.accept()))
                if flag == (default if default is not None else (flags.No if question else flags.Ok)):
                    button.setDefault(True)
                    default_button = button
        layout.addWidget(box)
        _qt_show_size(dialog, QtWidgets)
        if default_button is not None:
            default_button.setFocus()
        dialog.exec()
        return response[0]

    def information(parent, title, text, buttons=None, defaultButton=None):
        return message(parent, title, text, buttons, defaultButton,
                       icon=QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation)

    def warning(parent, title, text, buttons=None, defaultButton=None):
        return message(parent, title, text, buttons, defaultButton,
                       icon=QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning)

    def critical(parent, title, text, buttons=None, defaultButton=None):
        return message(parent, title, text, buttons, defaultButton,
                       icon=QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical)

    def question(parent, title, text, buttons=None, defaultButton=None):
        return message(parent, title, text, buttons, defaultButton, True,
                       QtWidgets.QStyle.StandardPixmap.SP_MessageBoxQuestion)

    def input_dialog(parent, title, text, editor):
        dialog, layout = shell(parent, title, text)
        layout.addWidget(editor)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                           QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(tr('OK'))
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText(tr('Anuluj'))
        layout.addWidget(buttons)
        _qt_show_size(dialog, QtWidgets)
        editor.setFocus()
        accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
        return dialog, accepted

    def get_text(parent, title, label, echo=None, text='', **_):
        editor = QtWidgets.QLineEdit(text)
        if echo is not None:
            editor.setEchoMode(echo)
        dialog, ok = input_dialog(parent, title, label, editor)
        return editor.text(), ok

    def get_int(parent, title, label, value=0, min=-2147483647, max=2147483647, step=1, **_):
        editor = QtWidgets.QSpinBox()
        editor.setRange(min, max)
        editor.setSingleStep(step)
        editor.setValue(value)
        dialog, ok = input_dialog(parent, title, label, editor)
        return editor.value(), ok

    def get_item(parent, title, label, items, current=0, editable=True, **_):
        editor = QtWidgets.QComboBox()
        editor.addItems(items)
        editor.setCurrentIndex(current)
        editor.setEditable(editable)
        dialog, ok = input_dialog(parent, title, label, editor)
        return editor.currentText(), ok

    return (SimpleNamespace(information=information, warning=warning, critical=critical,
                            question=question),
            SimpleNamespace(getText=get_text, getInt=get_int, getItem=get_item))


def new_tk_dialog(tk, ttk, parent, title):
    """Create a scrollable body and a separate action row inside 20 px padding."""
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.transient(parent)
    outer = ttk.Frame(dialog, padding=DIALOG_PADDING)
    outer.pack(fill='both', expand=True)
    region = ttk.Frame(outer)
    region.pack(fill='both', expand=True)
    canvas = tk.Canvas(region, borderwidth=0, highlightthickness=0)
    background = ttk.Style(parent).lookup('TFrame', 'background')
    if background:
        canvas.configure(background=background)
    scrollbar = ttk.Scrollbar(region, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    body = ttk.Frame(canvas)
    item = canvas.create_window(0, 0, window=body, anchor='nw')
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
    body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
    actions = ttk.Frame(outer, padding=(0, 12, 0, 0))
    actions.pack(fill='x')
    dialog._xdg_layout = (parent, body, actions, canvas, scrollbar)
    dialog._xdg_padding = DIALOG_PADDING
    return dialog, body, actions


def fit_tk_dialog(dialog):
    parent, body, actions, canvas, scrollbar = dialog._xdg_layout
    max_width, max_height = dialog_limits(parent.winfo_screenwidth(), parent.winfo_screenheight())
    inner_width = max_width - 2 * DIALOG_PADDING - 20
    for widget in body.winfo_children():
        if widget.winfo_class() in ('TLabel', 'Label'):
            widget.configure(wraplength=min(720, inner_width))
        elif widget.winfo_class() == 'Text':
            widget.configure(width=max(20, min(80, inner_width // 8)))
    dialog.update_idletasks()
    width = min(inner_width, max(140, body.winfo_reqwidth()))
    height = min(max(60, max_height - actions.winfo_reqheight() - 2 * DIALOG_PADDING),
                 body.winfo_reqheight())
    canvas.configure(width=width, height=height)
    if body.winfo_reqheight() > height:
        scrollbar.pack(side='right', fill='y')
    else:
        scrollbar.pack_forget()
    dialog.update_idletasks()
    width = min(max_width, dialog.winfo_reqwidth())
    height = min(max_height, dialog.winfo_reqheight())
    x = max(SCREEN_MARGIN, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2,
                              parent.winfo_screenwidth() - SCREEN_MARGIN - width))
    y = max(SCREEN_MARGIN, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2,
                              parent.winfo_screenheight() - SCREEN_MARGIN - height - 32))
    dialog.geometry(f'{width}x{height}+{x}+{y}')
    dialog.deiconify()


def tk_dialog_helpers(tk, ttk, root, tr):
    def show(title, message, *, question=False, editor=None, initialvalue=None,
             minvalue=None, maxvalue=None, parent=None, **_):
        parent = parent or root
        previous_grab = parent.grab_current()
        dialog, body, actions = new_tk_dialog(tk, ttk, parent, title)
        ttk.Label(body, text=str(message), justify='left').pack(anchor='w', fill='x')
        response = [False if question else None]
        field = None
        feedback = None
        if editor:
            field = ttk.Entry(actions)
            field.pack(fill='x', pady=(0, 10))
            if initialvalue is not None:
                field.insert(0, str(initialvalue))
            feedback = ttk.Label(actions, text='')
            feedback.pack(anchor='w')

        def accept():
            value = field.get() if field else ('yes' if question else 'ok')
            if editor == 'integer':
                try:
                    value = int(value)
                    if ((minvalue is not None and value < minvalue) or
                            (maxvalue is not None and value > maxvalue)):
                        raise ValueError()
                except ValueError:
                    feedback.configure(text=tr('Nieprawidłowa wartość.'))
                    fit_tk_dialog(dialog)
                    return
            response[0] = value if editor else (True if question else 'ok')
            dialog.destroy()

        buttons = ttk.Frame(actions)
        buttons.pack(fill='x')
        if question or editor:
            ttk.Button(buttons, text=tr('Anuluj') if editor else tr('Nie'),
                       command=dialog.destroy).pack(side='right')
        button = ttk.Button(buttons, text=tr('Tak') if question else tr('OK'), command=accept)
        button.pack(side='right', padx=(0, 8))
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.bind('<Escape>', lambda _: dialog.destroy())
        if field:
            def accept_key(_):
                accept()
                return 'break'
            field.bind('<Return>', accept_key)
            field.bind('<KP_Enter>', accept_key)
        fit_tk_dialog(dialog)
        dialog.wait_visibility()
        dialog.grab_set()
        (field or (buttons.winfo_children()[0] if question else button)).focus_set()
        dialog.wait_window()
        if previous_grab is not None:
            try:
                previous_grab.grab_set()
            except tk.TclError:
                pass
        return response[0]

    def info(title, message, **options):
        return show(title, message, **options)

    def yesno(title, message, **options):
        return bool(show(title, message, question=True, **options))

    def askstring(title, prompt, **options):
        return show(title, prompt, editor='string', **options)

    def askinteger(title, prompt, **options):
        return show(title, prompt, editor='integer', **options)

    return (SimpleNamespace(showinfo=info, showwarning=info, showerror=info, askyesno=yesno),
            SimpleNamespace(askstring=askstring, askinteger=askinteger))
