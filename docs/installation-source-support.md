# Źródła instalacji: Arch, APT/dpkg, RPM, Flatpak, Snap i AppImage

Dokument opisuje rozpoznawanie audytowanych aplikacji i ochronę ich danych.
Obsługa APT/RPM nie oznacza budowania paczek instalacyjnych xdg-audit.
Narzędzie nie instaluje ani nie odinstalowuje aplikacji.

## Natywna baza pakietów i autoryzacja MOVE

| Rodzina systemu | Baza obecnie zainstalowanych pakietów | Zachowanie |
| --- | --- | --- |
| Arch/CachyOS i pochodne | `pacman -Qq`; `pacman -Qmq` dla foreign | ACTIVE, historia pacmana i jawnie zatwierdzana kwarantanna |
| Debian/Ubuntu/APT i pochodne | `dpkg-query -W` z pełnym statusem | ACTIVE, historia `dpkg.log` (także operacje APT), jawnie zatwierdzana kwarantanna |
| Fedora/RHEL/openSUSE i pochodne | `rpm -qa --qf` | ACTIVE i jawnie zatwierdzana kwarantanna; bez zgadywania historii DNF/Zypper |

Baza jest wybierana na podstawie `ID`, następnie `ID_LIKE` z `os-release`.
Zainstalowanie obcego menedżera pakietów nie zastępuje natywnej bazy.
Nieznana rodzina systemu pozostaje tylko do odczytu. Utrzymano zgodność
starszego interfejsu Pythona z ośmioelementowymi inwentarzami pacmana.

Każdy MOVE ponownie odpytuje wszystkie źródła. Natywna baza musi być
prawidłowo odczytana i niepusta; błędy, timeout, niepełny wynik i nieznana
rodzina blokują operację. Zdrowie źródła i liczba znalezionych nazw są
osobnymi informacjami: pusta baza może być odczytana poprawnie, lecz nie
wystarcza do autoryzacji przenoszenia danych.

APT korzysta z bazy dpkg; nie parsujemy przeznaczonego dla ludzi `apt list`.
`deinstall ok installed` i `purge ok installed` nadal oznaczają obecny pakiet.
Pozostałe pliki konfiguracji (`config-files`) nie udają aktywnej instalacji.
Stany takie jak `unpacked`, `half-configured` lub `reinstreq` oznaczają
`partial` i blokują MOVE do czasu naprawienia bazy przez użytkownika.
xdg-audit sam jej nie naprawia.

Historia dpkg jest czytana w ograniczonym zakresie z plików zwykłych i gzip;
brak uprawnień lub logów nie jest dowodem odinstalowania. Wpis historyczny
nigdy nie przeważa nad obecną instalacją. RPM nie otrzymał niezweryfikowanego
parsera zmiennych formatów historii DNF/Zypper: nieznane dane pozostają
UNKNOWN/REVIEW, a ich przeniesienie wymaga dodatkowego potwierdzenia.

**CANDIDATE nie jest dowodem osierocenia.** REVIEW/UNKNOWN domyślnie nie
są przenoszone. CLI wymaga `--allow-uncertain` i potwierdzeń `UNCERTAIN`
oraz `MOVE`; GUI zachowuje odpowiednie osobne potwierdzenia.

## Snap i oddzielna przestrzeń danych

Zakres `snap` obejmuje wyłącznie bezpośrednie elementy `~/snap` i jest
dostępny w CLI, GTK, Qt oraz Tk. Przykład skanu tylko do odczytu:

```fish
python3 xdg_audit.py --scope snap --quick --json
```

- `snap list` jest czytany w stałym locale C, ze sprawdzeniem pełnego nagłówka,
  sześciu kolumn, rewizji i nazw instancji. Uszkodzony rekord odrzuca częściowy wynik.
- Identyfikatory są dokładne: `firefox` i `firefox_work` to różne instancje.
  Natywny pakiet Firefox nie dowodzi obecności Snapa o tej samej nazwie.
- Zainstalowane, również wyłączone instancje pozostają ACTIVE. Brak potwierdzonej
  instancji daje REVIEW; nie kwalifikujemy danych do automatycznego usunięcia.
- Ponowny odczyt przed MOVE blokuje operację po zainstalowaniu instancji.
  Niesprawny lub nieobecny dostawca Snap blokuje MOVE w zakresie `snap`.
- Przywracanie i PURGE korzystają z tego samego dziennika v3, sprawdzania inode,
  inwentarza SHA-256 i potwierdzeń co pozostałe zakresy.

