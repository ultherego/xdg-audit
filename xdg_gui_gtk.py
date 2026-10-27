"""Native GTK 4 / GTK 3 GUI using PyGObject IF already available.

GTK controls inherit real GTK theme and portal/desktop appearance. Local CSS uses only colors provided by the active GTK theme; no hardcoded palette. No modules are needed to run the CLI.
"""
from __future__ import annotations
from xdg_i18n import translate, translate_ui_text, entries_count, selected_count, format_message

import json
import threading
from pathlib import Path
from typing import Any

from xdg_inspector import details_text, click_is_inside_control, open_item_location
from xdg_theme import detect_appearance
from xdg_gui_jobs import run_gui_job
from xdg_gui_layout import visible_optional_scopes
from xdg_gui_dialogs import configure_gtk_dialog
from xdg_quarantine_messages import quarantine_error_details, identity_issue_details

def align_header_edges(header: Any, left: Any, right: Any, gtk: Any) -> None:
    """Anchor desktop/session information at the far right in GTK3 and GTK4.

    Gtk.Box.append() in GTK4 has no `expand` argument, unlike GTK3's
    pack_start().  The left-side expansion must therefore be explicit.
    """
    header.set_hexpand(True)
    left.set_hexpand(True)
    right.set_halign(gtk.Align.END)
    right.set_valign(gtk.Align.CENTER)


SCOPES = [('Wszystko','all'),('Konfiguracja','config'),('Dane','data'),
          ('Stan','state'),('Cache','cache'),('Flatpak','flatpak'),('Snap','snap'),('Dotfiles','dotfiles')]


