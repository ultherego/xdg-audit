# xdg-audit — audyt architektury i plan rozwoju po v1.4.8

> **Dokument historyczny (2026-10-25).** Dotyczy stanu po v1.4.8;
> część opisanych zadań została już wdrożona w aktualnym main.
> Bieżące priorytety: [Release Readiness 1.7.0](docs/release-readiness.md).
> Następna faza to [rozpoznawanie źródeł instalacji aplikacji](docs/installation-source-support.md),
> **nie** budowa paczek instalacyjnych xdg-audit.


Data: 2026-10-25. Analiza lokalnego kodu xdg-audit v1.4.7 i źródeł online. **Poniższe propozycje nie zostały wdrożone w v1.4.8**, poza dwiema poprawkami wyglądu opisanymi w README.

## Stan obecny (ustalenia z kodu)

- `xdg_audit.py:scan()` kataloguje pierwszopoziomowe elementy sześciu zakresów i ocenia je na podstawie pakietów, Flatpak, Snap, AppImage, usług, procesów, PATH, `.desktop` i historii pacmana.
- `read_active_names()` odpytuje każdorazowo `pacman`, `flatpak`, `snap`, `ps`, `systemctl` oraz szuka AppImage.
- `references()` czyta małe pliki tekstowe i szuka nazw podejrzanych katalogów w wybranych konfiguracjach Niri/DMS/Fish/systemd.
- `disk_sizes()` uruchamia `du -s -B1 -0` dla wszystkich znalezionych katalogów w paczkach po 100 ścieżek; timeout każdej paczki to 120 s. W efekcie czas może być zdominowany przez głębokie katalogi cache/profili.
- GTK4 opiera tabelę o `Gtk.ListBox` i ręcznie budowane `Gtk.Grid`, a `refresh()` odbudowuje wszystkie widoczne wiersze.
- `commit_quarantine()` ponownie bada bieżące instalacje, kontroluje właściciela, inode, symlinki, montowania, manifest i przenosi przez `Path.rename()` przy zgodnym urządzeniu.

## Wnioski z kodów i dokumentacji

1. **Natywny model tabeli GTK4**. `Gtk.ColumnView` udostępnia fabryki widocznych komórek, nagłówki, natywne sortowanie, zmianę szerokości oraz separatory. Jest lepszy dla rozwijającej się listy niż ręczny `Gtk.ListBox` + `Gtk.Grid`. Dokumentacja GTK: https://docs.gtk.org/gtk4/class.ColumnView.html oraz https://docs.gtk.org/gtk4/section-list-widget.html
2. **Postęp rzeczywisty kontra animacja**. Dokumentacja GTK rozróżnia `ProgressBar.pulse()` (nieznana liczba operacji) i `set_fraction()` (znany postęp). Obecny `pulse` jest prawidłowy; 1.4.8 nie obiecuje procentów. https://docs.gtk.org/gtk4/class.ProgressBar.html
3. **Baza wiedzy aplikacja → dane XDG**. xdg-unused-data przechowuje JSON-y wiążące pliki wykonywalne ze ścieżkami użytkownika i celowo nie ma automatycznego usuwania. https://github.com/pawel-0/xdg-unused-data
4. **OrphyCleaner** wykorzystuje zainstalowane pakiety, Flatpaki i desktope, ale sama heurystyka nazw nie rozstrzyga właściciela. https://github.com/dodog/orphycleaner/blob/main/orphycleaner.py
5. **pacrid** łączy bazę znanych ścieżek ze skanowaniem wariantów nazw. Potwierdza sens oddzielenia silnych przesłanek od heurystyk. https://github.com/ParkerrDev/pacrid
6. **Standard XDG** wymaga respektowania absolutnych ścieżek `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_STATE_HOME`, `$XDG_CACHE_HOME`; konfiguracja, dane, stan i cache mają inne znaczenie i ryzyko usunięcia. https://specifications.freedesktop.org/basedir-spec/latest/
7. **Bezpieczne przenoszenie**: `os.rename` na tym samym systemie plików jest atomowy, ale wciąż należy sprawdzać TOCTOU, kolizje, symlinki i transakcję manifestu. https://docs.python.org/3/library/os.html#os.rename

## Priorytety

### P0 — przed rozszerzeniem funkcji usuwania