Nie dotykamy systemowych danych `/var/snap`, montowań `/snap` ani snapshotów
w `/var/lib/snapd`. Ich obsługa nie jest częścią audytu danych użytkownika.
Analogicznie zakres Flatpak używa dokładnego application ID i sprawnej listy
Flatpaka; obecność natywnego pakietu nie nadaje mu własności danych Flatpak.

## AppImage

Wyszukiwanie jest statyczne i ograniczone. Sprawdzane są bezpośrednie pliki
`*.AppImage` w `~/Applications`, `~/AppImages`, `~/Downloads`, `~/.local/bin`,
`~/bin` i `~/.local/share/applications`, a także launchery `.desktop` w
`$XDG_DATA_HOME/applications`.

Launchery pozwalają odnaleźć AppImage również w innej lokalizacji, w tym
w ścieżce ze spacjami. Bezpieczny, istniejący plik musi być wskazany przez
bezpośrednie `Exec` (także prosty wrapper `env`), `TryExec` lub `X-AppImage-Path`.
Sam tytuł/stary launcher bez pliku nie jest dowodem obecności aplikacji.
Nie interpretujemy poleceń `sh -c` ani dowolnych skryptów pośredniczących.

Alias nazwy usuwa typowy numer wersji i architekturę: np.
`Obsidian-1.8.2-x86_64.AppImage` chroni również nazwę `obsidian`.
Rozpoznawane są nazwy sąsiednich danych portable `.AppImage.home` i
`.AppImage.config`; nie oznacza to dodatkowego skanowania całego dysku ani
przenoszenia binarek. Katalogi portable poza zakresami XDG nie są tu audytowane.

Nie uruchamiamy ani nie montujemy AppImage i nie wykonujemy `Exec`.
Symlinki i ich katalogi nadrzędne nie są podążane. Wielkość launcherów oraz
liczba wpisów są ograniczone; błędy odczytu nie udają kompletnego inwentarza.
Brak wyniku nie jest dowodem odinstalowania AppImage. Nowa obecność obrazu
przy ponownym odczycie blokuje MOVE dopasowanych danych XDG.

## Pozostałe źródła i ograniczenia

- **foreign ≠ AUR**: lista pacmana obejmuje również lokalne paczki i pakiety,
  które przestały być dostępne w repozytoriach. Nie wymagamy yay/paru.
- Ręczne binarki, katalogi `/opt`, npm global i pipx są przesłankami ochronnymi.
  Brak wpisu nie dowodzi braku aplikacji; niestandardowe prefixy mogą nie być wykryte.
- Reguły ochronne dla sekretów, profili, kopii, gier i danych sesji nadal obowiązują.
- Inwentarz aplikacji nie potwierdza własności katalogu XDG.
  `orphan_ownership_verified` pozostaje `false`.

## Weryfikacja

Testy obejmują wybór bazy systemu, niepełne rekordy i timeouty, ponowną
instalację po skanie, przestrzenie Snap/Flatpak, metadane AppImage i brak
wykonywania binarek, a także MOVE/RESTORE/PURGE na sztucznych danych.

CI wymaga pełnych regresji i `scripts/smoke_native_sources.py` uruchamianego
jako zwykły użytkownik w Ubuntu 24.04 (dpkg) i Fedora 43 (RPM), przed
zbudowaniem archiwów. Snapshoty/parsery Snap są testowane na fixture;
nie jest to deklaracja wykonania rzeczywistej instalacji Snapa w kontenerze.
AppImage jest testowany statycznie na plikach fixture, zgodnie z kontraktem
niewykonywania aplikacji.

## Źródła

- [os-release i ID_LIKE](https://www.freedesktop.org/software/systemd/man/latest/os-release.html)
- [dpkg-query i status pakietów](https://manpages.debian.org/bookworm/dpkg/dpkg-query.1.en.html)
- [Format zapytań RPM](https://rpm.org/docs/latest/man/rpm-queryformat.7)
- [Lokalizacje danych Snap](https://snapcraft.io/docs/reference/administration/data-locations/)
- [Tryby instalacji i kolumny snap list](https://snapcraft.io/docs/explanation/snap-development/install-modes/)
- [Równoległe instancje Snap](https://canonical.com/blog/parallel-installs-test-and-run-multiple-instances-of-snaps)
- [Dane portable AppImage](https://docs.appimage.org/user-guide/portable-mode.html)
