# v1.7.0 — Release Readiness checklist

**Stan:** prace stabilizacyjne na `main` (kod deklaruje `1.7.0-rc2`).
Ostatni opublikowany tag/Release: `v1.7.0-rc1`.
Nie publikować nowego wydania ani stabilnego tagu bez odrębnej decyzji.

## 1. Bezpieczeństwo (P0)

- [x] Dostęp do kwarantanny, manifestu i podrzędnych katalogów oparty
  na deskryptorach, bez podążania za symlinkami.
- [x] Rekurencyjny inwentarz SHA-256 oraz kontrola inode przed PURGE.
- [x] Brak automatycznych zmian przy nieznanej własności / urządzeniu
  i osobne potwierdzenia `ACCESS`, `ADOPT`, `PURGE`.
- [x] Testy zapisu dziennika, wznowienia po częściowym usunięciu,
  podmiany ścieżek, kolizji i danych spoza kwarantanny.
- [x] Regresje dla katalogów bez prawa odczytu, zapisu i przeszukiwania.
- [ ] Testy ręczne przy awarii/przerwaniu procesu na żywym środowisku
  z *wyłącznie sztucznymi danymi*.
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

- [ ] GNOME/Wayland — cały przepływ od skanu do przywrócenia i PURGE.
- [ ] KDE Plasma/Wayland — analogicznie, z zachowaniem motywu.
- [ ] Xfce/X11 — uruchomienie i przebieg na backendzie Tk/GTK.
- [ ] Brak pacmana: skan działa, MOVE pozostaje zablokowany (obecnie).
- [ ] Odporny UX dla pełnego/quasi-pełnego dysku oraz braku praw
  do katalogów, zrozumiały błąd i bez nadpisywania danych.

## 4. Publikacja (P1)

- [ ] Wybrać **licencję** (MIT/Apache-2.0/GPL-3.0 lub inna) i dopiero
  po decyzji właściciela dodać jej pełny tekst. Nie zgadywać licencji.
- [ ] Zaktualizować README, CHANGELOG i RELEASE_NOTES do kodu RC2.
- [ ] Zweryfikować screenshoty, neutralne ścieżki, brak sekretów w
  załącznikach/release artifacts.
- [ ] Przygotować udokumentowany scenariusz instalacji użytkownika,
  aktualizacji i odinstalowania (obecnie `install_desktop.py`
  wskazuje na aktualny katalog repozytorium).
- [ ] Opublikować **nowy RC** po akceptacji, dopiero potem wersję stabilną.

## 5. Po stabilizacji: źródła instalacji aplikacji

Rozwijać **inwentaryzację aplikacji**, nie paczki xdg-audit:
Arch/AUR/foreign → Flatpak/Snap/AppImage/binarki → dpkg i rpm.
Projekt adapterów i warunki bezpieczeństwa:
[installation-source-support.md](installation-source-support.md).