- **Dowodowość klasyfikacji**: wiersz i panel szczegółów muszą pokazać precyzyjną parę *(źródło danych, wynik)*, np. `pacman: brave-browser (brave*)` albo `desktop: opera.desktop (tylko przesłanka)`; nie wolno mylić znalezienia nazwy z dowodem aktywnej instalacji.
- **Reguły ochronne i konfliktowe**: dla profili przeglądarek, gier, VM, stanu sesji, menedżerów haseł i danych uwierzytelniających nie dopuszczać automatycznej kwalifikacji do usuwania. Współdzielone nazwy i wzorce oznaczać jako niejednoznaczne.
- **Transakcje kwarantanny**: testy awarii procesu między `rename()` a aktualizacją manifestu; recovery „planned but file already moved”; testy kolizji i symulowanego re-mount / symlink swap. Dodać bezpieczne wznowienie po awarii.
- **Testy na zbiorach rzeczywistych**: przygotować zbiór katalogów z oczekiwanym wynikiem (`brave`, `opera`, `go`, `gh`, `dms`, `solaar`, `wayland-sessions`, Flatpak, ręczne AppImage) i mierzyć false-positive / false-negative osobno dla różnych metod instalacji.

### P1 — wydajność i UX skanowania

- **Profilowanie faz**: czas `pacman`, `flatpak`, `.desktop`, analizy zależności, referencji i `du` w milisekundach; uruchomić na realnym `$HOME` użytkownika. Bez pomiaru nie należy nazywać żadnej fazy „najwolniejszą”.
- **Skanowanie dwuetapowe**: szybka klasyfikacja i pokazanie wyników, a rozmiary `du` liczyć później/na żądanie, z aktualizacją jedynie zmienionych wierszy.
- **Etapy postępu**: pokazać aktualną fazę, np. „Pakiety”, „Flatpak”, „Konfiguracje”, „Rozmiary”, ale procenty tylko jeśli znamy rzeczywistą liczbę elementów w danej fazie.
- **Anulowanie**: przycisk „Anuluj” z flagą przerwania między fazami i obsługą subprocess. Obecne worker `threading.Thread` nie ma bezpiecznego przerwania.
- **Gtk.ColumnView**: migrować w GTK4 na wirtualizowany model, `Gtk.SortListModel` i `Gtk.FilterListModel`, zostawiając Qt/Tk jako opcjonalne backendy.

### P2 — przydatność produktu

- **Persistent `KEEP` i własne aliasy**: per-user TOML/JSON w `$XDG_CONFIG_HOME/xdg-audit`, z podglądem i eksportem; nie usuwać nic automatycznie. Zdecydowana decyzja użytkownika powinna przetrwać następny skan.
- **Historia skanów**: zapis tylko na wyraźne żądanie; diff klasyfikacji i uzasadnień, zmiana rozmiaru i bieżącego pakietu.
- **Sortowanie i filtry**: po rozmiarze, ryzyku, źródle dowodu, wieku, „tylko nowe”, „tylko wcześniej odinstalowane”.
- **Przegląd zawartości**: nie wykonywać skryptów i nie otwierać sekretów bez żądania. Pokazywać jedynie metadane i bezpieczny podgląd nazw pierwszego poziomu.
- **Raport interoperacyjny**: wersjonowany schemat JSON, pola `evidence`, `confidence`, `risk_flags`, `scan_errors`, `source_health`; testy kompatybilności.

## Wymagania akceptacyjne do dalszych wersji

- Wyświetlanie `ACTIVE` nie opiera się wyłącznie na dopasowaniu `foo*` do przypadkowej biblioteki.
- Nieudane odczyty baz danych nie dają pewnego `CANDIDATE`; błędy źródeł są jawne.
- Kolejne skanowanie nie blokuje GTK main loop i nie pozwala przenieść plików do kwarantanny w trakcie audytu.
- Przerwana transakcja jest przywracalna bez ręcznej naprawy JSON.
- Pełne GUI GTK4 zachowuje widoczne nagłówki, szczegóły jednokliku, motyw systemowy i obsługę klawiatury.
- Testy integracyjne GTK4 z rzeczywistym display server w CI; testy Tk nie mogą służyć za dowód wyglądu GTK4.
