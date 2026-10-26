# xdg-audit 1.7.0-rc2 — przygotowanie do wydania

**Niewydany kandydat (main).** Ostatnie opublikowane wydanie pozostaje
`v1.7.0-rc1`. Tekst odzwierciedla aktualny kod; nie jest komunikatem
o opublikowaniu nowego tagu.

## Nowe od v1.7.0-rc1

- Licencja MIT, dołączana także do archiwów źródeł.
- Natywna autoryzacja MOVE na APT/dpkg i RPM, sprawdzanie ID/ID_LIKE,
  historia usunięć dpkg i blokada operacji przy niepełnej konfiguracji pakietów.
- Zakres `~/snap` w CLI i wszystkich GUI, dokładne identyfikatory instancji,
  ponowne sprawdzenie obecności przed MOVE i wspólne RESTORE/PURGE.
- Statyczne rozpoznawanie AppImage z numerem wersji i architekturą oraz
  bezpiecznych launcherów wskazujących istniejący obraz; bez wykonywania kodu.
- Obowiązkowe testy natywnych baz i cyklu kwarantanny na Ubuntu i Fedora w CI.

- Osiem testów rzeczywistego zakończenia procesu przez `SIGKILL` i odzyskiwania
  MOVE/RESTORE/PURGE; testy błędów ENOSPC/EACCES przy zapisie dziennika.
- Wznowienie zakończonego RESTORE uzgadnia dziennik na podstawie oryginalnego
  inode. Liczniki uwzględniają rename nawet przy późniejszym błędzie synchronizacji.
- Archiwa źródeł obejmują wyłącznie jawną listę plików projektu, a instalator
  desktopowy zapisuje atomowo bez podążania za symlinkami katalogów nadrzędnych.
- Rzeczywisty test dpkg bez pacmana potwierdza skan tylko do odczytu i blokadę
  MOVE; CI sprawdza również uruchomienie launchera o ścieżce ze znakami specjalnymi
  oraz komunikat pełnego dysku w GTK.
- Pełny cykl kwarantanny z jawnie zatwierdzanym `PURGE`, rekursywnym
  inwentarzem SHA-256, sprawdzaniem tożsamości plików i dziennikiem v3.
- Bezpieczne wznowienie po przerwaniu operacji oraz osobne `ADOPT`
  bieżącej zawartości, gdy inwentaryzacja nie powiodła się podczas MOVE.
- Naprawa ograniczonych uprawnień bieżącego użytkownika: `ACCESS`
  na dokładnie zweryfikowanym obiekcie w kwarantannie, następnie
  nowy preflight i oddzielne `PURGE`.
- Historyczne wpisy `PURGED` / `RESTORED`, ręczne czyszczenie
  zakończonej historii i opcjonalna retencja z jednostką systemd --user.
  Automatyczne usuwanie jest domyślnie wyłączone.
- Wyjaśnienia problemów w GTK/Qt/Tk i operacje na wątku roboczym,
  bez blokowania głównego interfejsu podczas liczenia SHA-256.
- Polskie/angielskie tłumaczenia interfejsu; natywny test GTK/Qt
  na Wayland (Weston) i kompletny syntetyczny test E2E.
- Wykrywanie źródeł instalacji aplikacji: stan zdrowia pacman,
  foreign (AUR **lub** lokalny), Flatpak, Snap, AppImage, ręczne binarki
  i katalogi /opt oraz odczyt pakietów dpkg/rpm.
  `--installed-sources` udostępnia diagnostykę tylko do odczytu.
- Ochronne, tylko-do-odczytu sprawdzenie pakietów npm global oraz pipx
  (wybrane katalogi, bez wykonywania kodu). Dodatkowe źródła chronią
  `CANDIDATE` przed MOVE, ale ich brak nie jest dowodem odinstalowania.
- Flatpak rozdziela kanoniczne identyfikatory aplikacji od nazw
  wyświetlanych; nowe `flatpak_app_ids` podaje liczbę rzeczywistych ID.
- Skan `--quick --json` oznacza niemierzone rozmiary przez `null`,
  a stan dowodów ma jawne `evidence_level` i `orphan_ownership_verified`.
- Zainstalowane pakiety dpkg/rpm chronią dane jako ACTIVE, ale
  MOVE korzysta teraz z natywnej bazy wybranej przez os-release.
- Dodatkowe testy bezpieczeństwa: awaria przed/po usunięciu,
  katalog bez prawa przeszukiwania, pliki bez odczytu,
  symlinki, hardlinki, obce inode i nieprawidłowe manifesty.

## Granice produktu

- Skanowanie jest tylko do odczytu; `CANDIDATE` nie oznacza
  pewnego osierocenia. Przed MOVE należy sprawdzić dane.
- MOVE wymaga prawidłowego, aktualnego inwentarza natywnego `pacman`,
  `dpkg-query` lub `rpm`, wybranego na podstawie rodziny systemu.
  Nieznany system, błąd dostawcy lub niepełna baza dpkg blokują operację.
- AUR instalowany przez pacmana znajduje się w `pacman -Qq`;
  pochodzenie z AUR nie jest dziś rozróżniane od innych pakietów foreign.
- Flatpak i Snap mają podstawowe przesłanki instalacji.
  AppImage i ręczne binarki nie są jeszcze wykrywane we wszystkich
  możliwych lokalizacjach.
- Test systemowego `pkexec` nie nadaje xdg-audit prawa
  do usuwania plików należących do roota. W rzeczywistej kwarantannie
  narzędzie naprawia tylko sprawdzone obiekty bieżącego użytkownika.
- `PURGE` nie oznacza bezpiecznego nadpisywania nośnika.
  Wewnętrzne limity lub brak dostępu blokują operację.
- To nadal kandydat. Autor potwierdził działanie testowanego GUI (2026-10-26),
  ale nie udokumentowano osobno macierzy GNOME/KDE/Xfce.
  Niezależny przegląd bezpieczeństwa, dodatkowe sesje pulpitów oraz odbiór
  finalnych artefaktów nadal pozostają otwarte.

## Weryfikacja

```sh
python3 -m unittest discover -s tests -q
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
python3 scripts/build_archives.py --output-dir dist
cd dist
sha256sum -c SHA256SUMS
cd ..
```

Dalsza kontrola jakości:
[docs/release-readiness.md](docs/release-readiness.md).
Rozwój wykrywania AUR / binarek / Flatpak / Snap / AppImage i później
DEB/RPM:
[docs/installation-source-support.md](docs/installation-source-support.md).

Dokumentacja instalacji/aktualizacji/usuwania rejestracji desktopowej:
[docs/desktop-installation.md](docs/desktop-installation.md).
