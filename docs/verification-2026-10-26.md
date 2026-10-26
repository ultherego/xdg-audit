# Weryfikacja P0/P1 — 2026-10-26

Zmiany: [PR #27](https://github.com/ultherego/xdg-audit/pull/27) i
[PR #28](https://github.com/ultherego/xdg-audit/pull/28).
Dokładny SHA oraz wyniki każdej wersji Pythona i natywnych smoke testów
udostępnia [CI PR #28](https://github.com/ultherego/xdg-audit/pull/28/checks).
Nie opublikowano nowego RC ani stabilnego wydania.

## Wykonane kontrole

Lokalnie: Ubuntu 24.04.3 LTS, Python 3.12.14, bez pacmana. Testy korzystały
wyłącznie z tymczasowych katalogów. Kontener wykonawczy mapuje tylko UID 0;
nie wyłączano zabezpieczenia roota w CLI ani instalatorze produktu.
Test instalatora używa kontrolowanej atrapy sprawdzenia UID; natywny test
launchera w CI wymaga zwykłego użytkownika.

| Kontrola | Wynik i zakres |
| --- | --- |
| `python3 -m unittest discover -s tests -q` | PASS lokalnie; szczegółowe przypadki poniżej |
| Osiem rzeczywistych SIGKILL | PASS: przed/po rename MOVE, przed/po rename RESTORE, przed usuwaniem, po pierwszym unlink, po usunięciu przed zapisem końcowym oraz podczas wymiany dziennika |
| Powrót po przerwaniu | PASS: identyczne bajty przy RESTORE, kontynuacja częściowego PURGE, jawne odzyskanie wyłącznie tymczasowego dziennika, plik kontrolny poza operacją nietknięty |
| ENOSPC / EACCES / EIO | PASS: zachowany właściwy kod błędu i poprzedni dziennik; brak niezatwierdzonych zmian; poprawne liczniki po wykonanym rename; ponowienie po usunięciu błędu |
| Rzeczywisty dpkg bez pacmana | PASS: odczyt bazy dpkg, skan fixture i jawna odmowa MOVE; bajty fixture niezmienione |
| Instalacja / aktualizacja / usunięcie rejestracji | PASS: dziewięć regresji; brak zmian cudzych wpisów i kwarantanny; odmowa symlinków i hardlinków, zachowanie wpisu po nieudanym zapisie |
| Archiwa ZIP i tar.gz | PASS lokalnie: budowanie, integralność i powtarzalność; wyłącznie jawna lista `scripts/archive-files.json` |
| Prywatność wejść archiwum | PASS: dodatkowe `.env`, raport JSON, prywatny plik Python i PEM nie trafiają do archiwum; zadeklarowany symlink lub wyjście poza projekt blokuje budowanie |
| Natywny Gio / błąd ENOSPC w GTK | Nowe smoke testy w zadaniu GUI; ich wynik należy odczytać z powiązanego CI, nie z lokalnych testów bez display servera |

PR #27, commit `8d7a70535134fce903f470fca7a8a9098af78999`, przeszedł
Python 3.10–3.14, Xvfb, Weston, E2E, benchmark i archiwa:
[run 40356697307](https://github.com/ultherego/xdg-audit/actions/runs/40356697307).
Po tym wyniku PR został scalony.

## Poprawione usterki

1. Dane testowe dpkg miały dosłowne `\\t`/`\\n`; test poprawnego rekordu
   nie testował rzeczywistego formatu. Zastąpiono je tabulatorami i końcami linii.
2. Zapis dziennika przy błędzie flush/fsync zamykał deskryptor drugi raz,
   maskując ENOSPC jako EBADF. Własność deskryptora jest teraz jednoznaczna.
3. MOVE i RESTORE zapisywały dziennik przez ścieżkę z potencjalnym symlinkiem
   nadrzędnym. Korzystają teraz z tego samego zakotwiczonego zapisu co PURGE.
4. RESTORE przerwany po rename pozostawiał dane na miejscu, ale nie kończył
   dziennika przy ponowieniu. Uzgodnienie wymaga zgodnego oryginalnego inode;
   nowa kolizja pozostaje nietknięta i nie jest uznawana za przywrócony obiekt.
5. Błąd synchronizacji po rename zaniżał liczbę już przeniesionych obiektów.
6. Instalator desktopowy nie sprawdzał wszystkich katalogów nadrzędnych,
   zapisywał bezpośrednio i nie obsługiwał poprawnie procentów w Exec.
7. Archiwizator zbierał dowolne pliki z checkoutu. Obecnie wymaga jawnego
   manifestu, również przy budowaniu poza repozytorium Git.

## Przegląd screenshotów i plików projektu

Sprawdzono wizualnie wszystkie dziewięć obrazów `docs/screenshots/*.webp`
oraz ich tekst przez OCR. Odczytano metadane obrazów; nie zawierały pól EXIF/XMP.
Nie zaobserwowano wartości haseł, tokenów, pełnych osobistych ścieżek HOME
ani nazw hostów. Widoczne pozostają nazwy aplikacji i neutralne ścieżki `~/…`.
Wzorzec OCR `@` dopasował ikonę Settings, nie adresy e-mail.
To przegląd zawartości, nie matematyczny dowód braku każdego możliwego sekretu.

README oznacza te screenshoty jako historyczne: klasyfikacje i przyciski
mogą różnić się od obecnego kodu. Archiwa są ponadto ograniczone do
przejrzanych plików projektu; wyniki skanów i lokalne logi nie są publikowane.
Odbiór binarnych załączników ostatniego opublikowanego RC1 nie był częścią
tej kontroli. Nowe artefakty nadal wymagają odbioru przed publikacją.

## Pozostałe decyzje i zewnętrzne dowody

- Licencję wybiera właściciel; nie dodano domyślnej licencji.
- Niezależny przegląd bezpieczeństwa wymaga innego recenzenta niż autor zmian.
- Potwierdzenie GUI właściciela jest przyjęte. Osobne sesje GNOME/KDE/Xfce
  nie zostały na tej podstawie oznaczone jako wykonane.
- Nowy RC/stable wymaga decyzji o wydaniu i przejścia wymaganych kontroli.
- Rozszerzenie RPM/MOVE pozostaje wstrzymane zgodnie z kolejnością P0/P1.

## Powtórzenie kontroli

```fish
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p test_process_recovery.py -v
python3 -m unittest discover -s tests -p test_journal_errors.py -v
python3 scripts/smoke_quarantine_cycle.py --synthetic-inventory
python3 scripts/build_archives.py --output-dir dist
cd dist
sha256sum -c SHA256SUMS
cd ..
```

Testy natywne Gio i GTK uruchamia CI z odpowiednimi zależnościami.
Nie uruchamiać CLI ani instalatora przez sudo.
