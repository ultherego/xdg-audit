# xdg-audit 1.7.0-dev

Natywny, ostrożny audyt pozostałości po aplikacjach na Linuksie (szczególnie Arch/CachyOS). Python 3.10+, bez obowiązkowej instalacji bibliotek GUI i bez przeglądarki. **Bez parametrów uruchamia GUI** przez pierwszy już dostępny i zgodny z pulpitem backend: KDE/LXQt preferują Qt6; GNOME/Niri i inne — GTK4/GTK3; Tk to wariant awaryjny w X11/XWayland. Jeśli GUI nie jest dostępne, CLI działa samodzielnie. Program nie instaluje zależności, nie zmienia ustawień pulpitu i nie używa `sudo`.

## Uruchomienie

Po rozpakowaniu ZIP do pustego katalogu:

```sh
python3 xdg_audit.py                   # natywne GUI
python3 xdg_audit.py --theme-info      # diagnostyka motywu i backendu
python3 xdg_audit.py --scope all       # tylko CLI, bez modyfikacji
python3 xdg_audit.py --scope config --json > before.json
python3 xdg_audit.py --scope config --compare before.json
python3 xdg_audit.py --list-quarantine
python3 xdg_audit.py --restore RUN_ID  # jawne potwierdzenie RESTORE
```

W GUI: **Ustawienia → Język / Language → Polski lub English → Zapisz**. Nowy język interfejsu jest stosowany **od razu po zapisaniu**, bez zamykania okna, ponownego uruchamiania programu ani skanowania dysku. W GTK naprawiono wcześniejszy błąd `NameError: appearance is not defined`, który blokował odświeżenie całego głównego okna. Język listy plików i danych systemowych pozostaje bez zmian; część komunikatów technicznych jest nadal dostępna tylko w języku oryginału. Skanowanie po zmianie aliasów i listy „Zachowaj” aktualizuje wyniki bez konieczności restartu. Techniczne identyfikatory stanów (`ACTIVE`, `UNKNOWN`, ...) pozostają wspólne dla obu języków. Część szczegółowych diagnostyk systemowych/komunikatów błędów zachowuje język oryginalnego źródła.

## Poprawki w 1.6.3

- **Ikona nagłówka**: na GTK4 zmieniono `Gtk.Image` na `Gtk.Picture` wyświetlający faktyczną grafikę 68 × 68 px. Wcześniej motyw GTK mógł ograniczać obraz do rozmiaru małej ikony, mimo większej przestrzeni wokół. W GTK3 i Qt6 grafika ma 68 px, w Tk 64 px.
- **Język w locie bez ponownego skanu**: zmiana tylko języka (`pl` ↔ `en`) aktualizuje istniejące etykiety, nagłówki i komunikaty, ale **nie wywołuje** skanowania. Nie resetuje listy, wyborów ani bieżącej zakładki.
- **Kiedy skan jest potrzebny?** Po zmianie `keep` (Zachowaj), aliasów lub `quick_scan`. `show_active` to tylko filtr; `startup_scope` zacznie działać przy następnym uruchomieniu.
- **GUI GTK3 i Tk**: aktualizacja języka bez odtwarzania całej tabeli wyników. **Qt6**: bez wymuszania ponownego nałożenia palety podczas zmiany języka.
- **Zgodność**: CLI, format raportów i manifesty kwarantanny nie uległy zmianie.

## Zmiany w 1.6.0

| Obszar | Działanie |
|---|---|
| Skanowanie przyrostowe | Po klasyfikacji wyniki trafiają od razu do GUI; rozmiary są obliczane później partiami i wyświetlane na bieżąco |
| Postęp | Widoczna nazwa etapu i postęp liczbowy tylko dla policzalnych partii `du`; brak fikcyjnych procentów całego skanu |
| Anulowanie | `Anuluj skan` sygnalizuje workerowi przerwanie między fazami i partiami `du`; rozpoczęty `du` może jeszcze potrwać |
| GTK4 | `Gtk.ColumnView` + `Gio.ListStore` + `Gtk.SortListModel`, własne komórki, natywne nagłówki/sortowanie oraz checkboxy |
| Qt6 | `QTableView` + `QAbstractTableModel` + `QSortFilterProxyModel`, sortowanie po rzeczywistym rozmiarze (nie tekstowe) |
| GTK3/Tk | Zachowane natywne fallbacki, w tym przyrostowy postęp i anulowanie; Tk korzysta z `ttk.Treeview` |
| Tłumaczenia | Ustawienia PL/EN we wszystkich GUI; teksty podstawowych kontrolek i panelu szczegółów |
| Ikona | Nagłówek używa miniatury 25–26 px, skalowanej w pamięci; duży plik ikony pozostaje dla docka/menu |
| Kwarantanna | Trwały manifest **przed** i **po** przeniesieniu (intencja `moving`, `moved`, `restoring`, `restored`), zapis przez plik tymczasowy + `os.replace` + `fsync` pliku i katalogów |
| Historia i porównanie | Eksport wersjonowanego JSON (na żądanie, bez nadpisania), wybór wcześniejszego pliku JSON w GUI i prezentacja zmian |
| Raport | Uzupełnione pola `evidence`, `risk_flags`, `schema_version` z zachowaniem starych `state/reasons` |
| Bezpieczeństwo skanu częściowego | Kwarantanna i wybór kandydatów w GUI pozostają niedostępne, dopóki pełny skan się nie zakończy |

