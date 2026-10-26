# xdg-audit 1.7.0-rc2 — przygotowanie do wydania

**Niewydany kandydat (main).** Ostatnie opublikowane wydanie pozostaje
`v1.7.0-rc1`. Tekst odzwierciedla aktualny kod; nie jest komunikatem
o opublikowaniu nowego tagu.

## Nowe od v1.7.0-rc1

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
  MOVE poza Arch pozostaje celowo zablokowany.
- Dodatkowe testy bezpieczeństwa: awaria przed/po usunięciu,
  katalog bez prawa przeszukiwania, pliki bez odczytu,
  symlinki, hardlinki, obce inode i nieprawidłowe manifesty.

## Granice produktu

- Skanowanie jest tylko do odczytu; `CANDIDATE` nie oznacza
  pewnego osierocenia. Przed MOVE należy sprawdzić dane.
- Aktualny MOVE wymaga prawidłowego inwentarza `pacman`; na systemach
  Debian/RPM wykrywanie zainstalowanych aplikacji jest tylko do odczytu.
  Bezpieczne przenoszenie na tych systemach pozostaje zablokowane.
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
  Niezależny przegląd bezpieczeństwa, decyzja o licencji oraz odbiór
  finalnych artefaktów nadal pozostają otwarte.

## Weryfikacja

```sh
python3 -m unittest discover -s tests -q
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
python3 scripts/build_archives.py --output-dir dist
(cd dist && sha256sum -c SHA256SUMS)
```

Dalsza kontrola jakości:
[docs/release-readiness.md](docs/release-readiness.md).
Rozwój wykrywania AUR / binarek / Flatpak / Snap / AppImage i później
DEB/RPM:
[docs/installation-source-support.md](docs/installation-source-support.md).

Dokumentacja instalacji/aktualizacji/usuwania rejestracji desktopowej:
[docs/desktop-installation.md](docs/desktop-installation.md).