def launch_gui(engine: Any, home: Path, args: Any, aliases: dict, runtime: dict, backend: str) -> int:

    _language = getattr(args, 'saved_prefs', {}).get('language', 'pl')
    def tr(value):
        return translate(value, _language)

    def tf(template, **values):
        return format_message(template, _language, **values)
    import gi
    gtk_version = '4.0' if backend == 'gtk4' else '3.0'
    gi.require_version('Gtk',gtk_version)
    gi.require_version("Pango", "1.0")
    from gi.repository import Gtk, GLib, Pango, Gdk, Gio
    GTK4 = backend == 'gtk4'

    # Presentation-only CSS. `currentColor` is resolved by GTK from the
    # user's theme, not from a hardcoded Catppuccin/Adwaita palette.
    # Status cards use the theme's selection/accent colour where available.
    CARD_CSS = b"""
    button.xdg-metric {
        border: 1px solid alpha(currentColor, 0.35);
        border-radius: 10px;
        background-color: alpha(currentColor, 0.035);
        padding: 0;
        transition: border-color 120ms ease-in-out, background-color 120ms ease-in-out;
    }
    button.xdg-metric:hover {
        border-color: alpha(currentColor, 0.65);
        background-color: alpha(currentColor, 0.075);
    }
    button.xdg-metric.xdg-active {
        border: 2px solid @theme_selected_bg_color;
        background-color: alpha(@theme_selected_bg_color, 0.12);
    }
    button.xdg-metric:focus-visible { outline: 2px solid currentColor; outline-offset: 1px; }
    .xdg-table-header {
        font-weight: 700;
    }
    .xdg-loading-card {
        border: 1px solid alpha(currentColor, 0.24);
        border-radius: 12px;
        background-color: alpha(currentColor, 0.03);
        padding: 26px 30px 28px;
    }
    .xdg-table-header label { font-weight: 700; font-size: 1.08em; }
    .xdg-table-rows row { border-bottom: 1px solid alpha(currentColor, 0.13); }
    .xdg-table-rows row:hover { background-color: alpha(currentColor, 0.045); }
    .xdg-table-rows row.xdg-focused { background-color: alpha(@theme_selected_bg_color, 0.14); }
    .xdg-table-rows row.xdg-heading-row {
        background-color: alpha(currentColor, 0.07);
        border-bottom: 1px solid alpha(currentColor, 0.26);
    }
    .xdg-table-rows row.xdg-heading-row:hover { background-color: alpha(currentColor, 0.07); }
    .xdg-settings-editor {
        border: 1px solid alpha(currentColor, 0.5);
        border-radius: 7px;
    }
    .xdg-settings-editor.xdg-editor-focused {
        border-color: @theme_selected_bg_color;
        box-shadow: inset 0 0 0 1px @theme_selected_bg_color;
    }
    """

    def install_styles():
        provider = Gtk.CssProvider()
        provider.load_from_data(CARD_CSS)
        if GTK4:
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(display, provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        else:
            screen = Gdk.Screen.get_default()
            if screen is not None:
                Gtk.StyleContext.add_provider_for_screen(screen, provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        return provider

    # GTK opens its display during Gtk.Application.run(), so install the CSS
    # provider from activate() rather than before the display exists.
    css_provider = None

    # Shared column geometry for headers and data cells.  Each row and
    # header is a Gtk.Grid with IDENTICAL slot widths, eliminating the old
    # loosely-aligned 'table made of labels' layout.
    COLUMN_WIDTHS = (42, 272, 132, 110, -1)
    def make_cells(contents, *, heading=False):
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_margin_start(10);grid.set_margin_end(10)
        grid.set_margin_top(12 if heading else 7)
        grid.set_margin_bottom(12 if heading else 7)
        grid.set_hexpand(True)
        if heading:
            grid.add_css_class('xdg-table-header') if GTK4 else grid.get_style_context().add_class('xdg-table-header')
        for n, child in enumerate(contents):
            width = COLUMN_WIDTHS[n]
            child.set_halign(Gtk.Align.START)
            if width > 0:
                child.set_size_request(width, -1)
            else:
                child.set_hexpand(True)
            grid.attach(child,n,0,1,1)
        return grid

    def append(box, child, expand=False):
        if isinstance(box, Gtk.ListBox):
            if GTK4: box.append(child)
            else: box.add(child)
        elif GTK4:
            box.append(child)
        else:
            box.pack_start(child,expand,expand,2)

    def set_child(parent, child):
        if GTK4: parent.set_child(child)
        else: parent.add(child)

    def clear(box):
        if GTK4:
            while box.get_first_child(): box.remove(box.get_first_child())
        else:
            for w in box.get_children(): box.remove(w)

    def wrap_label(widget):
        if GTK4:
            widget.set_wrap(True)
            widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        else:
            widget.set_line_wrap(True)
            widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)

    def label(text, xalign=0):
        obj=Gtk.Label(label=text,xalign=xalign)
        obj.set_selectable(False)
        return obj

    class Window:
        def __init__(self,app):
            self.app=app
            self.win=Gtk.ApplicationWindow(application=app)
            self.win._xdg_controller = self
            self.win.set_title('xdg-audit · Audit' if _language=='en' else 'xdg-audit · Audyt konfiguracji')
            self.win.set_default_size(1320,820)
            self.prefs = dict(getattr(args, 'saved_prefs', {}))
            self.prefs.setdefault('keep', [])
            self.prefs.setdefault('aliases', {})
            self.prefs.setdefault('startup_scope', 'all')
            self.prefs.setdefault('quick_scan', False)
            self.prefs.setdefault('show_active', False)
            self._set_app_icon()
            self.items=[]
            self._size_in_progress=False
            self.scan_complete=False
            self.roots=engine.xdg_roots(home)
            self.stats={}
            self.checked=set()
            self.row_data={}
            self.focused_row=None
            self.busy=False
            self._quarantine_job_busy=False
            self.allow_uncertain=False
            self.scope='all'
            outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            outer.set_margin_top(18);outer.set_margin_bottom(18)
            outer.set_margin_start(20);outer.set_margin_end(20)
            set_child(self.win,outer)

            # Desktop-native header; styling is inherited from GTK theme.
            header=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=14)
            append(outer,header)
            icon_file=Path(__file__).with_name('assets') / 'xdg-audit-128.png'
            if icon_file.exists():
                try:
                    # Gtk.Picture.set_size_request() only sets a *minimum*.
                    # Downscale the pixels themselves to avoid the 128px
                    # image expanding the header on GTK4/Wayland.
                    from gi.repository import GdkPixbuf
                    # GTK4 Gtk.Image applies *icon* sizing from the theme;
                    # it can render a tiny glyph inside a much larger requested
                    # widget. Gtk.Picture renders the actual pixbuf at 68px.
                    scaled=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_file),68,68,True)
                    if GTK4:
                        brand_icon=Gtk.Picture.new_for_pixbuf(scaled)
                        brand_icon.set_can_shrink(False)
                        brand_icon.set_alternative_text('xdg-audit')
                    else:
                        brand_icon=Gtk.Image.new_from_pixbuf(scaled)
                    brand_icon.set_size_request(68,68)
                    brand_icon.set_halign(Gtk.Align.START)
                    brand_icon.set_valign(Gtk.Align.CENTER)
                    append(header,brand_icon)
                except (OSError,AttributeError,TypeError):
                    pass
            head_left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            append(header,head_left,True)
            headline=label('xdg-audit')
            headline.set_markup('<span weight="bold" size="xx-large">xdg-audit</span>')
            append(head_left,headline)
            self.subtitle=label(tr('Audyt i bezpieczne porządki w katalogach użytkownika'))
            append(head_left,self.subtitle)
            environment=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
            self.appearance=detect_appearance(home)
            first=label((f"Desktop: {runtime['desktop']}  |  Session: {runtime['session']}" if _language=='en' else f"Środowisko: {runtime['desktop']}  |  Sesja: {runtime['session']}"),1)
            self.environment_first=first
            second=label((f"GUI: GTK {gtk_version}  |  Style: {self.appearance.source or 'unknown'}" if _language=='en' else f"GUI: GTK {gtk_version}  |  Styl: {self.appearance.source or 'nieznany'}"),1)
            self.environment_second=second
            for elem in (first,second):
                elem.set_xalign(1)
                append(environment,elem)
            append(header,environment)
            align_header_edges(header, head_left, environment, Gtk)

            self.metric_counts={}
            self.metric_buttons={}
            self.metric_captions={}
            overview=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10)
            append(outer,overview)
            for state,caption in [('CANDIDATE',tr('Kandydaci')),('REVIEW',tr('Do sprawdzenia')),
                                  ('UNKNOWN',tr('Nieznane')),('ACTIVE',tr('Aktywne')),('PROTECTED',tr('Chronione'))]:
                button=Gtk.Button()
                if GTK4:button.add_css_class('xdg-metric')
                else:button.get_style_context().add_class('xdg-metric')
                self.metric_buttons[state]=button
                content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
                content.set_margin_top(9);content.set_margin_bottom(9)
                content.set_margin_start(14);content.set_margin_end(14)
                counter=label('0')
                counter.set_markup('<span weight="bold" size="x-large">0</span>')
                self.metric_counts[state]=counter
                append(content,counter)
                caption_widget=label(caption)
                self.metric_captions[state]=caption_widget
                append(content,caption_widget)
                set_child(button,content)
                button.connect('clicked',lambda _,st=state:self.filter_status(st))
                button.set_hexpand(True)
                append(overview,button,True)

            section_header=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10)
            append(outer,section_header)
            heading=label(tr('Wyniki audytu'))
            heading.set_markup('<span weight="bold" size="large">'+GLib.markup_escape_text(tr('Wyniki audytu'))+'</span>')
            self.heading=heading
            append(section_header,heading)
            self.visible_count=label(entries_count(0,_language))
            append(section_header,self.visible_count)
            spacer=Gtk.Box();spacer.set_hexpand(True)
            append(section_header,spacer,True)
            self.settings_button=Gtk.Button(label=tr('⚙ Ustawienia'))
            self.settings_button.connect('clicked',self.open_settings)
            append(section_header,self.settings_button)
            self.rescan=Gtk.Button()
            self.rescan_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            self.rescan_spinner = Gtk.Spinner()
            self.rescan_spinner.set_visible(False)
            append(self.rescan_content, self.rescan_spinner)
            self.rescan_label = label(tr('Skanuj ponownie'))
            append(self.rescan_content, self.rescan_label)
            set_child(self.rescan, self.rescan_content)
            self.rescan.connect('clicked',lambda *_:self.start_scan())
            append(section_header,self.rescan)
            self.cancel_button = Gtk.Button(label='Anuluj skan')
            self.cancel_button.connect('clicked', lambda *_: self.cancel_scan.set())
            self.cancel_button.set_visible(False)
            append(section_header,self.cancel_button)

            searchrow=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10)
            append(outer,searchrow)
            self.search=Gtk.SearchEntry()
            self.search.set_placeholder_text(tr('Szukaj nazwy, ścieżki lub przesłanek…'))
            self.search.connect('search-changed',lambda *_:self.refresh())
            append(searchrow,self.search,True)
            self.state_filter=Gtk.ComboBoxText()
            for state in ('ALL','CANDIDATE','REVIEW','UNKNOWN','ACTIVE','PROTECTED'):
                self.state_filter.append_text(state)
            self.state_filter.set_active(0)
            self.state_filter.connect('changed',lambda *_:(self.update_metric_highlight(),self.refresh()))
            append(searchrow,self.state_filter)
            self.show_all=Gtk.CheckButton(label=tr('Aktywne / chronione'))
            self.show_all.set_active(args.all)
            self.show_all.connect('toggled',lambda *_:self.refresh())
            append(searchrow,self.show_all)

            self.stack=Gtk.Stack()
            self.stack.set_hexpand(True);self.stack.set_vexpand(True)
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
            switcher=Gtk.StackSwitcher(stack=self.stack)
            self.scope_switcher = switcher
            append(outer,switcher)

            self.results_or_loading = Gtk.Stack()
            self.results_or_loading.set_hexpand(True); self.results_or_loading.set_vexpand(True)
            self.results_or_loading.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
            loading_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            loading_outer.set_hexpand(True); loading_outer.set_vexpand(True)
            loading_outer.set_halign(Gtk.Align.CENTER); loading_outer.set_valign(Gtk.Align.CENTER)
            self.loading_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            # The card background/border belongs to this Box, so use CSS padding
            # INSIDE its border. Gtk.Widget margins are outside it and caused
            # the loading spinner/progress to crowd or protrude at high DPI.
            self.loading_card.set_size_request(400, -1)
            if GTK4: self.loading_card.add_css_class('xdg-loading-card')
            else: self.loading_card.get_style_context().add_class('xdg-loading-card')
            self.loading_spinner = Gtk.Spinner()
            self.loading_spinner.set_halign(Gtk.Align.CENTER)
            self.loading_spinner.set_size_request(24, 24)
            self.loading_spinner.set_margin_bottom(4)
            append(self.loading_card, self.loading_spinner)
            loading_title = label(tr('Skanowanie…'), 0.5)
            self.loading_title = loading_title
            loading_title.set_markup('<span weight="bold" size="large">'+GLib.markup_escape_text(tr('Skanowanie…'))+'</span>')
            append(self.loading_card, loading_title)
            loading_note = label(tr('Trwa zbieranie i analizowanie wpisów. Tabela pojawi się po zakończeniu skanowania.'), 0.5)
            self.loading_note = loading_note
            wrap_label(loading_note)
            loading_note.set_justify(Gtk.Justification.CENTER)
            loading_note.set_max_width_chars(42)
            append(self.loading_card, loading_note)
            self.loading_progress = Gtk.ProgressBar()
            self.loading_progress.set_show_text(False)
            self.loading_progress.set_margin_top(6)
            append(self.loading_card, self.loading_progress)
            append(loading_outer, self.loading_card)
            self.results_or_loading.add_titled(loading_outer, 'loading', 'Skanowanie')
            self.results_or_loading.add_titled(self.stack, 'results', 'Wyniki')
            self.lists={}
            self.gtk_models = {}
            self.gtk_selections = {}
            self.gtk_columns = {}
            for raw_title,scope in SCOPES:
                title = tr(raw_title)
                page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0)
                # The header is the first non-interactive ListBoxRow, not a
                # separate widget above the scroll view. This guarantees the
                # same viewport, background and column geometry as data rows.
                scrolling=Gtk.ScrolledWindow()
                scrolling.set_vexpand(True)
                if GTK4:
                    rows = self._new_column_view(scope)
                else:
                    rows=Gtk.ListBox()
                    rows.get_style_context().add_class('xdg-table-rows')
                    if hasattr(rows,'set_show_separators'): rows.set_show_separators(True)
                    rows.set_selection_mode(Gtk.SelectionMode.SINGLE)
                    rows.connect('row-selected',self._row_selected)
                set_child(scrolling,rows)
                append(page,scrolling,True)
                self.stack.add_titled(page,scope,title)
                self.lists[scope]=rows
            self.qscroll=Gtk.ScrolledWindow();self.qscroll.set_vexpand(True)
            self.qlist=Gtk.ListBox();self.qlist.set_selection_mode(Gtk.SelectionMode.NONE)
            set_child(self.qscroll,self.qlist)
            self.stack.add_titled(self.qscroll,'quarantine',tr('Kwarantanna'))
            self.stack.connect('notify::visible-child-name',self._change_scope)

            content_pane=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
            content_pane.set_hexpand(True);content_pane.set_vexpand(True)
            if GTK4:content_pane.set_start_child(self.results_or_loading)
            else:content_pane.pack1(self.results_or_loading,True,False)
            inspector=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
            inspector.set_size_request(310,-1)
            inspector.set_margin_start(13)
            self.inspector=inspector
            self.content_pane=content_pane
            inspect_header=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8)
            inspection=label(tr('Szczegóły wyboru'))
            inspection.set_markup('<span weight="bold" size="large">'+GLib.markup_escape_text(tr('Szczegóły wyboru'))+'</span>')
            self.inspector_heading=inspection
            append(inspect_header,inspection,True)
            close=Gtk.Button(label='✕')
            close.set_tooltip_text(tr('Zamknij szczegóły'))
            close.connect('clicked',lambda *_:self.hide_inspector())
            append(inspect_header,close)
            append(inspector,inspect_header)
            detailed_scroll=Gtk.ScrolledWindow()
            detailed_scroll.set_hexpand(True);detailed_scroll.set_vexpand(True)
            self.details=label('')
            self.details.set_selectable(True);wrap_label(self.details)
            self.details.set_valign(Gtk.Align.START)
            self.details.set_max_width_chars(38)
            self.details.set_margin_top(10);self.details.set_margin_bottom(10)
            self.details.set_margin_start(8);self.details.set_margin_end(8)
            set_child(detailed_scroll,self.details)
            append(inspector,detailed_scroll,True)
            note=label(tr('CANDIDATE to sugestia, nie dowód. REVIEW i UNKNOWN wymagają dodatkowej zgody.'))
            wrap_label(note);note.set_max_width_chars(38)
            self.inspector_note=note
            append(inspector,note)
            self.open_location_button = Gtk.Button(label=tr('Otwórz lokalizację'))
            self.open_location_button.set_sensitive(False)
            self.open_location_button.connect('clicked', self.open_selected_location)
            append(inspector,self.open_location_button)
            self.previewed_item = None
            if GTK4:content_pane.set_end_child(inspector)
            else:content_pane.pack2(inspector,False,False)
            if hasattr(content_pane,'set_position'):content_pane.set_position(910)
            append(outer,content_pane,True)
            inspector.set_visible(False)
            self.stack.set_visible_child_name(args.scope)

            footer=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10)
            append(outer,footer)
            self.all_button=Gtk.Button(label=tr('Zaznacz kandydatów'))
            self.all_button.connect('clicked',self.select_candidates)
            append(footer,self.all_button)
            clear_button=Gtk.Button(label=tr('Odznacz'))
            clear_button.connect('clicked',self.clear_selection)
            self.clear_button=clear_button
            append(footer,clear_button)
            self.uncertain=Gtk.CheckButton(label=tr('Zezwól na REVIEW / UNKNOWN'))
            self.uncertain.connect('toggled',self._toggle_uncertain)
            append(footer,self.uncertain)
            footer_spacer=Gtk.Box();footer_spacer.set_hexpand(True)
            append(footer,footer_spacer,True)
            self.selected_count=label(selected_count(0,_language))
            append(footer,self.selected_count)
            self.export_button=Gtk.Button(label=tr('Eksport JSON…'))
            self.export_button.connect('clicked',self.export)
            append(footer,self.export_button)
            compare_button=Gtk.Button(label='Porównaj raport…' if _language=='pl' else 'Compare report…')
            compare_button.connect('clicked',self.compare_report_gui)
            self.compare_button=compare_button
            append(footer,compare_button)
            self.move_button=Gtk.Button(label=tr('Przenieś do kwarantanny…'))
            self.move_button.connect('clicked',self.move)
            if GTK4:self.move_button.add_css_class('suggested-action')
            else:self.move_button.get_style_context().add_class('suggested-action')
            self.move_button.set_sensitive(False)
            append(footer,self.move_button)
            self.summary=label('')
            self.status=label(tr('Audyt nie zmienia danych. Kwarantanna wymaga MOVE; można ją przywrócić.'))
            self.status.set_ellipsize(Pango.EllipsizeMode.END)
            self.status.set_hexpand(True)
            append(outer,self.status)
            self.start_scan()
            self.win.present() if GTK4 else self.win.show_all()
            self.hide_inspector()  # Gtk3 show_all() would otherwise reveal it.

        def _set_loading_visible(self, visible: bool):
            if visible:
                self.results_or_loading.set_visible_child_name('loading')
                self.loading_spinner.start()
                self.rescan_spinner.set_visible(True)
                self.rescan_spinner.start()
                self.cancel_button.set_visible(True)
                self.rescan_label.set_text(tr('Skanowanie…'))
                if getattr(self, '_loading_timer', None):
                    return
                def pulse():
                    if not self.busy:
                        self.loading_progress.set_fraction(0.0)
                        self._loading_timer = None
                        return False
                    self.loading_progress.pulse()
                    return True
                self._loading_timer = GLib.timeout_add(120, pulse)
            else:
                self.results_or_loading.set_visible_child_name('results')
                self.loading_spinner.stop()
                self.rescan_spinner.stop()
                self.cancel_button.set_visible(False)
                self.rescan_spinner.set_visible(False)
                self.rescan_label.set_text(tr('Skanuj ponownie'))
                self.loading_progress.set_fraction(0.0)
                self._loading_timer = None

        def _set_app_icon(self):
            """Use bundled app icon, without changing/installing a desktop theme."""
            try:
                icon_name = 'io.github.xdgaudit'
                icons = Path(__file__).with_name('assets')
                display = self.win.get_display()
                if GTK4:
                    theme = Gtk.IconTheme.get_for_display(display)
                else:
                    theme = Gtk.IconTheme.get_default()
                theme.add_search_path(str(icons))
                self.win.set_icon_name(icon_name)
            except (OSError, AttributeError, TypeError):
                pass  # Window icons are not always displayed under Wayland.

        def open_settings(self, *_):
            """Explicit-save preferences; cancelling does not modify the disk."""
            from xdg_prefs import save as save_prefs, parse_alias_lines, format_aliases, SCOPES as scopes
            dialog=Gtk.Window(title=tr('Ustawienia xdg-audit'), transient_for=self.win, modal=True)
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            for side in ('top','bottom','start','end'):
                getattr(box, 'set_margin_'+side)(18)
            def section(text):
                title=label(text)
                title.set_markup('<b>'+GLib.markup_escape_text(text)+'</b>')
                append(box,title)
            section(tr('Zakres przy uruchomieniu'))
            start_scope=Gtk.ComboBoxText()
            for value in scopes:
                start_scope.append(value, value)
            start_scope.set_active_id(self.prefs['startup_scope'])
            append(box,start_scope)
            section(tr('Język / Language'))
            language_choice=Gtk.ComboBoxText()
            language_choice.append('pl', 'Polski')
            language_choice.append('en', 'English')
            language_choice.set_active_id(self.prefs.get('language','pl'))
            append(box,language_choice)
            quick=Gtk.CheckButton(label=tr('Szybki skan (bez liczenia rozmiarów katalogów)'))
            quick.set_active(self.prefs['quick_scan'])
            append(box,quick)
            show=Gtk.CheckButton(label=tr('Pokazuj aktywne i chronione pozycje'))
            show.set_active(self.prefs['show_active'])
            append(box,show)
            section(tr('Zachowaj — nazwy katalogów, jedna w linii'))
            def frame_editor(scroll, view):
                # Empty editors still need a visible boundary in flat themes.
                style=scroll.get_style_context()
                style.add_class('xdg-settings-editor')
                view.set_left_margin(10);view.set_right_margin(10)
                view.set_top_margin(8);view.set_bottom_margin(8)
                if GTK4:
                    focus=Gtk.EventControllerFocus()
                    focus.connect('enter',lambda *_:style.add_class('xdg-editor-focused'))
                    focus.connect('leave',lambda *_:style.remove_class('xdg-editor-focused'))
                    view.add_controller(focus)
                else:
                    view.connect('focus-in-event',lambda *_:(style.add_class('xdg-editor-focused'),False)[1])
                    view.connect('focus-out-event',lambda *_:(style.remove_class('xdg-editor-focused'),False)[1])
            keep_text=Gtk.TextView()
            keep_text.set_monospace(True)
            keep_text.get_buffer().set_text('\n'.join(self.prefs['keep']))
            keepsc=Gtk.ScrolledWindow();keepsc.set_min_content_height(95)
            frame_editor(keepsc,keep_text)
            set_child(keepsc,keep_text);append(box,keepsc)
            section(tr('Alias pakietu — katalog=wzorzec, jedna para w linii'))
            alias_text=Gtk.TextView();alias_text.set_monospace(True)
            alias_text.get_buffer().set_text(format_aliases(self.prefs['aliases']))
            asc=Gtk.ScrolledWindow();asc.set_min_content_height(100)
            frame_editor(asc,alias_text)
            set_child(asc,alias_text);append(box,asc)
            source_views={}
            for key, title in (('appimage_dirs', 'Dodatkowe katalogi AppImage — jedna ścieżka w linii'),
                               ('binary_dirs', 'Dodatkowe katalogi binarek — jedna ścieżka w linii')):
                section(tr(title))
                view=Gtk.TextView();view.set_monospace(True)
                view.get_buffer().set_text('\n'.join(self.prefs.get(key, [])))
                scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(65)
                frame_editor(scroll,view)
                set_child(scroll,view);append(box,scroll)
                source_views[key]=view
            hint=label(tr('Ścieżki bezwzględne lub ~/; odczyt bez uruchamiania plików.'))
            wrap_label(hint);append(box,hint)
            error=label(tr('Zapisane ustawienia dotyczą tylko Twojego konta.'))
            wrap_label(error);append(box,error)
            buttons=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8)
            append(box,buttons)
            cancel=Gtk.Button(label=tr('Anuluj'))
            cancel.connect('clicked',lambda *_:dialog.destroy())
            append(buttons,cancel)
            save=Gtk.Button(label=tr('Zapisz ustawienia'))
            if GTK4:save.add_css_class('suggested-action')
            append(buttons,save)
            def get_buffer_text(view):
                buffer=view.get_buffer()
                return buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)
            previous_prefs=dict(self.prefs)
            old_language=previous_prefs.get('language','pl')
            def on_save(*_):
                try:
                    from xdg_prefs import validate
                    keep=[x.strip() for x in get_buffer_text(keep_text).splitlines() if x.strip()]
                    new=validate({**{key:[line.strip() for line in get_buffer_text(view).splitlines() if line.strip()]
                                      for key,view in source_views.items()}, 'keep':keep,
                        'aliases':parse_alias_lines(get_buffer_text(alias_text)),
                        'quick_scan':quick.get_active(),
                        'show_active':show.get_active(),
                        'startup_scope':start_scope.get_active_id(),
                        'language':language_choice.get_active_id()})
                    save_prefs(home,new,engine.xdg_roots(home))
                except (OSError,ValueError) as exc:
                    error.set_text(tf('Błąd: {error}',error=exc));return
                from xdg_prefs import scan_inputs_changed
                needs_scan=scan_inputs_changed(previous_prefs,new)
                self.prefs=new
                args.keep=list(new['keep'])
                args.quick=new['quick_scan']
                aliases.clear();aliases.update(new['aliases'])
                args.all=new['show_active']
                if self.show_all.get_active() != args.all:
                    self.show_all.set_active(args.all)
                # startup_scope is for the *next* launch. Saving language must
                # not change the current tab or close its inspector.
                dialog.destroy()
                if new['language'] != old_language:
                    self.apply_language(new['language'])
                if needs_scan:
                    self.status.set_text('Settings saved. Rescanning…' if new['language']=='en'
                                         else 'Ustawienia zapisane. Uruchamiam ponowny audyt.')
                    self.start_scan()
                else:
                    # Language/UI-only settings must not re-run filesystem scan,
                    # change the selected entries, or rebuild the main table.
                    self.status.set_text('Settings saved. Scan results preserved.' if new['language']=='en'
                                         else 'Ustawienia zapisane. Wyniki audytu zachowane.')
            save.connect('clicked',on_save)
            configure_gtk_dialog(dialog,box,Gtk,Gdk,Pango)
            dialog.present() if GTK4 else dialog.show_all()

        def apply_language(self, language: str):
            """Apply UI language immediately, preserving scan results and selection."""
            nonlocal _language
            old=_language
            if old == language:
                return
            _language=language
            self.prefs['language']=language
            self.win.set_title('xdg-audit · Audit' if language=='en' else 'xdg-audit · Audyt konfiguracji')
            self.subtitle.set_text(tr('Audyt i bezpieczne porządki w katalogach użytkownika'))
            self.environment_first.set_text((f"Desktop: {runtime['desktop']}  |  Session: {runtime['session']}" if language=='en' else f"Środowisko: {runtime['desktop']}  |  Sesja: {runtime['session']}"))
            self.environment_second.set_text((f"GUI: GTK {gtk_version}  |  Style: {self.appearance.source or 'unknown'}" if language=='en' else f"GUI: GTK {gtk_version}  |  Styl: {self.appearance.source or 'nieznany'}"))
            for state, title in (('CANDIDATE','Kandydaci'),('REVIEW','Do sprawdzenia'),
                                 ('UNKNOWN','Nieznane'),('ACTIVE','Aktywne'),('PROTECTED','Chronione')):
                self.metric_captions[state].set_text(tr(title))
            self.heading.set_markup('<span weight="bold" size="large">'+
                                    GLib.markup_escape_text(tr('Wyniki audytu'))+'</span>')
            self.rescan_label.set_text(tr('Skanowanie…') if self.busy else tr('Skanuj ponownie'))
            self.cancel_button.set_label('Cancel scan' if language=='en' else 'Anuluj skan')
            self.settings_button.set_label(tr('⚙ Ustawienia'))
            self.search.set_placeholder_text(tr('Szukaj nazwy, ścieżki lub przesłanek…'))
            self.show_all.set_label(tr('Aktywne / chronione'))
            self.all_button.set_label(tr('Zaznacz kandydatów'))
            self.clear_button.set_label(tr('Odznacz'))
            self.uncertain.set_label(tr('Zezwól na REVIEW / UNKNOWN'))
            self.export_button.set_label(tr('Eksport JSON…'))
            self.compare_button.set_label(tr('Porównaj raport…'))
            self.move_button.set_label(tr('Przenieś do kwarantanny…'))
            if hasattr(self, 'open_location_button'):
                self.open_location_button.set_label(tr('Otwórz lokalizację'))
            self.inspector_heading.set_markup('<span weight="bold" size="large">'+
                         GLib.markup_escape_text(tr('Szczegóły wyboru'))+'</span>')
            self.inspector_note.set_text(tr('CANDIDATE to sugestia, nie dowód. REVIEW i UNKNOWN wymagają dodatkowej zgody.'))
            self.loading_title.set_markup('<span weight="bold" size="large">'+
                                          GLib.markup_escape_text(tr('Skanowanie…'))+'</span>')
            self.loading_note.set_text(tr('Trwa zbieranie i analizowanie wpisów. Tabela pojawi się po zakończeniu skanowania.'))
            for title, scope in SCOPES + [('Kwarantanna','quarantine')]:
                page=self.stack.get_child_by_name(scope)
                if page is not None:
                    if GTK4: self.stack.get_page(page).set_title(tr(title))
                    else: self.stack.child_set_property(page, 'title', tr(title))
            if GTK4:
                for view in self.gtk_columns.values():
                    for idx, title in enumerate(('✓','Nazwa','Status','Rozmiar','Lokalizacja')):
                        view.get_columns().get_item(idx).set_title(tr(title))
            else:
                # GTK3: update header labels in-place; never rebuild the table
                # or reset its scroll/selection simply to translate UI text.
                for rows in self.lists.values():
                    head=rows.get_row_at_index(0)
                    if head is None: continue
                    grid=head.get_child()
                    cells=grid.get_children() if grid is not None else []
                    for col,title in enumerate(('✓','Nazwa','Status','Rozmiar','Lokalizacja')):
                        if col < len(cells):
                            cells[col].set_markup('<span weight="bold" size="large">'+
                                    GLib.markup_escape_text(tr(title))+'</span>')
            self.visible_count.set_text(entries_count(sum(1 for _ in self._visible()),_language))
            self.selected_count.set_text(selected_count(len(self.checked),_language))
            # The status area is part of the main window too. Do not leave a
            # stale Polish scan message after switching to English (or back).
            if self.busy:
                self.status.set_text(tr('Trwa skanowanie… bez modyfikacji plików'))
            elif self.scan_complete:
                self.status.set_text((f'Scanned {len(self.items)} entries. No changes.'
                                     if language=='en' else f'Zbadano {len(self.items)} pozycji. Żadnych zmian.'))
            else:
                self.status.set_text(tr('Audyt nie zmienia danych. Kwarantanna wymaga MOVE; można ją przywrócić.'))
            if self.inspector.get_visible():
                self.show_inspector()

        def _new_column_view(self, scope):
            """GTK4 native virtualized table with in-widget column headers."""
            store = Gio.ListStore.new(Gtk.StringObject)
            selection = Gtk.SingleSelection.new(None)
            selection.set_autoselect(False)
            view = Gtk.ColumnView.new(selection)
            view.add_css_class('data-table')
            view.set_show_row_separators(True)
            view.set_hexpand(True)
            # Sorting is delegated to GTK model rather than handmade header cells.
            sorted_model = Gtk.SortListModel.new(store, view.get_sorter())
            selection.set_model(sorted_model)
            self.gtk_models[scope] = store
            self.gtk_selections[scope] = selection
            def changed(sel, _property=None):
                selected = sel.get_selected_item()
                if selected is None or self.scope != scope:
                    return
                it = next((x for x in self.items if str(x.path) == selected.get_string()), None)
                if it:
                    self.show_inspector(focused=it)
            selection.connect('notify::selected-item', changed)
            def sort_for(column):
                def compare(a, b, _data=None):
                    def key(obj):
                        text = obj.get_string()
                        entry = next((x for x in self.items if str(x.path) == text), None)
                        if entry is None: return '' if column != 3 else 0
                        return {1:entry.path.name.casefold(), 2:entry.state,
                                3:entry.bytes, 4:str(entry.path.parent).casefold()}[column]
                    aa, bb = key(a), key(b)
                    return Gtk.Ordering.SMALLER if aa < bb else (Gtk.Ordering.LARGER if aa > bb else Gtk.Ordering.EQUAL)
                return Gtk.CustomSorter.new(compare)
            for col, caption, width in ((0, '✓', 42), (1, tr('Nazwa'), 220),
                                        (2, tr('Status'), 130), (3, tr('Rozmiar'), 108),
                                        (4, tr('Lokalizacja'), 270)):
                factory = Gtk.SignalListItemFactory()
                def setup(_factory, list_item, field=col):
                    widget = Gtk.CheckButton() if field == 0 else Gtk.Label(xalign=0)
                    if field != 0:
                        widget.set_ellipsize(Pango.EllipsizeMode.MIDDLE if field == 4 else Pango.EllipsizeMode.END)
                        widget.set_hexpand(True)
                    else:
                        def toggled(button, li=list_item):
                            if getattr(button, '_xdg_rebinding', False): return
                            ref=li.get_item()
                            if ref is None:return
                            path=ref.get_string()
                            if button.get_active():self.checked.add(path)
                            else:self.checked.discard(path)
                            self.selected_count.set_text(selected_count(len(self.checked),_language))
                            self.move_button.set_sensitive(bool(self.checked) and not self.busy and self.scope!='quarantine')
                            self.show_inspector()
                        widget.connect('toggled', toggled)
                    list_item.set_child(widget)
                def bind(_factory, list_item, field=col):
                    ref=list_item.get_item()
                    if ref is None:return
                    it=next((x for x in self.items if str(x.path)==ref.get_string()),None)
                    if it is None:return
                    widget=list_item.get_child()
                    if field == 0:
                        widget._xdg_rebinding=True
                        widget.set_sensitive(self._eligible(it))
                        widget.set_active(str(it.path) in self.checked)
                        widget._xdg_rebinding=False
                    else:
                        widget.set_text((None, it.path.name, it.state, engine.human(it.bytes), str(it.path.parent))[field])
                factory.connect('setup', setup)
                factory.connect('bind', bind)
                column=Gtk.ColumnViewColumn.new(caption, factory)
                column.set_resizable(True)
                column.set_fixed_width(width)
                # Gtk.ColumnView distributes unused horizontal space across
                # expanding columns. Keep checkbox/status/size compact; let
                # name and location adapt when resizing the window or opening
                # the inspector.
                if col in (1, 4):
                    column.set_expand(True)
                if col:
                    column.set_sorter(sort_for(col))
                view.append_column(column)
            self.gtk_columns[scope] = view
            return view

        def filter_status(self,state):
            if state in {'ACTIVE','PROTECTED'}:
                self.show_all.set_active(True)
            values=('ALL','CANDIDATE','REVIEW','UNKNOWN','ACTIVE','PROTECTED')
            self.state_filter.set_active(values.index(state))
            self.update_metric_highlight()

        def update_metric_highlight(self):
            selected=self.state_filter.get_active_text()
            for state,btn in self.metric_buttons.items():
                enabled = state == selected
                context = btn.get_style_context()
                if GTK4:
                    (btn.add_css_class if enabled else btn.remove_css_class)('xdg-active')
                else:
                    (context.add_class if enabled else context.remove_class)('xdg-active')

        def _toggle_uncertain(self,*_):
            self.allow_uncertain=self.uncertain.get_active()
            self.refresh()

        def _change_scope(self,*_):
            self.scope=self.stack.get_visible_child_name() or 'all'
            self.hide_inspector()
            if not hasattr(self, 'summary'):
                return  # Gtk.Stack can fire while the window is still building.
            if self.scope=='quarantine':
                self.move_button.set_sensitive(False)
                self.all_button.set_sensitive(False)
                self.refresh_quarantine()
            else:
                self.all_button.set_sensitive(True)
                self.refresh()

        def _eligible(self,it):
            return self.scan_complete and not it.protected and (it.state=='CANDIDATE' or
                        (self.allow_uncertain and it.state in {'REVIEW','UNKNOWN'}))

        def _visible(self):
            q=self.search.get_text().strip().casefold()
            state=self.state_filter.get_active_text()
            for it in self.items:
                if state!='ALL' and it.state!=state:continue
                if self.scope!='all' and it.scope!=self.scope:continue
                if not self.show_all.get_active() and it.state in {'ACTIVE','PROTECTED'}:continue
                if q and q not in ' '.join((str(it.path),it.scope,it.state,*it.reasons)).casefold():continue
                yield it

        def hide_inspector(self):
            self.inspector.set_visible(False)
            self._clear_focused_row()
            if GTK4:
                for selection in self.gtk_selections.values():
                    selection.set_selected(Gtk.INVALID_LIST_POSITION)
            else:
                for rows in self.lists.values():
                    rows.unselect_all()

        def _clear_focused_row(self):
            row = self.focused_row
            self.focused_row = None
            if row is not None and GTK4:
                row.remove_css_class('xdg-focused')

        def open_selected_location(self, *_):
            if self.previewed_item is None:
                return
            try:
                open_item_location(self.previewed_item.path, home)
            except (OSError, RuntimeError, ValueError) as exc:
                self.status.set_text(str(exc))

        def show_inspector(self,focused=None):
            if self.scope == 'quarantine':
                return
            selected=[it for it in self.items if str(it.path) in self.checked]
            content=details_text(selected,engine.human,focused,language=_language)
            self.previewed_item = focused if focused is not None else (selected[0] if len(selected) == 1 else None)
            self.open_location_button.set_sensitive(self.previewed_item is not None)
            if not content:
                self.inspector.set_visible(False)
                return
            self.details.set_text(content)
            self.inspector.set_visible(True)
            self.content_pane.set_position(max(250,self.content_pane.get_allocated_width()-335))

        def _clicked_row(self,entry,row=None):
            """Row navigation always shows the clicked entry, not an old checkbox."""
            if row is not self.focused_row:
                self._clear_focused_row()
                self.focused_row = row
                if GTK4 and row is not None:
                    row.add_css_class('xdg-focused')
            self.show_inspector(focused=entry)

        def _pressed_row(self,gesture,n_press,x,y,entry,row):
            """GTK4 capture-phase click: labels, whitespace and row area work.

            A click originating in a CheckButton is reserved for bulk selection.
            Its 'toggled' handler handles the inspector after changing selection.
            """
            if n_press < 1:
                return
            picked = row.pick(x,y,Gtk.PickFlags.DEFAULT)
            if click_is_inside_control(picked,row,Gtk.CheckButton):
                return
            self._clicked_row(entry,row)

        def _row_selected(self,_,row):
            if row is not None and id(row) in self.row_data:
                self._clicked_row(self.row_data[id(row)],row)

        def _toggle(self,button,path):
            if button.get_active():self.checked.add(path)
            else:self.checked.discard(path)
            self.selected_count.set_text(selected_count(len(self.checked),_language))
            self.move_button.set_sensitive(bool(self.checked) and not self.busy and self.scope!='quarantine')
            # Checkbox changes show the (possibly multi-item) selection.
            # Clicking a different row is independent and uses _clicked_row.
            if self.checked:
                self.show_inspector()
            else:
                self.hide_inspector()

        def _add_table_heading(self,rows):
            titles=[]
            for name in ('✓',tr('Nazwa'),tr('Status'),tr('Rozmiar'),tr('Lokalizacja')):
                title=label('')
                title.set_markup('<span weight="bold">'
                                 + GLib.markup_escape_text(name) + '</span>')
                titles.append(title)
            heading_row=Gtk.ListBoxRow()
            heading_row.set_selectable(False)
            heading_row.set_activatable(False)
            if GTK4:
                heading_row.add_css_class('xdg-heading-row')
            else:
                heading_row.get_style_context().add_class('xdg-heading-row')
            content=make_cells(titles,heading=True)
            heading_row.set_child(content) if GTK4 else heading_row.add(content)
            append(rows,heading_row)

        def refresh(self):
            if self.scope=='quarantine':return
            rows=self.lists.get(self.scope)
            if rows is None:return
            lookup={str(it.path):it for it in self.items}
            self.checked={p for p in self.checked if p in lookup and self._eligible(lookup[p])}
            if GTK4:
                store=self.gtk_models[self.scope]
                store.remove_all()
                for it in self._visible():
                    store.append(Gtk.StringObject.new(str(it.path)))
            else:
                self._clear_focused_row()
                clear(rows)
                self.row_data.clear()
                self._add_table_heading(rows)
            for it in ([] if GTK4 else self._visible()):
                row=Gtk.ListBoxRow(); self.row_data[id(row)]=it
                check_box=Gtk.Box()
                if self._eligible(it):
                    chk=Gtk.CheckButton()
                    chk.set_active(str(it.path) in self.checked)
                    chk.connect('toggled',self._toggle,str(it.path))
                    append(check_box,chk)
                else:
                    append(check_box,label('—'))
                name=label('')
                name.set_markup('<b>'+GLib.markup_escape_text(it.path.name)+'</b>')
                name.set_ellipsize(Pango.EllipsizeMode.END)
                st=label(it.state)
                size=label(engine.human(it.bytes))
                location=label(str(it.path.parent))
                location.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                h=make_cells([check_box,name,st,size,location])
                row.set_child(h) if GTK4 else row.add(h)
                if GTK4:
                    click=Gtk.GestureClick()
                    click.set_button(1)
                    click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                    click.connect('pressed', self._pressed_row, it, row)
                    row.add_controller(click)
                append(rows,row)
            if not GTK4:rows.show_all()
            for state,counter in self.metric_counts.items():
                count=sum(it.state==state for it in self.items)
                counter.set_markup(f'<span weight="bold" size="x-large">{count}</span>')
            self.update_metric_highlight()
            self.visible_count.set_text(entries_count(sum(1 for _ in self._visible()),_language))
            self.selected_count.set_text(selected_count(len(self.checked),_language))
            self.move_button.set_sensitive(bool(self.checked) and not self.busy and self.scope!='quarantine')

        def start_scan(self):
            if self.busy:return
            self.busy=True
            self.scan_complete=False
            self.cancel_scan=threading.Event()
            self._clear_focused_row()
            self.rescan.set_sensitive(False)
            self.move_button.set_sensitive(False)
            self.hide_inspector()
            self._set_loading_visible(True)
            self.status.set_text(tr('Trwa skanowanie… bez modyfikacji plików'))
            def worker():
                try:
                    result=engine.scan(home,list(engine.SCOPES),{engine.normalize(x) for x in args.keep},aliases,args.quick,
                                       progress=lambda stage:GLib.idle_add(self._scan_stage,stage),
                                       on_batch=lambda phase, entries, done, total: GLib.idle_add(
                                           self._scan_batch, phase, entries, done, total),
                                       cancelled=self.cancel_scan.is_set)
                    GLib.idle_add(self.finish,result)
                except engine.ScanCancelled:
                    GLib.idle_add(self.cancel_finished)
                except Exception as exc:
                    GLib.idle_add(self.failed,str(exc))
            threading.Thread(target=worker,daemon=True).start()

        def _scan_stage(self,stage):
            if self.busy:
                self.loading_note.set_text(tr(stage) + '…')
                self.status.set_text(('Scanning: ' if _language=='en' else 'Skanowanie: ') + tr(stage))
            return False

        def _scan_batch(self, phase, entries, done, total):
            if not self.busy:
                return False
            if phase == 'classified':
                self.items = list(entries)
                self.results_or_loading.set_visible_child_name('results')
                self._size_in_progress = not bool(args.quick)
                self.refresh()
                self.status.set_text((f'Classified {len(self.items)} entries; calculating sizes…' if _language=='en' else f'Sklasyfikowano {len(self.items)} pozycji; obliczanie rozmiarów…'))
            elif phase == 'sizes':
                self.loading_progress.set_fraction(done / max(total, 1))
                self.refresh()
                self.status.set_text(f'{tr("Rozmiary katalogów")}: {done}/{total}')
            return False

        def cancel_finished(self):
            self.busy=False
            self.rescan.set_sensitive(True)
            self._set_loading_visible(False)
            self.status.set_text(tr('Skanowanie anulowano. Wyniki częściowe nie nadają się do kwarantanny.'))
            self.checked.clear()
            self.move_button.set_sensitive(False)
            return False

        def _update_optional_tabs(self):
            visible = visible_optional_scopes(self.items, self.stats)
            if self.stack.get_visible_child_name() in {'flatpak', 'snap'} - visible:
                self.stack.set_visible_child_name('all')
            for scope in ('flatpak', 'snap'):
                page = self.stack.get_child_by_name(scope)
                if GTK4:
                    self.stack.get_page(page).set_visible(scope in visible)
                else:
                    page.set_no_show_all(scope not in visible)
                page.set_visible(scope in visible)

        def finish(self,result):
            self.scan_complete=True
            self.items,self.roots,self.stats=result
            self._update_optional_tabs()
            self.checked.clear()
            self.hide_inspector()
            self.busy=False
            self.rescan.set_sensitive(True)
            self.move_button.set_sensitive(False)
            self._set_loading_visible(False)
            self.refresh()
            self.refresh_quarantine()
            self.status.set_text((f'Scanned {len(self.items)} entries. No changes. Stages: ' if _language=='en' else f'Zbadano {len(self.items)} pozycji. Żadnych zmian. Fazy: ') + ', '.join(f'{tr(k)} {v}ms' for k,v in self.stats.get('phase_times_ms',{}).items()))
            return False

        def failed(self,message):
            self.scan_complete=False
            self.busy=False
            self.rescan.set_sensitive(True)
            self.move_button.set_sensitive(False)
            self._set_loading_visible(False)
            self.status.set_text(tr('Błąd skanowania')+': '+message)
            return False

        def select_candidates(self,*_):
            if not self.scan_complete:return
            self.checked.update(str(it.path) for it in self._visible() if it.state=='CANDIDATE')
            self.refresh()
            self.show_inspector()

        def clear_selection(self,*_):
            self.checked.clear();self.refresh();self.hide_inspector()

        def prompt(self,title,description,need,callback):
            """Nonblocking, two-stage native confirmation dialog."""
            dialog=Gtk.Window(title=title,transient_for=self.win,modal=True)
            outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            for side in ('top','bottom','start','end'):
                getattr(outer,'set_margin_'+side)(16)
            txt=label(description)
            # This is informational text, not an editable/copyable field.
            # A selectable Gtk.Label grabs focus and looks like "select all"
            # when the transient modal first opens under some GTK themes.
            wrap_label(txt)
            append(outer,txt)
            entry=Gtk.Entry();entry.set_placeholder_text(tf('Wpisz {token}', token=need))
            append(outer,entry)
            actions=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=9)
            append(outer,actions)
            cancel=Gtk.Button(label=tr('Anuluj'))
            cancel.connect('clicked',lambda *_:dialog.destroy())
            append(actions,cancel)
            confirm=Gtk.Button(label=tr('Potwierdź'))
            def accept(*_):
                if entry.get_text()!=need:
                    self.status.set_text(tf('Nieprawidłowe potwierdzenie. Wpisz {token}.', token=need))
                    return
                dialog.destroy()
                callback()
            confirm.connect('clicked',accept)
            append(actions,confirm)
            configure_gtk_dialog(dialog,outer,Gtk,Gdk,Pango)
            # Set GTK window-local focus before mapping the transient modal;
            # an immediate grab_focus() alone can be lost on Wayland/Xvfb.
            dialog.set_focus(entry)
            dialog.present() if GTK4 else dialog.show_all()
            def ensure_entry_focus():
                if dialog.get_visible():
                    entry.grab_focus()
                return False
            GLib.idle_add(ensure_entry_focus)

        def move(self,*_):
            if self.busy:return
            selected=[it for it in self.items if str(it.path) in self.checked and self._eligible(it)]
            if not selected:
                self.status.set_text(tr('Zaznacz pozycje checkboxami, aby wykonać kwarantannę.'));return
            uncertain=[x for x in selected if x.state!='CANDIDATE']
            details='\n'.join(f'{it.state} {engine.human(it.bytes)} {it.path}' for it in selected[:14])
            if len(selected)>14:details+='\n'+tf('…oraz {count} kolejnych.',count=len(selected)-14)
            description=(tf('Plan: {count}, {size}.',count=entries_count(len(selected),_language), size=engine.human(sum(x.bytes for x in selected)))+'\n'+details+'\n\n'+tr('Dane zostaną PRZENIESIONE, nie usunięte.'))
            def commit():
                output=[]
                try:
                    result=engine.commit_quarantine(selected,self.roots,home,allow_uncertain=bool(uncertain),emit=output.append,extra_aliases=aliases,keep_names=args.keep)
                    self.status.set_text(tf('Kwarantanna: {run_id}, przeniesiono {count}.',run_id=result['run_id'],count=entries_count(len(result['moved']),_language)))
                    self.start_scan()
                    if any('purge inventory unavailable' in line for line in output):
                        self._quarantine_notice(
                            tr('Pliki przeniesiono, ale nie można było sprawdzić całej zawartości. Przed PURGE użyj „Sprawdź dostęp…”, następnie osobno „Zatwierdź stan…” (ADOPT).'))
                except (ValueError,OSError,SystemExit) as exc:self.status.set_text(tf('Błąd przenoszenia: {error}',error=exc))
            def confirm_move():self.prompt(tr('Ostateczne potwierdzenie'),description+'\n'+tr('Zamknij powiązane aplikacje.'), 'MOVE', commit)
            if uncertain:
                self.prompt(tr('Niepewne pozycje'),tf('UWAGA: {count} pozycji REVIEW/UNKNOWN może należeć do używanych programów.',count=len(uncertain)),
                            'UNCERTAIN',confirm_move)
            else:confirm_move()

        def compare_report_gui(self,*_):
            if not self.scan_complete:return
            from xdg_history import summary
            chooser=Gtk.FileChooserNative.new(tr('Wybierz wcześniejszy raport'),
                        self.win, Gtk.FileChooserAction.OPEN, tr('Otwórz'), tr('Anuluj'))
            def chosen(dlg,response):
                if response != Gtk.ResponseType.ACCEPT:
                    dlg.destroy();return
                source=dlg.get_file().get_path() if GTK4 else dlg.get_filename()
                dlg.destroy()
                try:
                    differences=engine.compare_report(self.items,Path(source),list(engine.SCOPES))
                    message=summary(differences,_language)
                except (OSError,SystemExit,ValueError) as exc:
                    self.status.set_text(tf('Błąd porównania: {error}',error=exc));return
                result_window=Gtk.Window(title=tr('Porównanie raportów'),
                                        transient_for=self.win,modal=True)
                body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
                body.set_margin_top(14);body.set_margin_bottom(14)
                body.set_margin_start(14);body.set_margin_end(14)
                scrolling=Gtk.ScrolledWindow();scrolling.set_vexpand(True)
                text=label(message);text.set_selectable(True);wrap_label(text)
                set_child(scrolling,text);append(body,scrolling,True)
                close=Gtk.Button(label='Close' if _language=='en' else 'Zamknij')
                close.connect('clicked',lambda *_:result_window.destroy())
                append(body,close)
                configure_gtk_dialog(result_window,body,Gtk,Gdk,Pango)
                result_window.present() if GTK4 else result_window.show_all()
                text.select_region(0,0)
                close.grab_focus()
            chooser.connect('response',chosen)
            chooser.show()

        def export(self,*_):
            # No portal browser; save into a predictable user-owned path.
            # Explicit confirmation avoids silent writes (even reports).
            from xdg_history import suggested_export_path
            target=suggested_export_path(home)
            def write():
                data={'version':engine.VERSION,'scopes':list(engine.SCOPES),
                      'stats':self.stats,'entries':[x.json() for x in self.items]}
                try:
                    if target.exists():
                        self.status.set_text(tf('Raport już istnieje — nie nadpisuję: {path}',path=target));return
                    with target.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False)
                    self.status.set_text(tf('Zapisano: {path}',path=target))
                except OSError as exc:self.status.set_text(tf('Błąd raportu: {error}',error=exc))
            self.prompt(tr('Eksport JSON'),tf('Zapisać raport do {path}?',path=target)+'\n'+tr('Istniejący plik nie zostanie nadpisany.'), 'EXPORT', write)

        def quarantine_preview(self,run):
            dialog=Gtk.Window(title=tr('Zawartość kwarantanny'),transient_for=self.win,modal=True)
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            for side in ('top','bottom','start','end'):
                getattr(body,'set_margin_'+side)(15)
            append(body,label(tf('Operacja: {run_id} · {count} przeniesionych',run_id=run['run_id'],count=run['moved'])))
            preview=Gtk.ScrolledWindow();preview.set_vexpand(True)
            text=label('\n'.join(str(i.get('source','?')) for i in run['items']) or tr('(pusty manifest)'))
            wrap_label(text);text.set_selectable(True)
            set_child(preview,text)
            append(body,preview,True)
            close=Gtk.Button(label=tr('Zamknij'))
            close.connect('clicked',lambda *_:dialog.destroy())
            append(body,close)
            configure_gtk_dialog(dialog,body,Gtk,Gdk,Pango)
            dialog.present() if GTK4 else dialog.show_all()
            text.select_region(0,0)
            close.grab_focus()

        def refresh_quarantine(self):
            clear(self.qlist)
            tools_row=Gtk.ListBoxRow()
            tools_box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10)
            append(tools_box,label(tr('Retencja: usuń wygasłe operacje')),True)
            expired=Gtk.Button(label=tr('Usuń wygasłe…'))
            expired.connect('clicked',lambda *_:self.purge_expired())
            append(tools_box,expired)
            retention=Gtk.Button(label=tr('Ustaw retencję…'))
            retention.connect('clicked',lambda *_:self.configure_retention())
            append(tools_box,retention)
            history=Gtk.Button(label=tr('Wyczyść całą zakończoną historię…'))
            history.connect('clicked',lambda *_:self.cleanup_all_history())
            append(tools_box,history)
            tools_row.set_child(tools_box) if GTK4 else tools_row.add(tools_box)
            append(self.qlist,tools_row)
            for run in engine.quarantine_runs(home,engine.xdg_roots(home)):
                row=Gtk.ListBoxRow()
                box=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12)
                append(box,label(run['run_id']+'   |   '+tr(run['status'])+'   |   '+
                    tf('{count} przeniesionych / {total} w manifest',count=run['moved'],total=len(run['items']))),True)
                preview=Gtk.Button(label=tr('Podgląd'))
                preview.connect('clicked',lambda _,r=run:self.quarantine_preview(r))
                append(box,preview)
                if run['status'] in ('PURGED','RESTORED','COMPLETED'):
                    history_button=Gtk.Button(label=tr('Usuń historię…'))
                    history_button.connect('clicked',lambda _,rid=run['run_id']:self.cleanup_history([rid]))
                    append(box,history_button)
                else:
                    button=Gtk.Button(label=tr('Przywróć…'))
                    button.connect('clicked',lambda _,rid=run['run_id']:self.restore(rid))
                    append(box,button)
                    purge=Gtk.Button(label=tr('Usuń trwale…'))
                    purge.connect('clicked',lambda _,rid=run['run_id']:self.purge_runs([rid]))
                    append(box,purge)
                    access=Gtk.Button(label=tr('Sprawdź dostęp…'))
                    access.connect('clicked',lambda _,rid=run['run_id']:self.access_diagnostics(rid))
                    append(box,access)
                    adopt=Gtk.Button(label=tr('Zatwierdź stan…'))
                    adopt.connect('clicked',lambda _,rid=run['run_id']:self.adopt_inventory(rid))
                    append(box,adopt)
                row.set_child(box) if GTK4 else row.add(box)
                append(self.qlist,row)
            if not GTK4:self.qlist.show_all()

        def configure_retention(self):
            from xdg_retention import load, save
            try:
                current=load(home,engine.xdg_roots(home))
            except (ValueError,OSError) as exc:
                self.status.set_text(tf('Nie można zapisać retencji: {error}',error=exc))
                return
            dialog=Gtk.Window(title=tr('Retencja'),transient_for=self.win,modal=True)
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            for side in ('top','bottom','start','end'):
                getattr(content,'set_margin_'+side)(15)
            append(content,label(tr('Dni przechowywania:')))
            days=Gtk.SpinButton.new_with_range(1,3650,1)
            days.set_value(current['days'])
            append(content,days)
            actions=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8)
            append(content,actions)
            cancel=Gtk.Button(label=tr('Anuluj'))
            cancel.connect('clicked',lambda *_:dialog.destroy())
            append(actions,cancel)
            button=Gtk.Button(label=tr('Zapisz'))
            def accept(*_):
                current['days']=days.get_value_as_int()
                try:
                    save(home,engine.xdg_roots(home),current)
                    self.status.set_text(tf('Ustawiono retencję: {days} dni',days=current['days']))
                    dialog.destroy()
                except (ValueError,OSError) as exc:
                    self.status.set_text(tf('Nie można zapisać retencji: {error}',error=exc))
            button.connect('clicked',accept)
            append(actions,button)
            configure_gtk_dialog(dialog,content,Gtk,Gdk,Pango)
            dialog.present() if GTK4 else dialog.show_all()

        def _quarantine_job(self, operation, completed, activity):
            """Never hash or unlink quarantine contents on the GTK main loop.

            The single-flight guard also prevents double-clicks or running
            overlapping destructive actions during an active verification.
            """
            if self._quarantine_job_busy:
                self.status.set_text(tr('Operacja kwarantanny jest już wykonywana.'))
                return
            self._quarantine_job_busy=True
            self._quarantine_progress=None
            self.status.set_text(tr(activity))

            def show_progress():
                # Quick operations never need an extra modal. For large trees,
                # show immediate visible progress rather than an inert button.
                if not self._quarantine_job_busy:
                    return False
                dialog=Gtk.Window(title=tr('Weryfikacja kwarantanny'),
                                  transient_for=self.win,modal=True)
                dialog.set_deletable(False)
                pane=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=12)
                for side in ('top','bottom','start','end'):
                    getattr(pane,'set_margin_'+side)(18)
                spinner=Gtk.Spinner()
                spinner.start()
                append(pane,spinner)
                append(pane,label(tr(activity)),True)
                configure_gtk_dialog(dialog,pane,Gtk,Gdk,Pango)
                self._quarantine_progress=dialog
                dialog.present() if GTK4 else dialog.show_all()
                return False

            GLib.timeout_add(200,show_progress)

            def finish(ok, outcome):
                self._quarantine_job_busy=False
                dialog=self._quarantine_progress
                self._quarantine_progress=None
                if dialog is not None:
                    dialog.destroy()
                try:
                    completed(ok, outcome)
                except Exception as exc:
                    self.status.set_text(tf('Błąd operacji kwarantanny: {error}',error=exc))
                return False

            run_gui_job(operation, finish, GLib.idle_add)

        def _quarantine_notice(self, message, title=None):
            """Show a visible GTK notice instead of a hard-to-see footer update."""
            dialog=Gtk.Window(title=title or tr('Historia'),transient_for=self.win,modal=True)
            pane=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
            for side in ('top','bottom','start','end'):
                getattr(pane,'set_margin_'+side)(16)
            note=label(message)
            note.set_selectable(True)
            wrap_label(note)
            append(pane,note)
            close=Gtk.Button(label=tr('Zamknij'))
            close.connect('clicked',lambda *_:dialog.destroy())
            append(pane,close)
            configure_gtk_dialog(dialog,pane,Gtk,Gdk,Pango)
            dialog.present() if GTK4 else dialog.show_all()
            close.grab_focus()
            note.select_region(0,0)

        def adopt_inventory(self, run_id, resume_purge=False):
            explanation=(tf('Operacja: {run_id}',run_id=run_id)+'\n'+
                         tr('Zatwierdzisz stan plików widoczny TERAZ. Nie oznacza to, że zawartość jest identyczna jak w dniu przeniesienia. PURGE nadal wymaga osobnej zgody.'))
            def commit():
                def done(ok, result):
                    if not ok:
                        self._quarantine_notice(quarantine_error_details(result,_language),
                                                title=tr('Zatwierdź aktualny stan'))
                    else:
                        self.refresh_quarantine()
                        if resume_purge:
                            # New preflight and a distinct PURGE confirmation follow.
                            self.purge_runs([run_id])
                        else:
                            self._quarantine_notice(
                                tf('Zatwierdzono aktualny stan: {count} obiektów.',count=result['adopted'])+
                                '\n'+tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'))
                self._quarantine_job(
                    lambda:engine.adopt_quarantine_inventory(
                        home,engine.xdg_roots(home),run_id),
                    done,'Weryfikacja kwarantanny')
            self.prompt(tr('Zatwierdź aktualny stan'),explanation,'ADOPT',commit)

        def access_diagnostics(self, run_id, resume_purge=False, repaired=False):
            """Investigate one run without granting elevated privileges."""
            def ready(ok, result):
                if not ok:
                    self._quarantine_notice(tf('Błąd diagnostyki: {error}',error=result))
                    return
                issues=result['issues']
                who=result['identity']['user']
                polkit_text=tf('pkexec zainstalowany: {state}',
                               state=tr('tak') if result['identity']['pkexec_installed'] else tr('nie'))
                if not issues:
                    if resume_purge and (repaired or result['unsealed']):
                        if result['unsealed']:
                            self.adopt_inventory(run_id, resume_purge=True)
                        else:
                            self.purge_runs([run_id])
                        return
                    note=tr('Nie znaleziono problemów z odczytem. Sprawdź pozostałe komunikaty PURGE.')
                    if result['unsealed']:
                        note+='\n'+tr('Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).')
                    self._quarantine_notice(note)
                    return
                issue=issues[0]
                if issue['code']=='ENTRY_IDENTITY_CHANGED':
                    self._quarantine_notice(identity_issue_details(issue,run_id,_language),
                                            title=tr('Zablokowano PURGE'))
                    return
                summary=(tf('Operacja: {run_id}',run_id=run_id)+'\n'+
                         tf('Użytkownik: {user}',user=who)+'\n'+
                         polkit_text+'\n'+
                         tf('Problem: {code}',code=issue['code'])+'\n'+
                         str(issue['path'])+'\n'+
                         tf('Uprawnienia: {mode}',mode=issue['mode'])+'\n')
                if not issue['repairable']:
                    self._quarantine_notice(
                        summary+'\n'+tr('Nie można automatycznie naprawić. Nie podnoszę uprawnień ani nie omijam kontroli PURGE.')+
                        '\n'+tr('Naprawa tego obiektu wymaga dodatkowej analizy. Zasady Polkit określa system; xdg-audit nie uruchamia kodu użytkownika jako root.'))
                    return
                summary+=('\n'+tf('Proponowana zmiana: {before} → {after}',
                                   before=issue['mode'],after=issue['suggested_mode'])+
                          '\n'+tr('Zmienię tylko wskazane uprawnienia właściciela w kwarantannie. Bez sudo i bez usuwania plików.'))
                def approved():
                    def operation():
                        return engine.repair_quarantine_access(
                            home,engine.xdg_roots(home),run_id,issue['relative'])
                    def completed(success, outcome):
                        if not success:
                            self._quarantine_notice(
                                tf('Naprawa zablokowana: {error}',error=outcome))
                            return
                        info=(tf('Zmieniono uprawnienia: {before} → {after}',
                                 before=outcome['old_mode'],after=outcome['new_mode'])+
                              '\n'+tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'))
                        if result['unsealed']:
                            info+='\n'+tr('Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).')
                        if resume_purge:
                            # Continue diagnosis until all inaccessible items are resolved.
                            self.access_diagnostics(run_id, resume_purge=True, repaired=True)
                        else:
                            self._quarantine_notice(info)
                    self._quarantine_job(operation,completed,'Naprawianie dostępu…')
                self.prompt(tr('Napraw dostęp'),summary,'ACCESS',approved)
            self._quarantine_job(
                lambda:engine.diagnose_quarantine_access(
                    home,engine.xdg_roots(home),run_id),
                ready,'Sprawdzanie dostępu…')

        def cleanup_all_history(self):
            """Manual all-history operation, not the automatic 30-day GC."""
            def query():
                return engine.completed_quarantine_history(home,engine.xdg_roots(home))
            def done(ok, result):
                if not ok:
                    self._quarantine_notice(tf('Błąd historii: {error}',error=result))
                elif result:
                    self.cleanup_history(result)
                else:
                    self._quarantine_notice(tr('Brak zakończonych operacji do wyczyszczenia. Aktywne i niedokończone pozostają chronione.'))
            self._quarantine_job(query,done,'Sprawdzanie historii…')

        def cleanup_expired_history(self):
            def query():
                return engine.expired_quarantine_history(home,engine.xdg_roots(home))
            def finish(ok, result):
                if not ok:
                    self.status.set_text(tf('Błąd retencji: {error}',error=result))
                elif result:
                    self.cleanup_history(result)
                else:
                    self.status.set_text(tr('Brak wygasłych manifestów.'))
            self._quarantine_job(query,finish,'Sprawdzanie historii…')

        def cleanup_history(self,run_ids):
            run_ids=tuple(run_ids)
            def preview():
                return [engine.cleanup_quarantine_history(
                    home,engine.xdg_roots(home),rid) for rid in run_ids]
            def preview_ready(ok, result):
                if not ok:
                    self.status.set_text(tf('Błąd historii: {error}',error=result))
                    return
                details='\\n'.join(plan['run_id']+' ('+plan['status']+')'
                                  for plan in result)
                def execute():
                    def operation():
                        for plan in result:
                            engine.cleanup_quarantine_history(
                                home,engine.xdg_roots(home),plan['run_id'],dry_run=False)
                        return len(result)
                    def done(success, outcome):
                        self.refresh_quarantine()
                        if success:
                            self.status.set_text(tr('Usunięto zakończone manifesty.'))
                        else:
                            self.status.set_text(tf('Błąd historii: {error}',error=outcome))
                    self._quarantine_job(operation,done,'Usuwanie historii…')
                self.prompt(tr('Usuń historię'),details+'\\n\\n'+
                            tr('Zostaną usunięte tylko zakończone dzienniki.'),
                            'HISTORY',execute)
            self._quarantine_job(preview,preview_ready,'Sprawdzanie historii…')

        def purge_runs(self,run_ids):
            run_ids=tuple(run_ids)
            def preview():
                return [engine.purge_quarantine_run(
                    home,engine.xdg_roots(home),run_id) for run_id in run_ids]
            def preview_ready(ok, outcome):
                if not ok:
                    self.status.set_text(tr('Zablokowano PURGE'))
                    self.status.set_tooltip_text(quarantine_error_details(outcome,_language))
                    if len(run_ids)==1 and engine.quarantine_access_recoverable_error(outcome):
                        self.access_diagnostics(run_ids[0], resume_purge=True)
                    else:
                        self._quarantine_notice(quarantine_error_details(outcome,_language),
                                                title=tr('Zablokowano PURGE'))
                    return
                details='\\n'.join(
                    f"{p['run_id']}: {p['objects']} entries, {p['bytes']} B"
                    for p in outcome)
                def execute():
                    def operation():
                        removed=0
                        for plan in outcome:
                            result=engine.purge_quarantine_run(
                                home,engine.xdg_roots(home),plan['run_id'],dry_run=False)
                            removed+=result['objects']
                        return removed
                    def done(success, result):
                        self.refresh_quarantine()
                        if success:
                            self.status.set_text(tr('Trwale usunięto obiektów: ')+str(result))
                        else:
                            self.status.set_text(tr('Zablokowano PURGE'))
                            self.status.set_tooltip_text(quarantine_error_details(result,_language))
                            self._quarantine_notice(quarantine_error_details(result,_language),
                                                    title=tr('Zablokowano PURGE'))
                    self._quarantine_job(operation,done,'Trwałe usuwanie z kwarantanny…')
                self.prompt(tr('Trwałe usunięcie'),details+'\\n\\n'+
                            tr('Nie można cofnąć tej operacji.'),'PURGE',execute)
            self._quarantine_job(preview,preview_ready,'Sprawdzanie kwarantanny…')

        def purge_expired(self):
            def query():
                return engine.expired_quarantine_runs(home,engine.xdg_roots(home))
            def finish(ok, result):
                if not ok:
                    self.status.set_text(tf('Błąd retencji: {error}',error=result))
                elif result:
                    self.purge_runs(result)
                else:
                    self.status.set_text(tr('Brak wygasłych kwarantann.'))
            self._quarantine_job(query,finish,'Sprawdzanie kwarantanny…')

        def restore(self,run_id):
            def do_restore():
                try:
                    result=engine.restore_quarantine_run(home,engine.xdg_roots(home),run_id)
                    self.status.set_text(tf('Przywrócono {restored}, pominięto {skipped}.',restored=result['restored'],skipped=result['skipped']))
                    self.start_scan()
                except (ValueError,OSError,KeyError) as exc:self.status.set_text(tf('Błąd przywracania: {error}',error=exc))
            self.prompt(tr('Przywracanie'),tf('Przywrócić operację {run_id}?',run_id=run_id)+'\n'+tr('Istniejące pliki nie zostaną nadpisane.'),'RESTORE',do_restore)

    app=Gtk.Application(application_id='io.github.xdgaudit')
    holder=[]
    def activate(a):
        nonlocal css_provider
        if holder:
            holder[0].win.present();return
        css_provider = install_styles()
        holder.append(Window(a))
    app.connect('activate',activate)
    exit_code = int(app.run([]))
    if exit_code != 0:
        raise RuntimeError(f'GTK {gtk_version} failed to open display (exit {exit_code})')
    return 0
