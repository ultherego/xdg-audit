# Changelog

## 1.7.0-dev

- More conservative, dirfd-anchored quarantine and restore using Linux renameat2 without destination overwrite.
- Single-pass references lookup for faster audits on large profile lists.
- Inspector action to open the parent folder in the file manager (GTK, Qt, Tk).
- Cross-version Python CI workflow and regression tests.
- No menu installation or package distribution changes.

## v1.6.3 — hotfix motywu, rozmiaru ikony i tłumaczeń

- Naprawiono `NameError: appearance is not defined` podczas zmiany języka w GTK4. Motyw jest przechowywany w stanie okna (`self.appearance`) i nie odwołuje się do lokalnej zmiennej z konstruktora.
- Ikona nagłówka ma 56 px w GTK4 i Qt6 oraz około 64 px w Tk, proporcjonalnie do dwuwierszowego bloku tytułu. Ikona systemowa pozostaje bez zmian.
- Zmiana języka PL/EN odświeża bieżące widoki i pasek stanu w GTK/Qt/Tk bez restartu.
- Dodano test regresji metody GTK `apply_language()` uruchamiany bez wiązań GTK.
- Ostrzeżenia `VK_SUBOPTIMAL_KHR` są niezależne od tego wyjątku; program nie wymusza zmiany rendererów użytkownika.

# 1.6.3

- Poprawiono rozmiar ikony w nagłówku GTK4, Qt6 i Tk.
- Kolumny tabeli wykorzystują szerokość okna i reagują na zmianę jej rozmiaru.
- Wybór języka Polski/English w Ustawieniach zmienia interfejs bez restartu.
- Rozszerzono testy, w tym test przełączenia języka w GUI Tk na X11.

# Zmiany xdg-audit

## 1.6.0
- Skanowanie etapowe i przyrostowe w GTK, Qt i Tk; etap i postęp partii rozmiarów.
- Anulowanie skanu z ochroną niekompletnych wyników przed kwarantanną.
- `Gtk.ColumnView` (GTK4) i `QTableView` (Qt6), sortowanie i natywne kolumny; fallback GTK3/Tk zachowany.
- Polski/English w ustawieniach i UI (zmiana po ponownym uruchomieniu).
- Ikona aplikacji zmniejszona do wysokości nagłówka.
- Trwalszy dziennik kwarantanny, `fsync`, atomowe manifesty i rekonstrukcja po przerwaniu.
- Raport JSON z ustrukturyzowanymi przesłankami i flagami ryzyka.
- Porównanie wcześniejszego raportu z GUI, osobne potwierdzenie eksportu bez nadpisywania pliku.
- Zachowano układ zaakceptowanego GUI, `--scope`, `--remove`, `--restore`, wszystkie źródła rozpoznawania pakietów i kompatybilność kwarantanny.

## 1.5.0
- Ikona i opcjonalne desktop entry; preferencje konta; etapy skanowania; rekonstrukcja starej kwarantanny.


## v1.6.3
- Język PL/EN zmienia się bez ponownego skanowania katalogów i resetowania zaznaczeń.
- Skanowanie ponawiane tylko po zmianie reguł `keep`, aliasów lub `quick_scan`.
- GTK4 pokazuje natywny `Gtk.Picture` z ikoną w rzeczywistym rozmiarze 68 px; Qt6 68 px, Tk 64 px.
- GTK3 i Tk nie odtwarzają całej tabeli przy zmianie języka.
