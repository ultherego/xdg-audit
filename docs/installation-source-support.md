# Wykrywanie źródeł instalacji — plan po stabilizacji v1.7.0

Ten dokument dotyczy **rozpoznawania zainstalowanych aplikacji i osieroconych danych XDG**.
Nie dotyczy tworzenia paczek instalacyjnych xdg-audit. Rozszerzanie źródeł
nie może pogorszyć reguł MOVE/RESTORE/PURGE ani klasyfikować błędu narzędzia
jako dowodu odinstalowania aplikacji.

## Stan w v1.7.0-rc2

| Źródło | Obecne wykrywanie | Ważne ograniczenie |
| --- | --- | --- |
| Repozytoria Arch + AUR + lokalne pakiety pacmana | `pacman -Qq` obejmuje pakiety **zainstalowane** przez pacmana, w tym z AUR | Nie rozróżnia pochodzenia. Pakiet „foreign” nie musi pochodzić z AUR |
| Flatpak | `flatpak list --app --columns=application,name` | Ograniczona obsługa wariantów nazw, identyfikatorów i instalacji |
| Snap | `snap list` | Podstawowa ochrona aktywnych Snapów; brak niezależnego modelu stanu źródła |
| AppImage | Szukanie plików *.AppImage w `~/Applications`, `~/.local/bin`, `~/bin` | Nie rozpoznaje wszystkich ręcznych lokalizacji lub launcherów |
| Instalacje ręczne / binarne | `ps`, `systemctl --user` i pliki `.desktop` stanowią przesłanki ochronne | Brak wiarygodnej bazy pakietów i własności plików |
| Debian/Ubuntu (DEB/APT) | Brak dostawcy pakietów | MOVE pozostaje zablokowany bez pacmana |
| Fedora/RHEL/openSUSE i podobne (RPM) | Brak dostawcy pakietów | MOVE pozostaje zablokowany bez pacmana |

**Nie utożsamiać „nie znaleziono” z „odinstalowano”.**
Dopiero skutecznie odczytana lista pakietów i odpowiednie dowody pozwalają
przejść z `UNKNOWN/REVIEW` do `CANDIDATE`. Dodatkowo `CANDIDATE` jest
propozycją do ręcznej analizy, nie pozwoleniem na automatyczne usunięcie.

## Kolejność prac

### Etap 1 — ujednolicony kontrakt inwentarza

Wydzielić adaptery od `read_active_names()` i oddzielić:
- `id`, `display_name`, `provider` (`pacman`, `flatpak`, `snap`,
  `appimage`, `manual_binary`, później `dpkg`, `rpm`);
- `provenance`: skąd wzięto informację, np. `pacman:localdb`,
  `desktop:Exec`, `flatpak:user`; 
- `confidence`: `authoritative_installed`, `protective_hint`,
  `historical_only`;
- `health`: `ok`, `unavailable`, `timeout`, `parse_error`,
  `partial`; wraz z krótkim diagnostycznym opisem.

Nie używać `bool(installed_packages)` jako synonimu sprawnego dostawcy:
pusta, poprawnie odczytana baza nie jest tym samym co błąd wykonania.
Ponadto każda akcja MOVE musi ponownie odczytać dostawców po ostatnim
skanowaniu oraz odrzucić zmianę, jeśli wymagane źródło jest niesprawne.

### Etap 2 — Arch/CachyOS: oficjalne i AUR

`pacman -Qq` pozostaje podstawowym, autorytatywnym inwentarzem.
Można dodatkowo korzystać z `pacman -Qm` (pakiety **foreign**), lecz
**foreign ≠ AUR**: dotyczy też pakietów zainstalowanych ręcznie oraz
pakietów, które wypadły z aktualnych repozytoriów. `yay` i `paru`
nie mogą być obowiązkowe. Etykieta w UI: „pacman (foreign / AUR lub lokalny)”.

### Etap 3 — Flatpak, Snap, AppImage i ręczne binarki

- Flatpak: zainstalowane identyfikatory aplikacji, widok instalacji
  użytkownika i systemowej (również dodatkowe instalacje, gdy występują).
  Runtimes/extensions nie są aplikacjami do kwalifikowania po samej nazwie.
- Snap: lista rzeczywiście zainstalowanych Snapów oraz oddzielna
  klasyfikacja stanu `~/snap`; nie usuwać w ciemno danych/snapshotów.
- AppImage: pliki w jawnie skonfigurowanych katalogach oraz powiązane
  launchery `.desktop`. Nie wykonywać `Exec` ani nie uruchamiać AppImage;
  dane launchera traktować jako *przesłankę ochronną*, nie dowód braku aplikacji.
- Binarki manualne: `~/.local/bin`, `~/bin`, `~/Applications`,
  `/usr/local/bin`, `/opt` i bezpieczne metadane launcherów.
  Nie przeszukiwać rekurencyjnie całego systemu ani nie wykonywać binarek.
  Bez potwierdzonego właściciela obiekt pozostaje co najmniej `REVIEW`.

### Etap 4 — Debian/Ubuntu i rodzina RPM

- Debian/Ubuntu: status rzeczywiście zainstalowanych pakietów
  odczytywać przez `dpkg-query`; `apt` służy przede wszystkim do
  zarządzania/repozytoriów/historii, nie jest substytutem bazy dpkg.
- RPM: `rpm -qa` i odpowiednie bezpieczne zapytania do bazy pakietów.
  `dnf` lub `zypper` mogą dostarczać historii, ale historyczny brak
  aplikacji nie dowodzi automatycznie, że jej dane można usunąć.
- Każdy backend testować na rzeczywistym systemie oraz na sztucznych
  rekordach zawierających kolizje nazw, niepełne źródła i timeouty.

## Warunki akceptacyjne

1. Aktywna aplikacja nie może być `CANDIDATE` wyłącznie na podstawie
   podobnego prefiksu nazwy lub starego wpisu historii.
2. Awaria dowolnego wymaganego dostawcy blokuje MOVE lub obniża wynik
   do `REVIEW/UNKNOWN`; nie zamienia się po cichu na pustą listę.
3. System rozpoznaje zainstalowane AUR już dziś przez pacmana,
   lecz nie przedstawia pakietu foreign jako pewnego AUR.
4. Flatpak user/system, Snap, AppImage i binarka manualna mają
   osobne, testowalne przesłanki i diagnostykę.
5. Dla DEB/RPM testy MOVE wymagają działającego odpowiedniego dostawcy,
   bez sztucznego uzależnienia od `pacman`.
6. Operacje destrukcyjne pozostają w katalogu użytkownika; mechanizm
   Polkit dla dowolnych obcych plików nie jest częścią adapterów.

## Materiały źródłowe

- ArchWiki, AUR i pacman foreign: https://wiki.archlinux.org/title/Arch_User_Repository
- pacman `-Qm` i `-Qn`: https://wiki.archlinux.org/title/Pacman/Tips_and_tricks
- Flatpak instalacje user/system: https://docs.flatpak.org/en/latest/using-flatpak.html
- Flatpak list: https://man.archlinux.org/man/flatpak-list.1.en
- Snap aplikacje i launchery: https://snapcraft.io/docs/commands-and-aliases/
- AppImage integracja bez instalacji: https://docs.appimage.org/user-guide/run-appimages.html
- dpkg-query — status bazy i format dla maszyn: https://man7.org/linux/man-pages/man1/dpkg-query.1.html
- RPM — zapytania do zainstalowanych pakietów: https://rpm.org/docs/latest/man/rpm-queryformat.7
