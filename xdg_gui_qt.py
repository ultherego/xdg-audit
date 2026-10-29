"""Optional small Qt6 GUI for xdg-audit. No GUI deps are imported by the CLI."""
from __future__ import annotations
from xdg_i18n import translate, translate_ui_text, entries_count, selected_count, format_message

import json
import os
from pathlib import Path
from typing import Any

from xdg_theme import Appearance, detect_appearance
from xdg_inspector import details_text, open_item_location
from xdg_gui_jobs import run_gui_job
from xdg_gui_layout import visible_optional_scopes
from xdg_gui_dialogs import qt_dialog_helpers, fit_qt_dialog
from xdg_quarantine_messages import quarantine_error_details, identity_issue_details, device_revalidation_details


def import_qt():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        return QtCore, QtGui, QtWidgets, QtCore.Signal
    except ImportError:
        try:
            from PyQt6 import QtCore, QtGui, QtWidgets
            return QtCore, QtGui, QtWidgets, QtCore.pyqtSignal
        except ImportError as exc:
            raise RuntimeError("Qt6 Python bindings are unavailable; checking other existing GUI backends") from exc


def launch_gui(engine: Any, home: Path, args: Any, aliases: dict[str, list[str]], runtime=None, backend="qt6") -> int:

    _language = getattr(args, 'saved_prefs', {}).get('language', 'pl')
    def tr(value):
        return translate(value, _language)

    def tf(template, **values):
        return format_message(template, _language, **values)
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        # Allow explicit offscreen testing, but do not set it for real users.
        pass
    QtCore, QtGui, QtWidgets, Signal = import_qt()
    Qt = QtCore.Qt
    Slot = QtCore.Slot if hasattr(QtCore, "Slot") else QtCore.pyqtSlot
    Role = Qt.ItemDataRole.UserRole
    messages, inputs = qt_dialog_helpers(QtWidgets, QtCore, tr)

    class AuditModel(QtCore.QAbstractTableModel):
        HEADERS = ('Wybór', 'Nazwa', 'Status', 'Rozmiar', 'Lokalizacja')
        def __init__(self, window):
            super().__init__(window)
            self.window = window
            self.rows = []
        def rowCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else len(self.rows)
        def columnCount(self, parent=QtCore.QModelIndex()):
            return 0 if parent.isValid() else 5
        def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
            if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
                return tr(self.HEADERS[section])
            return None
        def data(self, index, role=Qt.ItemDataRole.DisplayRole):
            if not index.isValid() or index.row() >= len(self.rows):
                return None
            it = self.rows[index.row()]
            if role == Role:
                return str(it.path)
            if role == Qt.ItemDataRole.UserRole + 1:
                return it.bytes if index.column() == 3 else it.path.name.casefold()
            if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
                if self.window.is_eligible(it):
                    return (Qt.CheckState.Checked if str(it.path) in self.window.checked
                            else Qt.CheckState.Unchecked)
            if role == Qt.ItemDataRole.DisplayRole:
                return ('', it.path.name, it.state, engine.human(it.bytes), str(it.path.parent))[index.column()]
            return None
        def flags(self, index):
            if not index.isValid():
                return Qt.ItemFlag.NoItemFlags
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.column() == 0 and self.window.is_eligible(self.rows[index.row()]):
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            return flags
        def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
            if (role != Qt.ItemDataRole.CheckStateRole or not index.isValid()
                    or index.column() != 0 or not self.window.is_eligible(self.rows[index.row()])):
                return False
            path = str(self.rows[index.row()].path)
            if value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked:
                self.window.checked.add(path)
            else:
                self.window.checked.discard(path)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            self.window.update_selection_status(reveal=True)
            return True
        def set_rows(self, rows):
            self.beginResetModel()
            self.rows = list(rows)
            self.endResetModel()

    class AuditProxy(QtCore.QSortFilterProxyModel):
        def lessThan(self, left, right):
            if left.column() == 3:
                return int(left.data(Qt.ItemDataRole.UserRole + 1) or 0) < int(right.data(Qt.ItemDataRole.UserRole + 1) or 0)
            return str(left.data(Qt.ItemDataRole.DisplayRole) or '').casefold() < str(right.data(Qt.ItemDataRole.DisplayRole) or '').casefold()

    class Scanner(QtCore.QObject):
        cancelled = Signal()
        finished = Signal(object, object, object)
        failed = Signal(str)
        batch = Signal(str, object, int, int)
        phase = Signal(str)

        def __init__(self, scopes, quick):
            super().__init__()
            import threading
            self.cancel_event = threading.Event()
            self.scopes, self.quick = scopes, quick

        @Slot()
        def run(self):
            try:
                result = engine.scan(home, self.scopes, {engine.normalize(x) for x in args.keep},
                                     aliases, self.quick,
                                     progress=self.phase.emit,
                                     on_batch=lambda kind, batch, done, total: self.batch.emit(kind, batch, done, total),
                                     cancelled=self.cancel_event.is_set)
                self.finished.emit(*result)
            except engine.ScanCancelled:
                self.cancelled.emit()
            except Exception as exc:
                self.failed.emit(f"{type(exc).__name__}: {exc}")

    class QuarantineSignals(QtCore.QObject):
        finished = Signal(object, object)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('xdg-audit · Audit' if _language=='en' else 'xdg-audit · Audyt konfiguracji')
            self.setWindowIcon(QtGui.QIcon(str(Path(__file__).with_name('assets') / 'xdg-audit.png')))
            self.prefs = dict(getattr(args, 'saved_prefs', {}))
            self.resize(1350, 840)
            self.setMinimumSize(1040, 665)
            self.items = []
            self.checked = set()
            self.scan_complete=False
            self._quarantine_job_busy=False
            self._quarantine_callback=None
            self._quarantine_signals=QuarantineSignals(self)
            self._quarantine_signals.finished.connect(self._quarantine_finished)
            self.roots = {}
            self.stats = {}
            self.thread = None
            self.worker = None
            self.scheme_info: Appearance | None = None
            self.original_palette = QtGui.QPalette(QtWidgets.QApplication.palette())
            self._build()
            self.apply_system_theme(force=True)
            self.refresh_theme_timer = QtCore.QTimer(self)
            self.refresh_theme_timer.timeout.connect(self.apply_system_theme)
            self.refresh_theme_timer.start(15000)
            self.scan_async()

        def _build(self):
            app_root = QtWidgets.QWidget()
            self.setCentralWidget(app_root)
            layout = QtWidgets.QVBoxLayout(app_root)
            layout.setContentsMargins(22, 18, 22, 14)
            layout.setSpacing(13)

            # Header and short environment subtitle; native palette stays intact.
            hero = QtWidgets.QHBoxLayout()
            titles = QtWidgets.QVBoxLayout()
            titles.setSpacing(2)
            heading = QtWidgets.QLabel('xdg-audit')
            font = heading.font()
            font.setPointSize(max(17, font.pointSize() + 8))
            font.setBold(True)
            heading.setFont(font)
            titles.addWidget(heading)
            subtitle = QtWidgets.QLabel(tr('Audyt i bezpieczne porządki w katalogach użytkownika'))
            self.subtitle=subtitle
            titles.addWidget(subtitle)
            app_icon = QtWidgets.QLabel()
            icon_pixmap = QtGui.QPixmap(str(Path(__file__).with_name('assets') / 'xdg-audit-128.png'))
            if not icon_pixmap.isNull():
                app_icon.setPixmap(icon_pixmap.scaled(68, 68,
                    Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                app_icon.setFixedSize(68, 68)
                hero.addWidget(app_icon)
            hero.addLayout(titles,1)
            self.theme_label = QtWidgets.QLabel(tr('Wykrywanie motywu…'))
            self.theme_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.theme_label.setToolTip(tr('Środowisko i motyw wykrywane automatycznie, bez instalowania bibliotek.'))
            hero.addWidget(self.theme_label)
            layout.addLayout(hero)

            # Clickable metric cards filter table by state.
            cards = QtWidgets.QHBoxLayout()
            cards.setSpacing(10)
            self.metric_values = {}
            self.metric_buttons = {}
            self.metric_captions = {}
            metric_labels = [('CANDIDATE',tr('Kandydaci')),('REVIEW',tr('Do sprawdzenia')),
                             ('UNKNOWN',tr('Nieznane')),('ACTIVE',tr('Aktywne')),('PROTECTED',tr('Chronione'))]
            for state, label in metric_labels:
                frame = QtWidgets.QPushButton()
                frame.setObjectName('metricCard')
                frame.setStyleSheet('''
                    QPushButton#metricCard {border: 1px solid palette(mid); border-radius: 10px; background: palette(base); text-align: left;}
                    QPushButton#metricCard:hover {border: 1px solid palette(highlight); background: palette(alternate-base);}
                    QPushButton#metricCard:focus {border: 2px solid palette(highlight);}
                    ''')
                box = QtWidgets.QVBoxLayout(frame)
                box.setContentsMargins(14,10,14,10)
                box.setSpacing(3)
                count=QtWidgets.QLabel('0')
                countfont=count.font();countfont.setPointSize(countfont.pointSize()+10);countfont.setBold(True)
                count.setFont(countfont)
                caption=QtWidgets.QLabel(label)
                box.addWidget(count)
                box.addWidget(caption)
                self.metric_values[state]=count
                self.metric_buttons[state]=frame
                self.metric_captions[state]=caption
                frame.setToolTip(tf('Pokaż tylko pozycje: {state}',state=state))
                frame.clicked.connect(lambda _checked=False, st=state:self.filter_metric(st))
                for widget in (count,caption): widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
                cards.addWidget(frame,1)
            layout.addLayout(cards)

            scopes = [tr('Wszystko'),tr('Konfiguracja'),tr('Dane'),tr('Stan'),'Cache',tr('Flatpak'),tr('Snap'),tr('Dotfiles'),tr('Kwarantanna')]
            self.scope_tabs = QtWidgets.QTabBar()
            self.scope_tabs.setExpanding(False)
            self.scope_tabs.setDrawBase(False)
            self.scope_values = ['all','config','data','state','cache','flatpak','snap','dotfiles']
            for title in scopes: self.scope_tabs.addTab(title)
            self.scope_tabs.setCurrentIndex(self.scope_values.index(args.scope))
            self.scope_tabs.currentChanged.connect(self.scope_tab_changed)
            layout.addWidget(self.scope_tabs)

            # Scope is a filter of one scan, not a fresh filesystem traversal.
            self.scope_combo = QtWidgets.QComboBox()
            for title,value in [(tr('Wszystko'),'all'),('~/.config','config'),
                         ('~/.local/share','data'),('~/.local/state','state'),('~/.cache','cache'),
                         (tr('Flatpak'),'flatpak'),(tr('Snap'),'snap'),(tr('Dotfiles'),'dotfiles')]:
                self.scope_combo.addItem(title,value)
            self.scope_combo.setCurrentIndex(self.scope_combo.findData(args.scope))
            self.scope_combo.hide()

            toolbar = QtWidgets.QHBoxLayout()
            title = QtWidgets.QLabel(tr('Wyniki audytu'))
            title_font=title.font();title_font.setBold(True);title_font.setPointSize(title_font.pointSize()+2);title.setFont(title_font)
            self.audit_heading=title
            toolbar.addWidget(title)
            self.visible_count=QtWidgets.QLabel(entries_count(0,_language))
            toolbar.addWidget(self.visible_count)
            toolbar.addStretch(1)
            settings_button=QtWidgets.QPushButton(tr('⚙ Ustawienia'))
            self.settings_button=settings_button
            settings_button.clicked.connect(self.open_settings)
            toolbar.addWidget(settings_button)
            self.refresh_button=QtWidgets.QPushButton('↻  '+tr('Skanuj ponownie'))
            self.refresh_button.clicked.connect(self.scan_async)
            toolbar.addWidget(self.refresh_button)
            self.cancel_button=QtWidgets.QPushButton('Anuluj skan')
            self.cancel_button.setVisible(False)
            self.cancel_button.clicked.connect(self.cancel_scan)
            toolbar.addWidget(self.cancel_button)
            layout.addLayout(toolbar)
            self.scan_progress=QtWidgets.QProgressBar()
            self.scan_progress.setRange(0,0)
            self.scan_progress.setTextVisible(True)
            self.scan_progress.setFormat(tr('Skanowanie…'))
            self.scan_progress.hide()
            layout.addWidget(self.scan_progress)

            controls=QtWidgets.QHBoxLayout()
            self.search_box=QtWidgets.QLineEdit()
            self.search_box.setPlaceholderText(tr('Szukaj nazwy, lokalizacji lub uzasadnienia…'))
            self.search_box.setClearButtonEnabled(True)
            self.search_box.textChanged.connect(self.refresh_table)
            controls.addWidget(self.search_box,1)
            self.status_heading=QtWidgets.QLabel(tr('Status'))
            controls.addWidget(self.status_heading)
            self.status_filter=QtWidgets.QComboBox()
            self.status_filter.addItems(['ALL','CANDIDATE','REVIEW','UNKNOWN','ACTIVE','PROTECTED'])
            self.status_filter.currentTextChanged.connect(lambda *_:(self.update_metric_borders(),self.refresh_table()))
            controls.addWidget(self.status_filter)
            self.show_all=QtWidgets.QCheckBox(tr('Aktywne / chronione'))
            self.show_all.setChecked(args.all)
            self.show_all.toggled.connect(self.refresh_table)
            controls.addWidget(self.show_all)
            self.quick=QtWidgets.QCheckBox(tr('Szybki skan'))
            self.quick.setChecked(args.quick)
            self.quick.toggled.connect(self.scan_async)
            controls.addWidget(self.quick)
            layout.addLayout(controls)

            self.content_stack=QtWidgets.QStackedWidget()
            results=QtWidgets.QWidget()
            results_layout=QtWidgets.QVBoxLayout(results)
            results_layout.setContentsMargins(0,0,0,0)
            splitter=QtWidgets.QSplitter(Qt.Orientation.Horizontal)
            self.table=QtWidgets.QTableView()
            self.audit_model=AuditModel(self)
            self.proxy_model=AuditProxy(self)
            self.proxy_model.setSourceModel(self.audit_model)
            self.table.setModel(self.proxy_model)
            self.table.setSortingEnabled(True)
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table.setAlternatingRowColors(True)
            self.table.setShowGrid(False)
            self.table.setWordWrap(False)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(33)
            header = self.table.horizontalHeader()
            header.setStretchLastSection(False)
            # Match the viewport width: name/location expand, other columns stay compact.
            for col in (0, 2, 3):
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeMode.Interactive)
            for col in (1, 4):
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeMode.Stretch)
            for col,size in enumerate((55,185,112,95,250)):self.table.setColumnWidth(col,size)
            self.table.selectionModel().currentRowChanged.connect(lambda *_: self.update_details())
            splitter.addWidget(self.table)

            inspection=QtWidgets.QWidget()
            self.inspection=inspection
            self.splitter=splitter
            inspector_layout=QtWidgets.QVBoxLayout(inspection)
            inspector_layout.setContentsMargins(14,6,4,6)
            inspector_layout.setSpacing(9)
            inspect_top=QtWidgets.QHBoxLayout()
            inspect_title=QtWidgets.QLabel(tr('Szczegóły wyboru'))
            inspect_font=inspect_title.font();inspect_font.setBold(True);inspect_font.setPointSize(inspect_font.pointSize()+2)
            inspect_title.setFont(inspect_font)
            self.inspector_heading=inspect_title
            inspect_top.addWidget(inspect_title,1)
            close_inspect=QtWidgets.QPushButton('✕')
            close_inspect.setToolTip(tr('Zamknij szczegóły'))
            close_inspect.setFixedWidth(36)
            close_inspect.clicked.connect(self.hide_inspector)
            inspect_top.addWidget(close_inspect)
            inspector_layout.addLayout(inspect_top)
            self.details=QtWidgets.QPlainTextEdit()
            self.details.setReadOnly(True)
            self.details.setPlaceholderText(tr('Wybierz pozycję z listy, aby sprawdzić przesłanki klasyfikacji.'))
            inspector_layout.addWidget(self.details,1)
            note=QtWidgets.QLabel(tr('CANDIDATE to sugestia, nie dowód.\nREVIEW i UNKNOWN wymagają dodatkowej zgody.'))
            note.setWordWrap(True)
            self.inspector_note=note
            inspector_layout.addWidget(note)
            self.open_location_button = QtWidgets.QPushButton(tr('Otwórz lokalizację'))
            self.open_location_button.setEnabled(False)
            self.open_location_button.clicked.connect(self.open_selected_location)
            inspector_layout.addWidget(self.open_location_button)
            self.previewed_item = None
            splitter.addWidget(inspection)
            splitter.setStretchFactor(0,4)
            splitter.setStretchFactor(1,1)
            splitter.setSizes([845,320])
            inspection.hide()  # Full-width table until an item is clicked or checked.
            results_layout.addWidget(splitter)
            self.content_stack.addWidget(results)

            qpage=QtWidgets.QWidget()
            qlayout=QtWidgets.QVBoxLayout(qpage)
            qlayout.setContentsMargins(0,0,0,0)
            qlayout.addWidget(QtWidgets.QLabel(tr('Historia przeniesień do kwarantanny')))
            self.qtree=QtWidgets.QTreeWidget()
            self.qtree.setHeaderLabels(['Identyfikator operacji','Status','W manifestie','Przeniesione'])
            self.qtree.setAlternatingRowColors(True)
            self.qtree.header().setStretchLastSection(True)
            qlayout.addWidget(self.qtree,1)
            qb=QtWidgets.QHBoxLayout()
            self.qpreview=QtWidgets.QPushButton(tr('Pokaż zawartość…'))
            self.qpreview.clicked.connect(self.quarantine_preview)
            qb.addWidget(self.qpreview)
            qb.addStretch(1)
            qrefresh=QtWidgets.QPushButton(tr('Odśwież historię'))
            qrefresh.clicked.connect(self.refresh_quarantine)
            qb.addWidget(qrefresh)
            qrestore=QtWidgets.QPushButton(tr('Przywróć wybraną…'))
            qrestore.clicked.connect(self.restore_dialog)
            qb.addWidget(qrestore)
            qpurge=QtWidgets.QPushButton(tr('Usuń trwale wybraną…'))
            qpurge.clicked.connect(self.purge_dialog)
            qb.addWidget(qpurge)
            qaccess=QtWidgets.QPushButton(tr('Sprawdź dostęp…'))
            qaccess.clicked.connect(lambda: self.access_diagnostics_dialog())
            qb.addWidget(qaccess)
            qadopt=QtWidgets.QPushButton(tr('Zatwierdź stan…'))
            qadopt.clicked.connect(lambda: self.adopt_inventory_dialog())
            qb.addWidget(qadopt)
            qhistory=QtWidgets.QPushButton(tr('Usuń historię…'))
            qhistory.clicked.connect(self.cleanup_history_dialog)
            qb.addWidget(qhistory)
            qexpired=QtWidgets.QPushButton(tr('Usuń wygasłe pliki…'))
            qexpired.clicked.connect(self.purge_expired_dialog)
            qb.addWidget(qexpired)
            qexpired_history=QtWidgets.QPushButton(tr('Wyczyść całą zakończoną historię…'))
            qexpired_history.clicked.connect(self.cleanup_all_history_dialog)
            qb.addWidget(qexpired_history)
            qretention=QtWidgets.QPushButton(tr('Ustaw retencję…'))
            qretention.clicked.connect(self.configure_retention_dialog)
            qb.addWidget(qretention)
            qlayout.addLayout(qb)
            qhelp=QtWidgets.QLabel(tr('Usuwanie wygasłych kasuje pliki według retencji. Czyszczenie historii usuwa tylko dzienniki pustych operacji.'))
            qhelp.setWordWrap(True)
            qlayout.addWidget(qhelp)
            self.content_stack.addWidget(qpage)
            layout.addWidget(self.content_stack,1)

            actions=QtWidgets.QHBoxLayout()
            self.select_candidates_button=QtWidgets.QPushButton(tr('Zaznacz kandydatów'))
            self.select_candidates_button.clicked.connect(self.select_candidates)
            actions.addWidget(self.select_candidates_button)
            self.clear_button=QtWidgets.QPushButton(tr('Odznacz'))
            self.clear_button.clicked.connect(self.clear_selection)
            actions.addWidget(self.clear_button)
            self.allow_uncertain_box=QtWidgets.QCheckBox(tr('Zezwól na REVIEW / UNKNOWN'))
            self.allow_uncertain_box.toggled.connect(self.refresh_table)
            actions.addWidget(self.allow_uncertain_box)
            actions.addStretch(1)
            self.summary=QtWidgets.QLabel(selected_count(0,_language))
            actions.addWidget(self.summary)
            self.export_button=QtWidgets.QPushButton(tr('Eksport JSON…'))
            self.export_button.clicked.connect(self.export_json)
            actions.addWidget(self.export_button)
            comparison=QtWidgets.QPushButton('Porównaj raport…' if _language=='pl' else 'Compare report…')
            self.compare_button=comparison
            comparison.clicked.connect(self.compare_report_gui)
            actions.addWidget(comparison)
            self.move_button=QtWidgets.QPushButton(tr('Przenieś do kwarantanny…'))
            self.move_button.clicked.connect(self.move_selected)
            self.move_button.setEnabled(False)
            self.move_button.setToolTip(tr('Wymaga zaznaczenia i wpisania MOVE; dane pozostają do przywrócenia.'))
            actions.addWidget(self.move_button)
            layout.addLayout(actions)
            self.statusBar().showMessage(tr('Audyt tylko do odczytu · MOVE i PURGE wymagają potwierdzenia'))

        def update_metric_borders(self):
            for state,button in self.metric_buttons.items():
                active=(state==self.status_filter.currentText())
                button.setStyleSheet('''
                    QPushButton#metricCard {
                        border: %s solid palette(%s);
                        border-radius: 10px;
                        background: palette(base);
                        text-align: left;
                    }
                    QPushButton#metricCard:hover {
                        border: 1px solid palette(highlight);
                        background: palette(alternate-base);
                    }
                    QPushButton#metricCard:focus {border: 2px solid palette(highlight);}
                    ''' % ('2px' if active else '1px',
                             'highlight' if active else 'mid'))

        def filter_metric(self,state):
            if state in {'ACTIVE','PROTECTED'}:
                self.show_all.setChecked(True)
            self.status_filter.setCurrentText(state)

        def scope_tab_changed(self,index):
            self.hide_inspector()
            if index >= len(self.scope_values):
                self.content_stack.setCurrentIndex(1)
                self.refresh_quarantine()
                self.move_button.setVisible(False)
                self.select_candidates_button.setVisible(False)
                self.clear_button.setVisible(False)
                self.allow_uncertain_box.setVisible(False)
                return
            self.content_stack.setCurrentIndex(0)
            self.move_button.setVisible(True)
            self.select_candidates_button.setVisible(True)
            self.clear_button.setVisible(True)
            self.allow_uncertain_box.setVisible(True)
            self.scope_combo.blockSignals(True)
            self.scope_combo.setCurrentIndex(self.scope_combo.findData(self.scope_values[index]))
            self.scope_combo.blockSignals(False)
            self.refresh_table()

        def refresh_quarantine(self):
            self.qtree.clear()
            for entry in engine.quarantine_runs(home,engine.xdg_roots(home)):
                record=QtWidgets.QTreeWidgetItem([entry['run_id'],entry['status'],
                                                str(len(entry['items'])),str(entry['moved'])])
                record.setData(0,Role,entry['run_id'])
                self.qtree.addTopLevelItem(record)

        def quarantine_preview(self):
            entry=self.qtree.currentItem()
            if entry is None:return
            run_id=entry.data(0,Role)
            run=next((r for r in engine.quarantine_runs(home,engine.xdg_roots(home)) if r['run_id']==run_id),None)
            if run:
                messages.information(self,tr('Zawartość kwarantanny'),
                    '\n'.join(x.get('source','?') for x in run['items'][:45]) or tr('(brak danych)'))

        def configure_retention_dialog(self):
            from xdg_retention import load, save
            try:
                current=load(home,engine.xdg_roots(home))
                days,ok=inputs.getInt(self,tr('Retencja'),
                    tr('Dni przechowywania:'),current['days'],1,3650,1)
                if ok:
                    current['days']=days
                    save(home,engine.xdg_roots(home),current)
                    self.statusBar().showMessage(
                        tf('Ustawiono retencję: {days} dni',days=days))
            except (ValueError,OSError) as exc:
                messages.warning(self,tr('Retencja'),
                    tf('Nie można zapisać retencji: {error}',error=exc))

        @Slot(object, object)
        def _quarantine_finished(self, ok, outcome):
            """Qt delivers worker results to this QObject on the GUI thread."""
            callback=self._quarantine_callback
            self._quarantine_callback=None
            self._quarantine_job_busy=False
            if callback is not None:
                try:
                    callback(ok, outcome)
                except Exception as exc:
                    self.statusBar().showMessage(
                        tf('Błąd operacji kwarantanny: {error}',error=exc))

        def _quarantine_job(self, operation, callback, activity):
            if self._quarantine_job_busy:
                self.statusBar().showMessage(tr('Operacja kwarantanny jest już wykonywana.'))
                return
            self._quarantine_job_busy=True
            self._quarantine_callback=callback
            self.statusBar().showMessage(tr(activity))
            run_gui_job(operation, lambda *_: None,
                        lambda _done, ok, outcome:self._quarantine_signals.finished.emit(ok,outcome))

        def cleanup_history_dialog(self):
            selected=self.qtree.currentItem()
            if selected is not None:
                self._cleanup_history_runs([selected.data(0,Role)])

        def cleanup_all_history_dialog(self):
            def completed(ok, outcome):
                if not ok:
                    messages.critical(self,tr('Historia'),str(outcome))
                elif outcome:
                    self._cleanup_history_runs(outcome)
                else:
                    messages.information(self,tr('Historia'),
                        tr('Brak zakończonych operacji do wyczyszczenia. Aktywne i niedokończone pozostają chronione.'))
            self._quarantine_job(
                lambda:engine.completed_quarantine_history(home,engine.xdg_roots(home)),
                completed,'Sprawdzanie historii…')

        def cleanup_expired_history_dialog(self):
            def completed(ok, outcome):
                if not ok:
                    messages.critical(self,tr('Historia'),str(outcome))
                elif outcome:
                    self._cleanup_history_runs(outcome)
                else:
                    messages.information(self,tr('Historia'),
                        tr('Brak wygasłych manifestów.'))
            self._quarantine_job(
                lambda:engine.expired_quarantine_history(home,engine.xdg_roots(home)),
                completed,'Sprawdzanie historii…')

        def _cleanup_history_runs(self,run_ids):
            run_ids=tuple(run_ids)
            def completed(ok, outcome):
                if not ok:
                    messages.critical(self,tr('Historia'),str(outcome))
                    return
                summary='\\n'.join(x['run_id']+' ('+x['status']+')' for x in outcome)
                if messages.question(self,tr('Usuń historię'),
                        summary+'\\n\\n'+tr('Zostaną usunięte tylko zakończone dzienniki.'),
                        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
                answer,ok=inputs.getText(self,tr('Potwierdzenie'),
                                                         tr('Wpisz HISTORY:'))
                if not ok or answer != 'HISTORY':
                    return
                def delete():
                    for plan in outcome:
                        engine.cleanup_quarantine_history(
                            home,engine.xdg_roots(home),plan['run_id'],dry_run=False)
                    return len(outcome)
                def after_delete(success, result):
                    self.refresh_quarantine()
                    if success:
                        self.statusBar().showMessage(tr('Usunięto zakończone manifesty.'))
                    else:
                        messages.critical(self,tr('Historia'),str(result))
                self._quarantine_job(delete,after_delete,'Usuwanie historii…')
            self._quarantine_job(
                lambda:[engine.cleanup_quarantine_history(
                    home,engine.xdg_roots(home),rid) for rid in run_ids],
                completed,'Sprawdzanie historii…')

        def adopt_inventory_dialog(self, run_id=None, resume_purge=False):
            if run_id is None:
                entry=self.qtree.currentItem()
                if entry is None:return
                run_id=entry.data(0,Role)
            def ready(ok, result):
                if not ok:
                    messages.warning(self,tr('Zatwierdź aktualny stan'),quarantine_error_details(result,_language))
                    return
                self._adopt_inventory_confirm(run_id, resume_purge, result.get('approval_token'))
            self._quarantine_job(
                lambda:engine.preview_quarantine_adoption(home,engine.xdg_roots(home),run_id),
                ready,'Weryfikacja kwarantanny')

        def _adopt_inventory_confirm(self, run_id, resume_purge=False, approval_token=None):
            if run_id is None:
                entry=self.qtree.currentItem()
                if entry is None:return
                run_id=entry.data(0,Role)
            explanation=(tf('Operacja: {run_id}',run_id=run_id)+'\n'+
                tr('Zatwierdzisz stan plików widoczny TERAZ. Nie oznacza to, że zawartość jest identyczna jak w dniu przeniesienia. PURGE nadal wymaga osobnej zgody.'))
            if messages.question(self,tr('Zatwierdź aktualny stan'),explanation,
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:return
            token,ok=inputs.getText(self,tr('Zatwierdź aktualny stan'),tr('Wpisz ADOPT:'))
            if not ok or token!='ADOPT':return
            def done(success,outcome):
                if not success:
                    messages.warning(self,tr('Zatwierdź aktualny stan'),quarantine_error_details(outcome,_language))
                else:
                    self.refresh_quarantine()
                    if resume_purge:
                        self._purge_runs([run_id])
                    else:
                        messages.information(self,tr('Zatwierdź aktualny stan'),
                            tf('Zatwierdzono aktualny stan: {count} obiektów.',count=outcome['adopted'])+
                            '\n'+tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'))
            self._quarantine_job(
                lambda:engine.adopt_quarantine_inventory(
                    home,engine.xdg_roots(home),run_id,approval_token=approval_token),
                done,'Weryfikacja kwarantanny')

        def access_diagnostics_dialog(self, run_id=None, resume_purge=False, repaired=False):
            if run_id is None:
                current=self.qtree.currentItem()
                if current is None:return
                run_id=current.data(0,Role)
            def finished(ok, report):
                if not ok:
                    messages.warning(
                        self,tr('Diagnostyka dostępu'),str(report))
                    return
                issues=report['issues']
                if not issues:
                    if resume_purge and (repaired or report['unsealed']):
                        if report['unsealed']:
                            self.adopt_inventory_dialog(run_id, resume_purge=True)
                        else:
                            self._purge_runs([run_id])
                        return
                    note=tr('Nie znaleziono problemów z odczytem. Sprawdź pozostałe komunikaty PURGE.')
                    if report['unsealed']:
                        note+='\n'+tr('Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).')
                    messages.information(self,tr('Diagnostyka dostępu'),note)
                    return
                issue=issues[0]
                if issue['code']=='ENTRY_IDENTITY_CHANGED':
                    plan=report.get('device_revalidation') or {}
                    if plan.get('eligible'):
                        title=tr('Ponowna weryfikacja urządzenia')
                        if messages.question(self,title,device_revalidation_details(plan,_language),
                            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                            QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:return
                        token,accepted=inputs.getText(self,title,tr('Wpisz REVALIDATE:'))
                        if not accepted or token!='REVALIDATE':return
                        def done(success,outcome):
                            if not success:
                                messages.critical(self,title,quarantine_error_details(outcome,_language))
                                return
                            self.refresh_quarantine()
                            if resume_purge:
                                self._purge_runs([run_id])
                            else:
                                messages.information(self,title,tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'))
                        self._quarantine_job(
                            lambda:engine.revalidate_quarantine_device(home,engine.xdg_roots(home),
                                run_id,plan['approval_token']),done,'Weryfikacja kwarantanny')
                        return
                    messages.critical(self,tr('Zablokowano PURGE'),identity_issue_details(issue,run_id,_language))
                    return
                message=(tf('Użytkownik: {user}',user=report['identity']['user'])+
                         '\n'+tf('pkexec zainstalowany: {state}',
                                   state=tr('tak') if report['identity']['pkexec_installed'] else tr('nie'))+
                         '\n'+tf('Problem: {code}',code=issue['code'])+
                         '\n'+issue['path']+
                         '\n'+tf('Uprawnienia: {mode}',mode=issue['mode']))
                if not issue['repairable']:
                    messages.warning(
                        self,tr('Diagnostyka dostępu'),message+'\n'+
                        tr('Nie można automatycznie naprawić. Nie podnoszę uprawnień ani nie omijam kontroli PURGE.')+
                        '\n'+tr('Naprawa tego obiektu wymaga dodatkowej analizy. Zasady Polkit określa system; xdg-audit nie uruchamia kodu użytkownika jako root.'))
                    return
                message+='\n'+tf('Proponowana zmiana: {before} → {after}',
                                 before=issue['mode'],after=issue['suggested_mode'])
                message+='\n'+tr('Zmienię tylko wskazane uprawnienia właściciela w kwarantannie. Bez sudo i bez usuwania plików.')
                if messages.question(self,tr('Napraw dostęp'),message,
                        QtWidgets.QMessageBox.StandardButton.Yes |
                        QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
                token,accepted=inputs.getText(
                    self,tr('Napraw dostęp'),tr('Wpisz ACCESS:'))
                if not accepted or token!='ACCESS':return
                def after_repair(success,outcome):
                    if not success:
                        messages.warning(
                            self,tr('Napraw dostęp'),str(outcome))
                        return
                    result=(tf('Zmieniono uprawnienia: {before} → {after}',
                               before=outcome['old_mode'],after=outcome['new_mode'])+
                            '\n'+tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'))
                    if report['unsealed']:
                        result+='\n'+tr('Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).')
                    if resume_purge:
                        self.access_diagnostics_dialog(run_id, resume_purge=True, repaired=True)
                    else:
                        messages.information(self,tr('Napraw dostęp'),result)
                self._quarantine_job(
                    lambda:engine.repair_quarantine_access(
                        home,engine.xdg_roots(home),run_id,issue['relative']),
                    after_repair,'Naprawianie dostępu…')
            self._quarantine_job(
                lambda:engine.diagnose_quarantine_access(
                    home,engine.xdg_roots(home),run_id),
                finished,'Sprawdzanie dostępu…')

        def purge_dialog(self):
            entry=self.qtree.currentItem()
            if entry is None:
                return
            if entry.text(1) in ("PURGED","RESTORED","COMPLETED","EMPTY"):
                messages.information(self,tr('Historia'),
                    tr('Ta operacja jest zakończona. Użyj opcji Usuń historię.'))
                return
            self._purge_runs([entry.data(0,Role)])

        def purge_expired_dialog(self):
            def completed(ok, outcome):
                if not ok:
                    messages.warning(self,tr('Kwarantanna'),str(outcome))
                elif outcome:
                    self._purge_runs(outcome)
                else:
                    messages.information(self,tr('Kwarantanna'),
                        tr('Nie znaleziono wygasłych kwarantann.'))
            self._quarantine_job(
                lambda:engine.expired_quarantine_runs(home,engine.xdg_roots(home)),
                completed,'Sprawdzanie kwarantanny…')

        def _purge_runs(self,run_ids):
            run_ids=tuple(run_ids)
            def completed(ok, outcome):
                if not ok:
                    messages.critical(self,tr('Zablokowano PURGE'),quarantine_error_details(outcome,_language))
                    if len(run_ids)==1 and engine.quarantine_access_recoverable_error(outcome):
                        self.access_diagnostics_dialog(run_ids[0], resume_purge=True)
                    return
                description='\\n'.join(
                    str(plan['run_id'])+': '+str(plan['objects'])+' entries / '+str(plan['bytes'])+' B'
                    for plan in outcome)
                if messages.question(self,tr('Trwałe usuwanie'),
                        description+'\\n\\n'+tr('Tej operacji nie da się cofnąć. Kontynuować?'),
                        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
                answer, ok=inputs.getText(self,tr('Potwierdzenie PURGE'),tr('Wpisz PURGE:'))
                if not ok or answer != 'PURGE':
                    return
                def delete():
                    removed=0
                    for plan in outcome:
                        result=engine.purge_quarantine_run(
                            home,engine.xdg_roots(home),plan['run_id'],dry_run=False)
                        removed+=result['objects']
                    return removed
                def after_delete(success, result):
                    self.refresh_quarantine()
                    if success:
                        messages.information(self,tr('Kwarantanna'),
                            tr('Usunięto obiektów: ')+str(result))
                    else:
                        messages.critical(self,tr('Zablokowano PURGE'),quarantine_error_details(result,_language))
                self._quarantine_job(delete,after_delete,'Trwałe usuwanie z kwarantanny…')
            self._quarantine_job(
                lambda:[engine.purge_quarantine_run(
                    home,engine.xdg_roots(home),run_id) for run_id in run_ids],
                completed,'Sprawdzanie kwarantanny…')

        def compare_report_gui(self):
            if not self.scan_complete:return
            from xdg_history import summary
            path, _filter = QtWidgets.QFileDialog.getOpenFileName(self,
                tr('Wybierz wcześniejszy raport'),
                str(home), 'JSON (*.json)')
            if not path:return
            try:
                differences = engine.compare_report(self.items, Path(path), list(engine.SCOPES))
                content=summary(differences, _language)
            except (OSError, SystemExit, ValueError) as exc:
                messages.warning(self, tr('Błąd porównania'), str(exc));return
            dialog=QtWidgets.QDialog(self);dialog.setWindowTitle(tr('Porównanie raportów'))
            box=QtWidgets.QVBoxLayout(dialog)
            view=QtWidgets.QPlainTextEdit(content);view.setReadOnly(True)
            box.addWidget(view)
            close=QtWidgets.QPushButton('Close' if _language=='en' else 'Zamknij')
            close.clicked.connect(dialog.accept);box.addWidget(close)
            fit_qt_dialog(dialog, QtWidgets, QtCore, tr)
            dialog.exec()

        def export_json(self):
            from xdg_history import suggested_export_path
            file_name, _ = QtWidgets.QFileDialog.getSaveFileName(self, tr('Eksport raportu'),
                              str(suggested_export_path(home)), 'JSON (*.json)')
            if not file_name:
                return
            try:
                with open(file_name, 'x', encoding='utf-8') as file:
                    json.dump({'version': engine.VERSION, 'scopes': list(engine.SCOPES),
                               'stats': self.stats, 'entries': [it.json() for it in self.items]},
                              file, indent=2, ensure_ascii=False)
                self.statusBar().showMessage(tf('Zapisano: {path}',path=file_name))
            except OSError as exc:
                messages.warning(self, tr('Błąd zapisu'),
                     f'{exc}\n'+tr('Istniejące pliki nie są nadpisywane.'))

        def restore_dialog(self):
            runs = [r for r in engine.quarantine_runs(home, engine.xdg_roots(home))
                    if r['status'] not in ('PURGED','RESTORED','COMPLETED','EMPTY')]
            if not runs:
                messages.information(self, tr('Kwarantanna'), tr('Nie znaleziono operacji.'))
                return
            chosen_row = self.qtree.currentItem() if self.content_stack.currentIndex() == 1 else None
            if chosen_row and chosen_row.text(1) in ('PURGED','RESTORED','COMPLETED','EMPTY'):
                messages.information(self,tr('Historia'),
                    tr('Ta operacja jest zakończona. Użyj opcji Usuń historię.'))
                return
            labels = [x['run_id']+'  ('+tf('{count} przeniesionych / {total} zapisanych',count=x['moved'],total=len(x['items']))+')' for x in runs]
            if chosen_row:
                label=next((key for key,run in zip(labels,runs) if run['run_id']==chosen_row.data(0,Role)),labels[0])
                ok=True
            else:
                label,ok=inputs.getItem(self,tr('Kwarantanna'),
                    tr('Wybierz operację do przywrócenia:'),labels,0,False)
            if not ok:
                return
            selected = runs[labels.index(label)]
            details = '\n'.join(f"{x.get('move_status', '?')}: {x.get('source', '?')}" for x in selected['items'][:22])
            if messages.question(self, tr('Plan przywracania'),
                     tf('Operacja {run_id}',run_id=selected['run_id'])+'\n\n'+details+'\n\n'+tr('Istniejące pliki NIE zostaną nadpisane. Kontynuować?'),
                     QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                     QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            answer, confirmed = inputs.getText(self, tr('Potwierdzenie'), tr('Wpisz RESTORE:'))
            if not confirmed or answer != 'RESTORE':
                return
            output = []
            try:
                result = engine.restore_quarantine_run(home, engine.xdg_roots(home),
                           selected['run_id'], emit=output.append)
                messages.information(self, tr('Przywracanie'),
                   tf('Przywrócono: {count}',count=result['restored'])+'\n'+tf('Pominięto: {count}',count=result['skipped']))
                self.scan_async()
            except (ValueError, OSError, KeyError) as exc:
                messages.critical(self, tr('Błąd przywracania'), str(exc))

        def open_settings(self):
            from xdg_prefs import (defaults, load, save, validate, parse_alias_lines,
                                   format_aliases, SCOPES)
            current, warning = load(home, engine.xdg_roots(home))
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle(tr('Ustawienia xdg-audit'))
            layout = QtWidgets.QVBoxLayout(dialog)
            layout.addWidget(QtWidgets.QLabel(tr('Zakres początkowy')))
            scope = QtWidgets.QComboBox()
            for name in SCOPES: scope.addItem(name)
            scope.setCurrentText(current['startup_scope'])
            layout.addWidget(scope)
            layout.addWidget(QtWidgets.QLabel(tr('Język / Language')))
            language = QtWidgets.QComboBox()
            language.addItem('Polski', 'pl')
            language.addItem('English', 'en')
            language.setCurrentIndex(max(0, language.findData(current['language'])))
            layout.addWidget(language)
            quick = QtWidgets.QCheckBox(tr('Szybki skan (bez rozmiarów)'))
            quick.setChecked(current['quick_scan'])
            layout.addWidget(quick)
            shown = QtWidgets.QCheckBox(tr('Pokazuj aktywne i chronione'))
            shown.setChecked(current['show_active'])
            layout.addWidget(shown)
            def frame_editor(editor):
                editor.setStyleSheet('QPlainTextEdit { border: 1px solid palette(mid); '
                    'border-radius: 7px; padding: 8px; background: palette(base); color: palette(text); } '
                    'QPlainTextEdit:focus { border: 1px solid palette(highlight); }')
            layout.addWidget(QtWidgets.QLabel(tr('Zachowaj — jedna nazwa katalogu w linii')))
            keep = QtWidgets.QPlainTextEdit('\n'.join(current['keep']))
            frame_editor(keep)
            keep.setMaximumHeight(110)
            layout.addWidget(keep)
            layout.addWidget(QtWidgets.QLabel(tr('Alias — katalog=wzorzec')))
            alias = QtWidgets.QPlainTextEdit(format_aliases(current['aliases']))
            frame_editor(alias)
            alias.setMaximumHeight(125)
            layout.addWidget(alias)
            source_views = {}
            for key, title in (('appimage_dirs', 'Dodatkowe katalogi AppImage — jedna ścieżka w linii'),
                               ('binary_dirs', 'Dodatkowe katalogi binarek — jedna ścieżka w linii')):
                layout.addWidget(QtWidgets.QLabel(tr(title)))
                editor = QtWidgets.QPlainTextEdit('\n'.join(current.get(key, [])))
                frame_editor(editor)
                editor.setMaximumHeight(80)
                layout.addWidget(editor)
                source_views[key] = editor
            hint = QtWidgets.QLabel(tr('Ścieżki bezwzględne lub ~/; odczyt bez uruchamiania plików.'))
            hint.setWordWrap(True)
            layout.addWidget(hint)
            info = QtWidgets.QLabel(warning or tr('Zapis jest wykonywany dopiero po kliknięciu Zapisz.'))
            info.setWordWrap(True)
            layout.addWidget(info)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save |
                                                 QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            def commit():
                try:
                    new = validate({**{key:[line.strip() for line in view.toPlainText().splitlines() if line.strip()]
                                       for key,view in source_views.items()}, 'startup_scope':scope.currentText(),
                                    'quick_scan':quick.isChecked(), 'show_active':shown.isChecked(),
                                    'language':language.currentData(),
                                    'keep':[x.strip() for x in keep.toPlainText().splitlines() if x.strip()],
                                    'aliases':parse_alias_lines(alias.toPlainText())})
                    save(home, new, engine.xdg_roots(home))
                except (OSError, ValueError) as exc:
                    info.setText(tf('Błąd: {error}',error=exc)); return
                from xdg_prefs import scan_inputs_changed
                needs_scan=scan_inputs_changed(current,new)
                self.prefs = new
                args.keep=list(new['keep'])
                aliases.clear();aliases.update(new['aliases'])
                args.quick=new['quick_scan']
                args.all=new['show_active']
                self.show_all.setChecked(args.all)
                self.quick.setChecked(args.quick)
                # Saved startup scope takes effect on the next launch.
                dialog.accept()
                if current['language'] != new['language']:
                    self.apply_language(new['language'])
                if needs_scan:
                    self.scan_async()
                else:
                    self.statusBar().showMessage(tr('Ustawienia zapisane. Wyniki audytu zachowane.'))
            buttons.accepted.connect(commit)
            fit_qt_dialog(dialog, QtWidgets, QtCore, tr)
            dialog.exec()

        def apply_language(self, language: str):
            """Re-translate controls and model headers without restarting Qt."""
            nonlocal _language
            old=_language
            if old==language:return
            _language=language
            self.prefs['language']=language
            self.setWindowTitle('xdg-audit · Audit' if language=='en' else 'xdg-audit · Audyt konfiguracji')
            # Update fixed UI labels, not file paths or model data.
            for cls in (QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QCheckBox):
                for widget in self.findChildren(cls):
                    original_text=widget.text()
                    translated=translate_ui_text(original_text,old,language)
                    if translated!=original_text:widget.setText(translated)
            self.subtitle.setText(tr('Audyt i bezpieczne porządki w katalogach użytkownika'))
            for state,title in (('CANDIDATE','Kandydaci'),('REVIEW','Do sprawdzenia'),
                                ('UNKNOWN','Nieznane'),('ACTIVE','Aktywne'),('PROTECTED','Chronione')):
                self.metric_captions[state].setText(tr(title))
            self.refresh_button.setText(('◌ ' + tr('Skanowanie…')) if self.thread and self.thread.isRunning()
                                        else '↻  '+tr('Skanuj ponownie'))
            self.cancel_button.setText('Cancel scan' if language=='en' else 'Anuluj skan')
            self.settings_button.setText(tr('⚙ Ustawienia'))
            self.audit_heading.setText(tr('Wyniki audytu'))
            self.theme_label.setToolTip(tr('Środowisko i motyw wykrywane automatycznie, bez instalowania bibliotek.'))
            self.move_button.setToolTip(tr('Wymaga zaznaczenia i wpisania MOVE; dane pozostają do przywrócenia.'))
            for state, button in self.metric_buttons.items():
                button.setToolTip(tf('Pokaż tylko pozycje: {state}',state=state))
            self.status_heading.setText(tr('Status'))
            self.search_box.setPlaceholderText(tr('Szukaj nazwy, lokalizacji lub uzasadnienia…'))
            self.scan_progress.setFormat(tr('Skanowanie…'))
            for index,(_,scope) in enumerate([('Wszystko','all'),('Konfiguracja','config'),
                    ('Dane','data'),('Stan','state'),('Cache','cache'),('Flatpak','flatpak'),
                    ('Snap','snap'),('Dotfiles','dotfiles'),('Kwarantanna','quarantine')]):
                title=('Wszystko','Konfiguracja','Dane','Stan','Cache','Flatpak','Snap','Dotfiles','Kwarantanna')[index]
                self.scope_tabs.setTabText(index,tr(title))
            self.scope_combo.setItemText(0,tr('Wszystko'))
            self.scope_combo.setItemText(5,tr('Flatpak'))
            self.scope_combo.setItemText(6,tr('Snap'))
            self.scope_combo.setItemText(7,tr('Dotfiles'))
            self.audit_model.headerDataChanged.emit(Qt.Orientation.Horizontal,0,4)
            self.visible_count.setText(entries_count(self.audit_model.rowCount(),_language))
            self.update_selection_status(reveal=False)
            # Theme/palette is unchanged by language; avoid repainting widgets.
            # Dynamic messages in QStatusBar aren't QLabel children; translate
            # them explicitly when changing language without restarting.
            if self.thread is not None and self.thread.isRunning():
                self.statusBar().showMessage('Scanning…' if language=='en' else 'Skanowanie…')
            elif self.scan_complete:
                self.statusBar().showMessage((f'Scanned {len(self.items)} entries. No changes.' if language=='en'
                                              else f'Zbadano {len(self.items)} pozycji. Żadnych zmian.'))

        def scan_async(self, *_):
            if self.thread is not None and self.thread.isRunning():
                return
            scopes = list(engine.SCOPES)
            self.refresh_button.setEnabled(False)
            self.refresh_button.setText('◌ '+tr('Skanowanie…'))
            self.scan_progress.show()
            self.scan_progress.setRange(0,0)
            self.cancel_button.setVisible(True)
            self.scan_complete=False
            self.items = []
            self.checked.clear()
            self.refresh_table()
            self.scope_tabs.setEnabled(False)
            self.scope_combo.setEnabled(False)
            self.move_button.setEnabled(False)
            self.statusBar().showMessage('Scanning (read-only)…' if _language=='en' else 'Trwa skanowanie (tylko odczyt)…')
            self.thread = QtCore.QThread(self)
            self.worker = Scanner(scopes, self.quick.isChecked())
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.scan_done)
            self.worker.phase.connect(self.scan_phase)
            self.worker.batch.connect(self.scan_batch)
            self.worker.failed.connect(self.scan_error)
            self.worker.cancelled.connect(self.scan_cancelled)
            self.worker.finished.connect(self.thread.quit)
            self.worker.failed.connect(self.thread.quit)
            self.worker.cancelled.connect(self.thread.quit)
            self.thread.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.thread.finished.connect(self.clear_worker)
            self.thread.start()

        def clear_worker(self):
            self.thread = None
            self.worker = None
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText('↻ '+tr('Skanuj ponownie'))
            self.scan_progress.hide()
            self.cancel_button.setVisible(False)
            self.scope_tabs.setEnabled(True)
            self.scope_combo.setEnabled(True)
            self.update_selection_status()

        def cancel_scan(self):
            if self.worker is not None:
                self.worker.cancel_event.set()
                self.statusBar().showMessage(tr('Anulowanie skanu po bieżącym etapie…'))

        def scan_cancelled(self):
            self.scan_complete=False
            self.checked.clear()
            self.move_button.setEnabled(False)
            self.statusBar().showMessage(tr('Skan anulowany. Częściowe wyniki nie służą do przenoszenia plików.'))

        def scan_phase(self, name):
            self.scan_progress.setFormat(tf('Skanowanie: {stage}',stage=tr(name)))
            self.statusBar().showMessage(('Scanning: ' if _language=='en' else 'Skanowanie: ') + tr(name))

        def scan_batch(self, kind, batch, done, total):
            if kind == 'classified':
                self.items = list(batch)
                self.refresh_table()
            elif kind == 'sizes':
                self.scan_progress.setRange(0, max(total, 1))
                self.scan_progress.setValue(done)
                self.refresh_table()

        def is_eligible(self, it):
            return self.scan_complete and not it.protected and (it.state == 'CANDIDATE' or
                (self.allow_uncertain_box.isChecked() and it.state in {'REVIEW', 'UNKNOWN'}))

        def focused_item(self):
            index = self.table.currentIndex()
            if not index.isValid():
                return None
            source = self.proxy_model.mapToSource(index)
            return self.audit_model.rows[source.row()] if source.isValid() else None

        def _update_optional_tabs(self):
            visible = visible_optional_scopes(self.items, self.stats)
            current = self.scope_tabs.currentIndex()
            if current < len(self.scope_values) and self.scope_values[current] in {'flatpak', 'snap'} - visible:
                self.scope_tabs.setCurrentIndex(0)
            for scope in ('flatpak', 'snap'):
                self.scope_tabs.setTabVisible(self.scope_values.index(scope), scope in visible)

        def scan_done(self, items, roots, stats):
            self.scan_complete=True
            self.items, self.roots, self.stats = items, roots, stats
            self._update_optional_tabs()
            self.hide_inspector()
            self.refresh_table()
            self.refresh_quarantine()
            self.statusBar().showMessage((f'Scanned {len(items)} entries. No files changed.' if _language=='en' else f'Zbadano {len(items)} pozycji. Żadnych zmian w plikach.'))

        def scan_error(self, message):
            self.scan_complete=False
            self.statusBar().showMessage(tr('Błąd skanowania'))
            messages.critical(self, tr('Błąd skanowania'), message)

        def display_items(self):
            query = self.search_box.text().strip().casefold()
            result = []
            scope=self.scope_combo.currentData()
            for item in self.items:
                if scope != 'all' and item.scope != scope: continue
                if self.status_filter.currentText() != 'ALL' and item.state != self.status_filter.currentText():
                    continue
                if not self.show_all.isChecked() and item.state in {"ACTIVE", "PROTECTED"}:
                    continue
                hay = " ".join([str(item.path), item.scope, item.state, *item.reasons]).casefold()
                if query and query not in hay:
                    continue
                result.append(item)
            return result

        def refresh_table(self, *_):
            self.audit_model.set_rows(self.display_items())
            counts = {state: sum(it.state == state for it in self.items) for state in
                      ('CANDIDATE', 'REVIEW', 'UNKNOWN', 'ACTIVE', 'PROTECTED')}
            for name, value in counts.items():
                self.metric_values[name].setText(str(value))
            self.update_metric_borders()
            self.visible_count.setText(entries_count(self.audit_model.rowCount(),_language))
            self.update_selection_status()

        def chosen_paths(self):
            return set(self.checked)

        def select_candidates(self):
            if not self.scan_complete:return
            self.checked.update(str(it.path) for it in self.display_items() if it.state == 'CANDIDATE')
            self.audit_model.set_rows(self.audit_model.rows)
            self.update_selection_status(reveal=True)

        def clear_selection(self):
            self.checked.clear()
            self.audit_model.set_rows(self.audit_model.rows)
            self.update_selection_status()
            self.hide_inspector()

        def update_selection_status(self, *_, reveal=False):
            self.select_candidates_button.setEnabled(bool(self.items))
            self.summary.setText(selected_count(len(self.checked),_language))
            if self.thread is None or not self.thread.isRunning():
                self.move_button.setEnabled(bool(self.checked))
            if reveal:
                self.update_details()

        def hide_inspector(self):
            self.inspection.hide()

        def open_selected_location(self):
            if self.previewed_item is None:
                return
            try:
                open_item_location(self.previewed_item.path, home)
            except (OSError, ValueError, RuntimeError) as exc:
                self.statusBar().showMessage(str(exc))

        def update_details(self):
            focused = self.focused_item()
            chosen = [it for it in self.items if str(it.path) in self.checked]
            content = details_text(chosen, engine.human, focused, language=_language)
            self.previewed_item = focused if focused is not None else (chosen[0] if len(chosen) == 1 else None)
            self.open_location_button.setEnabled(self.previewed_item is not None)
            if not content:
                self.hide_inspector()
                return
            self.details.setPlainText(content)
            self.inspection.show()
            self.splitter.setSizes([max(480, self.splitter.width()-330),330])

        def open_quarantine(self):
            root = engine.quarantine_dir(home, engine.xdg_roots(home))
            if not root.is_dir():
                messages.information(self, tr('Kwarantanna'), tr('Brak operacji kwarantanny.'))
                return
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(root)))

        def move_selected(self):
            if self.thread is not None:
                return
            selected = self.chosen_paths()
            selected_items = [it for it in self.items if str(it.path) in selected]
            chosen = [it for it in selected_items if (it.state == "CANDIDATE" or
                      (self.allow_uncertain_box.isChecked() and it.state in {"REVIEW", "UNKNOWN"})) and not it.protected]
            if not chosen:
                messages.information(self, tr('Brak wyboru'), tr('Nie zaznaczono pozycji dostępnych do kwarantanny.'))
                return
            uncertain = [it for it in chosen if it.state in {"REVIEW", "UNKNOWN"}]
            details = "\n".join(f"{it.state:10} {engine.human(it.bytes):>9}  {it.path}" for it in chosen[:30])
            if len(chosen) > 30:
                details += '\n'+tf('... i {count} kolejnych',count=len(chosen)-30)
            total = engine.human(sum(it.bytes for it in chosen))
            message = tf('Przenieść {count} ({size}) do kwarantanny?',count=entries_count(len(chosen),_language),size=total)+'\n'+tr('Żadne pliki nie zostaną trwale usunięte.')+'\n\n'+details
            if messages.question(self, tr('Plan kwarantanny'), message,
                   QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                   QtWidgets.QMessageBox.StandardButton.No) != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            if uncertain:
                answer, ok = inputs.getText(self, tr('Niepewne pozycje'),
                    tf('Wybierasz {count} REVIEW/UNKNOWN.',count=len(uncertain))+'\n'+
                    tr('Nie ustalono, czy są niepotrzebne. Wpisz UNCERTAIN:'))
                if not ok or answer != "UNCERTAIN":
                    return
            answer, ok = inputs.getText(self, tr('Ostateczne potwierdzenie'),
                      tr('Zamknij powiązane aplikacje. Aby zatwierdzić przeniesienie wpisz MOVE:'))
            if not ok or answer != "MOVE":
                return
            output = []
            progress = QtWidgets.QProgressDialog(
                tr('Trwa przenoszenie do kwarantanny…'), '', 0, 0, self)
            progress.setWindowTitle(tr('Kwarantanna'))
            progress.setCancelButton(None)
            progress.setMinimumDuration(0)
            progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            self._move_progress = progress

            def operation():
                return engine.commit_quarantine(chosen, self.roots, home,
                    allow_uncertain=bool(uncertain), emit=output.append,
                    extra_aliases=aliases, keep_names=args.keep)

            def completed(ok, outcome):
                progress.close()
                self._move_progress = None
                if ok:
                    message = tf('Run ID: {run_id}',run_id=outcome['run_id'])+'\\n'+tf(
                        'Przeniesiono {moved}/{total}.',moved=len(outcome['moved']),total=len(chosen))
                    if any('purge inventory unavailable' in line for line in output):
                        messages.warning(self,tr('Kwarantanna'),message+'\\n\\n'+
                            tr('Pliki przeniesiono, ale nie można było sprawdzić całej zawartości. Przed PURGE użyj „Sprawdź dostęp…”, następnie osobno „Zatwierdź stan…” (ADOPT).'))
                    else:
                        messages.information(self,tr('Kwarantanna'),message)
                else:
                    messages.critical(self,tr('Błąd'),tf('Nie udało się przeprowadzić operacji:\\n{error}',error=outcome))
                self.scan_async()

            self._quarantine_job(operation, completed, 'Trwa przenoszenie do kwarantanny…')
            if self._quarantine_job_busy:
                progress.show()
            else:
                progress.close()
                self._move_progress = None

        def apply_system_theme(self, force=False):
            appearance = detect_appearance(home)
            if appearance == self.scheme_info and not force:
                return
            self.scheme_info = appearance
            app = QtWidgets.QApplication.instance()
            # Always inherit native Qt platform palette first; honor KDE/qt6ct plugins.
            palette = QtGui.QPalette(self.original_palette)
            roles = {
                "window": QtGui.QPalette.ColorRole.Window,
                "window_text": QtGui.QPalette.ColorRole.WindowText,
                "base": QtGui.QPalette.ColorRole.Base,
                "text": QtGui.QPalette.ColorRole.Text,
                "button": QtGui.QPalette.ColorRole.Button,
                "button_text": QtGui.QPalette.ColorRole.ButtonText,
                "highlight": QtGui.QPalette.ColorRole.Highlight,
                "highlight_text": QtGui.QPalette.ColorRole.HighlightedText,
                "tooltip_base": QtGui.QPalette.ColorRole.ToolTipBase,
                "tooltip_text": QtGui.QPalette.ColorRole.ToolTipText,
            }
            # KDE stores actual RGB palette. In other environments, preserve
            # Qt's platform theme; portal only supplies light/dark/accent.
            if appearance.desktop == "KDE Plasma" and appearance.kde_colors:
                for name, color in appearance.kde_colors.items():
                    if name in roles:
                        palette.setColor(roles[name], QtGui.QColor(*color))
            elif appearance.scheme in {"light", "dark"} and "qt6ct" not in os.environ.get("QT_QPA_PLATFORMTHEME", "").lower():
                dark = appearance.scheme == "dark"
                native_dark = palette.color(QtGui.QPalette.ColorRole.Window).lightnessF() < 0.5
                if native_dark != dark:
                    # Qt platform integration is missing/mismatched (common on bare
                    # Wayland compositors). Generate contrast from the inherited Qt
                    # hues; do not embed a fixed RGB desktop color theme.
                    def adjust(role, target_lightness):
                        color = palette.color(role).toHsl()
                        h = color.hslHueF()
                        saturation = color.hslSaturationF()
                        return QtGui.QColor.fromHslF(0 if h < 0 else h,
                            max(0.02, saturation), target_lightness)
                    values = (
                        ("window", 0.17 if dark else 0.94),
                        ("base", 0.12 if dark else 0.99),
                        ("button", 0.23 if dark else 0.88),
                        ("window_text", 0.92 if dark else 0.10),
                        ("text", 0.92 if dark else 0.10),
                        ("button_text", 0.92 if dark else 0.10),
                        ("tooltip_base", 0.23 if dark else 0.96),
                        ("tooltip_text", 0.92 if dark else 0.10),
                    )
                    for name, luminance in values:
                        palette.setColor(roles[name], adjust(roles[name], luminance))
            if appearance.accent:
                palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(*appearance.accent))
                r, g, b = appearance.accent
                luminosity = 0.2126*r + 0.7152*g + 0.0722*b
                palette.setColor(QtGui.QPalette.ColorRole.HighlightedText,
                                 QtGui.QColor(0, 0, 0) if luminosity > 148 else QtGui.QColor(255, 255, 255))
            app.setPalette(palette)
            self.theme_label.setText((f"Desktop: {appearance.desktop} · Session: {runtime['session']}\nGUI: Qt6 · Style: {appearance.source or 'unknown'}"
                  if _language=='en' else
                  f"Środowisko: {appearance.desktop} · Sesja: {runtime['session']}\nGUI: Qt6 · Styl: {appearance.source or 'nieznany'}"))

        def closeEvent(self, event):
            if self.thread is not None and self.thread.isRunning():
                messages.information(self, tr('Skanowanie'), tr('Skanowanie jeszcze trwa. Zamknij okno po zakończeniu.'))
                event.ignore()
                return
            event.accept()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["xdg-audit"])
    app.setApplicationName("xdg-audit")
    window = MainWindow()
    window.show()
    return int(app.exec())
