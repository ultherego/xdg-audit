# v1.7.0 — Release Readiness checklist

**Stan:** prace stabilizacyjne na `main` (kod deklaruje `1.7.0-rc2`).
Ostatni opublikowany tag/Release: `v1.7.0-rc1`.
Nie publikować nowego wydania ani stabilnego tagu bez odrębnej decyzji.

Dowody wymagane do zamknięcia otwartych pozycji: [protokół walidacji P0/P1](release-verification-evidence.md).
Zaznaczenie checkboxa wymaga podlinkowanego wyniku; sam skrypt/test dodany do repozytorium nie jest dowodem jego uruchomienia.

Wyniki prac i wykonanych kontroli z 2026-10-26:
[rejestr weryfikacji](verification-2026-10-26.md).

## 1. Bezpieczeństwo (P0)

- [x] Dostęp do kwarantanny, manifestu i podrzędnych katalogów oparty
  na deskryptorach, bez podążania za symlinkami.
- [x] Rekurencyjny inwentarz SHA-256 oraz kontrola inode przed PURGE.
- [x] Brak automatycznych zmian przy nieznanej własności / urządzeniu
  i osobne potwierdzenia `ACCESS`, `ADOPT`, `PURGE`.
- [x] Testy zapisu dziennika, wznowienia po częściowym usunięciu,
  podmiany ścieżek, kolizji i danych spoza kwarantanny.
- [x] Regresje dla katalogów bez prawa odczytu, zapisu i przeszukiwania.
- [x] Rzeczywiste przerwanie procesu w ośmiu punktach MOVE/RESTORE/PURGE
  przez `SIGKILL`, z *wyłącznie sztucznymi danymi*, oraz odzyskanie po
  ponownym uruchomieniu — [wyniki i zakres](verification-2026-10-26.md).
  Nie jest to test odcięcia zasilania ani awarii jądra.
- [ ] Przegląd bezpieczeństwa ostatnich zmian przez drugą osobę.

## 2. CI i ochrona main (P0)

Repozytorium ma aktywny ruleset `Protect main`, wymagający PR,
blokujący force-push/usunięcie `main` i sprawdzający testy Python,
GUI Xvfb, benchmark oraz archiwum źródeł.

**Istotny szczegół:** check `Source ZIP and tar.gz` ma w workflow
`needs: [test, gui-smoke, wayland-smoke, benchmark, quarantine-cycle]`.
Zatem poprawne zbudowanie archiwum wymaga także sukcesu testu Wayland
i testu `Quarantine and restore E2E (isolated)`, mimo że nie są wpisane
bezpośrednio na listę wymaganych kontekstów rulesetu.

- [x] Testy Python 3.10–3.14 i natywne GUI (Xvfb/Weston).
- [x] Izolowany pełny test MOVE → RESTORE i awarii bezpieczeństwa.
- [x] Bramka budowania release zależna od kontroli Wayland i E2E.
- [ ] **Opcjonalnie** dopisać dwa testy do rulesetu bezpośrednio,
  aby administrator widział je osobno jako obowiązkowe.
  Wymaga uprawnień administracyjnych GitHub; nie wykonywać obejścia
  bez odpowiednich uprawnień.

## 3. Kompatybilność Linux i GUI (P0)

**Potwierdzenie użytkownika (2026-10-26):** autor projektu testował GUI
i potwierdził działanie wszystkich sprawdzanych funkcji. Odbiór tego
środowiska jest zakończony; nie wymaga ponownego wykonywania tych samych testów.
Poniższa macierz dotyczy dodatkowego pokrycia osobnych środowisk, którego
potwierdzenie użytkownika nie wymienia.

- [x] Testy funkcjonalne GUI w środowisku autora — potwierdzenie użytkownika.

- [ ] GNOME/Wayland — cały przepływ od skanu do przywrócenia i PURGE.
- [ ] KDE Plasma/Wayland — analogicznie, z zachowaniem motywu.
- [ ] Xfce/X11 — uruchomienie i przebieg na backendzie Tk/GTK.
- [x] Brak pacmana: rzeczywisty odczyt dpkg i skan działają, MOVE pozostaje
  zablokowany — [wykonany test](verification-2026-10-26.md).
- [ ] Odporny UX dla pełnego/quasi-pełnego dysku oraz braku praw
  do katalogów, zrozumiały błąd i bez nadpisywania danych. Testy silnika
  ENOSPC/EACCES wykonane; natywny smoke błędu GTK musi przejść CI.

## 4. Publikacja (P1)

- [ ] Wybrać **licencję** (MIT/Apache-2.0/GPL-3.0 lub inna) i dopiero
  po decyzji właściciela dodać jej pełny tekst. Nie zgadywać licencji.
- [x] Zaktualizować README, CHANGELOG i RELEASE_NOTES do kodu RC2.
- [x] Zweryfikować bieżące screenshoty, neutralne ścieżki oraz wejścia do
  archiwów źródeł; wykluczyć przypadkowe pliki z checkoutu —
  [zakres i wyniki](verification-2026-10-26.md). Finalny opublikowany
  artefakt wymaga jeszcze odbioru przed wydaniem.
- [x] Przygotować i przetestować udokumentowany scenariusz instalacji użytkownika,
  aktualizacji i odinstalowania (obecnie `install_desktop.py`
  wskazuje na aktualny katalog repozytorium) —
  [opis i testy](desktop-installation.md).
- [ ] Opublikować **nowy RC** po akceptacji, dopiero potem wersję stabilną.

## 5. Po stabilizacji: źródła instalacji aplikacji

Rozwijać **inwentaryzację aplikacji**, nie paczki xdg-audit:
Arch/AUR/foreign → Flatpak/Snap/AppImage/binarki → dpkg i rpm.
Projekt adapterów i warunki bezpieczeństwa:
[installation-source-support.md](installation-source-support.md).