## Kwarantanna — zasady

`CANDIDATE` nie jest dowodem, że aplikacja została usunięta. `REVIEW` i `UNKNOWN` wymagają dodatkowego `UNCERTAIN`; wszystkie operacje przenoszenia wymagają jawnego `MOVE`. `ACTIVE` oraz `PROTECTED` są zablokowane, a tuż przed przeniesieniem program ponownie sprawdza aktualnie zainstalowane pakiety, wzorce aliasów, wyjątki użytkownika, urządzenia, symlinki, mounty i tożsamość plików. **Nie ma automatycznego, bezpowrotnego kasowania.**

Kwarantanna: `~/.local/share/xdg-audit-quarantine/<RUN_ID>/`. Stare manifesty z wersji 1.1–1.5 nadal można odczytać i przywrócić. Nowe manifesty mają trwalszy dziennik operacji. Jeśli aplikacja zostanie przerwana między zmianą danych na dysku a zapisem manifestu, historia odczytuje i weryfikuje fizyczną lokalizację pliku. Odtworzenie wymaga osobnego polecenia/użytkownika.

**Granica gwarancji:** kilka przeniesień nie stanowi jednej niepodzielnej transakcji ACID. Dziennik i rekoncyliacja służą odzyskiwaniu po przerwaniu, ale nie zastępują kopii zapasowej ani ochrony przed utratą zasilania w niesprawnym systemie plików. Operacje na innym urządzeniu są odrzucane, nie kopiowane.

## Ustawienia

`$XDG_CONFIG_HOME/xdg-audit/settings.json` (domyślnie `~/.config/xdg-audit/settings.json`), zapis dopiero po kliknięciu **Zapisz**, prawa `0600`. Dostępne: `language`, `keep`, `aliases`, `quick_scan`, `startup_scope`, `show_active`.

```text
BraveSoftware=brave*
opera=opera*
```

Użytkownik nie musi wybierać frameworka graficznego ani motywu. Dostępność GTK/Qt/Tk jest wykrywana automatycznie; kolory wynikają z działających integracji systemowych (nie każde CSS GTK ma odpowiednik w Qt/Tk).

## Testy

```sh
python3 -m unittest discover -s tests -v
# lub jeśli pytest jest dostępny:
python3 -m pytest -q
```

Przeprowadzono 92 testy jednostkowe oraz 21 podtestów; dodatkowo wykonano test rzeczywistego przełączenia PL → EN w GUI Tk/X11; smoke-test Tk na X11 przez Xvfb uruchomił się bez tracebacku. GTK4 i Qt6 **nie zostały wykonane na prawdziwym display serverze w środowisku testowym** — kontrola składni, modułów, modeli i logiki skanu nie zastępuje testu wizualnego na Niri i KDE. Zalecane pierwsze uruchomienie GUI bez operacji kwarantanny i weryfikacja zachowania tabeli.

## Zewnętrzne materiały projektowe

- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/)
- [GTK4 `Gtk.ColumnView`](https://docs.gtk.org/gtk4/class.ColumnView.html)
- [GTK4 `Gtk.SortListModel`](https://docs.gtk.org/gtk4/class.SortListModel.html)
- [Qt for Python — Model/View](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-model-view-programming.html)
- [Python `os.rename`/`os.replace`](https://docs.python.org/3/library/os.html)
- [OrphyCleaner](https://github.com/dodog/orphycleaner)
- [pacrid](https://github.com/ParkerrDev/pacrid)
- [xdg-unused-data](https://github.com/pawel-0/xdg-unused-data)

## Pliki

`xdg_audit.py` – silnik/CLI; `xdg_gui.py` – automatyczne wykrywanie GUI; `xdg_gui_gtk.py`, `xdg_gui_qt.py`, `xdg_gui_tk.py` – prezentacje; `xdg_prefs.py` – ustawienia; `xdg_i18n.py` – katalog językowy; `xdg_inspector.py` – wspólny opis wyboru; `xdg_history.py` – porównania; `install_desktop.py` – **opcjonalny** wpis `.desktop`; `assets/` – ikony; `tests/` – testy.

## Developer preview 1.7.0

- One-pass session reference matching instead of per-folder full-text scans.
- Directory-fd-anchored `renameat2(RENAME_NOREPLACE)` prevents target overwrites and unsafe parent symlinks during quarantine and restore. Requires Linux/glibc with renameat2 support; otherwise moves fail closed.
- A user-initiated **Open location** action in the item inspector, using the desktop's file-manager handler; it opens a parent directory, not the selected file.
- CI covers Python 3.10 through 3.14; additional tests cover overwrite, parent symlink, identity changes and session-reference matching.

**Not a stable release.** GTK/Qt integration is not verified in real Niri/KDE sessions. Keep v1.6.3 for regular work until review. No desktop-menu install or automatic updater has been added.
