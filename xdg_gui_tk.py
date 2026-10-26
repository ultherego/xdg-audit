"""No-install native GUI fallback using the Python Tcl/Tk binding already present.

Ttk is themed; KDE/GNOME palettes are applied when discoverable. Tk on Linux
needs DISPLAY (X11 or XWayland). It does not reproduce arbitrary GTK CSS.
"""
from __future__ import annotations
from xdg_i18n import translate, translate_ui_text, entries_count, selected_count, format_message

import json
import queue
import threading
from pathlib import Path
from typing import Any

from xdg_theme import detect_appearance
from xdg_inspector import details_text, open_item_location
from xdg_gui_jobs import run_gui_job

SCOPE_LABELS = [('Wszystko', 'all'), ('Konfiguracja', 'config'),
                ('Dane aplikacji', 'data'), ('Stan', 'state'),
                ('Cache', 'cache'), ('Flatpak', 'flatpak'), ('Snap', 'snap'), ('Dotfiles', 'dotfiles')]
STATES = ('CANDIDATE', 'REVIEW', 'UNKNOWN', 'ACTIVE', 'PROTECTED')


def launch_gui(engine: Any, home: Path, args: Any, aliases: dict, runtime: dict, backend: str='tk') -> int:

    _language = getattr(args, 'saved_prefs', {}).get('language', 'pl')
    def tr(value):
        return translate(value, _language)

    def tf(template, **values):
        return format_message(template, _language, **values)
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, simpledialog, filedialog
    except (ImportError, OSError) as exc:
        raise RuntimeError(f'Tkinter niedostępny: {exc}') from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError(f'Tk nie może połączyć się z ekranem X11/XWayland: {exc}') from exc

    class Window:
        def __init__(self):
            self.root = root
            root.title('xdg-audit · Audit' if _language=='en' else 'xdg-audit · Audyt konfiguracji')
            self.prefs = dict(getattr(args, 'saved_prefs', {}))
            try:
                self._icon_img = tk.PhotoImage(file=str(Path(__file__).with_name('assets') / 'xdg-audit.png'))
                root.iconphoto(True, self._icon_img)
            except (OSError, tk.TclError):
                pass
            root.geometry('1320x830')
            root.minsize(1020, 650)
            self.appearance = detect_appearance(home)
            self._style()
            self.items = []
            self.roots = engine.xdg_roots(home)
            self.stats = {}
            self.checked: set[str] = set()
            self.views = {}
            self.active_scope = args.scope
            self.busy = False
            self._quarantine_job_busy=False
            self._quarantine_callback=None
            self.scan_complete=False
            self.jobs = queue.Queue()
            self.query = tk.StringVar()
            self.filter_state = tk.StringVar(value='ALL')
            self.show_all = tk.BooleanVar(value=args.all)
            self.quick = tk.BooleanVar(value=args.quick)
            self.allow_uncertain = tk.BooleanVar(value=False)
            self.status = tk.StringVar(value=tr('Przygotowanie audytu…'))
            self.summary = tk.StringVar()
            self.selected_count = tk.StringVar(value=selected_count(0,_language))
            self.stat_values = {key: tk.StringVar(value='0') for key in STATES}
            self.visible_count = tk.StringVar(value=entries_count(0,_language))
            self._build()
            self.query.trace_add('write', lambda *_: self._refresh_tables())
            self.filter_state.trace_add('write', lambda *_: (self._update_metric_edges(),self._refresh_tables()))
            self.show_all.trace_add('write', lambda *_: self._refresh_tables())
            self.allow_uncertain.trace_add('write', lambda *_: self._refresh_tables())
            self.quick.trace_add('write', lambda *_: self.start_scan())
            root.after(60, self.poll)
            root.protocol('WM_DELETE_WINDOW', self.close)
            self.start_scan()

        def _style(self):
            style = ttk.Style(root)
            if 'clam' in style.theme_names():
                style.theme_use('clam')
            palette = self.appearance.kde_colors
            dark = self.appearance.scheme == 'dark'
            background = palette.get('window', (35, 37, 42) if dark else (245, 246, 248))
            foreground = palette.get('window_text', (235, 237, 241) if dark else (35, 39, 46))
            base = palette.get('base', (29, 31, 36) if dark else (255, 255, 255))
            text_color = palette.get('text', foreground)
            button_color = palette.get('button', background)
            accent = palette.get('highlight', self.appearance.accent or (99, 132, 184))
            selected_text = palette.get('highlight_text', (255, 255, 255))
            def hx(rgb): return '#%02x%02x%02x' % rgb
            def mix(a, b, strength):
                return tuple(round(x * (1 - strength) + y * strength) for x, y in zip(a,b))
            colors = {
                'bg': hx(background), 'fg':hx(foreground), 'base':hx(base),
                'text':hx(text_color), 'button':hx(button_color), 'accent':hx(accent),
                'line':hx(mix(background,foreground,.17)),
                'muted':hx(mix(foreground,background,.42)),
                'card':hx(mix(base,background,.12)),
                'softaccent':hx(mix(base,accent,.12)),
                'stripe':hx(mix(base,foreground,.035)),
            }
            self.colors = colors
            root.configure(bg=colors['bg'])
            style.configure('.', font=('Sans', 10), background=colors['bg'], foreground=colors['fg'])
            style.configure('TFrame', background=colors['bg'])
            style.configure('TLabel', background=colors['bg'], foreground=colors['fg'])
            style.configure('Hero.TLabel',font=('Sans', 21, 'bold'))
            style.configure('Subtitle.TLabel',font=('Sans', 10), foreground=colors['muted'])
            style.configure('Section.TLabel',font=('Sans', 11, 'bold'))
            style.configure('Muted.TLabel',font=('Sans', 9), foreground=colors['muted'])
            style.configure('TButton', background=colors['button'], foreground=colors['fg'], padding=(13,9))
            style.configure('Primary.TButton',background=colors['accent'], foreground=hx(selected_text),padding=(16,10))
            style.map('Primary.TButton',background=[('active',colors['accent'])])
            style.configure('TCheckbutton', background=colors['bg'], foreground=colors['fg'])
            style.configure('TNotebook', background=colors['bg'], borderwidth=0)
            style.configure('TNotebook.Tab', padding=(16,11), font=('Sans',10))
            style.configure('Treeview', background=colors['base'],fieldbackground=colors['base'],
                            foreground=colors['text'], rowheight=35, borderwidth=0, font=('Sans',10))
            style.map('Treeview', background=[('selected',colors['accent'])],
                      foreground=[('selected',hx(selected_text))])
            style.configure('Treeview.Heading', background=colors['button'],foreground=colors['fg'],
                            padding=(9,10),font=('Sans',10,'bold'))
            style.configure('TEntry', fieldbackground=colors['base'], foreground=colors['text'], padding=6)
            style.configure('TCombobox', fieldbackground=colors['base'], foreground=colors['text'],padding=5)
            style.configure('TSeparator',background=colors['line'])

        def _build(self):
            c = self.colors
            container = ttk.Frame(root,padding=(18,16))
            container.pack(fill='both',expand=True)

            # A short application header, with the desktop information outside
            # the task controls. Colours are derived from the detected palette.
            hero = ttk.Frame(container)
            hero.pack(fill='x',pady=(0,13))
            left = ttk.Frame(hero)
            left.pack(side='left',fill='x',expand=True)
            try:
                self._small_icon = tk.PhotoImage(file=str(Path(__file__).with_name('assets') / 'xdg-audit-128.png')).subsample(2,2)
                ttk.Label(left,image=self._small_icon).pack(side='left',padx=(0,12))
            except (OSError, tk.TclError):
                pass
            ttk.Label(left,text='xdg-audit',style='Hero.TLabel').pack(anchor='w')
            ttk.Label(left,text=tr('Audyt i bezpieczne porządki w katalogach użytkownika'),style='Subtitle.TLabel').pack(anchor='w',pady=(2,0))
            right = ttk.Frame(hero)
            right.pack(side='right')
            ttk.Label(right,text=f"{runtime['desktop']}  ·  {runtime['session']}  ·  {backend.upper()}",
                      style='Muted.TLabel').pack(anchor='e',pady=(3,1))
            ttk.Label(right,text=f"Styl: {self.appearance.source} · tryb: {self.appearance.scheme}",style='Muted.TLabel').pack(anchor='e')

            # Compact KPI cards double as clickable status filters.
            metrics=ttk.Frame(container)
            metrics.pack(fill='x',pady=(0,14))
            labels={'CANDIDATE':tr('Kandydaci'),'REVIEW':tr('Do sprawdzenia'),
                    'UNKNOWN':tr('Nieznane'),'ACTIVE':tr('Aktywne'),'PROTECTED':tr('Chronione')}
            self.metric_tiles={}
            for column,(key,caption) in enumerate(labels.items()):
                metrics.columnconfigure(column,weight=1,uniform='metric')
                tile=tk.Frame(metrics,bg=c['card'],highlightbackground=c['line'],
                              highlightthickness=1,cursor='hand2')
                tile.grid(row=0,column=column,sticky='ew',padx=(0,9) if column<4 else 0)
                self.metric_tiles[key]=tile
                number=tk.Label(tile,textvariable=self.stat_values[key],font=('Sans',19,'bold'),
                                fg=c['fg'],bg=c['card'],anchor='w',cursor='hand2')
                number.pack(fill='x',padx=14,pady=(9,0))
                label_widget=tk.Label(tile,text=caption,font=('Sans',9),fg=c['muted'],
                                      bg=c['card'],anchor='w',cursor='hand2')
                label_widget.pack(fill='x',padx=14,pady=(1,10))
                for widget in (tile,number,label_widget):
                    widget.bind('<Button-1>',lambda e,status=key: self._filter_metric(status))
                    widget.bind('<Enter>',lambda e,k=key: self._metric_hover(k, True))
                    widget.bind('<Leave>',lambda e,k=key: self._metric_hover(k, False))

            # Table toolbar: query, status and deliberate safe defaults.
            toolbar = ttk.Frame(container)
            toolbar.pack(fill='x',pady=(0,8))
            ttk.Label(toolbar,text=tr('Wyniki audytu'),style='Section.TLabel').pack(side='left')
            ttk.Label(toolbar,textvariable=self.visible_count,style='Muted.TLabel').pack(side='left',padx=(12,20))
            ttk.Button(toolbar,text=tr('⚙ Ustawienia'),command=self.open_settings).pack(side='right',padx=(8,0))
            self.scan_button=ttk.Button(toolbar,text='↻  '+tr('Skanuj ponownie'),command=self.start_scan)
            self.scan_button.pack(side='right')
            self.cancel_button=ttk.Button(toolbar,text='Anuluj skan',command=self.cancel_scan_action)
            self.cancel_button.pack(side='right',padx=(0,8))
            self.cancel_button.state(['disabled'])
            self.scan_progress=ttk.Progressbar(toolbar,mode='indeterminate',length=96)

            filters=ttk.Frame(container)
            filters.pack(fill='x',pady=(0,12))
            ttk.Label(filters,text='Szukaj').pack(side='left')
            ttk.Entry(filters,textvariable=self.query,width=31).pack(side='left',fill='x',expand=True,padx=(9,16))
            ttk.Label(filters,text=tr('Status')).pack(side='left')
            ttk.Combobox(filters,textvariable=self.filter_state,values=('ALL',*STATES),
                         width=13,state='readonly').pack(side='left',padx=(8,18))
            ttk.Checkbutton(filters,text=tr('Aktywne / chronione'),variable=self.show_all).pack(side='left',padx=(0,12))
            ttk.Checkbutton(filters,text=tr('Szybki skan'),variable=self.quick).pack(side='left')

            # Large results area and persistent inspector side-by-side.
            workspace=ttk.PanedWindow(container,orient='horizontal')
            workspace.pack(fill='both',expand=True)
            center=ttk.Frame(workspace)
            inspector=ttk.Frame(workspace,padding=(12,0,0,0))
            workspace.add(center,weight=4)
            self.workspace=workspace
            self.inspector=inspector

            self.tabs=ttk.Notebook(center)
            self.tabs.pack(fill='both',expand=True)
            for scope_label,scope in SCOPE_LABELS:
                tab=ttk.Frame(self.tabs,padding=(0,7))
                self.tabs.add(tab,text=tr(scope_label))
                table_frame=ttk.Frame(tab)
                table_frame.pack(fill='both',expand=True)
                tree=ttk.Treeview(table_frame,columns=('check','name','status','size','path'),
                                  show='headings',selectmode='browse',height=9)
                for name,title,width,stretch in [('check','✓',42,False),('name',tr('Nazwa'),170,True),
                         ('status',tr('Status'),105,False),('size',tr('Rozmiar'),85,False),('path',tr('Lokalizacja'),350,True)]:
                    tree.heading(name,text=title)
                    tree.column(name,width=width,stretch=stretch,
                                anchor='center' if name in ('check','size','status') else 'w')
                tree.tag_configure('stripe',background=c['stripe'])
                scroll=ttk.Scrollbar(table_frame,orient='vertical',command=tree.yview)
                tree.configure(yscrollcommand=scroll.set)
                tree.pack(side='left',fill='both',expand=True)
                scroll.pack(side='right',fill='y')
                tree.bind('<ButtonRelease-1>',lambda e,s=scope:self._clicked(e,s))
                tree.bind('<<TreeviewSelect>>',lambda e,s=scope:self._details_selected(s))
                self.views[scope]=tree
            quarantine_tab=ttk.Frame(self.tabs,padding=10)
            self.tabs.add(quarantine_tab,text=tr('Kwarantanna'))
            ttk.Label(quarantine_tab,text=tr('Historia bezpiecznych przeniesień'),
                      style='Section.TLabel').pack(anchor='w',pady=(0,3))
            ttk.Label(quarantine_tab,text=tr('Przywracanie nigdy nie nadpisuje istniejących plików.'),
                      style='Muted.TLabel').pack(anchor='w',pady=(0,10))
            self.qtree=ttk.Treeview(quarantine_tab,columns=('run','status','entries','moved'),show='headings',selectmode='browse')
            for name,title,width in [('run',tr('Identyfikator operacji'),270),('status',tr('Status operacji'),130),('entries',tr('W manifestie'),110),('moved',tr('Przeniesione'),135)]:
                self.qtree.heading(name,text=title);self.qtree.column(name,width=width)
            self.qtree.pack(fill='both',expand=True)
            qbuttons=ttk.Frame(quarantine_tab)
            qbuttons.pack(fill='x',pady=(10,0))
            ttk.Button(qbuttons,text=tr('Odśwież listę'),command=self._refresh_quarantine).pack(side='left')
            ttk.Button(qbuttons,text=tr('Pokaż zawartość'),command=self.quarantine_details).pack(side='left',padx=8)
            ttk.Button(qbuttons,text=tr('Przywróć operację…'),command=self.restore).pack(side='right')
            ttk.Button(qbuttons,text=tr('Usuń trwale…'),command=self.purge_quarantine).pack(side='right',padx=6)
            ttk.Button(qbuttons,text=tr('Sprawdź dostęp…'),
                       command=self.access_diagnostics).pack(side='right',padx=6)
            ttk.Button(qbuttons,text=tr('Zatwierdź stan…'),
                       command=self.adopt_inventory).pack(side='right',padx=6)
            ttk.Button(qbuttons,text=tr('Usuń wygasłe…'),command=self.purge_expired).pack(side='right',padx=6)
            ttk.Button(qbuttons,text=tr('Ustaw retencję…'),command=self.configure_retention).pack(side='right',padx=6)
            ttk.Button(qbuttons,text=tr('Usuń historię…'),command=self.cleanup_history).pack(side='right',padx=6)
            ttk.Button(qbuttons,text=tr('Wyczyść całą zakończoną historię…'),
                       command=self.cleanup_all_history).pack(side='right',padx=6)
            idx=next((i for i,(_,scope) in enumerate(SCOPE_LABELS) if scope==args.scope),0)
            self.tabs.select(idx)
            self.tabs.bind('<<NotebookTabChanged>>',self._on_tab_changed)

            inspect_top=ttk.Frame(inspector)
            inspect_top.pack(fill='x',pady=(3,12))
            ttk.Label(inspect_top,text=tr('Szczegóły wyboru'),style='Section.TLabel').pack(side='left')
            ttk.Button(inspect_top,text='✕',width=3,command=self.hide_inspector).pack(side='right')
            ttk.Separator(inspector).pack(fill='x',pady=(0,10))
            self.details=tk.Text(inspector,height=10,width=30,wrap='word',font=('Sans',10),
                                 bg=c['base'],fg=c['text'],relief='flat',padx=12,pady=12,
                                 highlightthickness=1,highlightbackground=c['line'])
            self.details.pack(fill='both',expand=True)
            self.details.configure(state='disabled')
            self.open_location_button=ttk.Button(inspector,text=tr('Otwórz lokalizację'),command=self.open_selected_location)
            self.open_location_button.pack(anchor='w',pady=(6,4))
            self.open_location_button.state(['disabled'])
            self.previewed_item=None
            ttk.Label(inspector,text=tr('CANDIDATE to sugestia, nie dowód. REVIEW i UNKNOWN wymagają dodatkowej zgody.'),
                      style='Muted.TLabel',wraplength=255).pack(anchor='w',pady=(11,2))

            # Persistent actions and descriptive, unobtrusive status bar.
            action_divider=ttk.Separator(container)
            action_divider.pack(fill='x',pady=(13,11))
            actions=ttk.Frame(container)
            actions.pack(fill='x')
            ttk.Button(actions,text=tr('Zaznacz kandydatów'),command=self.select_candidates).pack(side='left')
            ttk.Button(actions,text=tr('Odznacz'),command=self.clear_selection).pack(side='left',padx=8)
            ttk.Checkbutton(actions,text=tr('Zezwól na REVIEW / UNKNOWN'),variable=self.allow_uncertain).pack(side='left',padx=(14,0))
            self.move_button=ttk.Button(actions,text=tr('Przenieś do kwarantanny…'),
                                        style='Primary.TButton',command=self.move)
            self.move_button.pack(side='right')
            ttk.Button(actions,text=tr('Eksport JSON…'),command=self.export).pack(side='right',padx=(0,9))
            ttk.Button(actions,text='Porównaj raport…' if _language=='pl' else 'Compare report…',command=self.compare_report_gui).pack(side='right',padx=(0,9))
            ttk.Label(actions,textvariable=self.selected_count,style='Muted.TLabel').pack(side='right',padx=(0,16))
            statusbar=ttk.Frame(container)
            statusbar.pack(fill='x',pady=(10,0))
            ttk.Label(statusbar,textvariable=self.status,style='Muted.TLabel').pack(side='left')
            ttk.Label(statusbar,text=tr('Tylko przenoszenie · wymaga MOVE · możliwe przywrócenie'),
                      style='Muted.TLabel').pack(side='right')

            # Reserve the action bar first. The resizable table must not push
            # destructive-action confirmations below the bottom of the window.
            workspace.pack_forget()
            action_divider.pack_forget()
            actions.pack_forget()
            statusbar.pack_forget()
            statusbar.pack(side='bottom',fill='x',pady=(10,0))
            actions.pack(side='bottom',fill='x')
            action_divider.pack(side='bottom',fill='x',pady=(13,11))
            workspace.pack(side='top',fill='both',expand=True)

        def _update_metric_edges(self):
            active=self.filter_state.get()
            for key,tile in self.metric_tiles.items():
                tile.configure(highlightthickness=2 if key==active else 1,
                               highlightbackground=self.colors['accent'] if key==active else self.colors['line'])

        def _metric_hover(self,key,enter):
            if key != self.filter_state.get():
                self.metric_tiles[key].configure(highlightbackground=self.colors['accent'] if enter else self.colors['line'])

        def _filter_metric(self,status):
            if status in {'ACTIVE','PROTECTED'}:
                self.show_all.set(True)
            self.filter_state.set(status)

        def hide_inspector(self):
            if str(self.inspector) in self.workspace.panes():
                self.workspace.forget(self.inspector)

        def _set_details(self,text):
            if not text:
                self.hide_inspector();return
            self.details.configure(state='normal')
            self.details.delete('1.0','end')
            self.details.insert('end',text)
            self.details.configure(state='disabled')
            if str(self.inspector) not in self.workspace.panes():
                self.workspace.add(self.inspector,weight=1)

        def _on_tab_changed(self,_=None):
            self.hide_inspector()
            selected = self.tabs.index(self.tabs.select())
            if selected < len(SCOPE_LABELS):
                self.active_scope = SCOPE_LABELS[selected][1]
                self._refresh_tables()
            else:
                self.move_button.state(['disabled'])
                self._refresh_quarantine()

        def _eligible(self,item):
            if not self.scan_complete:return False
            return not item.protected and (item.state=='CANDIDATE' or
                   (self.allow_uncertain.get() and item.state in {'REVIEW','UNKNOWN'}))

        def _clicked(self,event,scope):
            tree = self.views[scope]
            if tree.identify_column(event.x) != '#1':
                return
            path = tree.identify_row(event.y)
            if not path:
                return
            item = next((it for it in self.items if str(it.path)==path),None)
            if not item or not self._eligible(item):
                return
            if path in self.checked: self.checked.remove(path)
            else: self.checked.add(path)
            self._refresh_tables()
            self._show_checked_details()

        def open_selected_location(self):
            if self.previewed_item is None:
                return
            try:
                open_item_location(self.previewed_item.path, home)
            except (OSError, RuntimeError, ValueError) as exc:
                self.status.set(str(exc))

        def _show_checked_details(self,focused=None):
            chosen=[it for it in self.items if str(it.path) in self.checked]
            self.previewed_item=focused if focused is not None else (chosen[0] if len(chosen)==1 else None)
            self.open_location_button.state(['!disabled'] if self.previewed_item else ['disabled'])
            self._set_details(details_text(chosen,engine.human,focused,language=_language))

        def _details_selected(self,scope):
            choice = self.views[scope].selection()
            if choice:
                item = next((it for it in self.items if str(it.path)==choice[0]),None)
                if item:
                    self._show_checked_details(item)

        def open_settings(self):
            from xdg_prefs import load, save, validate, parse_alias_lines, format_aliases, SCOPES
            current, warning = load(home,engine.xdg_roots(home))
            dialog=tk.Toplevel(root)
            dialog.title(tr('Ustawienia xdg-audit'))
            dialog.geometry('600x550')
            dialog.transient(root)
            dialog.grab_set()
            frame=ttk.Frame(dialog,padding=18);frame.pack(fill='both',expand=True)
            ttk.Label(frame,text=tr('Zakres przy starcie')).pack(anchor='w')
            scope=tk.StringVar(value=current['startup_scope'])
            ttk.Combobox(frame,textvariable=scope,values=SCOPES,state='readonly').pack(fill='x',pady=(3,12))
            quick=tk.BooleanVar(value=current['quick_scan'])
            ttk.Checkbutton(frame,text=tr('Szybki skan (bez rozmiarów)'),variable=quick).pack(anchor='w')
            show=tk.BooleanVar(value=current['show_active'])
            ttk.Checkbutton(frame,text=tr('Pokazuj aktywne i chronione'),variable=show).pack(anchor='w',pady=(0,12))
            ttk.Label(frame,text=tr('Zachowaj — jedna nazwa katalogu w linii')).pack(anchor='w')
            keep=tk.Text(frame,height=5)
            keep.pack(fill='x'); keep.insert('1.0','\n'.join(current['keep']))
            ttk.Label(frame,text=tr('Język / Language')).pack(anchor='w',pady=(10,0))
            language=tk.StringVar(value='English' if current.get('language')=='en' else 'Polski')
            ttk.Combobox(frame,textvariable=language,values=('Polski', 'English'),state='readonly').pack(fill='x',pady=(3,8))
            ttk.Label(frame,text=tr('Alias — katalog=wzorzec')).pack(anchor='w',pady=(10,0))
            alias=tk.Text(frame,height=5)
            alias.pack(fill='x');alias.insert('1.0',format_aliases(current['aliases']))
            feedback=tk.StringVar(value=warning or tr('Zapis dopiero po kliknięciu Zapisz.'))
            ttk.Label(frame,textvariable=feedback,wraplength=530).pack(fill='x',pady=(10,6))
            actions=ttk.Frame(frame);actions.pack(fill='x')
            ttk.Button(actions,text=tr('Anuluj'),command=dialog.destroy).pack(side='right')
            def commit():
                try:
                    new=validate({'startup_scope':scope.get(),
                         'quick_scan':quick.get(), 'show_active':show.get(), 'language':'en' if language.get()=='English' else 'pl',
                         'keep':[x.strip() for x in keep.get('1.0','end').splitlines() if x.strip()],
                         'aliases':parse_alias_lines(alias.get('1.0','end'))})
                    save(home,new,engine.xdg_roots(home))
                except (OSError,ValueError) as exc:
                    feedback.set(tf('Błąd: {error}',error=exc));return
                from xdg_prefs import scan_inputs_changed
                needs_scan=scan_inputs_changed(current,new)
                self.prefs=new
                args.keep=list(new['keep'])
                aliases.clear();aliases.update(new['aliases'])
                args.quick=new['quick_scan']
                args.all=new['show_active']
                if self.show_all.get() != args.all:
                    self.show_all.set(args.all)
                dialog.destroy()
                if new['language'] != current['language']:
                    self.apply_language(new['language'])
                if needs_scan:
                    # quick_scan can already trigger a scan via its variable trace
                    # if its value changes. Avoid starting the same scan twice.
                    if self.quick.get() != new['quick_scan']:
                        self.quick.set(new['quick_scan'])
                    else:
                        self.start_scan()
                else:
                    self.status.set('Settings saved. Scan results preserved.' if new['language']=='en'
                                    else 'Ustawienia zapisane. Wyniki audytu zachowane.')
            ttk.Button(actions,text=tr('Zapisz'),command=commit).pack(side='right',padx=(0,8))

        def apply_language(self, language: str):
            """Apply translation to existing Tk widgets without rebuilding scans."""
            nonlocal _language
            old=_language
            if old==language:return
            _language=language
            self.prefs['language']=language
            root.title('xdg-audit · Audit' if language=='en' else 'xdg-audit · Audyt konfiguracji')
            def walk(widget):
                try:
                    current=widget.cget('text')
                    updated=translate_ui_text(current,old,language)
                    if updated!=current:widget.configure(text=updated)
                except (tk.TclError,AttributeError,TypeError):
                    pass
                for child in widget.winfo_children():walk(child)
            walk(root)
            for index,(title,scope) in enumerate(SCOPE_LABELS):
                self.tabs.tab(index,text=tr(title))
            self.tabs.tab(len(SCOPE_LABELS),text=tr('Kwarantanna'))
            for tree in self.views.values():
                for name,title in [('name','Nazwa'),('status','Status'),
                                   ('size','Rozmiar'),('path','Lokalizacja')]:
                    tree.heading(name,text=tr(title))
            for name,title in [('run','Identyfikator operacji'), ('entries','W manifestie'), ('moved','Przeniesione')]:
                self.qtree.heading(name,text=tr(title))
            self.scan_button.configure(text='↻  '+tr('Skanuj ponownie'))
            # Language-only switch updates existing controls. Preserve cached
            # rows, active sort/scroll position, selection and filesystem data.
            self.visible_count.set(entries_count(sum(1 for _ in self._visible(self.active_scope)), _language)
                                   if self.active_scope!='quarantine' else tr('Historia operacji'))
            self.selected_count.set(selected_count(len(self.checked), _language))
            self.status.set(tr('Skanowanie wszystkich lokalizacji — bez zapisywania zmian…') if self.busy
                            else (f'Scanned {len(self.items)} entries. No changes.' if language=='en'
                                  else f'Zbadano {len(self.items)} pozycji. Żadnych zmian.'))
            if self.inspector.winfo_manager():self._show_checked_details()

        def cancel_scan_action(self):
            if self.busy:
                self.cancel_scan.set()
                self.status.set(tr('Anulowanie skanowania po bieżącym etapie…'))

        def start_scan(self):
            if self.busy:
                return
            self.busy = True
            self.scan_complete=False
            self.cancel_scan=threading.Event()
            self.cancel_button.state(['!disabled'])
            self.scan_progress.pack(side='right',padx=(0,8))
            self.scan_progress.start(90)
            self.items = []
            self.checked.clear()
            self._refresh_tables()
            self.scan_button.state(['disabled'])
            self.move_button.state(['disabled'])
            self.status.set(tr('Skanowanie wszystkich lokalizacji — bez zapisywania zmian…'))
            quick = self.quick.get()
            def worker():
                try:
                    # Always scan everything once; Notebook tabs filter the result.
                    result = engine.scan(home,list(engine.SCOPES),{engine.normalize(x) for x in args.keep},aliases,quick,
                        progress=lambda stage: self.jobs.put(('phase', stage)),
                        on_batch=lambda phase, items, done, total: self.jobs.put(
                            ('batch',(phase,items,done,total))),
                        cancelled=self.cancel_scan.is_set)
                    self.jobs.put(('scan',result))
                except engine.ScanCancelled:
                    self.jobs.put(('cancelled','Skanowanie anulowano.'))
                except Exception as exc:
                    self.jobs.put(('error',str(exc)))
            threading.Thread(target=worker,daemon=True).start()

        def poll(self):
            try:
                while True:
                    kind,result = self.jobs.get_nowait()
                    if kind == 'quarantine-job':
                        self._quarantine_job_busy=False
                        callback=self._quarantine_callback
                        self._quarantine_callback=None
                        if callback is not None:
                            try:
                                callback(*result)
                            except Exception as exc:
                                self.status.set(tf('Błąd operacji kwarantanny: {error}',error=exc))
                        continue
                    if kind == 'phase':
                        self.status.set(('Scanning: ' if _language=='en' else 'Skanowanie: ') + tr(result))
                        continue
                    if kind == 'batch':
                        phase, entries, done, total = result
                        if phase == 'classified':
                            self.items = list(entries)
                            self._refresh_tables()
                        elif phase == 'sizes':
                            self._refresh_tables()
                            self.status.set((f'Calculating sizes: {done}/{total}' if _language=='en' else f'Obliczanie rozmiarów: {done}/{total}'))
                        continue
                    self.busy = False
                    self.scan_button.state(['!disabled'])
                    self.cancel_button.state(['disabled'])
                    self.scan_progress.stop()
                    self.scan_progress.pack_forget()
                    self.move_button.state(['!disabled'])
                    if kind=='scan':
                        self.scan_complete=True
                        self.items,self.roots,self.stats = result
                        self.checked.clear()
                        self.hide_inspector()
                        self._refresh_tables()
                        self._refresh_quarantine()
                        self.status.set((f'Scan completed: {len(self.items)} entries. No files changed.' if _language=='en' else f'Skan ukończony: {len(self.items)} pozycji. Żadnych zmian w plikach.'))
                    elif kind=='cancelled':
                        self.scan_complete=False
                        self.checked.clear()
                        self.move_button.state(['disabled'])
                        self.status.set(result)
                    else:
                        self.status.set(tr('Błąd skanowania'))
                        messagebox.showerror(tr('Błąd skanowania'),result,parent=root)
            except queue.Empty:
                pass
            root.after(90,self.poll)

        def _visible(self,scope):
            q = self.query.get().strip().casefold()
            state = self.filter_state.get()
            for item in self.items:
                if scope != 'all' and item.scope != scope: continue
                if not self.show_all.get() and item.state in {'ACTIVE','PROTECTED'}: continue
                if state != 'ALL' and item.state != state: continue
                if q and q not in (' '.join([str(item.path),item.scope,item.state,*item.reasons])).casefold():
                    continue
                yield item

        def _refresh_tables(self):
            if not self.views: return
            lookup = {str(it.path):it for it in self.items}
            self.checked = {p for p in self.checked if p in lookup and self._eligible(lookup[p])}
            for scope,tree in self.views.items():
                # Rebuild only on scan/filter updates, preserve scroll and selection.
                old = tree.yview()
                focused = tree.selection()
                tree.delete(*tree.get_children(''))
                tree_index=0
                for item in self._visible(scope):
                    path = str(item.path)
                    mark = ('☑' if path in self.checked else '☐') if self._eligible(item) else '—'
                    tree.insert('', 'end', iid=path,values=(mark,item.path.name,item.state,engine.human(item.bytes),str(item.path.parent)), tags=('stripe',) if tree_index%2 else ())
                    tree_index+=1
                if focused and tree.exists(focused[0]):tree.selection_set(focused[0])
                if old: tree.yview_moveto(old[0])
            counts = {state:sum(it.state==state for it in self.items) for state in STATES}
            for s,v in counts.items(): self.stat_values[s].set(str(v))
            self.visible_count.set(entries_count(sum(1 for _ in self._visible(self.active_scope)),_language) if self.active_scope!='quarantine' else ('Operations history' if _language=='en' else 'Historia operacji'))
            self.selected_count.set(selected_count(len(self.checked),_language))
            quarantine_active=self.tabs.index(self.tabs.select()) >= len(SCOPE_LABELS)
            self.move_button.state(['!disabled'] if self.checked and not self.busy and not quarantine_active else ['disabled'])

        def select_candidates(self):
            if not self.scan_complete:return
            scope = self.active_scope
            self.checked.update(str(it.path) for it in self._visible(scope) if it.state=='CANDIDATE')
            self._refresh_tables()
            self._show_checked_details()

        def clear_selection(self):
            self.checked.clear()
            self._refresh_tables()
            self.hide_inspector()

        def move(self):
            if self.busy or not self.checked:return
            chosen = [item for item in self.items if str(item.path) in self.checked and self._eligible(item)]
            if not chosen:return
            uncertain = [it for it in chosen if it.state != 'CANDIDATE']
            lines = '\n'.join(f'{it.state}  {engine.human(it.bytes)}  {it.path}' for it in chosen[:20])
            if len(chosen)>20: lines += '\n'+tf('… oraz {count} innych',count=len(chosen)-20)
            total = engine.human(sum(it.bytes for it in chosen))
            if not messagebox.askyesno(tr('Plan kwarantanny'),tf('Przenieść {count} ({size})?',count=entries_count(len(chosen),_language),size=total)+'\n\n'+lines+'\n\n'+tr('Dane nie zostaną trwale usunięte.'),parent=root):
                return
            if uncertain:
                msg = tf('{count} pozycji ma status REVIEW/UNKNOWN. Wpisz UNCERTAIN:',count=len(uncertain))
                if simpledialog.askstring(tr('Niepewne dane'),msg,parent=root)!='UNCERTAIN':return
            if simpledialog.askstring(tr('Potwierdzenie'),tr('Zamknij powiązane aplikacje. Wpisz MOVE, aby przenieść:'),parent=root)!='MOVE':return
            notes=[]
            try:
                result=engine.commit_quarantine(chosen,self.roots,home,allow_uncertain=bool(uncertain),emit=notes.append,extra_aliases=aliases,keep_names=args.keep)
                message=tf('Operacja {run_id}',run_id=result['run_id'])+'\n'+tf('Przeniesiono {moved}/{total}.',moved=len(result['moved']),total=len(chosen))
                if any('purge inventory unavailable' in line for line in notes):
                    messagebox.showwarning(tr('Kwarantanna'),message+'\n\n'+
                        tr('Pliki przeniesiono, ale nie można było sprawdzić całej zawartości. Przed PURGE użyj „Sprawdź dostęp…”, następnie osobno „Zatwierdź stan…” (ADOPT).'),parent=root)
                else:
                    messagebox.showinfo(tr('Kwarantanna'),message,parent=root)
            except (ValueError, OSError, SystemExit) as exc:
                messagebox.showerror(tr('Błąd'),str(exc),parent=root)
            self.start_scan()

        def compare_report_gui(self):
            if not self.scan_complete:return
            from tkinter import filedialog
            from xdg_history import summary
            path=filedialog.askopenfilename(parent=root,title=tr('Wybierz wcześniejszy raport'),
                                            filetypes=[('JSON','*.json')])
            if not path:return
            try:
                diffs=engine.compare_report(self.items,Path(path),list(engine.SCOPES))
                content=summary(diffs,_language)
            except (OSError,SystemExit,ValueError) as exc:
                messagebox.showerror(tr('Błąd porównania'),str(exc),parent=root);return
            dialog=tk.Toplevel(root);dialog.title(tr('Porównanie raportów'))
            dialog.geometry('720x490')
            textbox=tk.Text(dialog,wrap='word')
            textbox.pack(fill='both',expand=True,padx=12,pady=12)
            textbox.insert('1.0',content);textbox.configure(state='disabled')
            ttk.Button(dialog,text='Close' if _language=='en' else 'Zamknij',command=dialog.destroy).pack(pady=(0,10))

        def export(self):
            from xdg_history import suggested_export_path
            file=filedialog.asksaveasfilename(parent=root,initialfile=suggested_export_path(home).name,defaultextension='.json',filetypes=[('JSON','*.json')])
            if not file:return
            data={'version':engine.VERSION,'scopes':list(engine.SCOPES),'stats':self.stats,'entries':[x.json() for x in self.items]}
            try:
                with Path(file).open('x',encoding='utf-8') as stream:
                    json.dump(data,stream,ensure_ascii=False,indent=2)
                self.status.set(tf('Wyeksportowano raport: {path}',path=file))
            except OSError as exc:messagebox.showerror(tr('Błąd zapisu'),str(exc),parent=root)

        def _refresh_quarantine(self):
            self.qtree.delete(*self.qtree.get_children(''))
            for run in engine.quarantine_runs(home,engine.xdg_roots(home)):
                self.qtree.insert('','end',iid=run['run_id'],
                                  values=(run['run_id'],tr(run['status']),
                                          len(run['items']),run['moved']))

        def quarantine_details(self):
            row=self.qtree.selection()
            if not row:return
            match=next((x for x in engine.quarantine_runs(home,engine.xdg_roots(home)) if x['run_id']==row[0]),None)
            if not match:return
            text='\n'.join(f"{it.get('move_status','?')}: {it.get('source','?')}" for it in match['items'])
            self._set_details(text or tr('(pusty manifest)'))

        def restore(self):
            row=self.qtree.selection()
            if not row:return
            if self.qtree.set(row[0], 'status') in ('PURGED','RESTORED','COMPLETED'):
                messagebox.showinfo(tr('Historia'),
                    tr('Ta operacja jest zakończona. Użyj opcji Usuń historię.'),parent=root)
                return
            run_id=row[0]
            if not messagebox.askyesno(tr('Przywracanie'),tf('Przywrócić dane z operacji {run_id}?',run_id=run_id)+'\n'+tr('Istniejące pliki nie zostaną nadpisane.'),parent=root):return
            if simpledialog.askstring(tr('Potwierdzenie'),tr('Wpisz RESTORE:'),parent=root)!='RESTORE':return
            notes=[]
            try:
                result=engine.restore_quarantine_run(home,engine.xdg_roots(home),run_id,emit=notes.append)
                messagebox.showinfo(tr('Przywracanie'),tf('Przywrócono: {count}',count=result['restored'])+'\n'+tf('Pominięto: {count}',count=result['skipped']),parent=root)
            except (ValueError,OSError,KeyError) as exc:messagebox.showerror(tr('Błąd'),str(exc),parent=root)
            self.start_scan()

        def _quarantine_job(self, operation, callback, activity):
            if self._quarantine_job_busy:
                self.status.set(tr('Operacja kwarantanny jest już wykonywana.'))
                return
            self._quarantine_job_busy=True
            self._quarantine_callback=callback
            self.status.set(tr(activity))
            run_gui_job(operation, lambda *_:None,
                        lambda _cb, ok, value:self.jobs.put(
                            ('quarantine-job',(ok,value))))

        def cleanup_all_history(self):
            def done(ok, result):
                if not ok:
                    messagebox.showerror(tr('Historia'),str(result),parent=root)
                elif result:
                    self._cleanup_history_runs(result)
                else:
                    messagebox.showinfo(tr('Historia'),
                        tr('Brak zakończonych operacji do wyczyszczenia. Aktywne i niedokończone pozostają chronione.'),
                        parent=root)
            self._quarantine_job(
                lambda:engine.completed_quarantine_history(home,engine.xdg_roots(home)),
                done,'Sprawdzanie historii…')

        def cleanup_expired_history(self):
            def done(ok, result):
                if not ok:
                    messagebox.showerror(tr('Historia'),str(result),parent=root)
                elif result:
                    self._cleanup_history_runs(result)
                else:
                    messagebox.showinfo(tr('Historia'),tr('Brak wygasłych manifestów.'),parent=root)
            self._quarantine_job(
                lambda:engine.expired_quarantine_history(home,engine.xdg_roots(home)),
                done,'Sprawdzanie historii…')

        def cleanup_history(self):
            selected=self.qtree.selection()
            if selected:
                self._cleanup_history_runs([selected[0]])

        def _cleanup_history_runs(self,ids):
            ids=tuple(ids)
            def preview_ready(ok, result):
                if not ok:
                    messagebox.showerror(tr('Historia'),str(result),parent=root)
                    return
                summary='\\n'.join(p['run_id']+' ('+p['status']+')' for p in result)
                if not messagebox.askyesno(tr('Usuń historię'),
                    summary+'\\n\\n'+tr('Zostaną usunięte tylko zakończone dzienniki.'),
                    parent=root):
                    return
                if simpledialog.askstring(tr('Potwierdzenie'),tr('Wpisz HISTORY:'),
                                          parent=root) != 'HISTORY':
                    return
                def execute():
                    for plan in result:
                        engine.cleanup_quarantine_history(
                            home,engine.xdg_roots(home),plan['run_id'],dry_run=False)
                    return len(result)
                def done(success, outcome):
                    self._refresh_quarantine()
                    if success:
                        self.status.set(tr('Usunięto zakończone manifesty.'))
                    else:
                        messagebox.showerror(tr('Historia'),str(outcome),parent=root)
                self._quarantine_job(execute,done,'Usuwanie historii…')
            self._quarantine_job(
                lambda:[engine.cleanup_quarantine_history(
                    home,engine.xdg_roots(home),rid) for rid in ids],
                preview_ready,'Sprawdzanie historii…')

        def configure_retention(self):
            from xdg_retention import load, save
            try:
                current=load(home,engine.xdg_roots(home))
                days=simpledialog.askinteger(tr('Retencja'),tr('Dni przechowywania:'),
                                             initialvalue=current['days'],minvalue=1,
                                             maxvalue=3650,parent=root)
                if days is not None:
                    current['days']=days
                    save(home,engine.xdg_roots(home),current)
                    self.status.set(tf('Ustawiono retencję: {days} dni',days=days))
            except (ValueError,OSError) as exc:
                messagebox.showerror(tr('Retencja'),
                    tf('Nie można zapisać retencji: {error}',error=exc),parent=root)

        def adopt_inventory(self, run_id=None, resume_purge=False):
            if run_id is None:
                selected=self.qtree.selection()
                if not selected:return
                run_id=selected[0]
            message=(tf('Operacja: {run_id}',run_id=run_id)+'\n'+
                tr('Zatwierdzisz stan plików widoczny TERAZ. Nie oznacza to, że zawartość jest identyczna jak w dniu przeniesienia. PURGE nadal wymaga osobnej zgody.'))
            if not messagebox.askyesno(tr('Zatwierdź aktualny stan'),message,parent=root):return
            if simpledialog.askstring(tr('Zatwierdź aktualny stan'),tr('Wpisz ADOPT:'),parent=root)!='ADOPT':return
            def done(ok,result):
                if not ok:
                    messagebox.showerror(tr('Zatwierdź aktualny stan'),str(result),parent=root)
                else:
                    self._refresh_quarantine()
                    if resume_purge:
                        self._purge_runs([run_id])
                    else:
                        messagebox.showinfo(tr('Zatwierdź aktualny stan'),
                            tf('Zatwierdzono aktualny stan: {count} obiektów.',count=result['adopted'])+
                            '\n'+tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'),
                            parent=root)
            self._quarantine_job(
                lambda:engine.adopt_quarantine_inventory(
                    home,engine.xdg_roots(home),run_id),
                done,'Weryfikacja kwarantanny')

        def access_diagnostics(self,run_id=None, resume_purge=False, repaired=False):
            if run_id is None:
                selected=self.qtree.selection()
                if not selected:return
                run_id=selected[0]
            def finish(ok, report):
                if not ok:
                    messagebox.showerror(tr('Diagnostyka dostępu'),str(report),parent=root)
                    return
                issues=report['issues']
                if not issues:
                    if resume_purge and (repaired or report['unsealed']):
                        if report['unsealed']:
                            self.adopt_inventory(run_id, resume_purge=True)
                        else:
                            self._purge_runs([run_id])
                        return
                    note=tr('Nie znaleziono problemów z odczytem. Sprawdź pozostałe komunikaty PURGE.')
                    if report['unsealed']:
                        note+='\n'+tr('Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).')
                    messagebox.showinfo(tr('Diagnostyka dostępu'),note,parent=root)
                    return
                issue=issues[0]
                msg=(tf('Użytkownik: {user}',user=report['identity']['user'])+
                     '\n'+tf('pkexec zainstalowany: {state}',
                               state=tr('tak') if report['identity']['pkexec_installed'] else tr('nie'))+
                     '\n'+tf('Problem: {code}',code=issue['code'])+
                     '\n'+issue['path']+'\n'+
                     tf('Uprawnienia: {mode}',mode=issue['mode']))
                if not issue['repairable']:
                    messagebox.showwarning(tr('Diagnostyka dostępu'),msg+'\n'+
                        tr('Nie można automatycznie naprawić. Nie podnoszę uprawnień ani nie omijam kontroli PURGE.')+
                        '\n'+tr('Naprawa tego obiektu wymaga dodatkowej analizy. Zasady Polkit określa system; xdg-audit nie uruchamia kodu użytkownika jako root.'),
                        parent=root)
                    return
                msg+='\n'+tf('Proponowana zmiana: {before} → {after}',
                              before=issue['mode'],after=issue['suggested_mode'])
                msg+='\n'+tr('Zmienię tylko wskazane uprawnienia właściciela w kwarantannie. Bez sudo i bez usuwania plików.')
                if not messagebox.askyesno(tr('Napraw dostęp'),msg,parent=root):return
                if simpledialog.askstring(tr('Napraw dostęp'),tr('Wpisz ACCESS:'),
                                          parent=root) != 'ACCESS':return
                def done(success,outcome):
                    if not success:
                        messagebox.showerror(tr('Napraw dostęp'),str(outcome),parent=root)
                        return
                    note=(tf('Zmieniono uprawnienia: {before} → {after}',
                             before=outcome['old_mode'],after=outcome['new_mode'])+
                          '\n'+tr('Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.'))
                    if report['unsealed']:
                        note+='\n'+tr('Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).')
                    if resume_purge:
                        self.access_diagnostics(run_id, resume_purge=True, repaired=True)
                    else:
                        messagebox.showinfo(tr('Napraw dostęp'),note,parent=root)
                self._quarantine_job(
                    lambda:engine.repair_quarantine_access(
                        home,engine.xdg_roots(home),run_id,issue['relative']),
                    done,'Naprawianie dostępu…')
            self._quarantine_job(
                lambda:engine.diagnose_quarantine_access(
                    home,engine.xdg_roots(home),run_id),
                finish,'Sprawdzanie dostępu…')

        def purge_expired(self):
            def done(ok, result):
                if not ok:
                    messagebox.showerror(tr('Kwarantanna'),str(result),parent=root)
                elif result:
                    self._purge_runs(result)
                else:
                    messagebox.showinfo(tr('Kwarantanna'),tr('Nie ma wygasłych operacji.'),parent=root)
            self._quarantine_job(
                lambda:engine.expired_quarantine_runs(home,engine.xdg_roots(home)),
                done,'Sprawdzanie kwarantanny…')

        def purge_quarantine(self):
            selected=self.qtree.selection()
            if selected:
                if self.qtree.set(selected[0], 'status') in ('PURGED','RESTORED','COMPLETED'):
                    messagebox.showinfo(tr('Historia'),
                        tr('Ta operacja jest zakończona. Użyj opcji Usuń historię.'),parent=root)
                    return
                self._purge_runs([selected[0]])

        def _purge_runs(self,run_ids):
            run_ids=tuple(run_ids)
            def preview_ready(ok, result):
                if not ok:
                    messagebox.showerror(tr('Zablokowano PURGE'),str(result),parent=root)
                    if len(run_ids)==1 and engine.quarantine_access_recoverable_error(result):
                        self.access_diagnostics(run_ids[0], resume_purge=True)
                    return
                details='\\n'.join(
                    str(p['run_id'])+': '+str(p['objects'])+' entries / '+str(p['bytes'])+' B'
                    for p in result)
                if not messagebox.askyesno(tr('Trwałe usunięcie'),
                        details+'\\n\\n'+tr('Ta operacja jest nieodwracalna. Kontynuować?'),
                        parent=root):
                    return
                if simpledialog.askstring(tr('Potwierdzenie'),tr('Wpisz PURGE:'),parent=root)!='PURGE':
                    return
                def execute():
                    deleted=0
                    for plan in result:
                        deleted+=engine.purge_quarantine_run(
                            home,engine.xdg_roots(home),plan['run_id'],
                            dry_run=False)['objects']
                    return deleted
                def done(success, outcome):
                    self._refresh_quarantine()
                    if success:
                        messagebox.showinfo(tr('Kwarantanna'),
                            tr('Usunięto obiektów: ')+str(outcome),parent=root)
                    else:
                        messagebox.showerror(tr('Zablokowano PURGE'),str(outcome),parent=root)
                self._quarantine_job(execute,done,'Trwałe usuwanie z kwarantanny…')
            self._quarantine_job(
                lambda:[engine.purge_quarantine_run(
                    home,engine.xdg_roots(home),run_id) for run_id in run_ids],
                preview_ready,'Sprawdzanie kwarantanny…')

        def close(self):
            if self.busy and not messagebox.askyesno(tr('Skanowanie'),tr('Skanowanie trwa. Zamknąć okno?'),parent=root):return
            root.destroy()

    Window()
    root.mainloop()
    return 0
