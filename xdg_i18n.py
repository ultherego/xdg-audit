"""Tiny built-in PL/EN UI catalog. Status identifiers and file paths stay untranslated.

Language is a user preference, not inferred from the GUI backend. Fallback to
source Polish for missing keys so the GUI never loses a label.
"""
from __future__ import annotations

LANGUAGES = {'pl': 'Polski', 'en': 'English'}
EN = {
    'Tożsamość obiektu w kwarantannie nie zgadza się z dziennikiem.': 'The quarantined object identity does not match the journal.',
    'Zapisano:': 'Recorded:',
    'Odczytano teraz:': 'Read now:',
    'Sama nazwa ścieżki nie potwierdza tożsamości plików. Skopiowanie lub odtworzenie katalogu może zmienić te numery; sam komunikat nie rozstrzyga przyczyny.': 'A path name does not establish file identity. Copying or restoring a directory can change these numbers; this message alone does not establish the cause.',
    'To nie jest błąd uprawnień. ACCESS ani ADOPT nie zatwierdzają podmienionego obiektu. PURGE pozostaje zablokowany.': 'This is not a permission error. ACCESS and ADOPT do not approve a substituted object. PURGE remains blocked.',
    'Skopiuj szczegóły z tego okna do dalszej diagnozy. Nie zmieniaj identyfikatorów w manifest.json.': 'Copy these details for further diagnosis. Do not edit identities in manifest.json.',
    'Operacja została zatrzymana. Sprawdź szczegóły błędu i dziennik przed ponowną próbą.': 'The operation was stopped. Review the error details and journal before retrying.',
    'Dodatkowe katalogi AppImage — jedna ścieżka w linii': 'Additional AppImage directories — one path per line',
    'Dodatkowe katalogi binarek — jedna ścieżka w linii': 'Additional binary directories — one path per line',
    'Ścieżki bezwzględne lub ~/; odczyt bez uruchamiania plików.': 'Absolute paths or ~/; files are inspected without execution.',
    'Tak': 'Yes',
    'Nie': 'No',
    'Nieprawidłowa wartość.': 'Invalid value.',
    'Snap': 'Snap',
    "Test uprawnień ~/.config…": "Test ~/.config permissions…",
    "Test uprawnień ~/.config": "Test ~/.config permissions",
    "pkexec lub systemowy /usr/bin/id jest niedostępny.": "pkexec or the trusted system /usr/bin/id program is unavailable.",
    "Systemowy Polkit poprosi o autoryzację uruchomienia /usr/bin/id -u. Nic nie zostanie zapisane ani usunięte. Nie wymaga instalacji helpera.": "System Polkit will request authorization for /usr/bin/id -u. No files will be created or deleted. No additional helper installation is needed.",
    "Wpisz AUTH:": "Type AUTH:",
    "Polkit potwierdził uprawnienia administratora. Uruchomiono tylko odczyt UID=0; żadne pliki nie zostały zmienione.": "Polkit authorized a read-only UID=0 check; no files were modified.",
    "Utworzę ~/.config/xdg-audit-polkit-test z katalogiem 111 i plikiem 000. Nie zmienię innych danych.": "Create ~/.config/xdg-audit-polkit-test with a directory mode 111 and a file mode 000; no other data will be changed.",
    "Utworzono testowe pliki użytkownika:": "Created user-owned test objects:",
    "Katalog: {mode}": "Directory: {mode}",
    "Plik: {mode}": "File: {mode}",
    "Naprawię odczyt tylko tych dwóch obiektów, bez Polkit i bez roota.": "Add owner-read permission to only these two objects, without Polkit or root.",
    "Naprawa testowych uprawnień": "Repair test permissions",
    "Wpisz ACCESS TEST:": "Type ACCESS TEST:",
    "Usuń katalog testowy": "Delete test directory",
    "Zakończono naprawę. Zatwierdź usunięcie wyłącznie katalogu testowego.": "Repair completed. Confirm deletion of only the test directory.",
    "Usunięto wyłącznie katalog testowy ~/.config/xdg-audit-polkit-test.": "Only ~/.config/xdg-audit-polkit-test was deleted.",
    "Błąd testu uprawnień: {error}": "Permission test error: {error}",
    "Tworzenie plików testowych…": "Creating test objects…",
    "Test naprawy uprawnień…": "Testing permission repair…",
    "Usuwanie katalogu testowego…": "Removing test directory…",
    "Test Polkit…": "Test Polkit…",
    "Test Polkit": "Polkit test",
    "Test Polkit wymaga instalacji systemowego helpera. Instrukcja: packaging/polkit/README.md": "The Polkit test needs an installed system helper. Instructions: packaging/polkit/README.md",
    "Poproszę system Polkit o autoryzację i utworzę odizolowany katalog testowy, bez dotykania danych kwarantanny.": "The system's Polkit agent will request authentication to create an isolated test folder, without touching quarantined data.",
    "Uwierzytelnianie Polkit…": "Authenticating with Polkit…",
    "Usuń katalog testowy Polkit": "Delete Polkit test folder",
    "Polkit utworzył katalog testowy. Usunę tylko ten katalog, nigdy kwarantannę użytkownika.": "Polkit created the test folder. Only that exact test folder will be deleted, never user quarantine data.",
    "Wpisz TEST:": "Type TEST:",
    "Wpisz DELETE TEST:": "Type DELETE TEST:",
    "Test Polkit zakończony: usunięto wyłącznie odizolowany katalog testowy.": "Polkit test completed: only the isolated test folder was removed.",
    "Błąd testu Polkit: {error}": "Polkit test failed: {error}",
    "pkexec zainstalowany: {state}": "pkexec installed: {state}",
    "tak": "yes",
    "nie": "no",
    "Naprawa tego obiektu wymaga dodatkowej analizy. Zasady Polkit określa system; xdg-audit nie uruchamia kodu użytkownika jako root.": "This object requires further analysis. The system controls Polkit authorization; xdg-audit never runs user-owned code as root.",
    "Pliki przeniesiono, ale nie można było sprawdzić całej zawartości. Przed PURGE użyj „Sprawdź dostęp…”, następnie osobno „Zatwierdź stan…” (ADOPT).": "Files were moved, but their full contents could not be inspected. Before PURGE use Check access, then separately approve the current state (ADOPT).",
    "Zatwierdź stan…": "Approve current state…",
    "Zatwierdź aktualny stan": "Approve current state",
    "Zatwierdzisz stan plików widoczny TERAZ. Nie oznacza to, że zawartość jest identyczna jak w dniu przeniesienia. PURGE nadal wymaga osobnej zgody.": "You will bind the files as they exist NOW. This does not prove they match the contents at quarantine time. PURGE still needs separate authorization.",
    "Wpisz ADOPT:": "Type ADOPT:",
    "Zatwierdzono aktualny stan: {count} obiektów.": "Current state approved: {count} objects.",
    'Sprawdź dostęp…': 'Check access…',
    'Napraw dostęp': 'Repair access',
    'Diagnostyka dostępu': 'Access diagnostics',
    'Błąd diagnostyki: {error}': 'Access diagnosis failed: {error}',
    'Nie znaleziono problemów z odczytem. Sprawdź pozostałe komunikaty PURGE.': 'No unreadable objects found. Check other PURGE diagnostics.',
    'Brak kompletnego spisu plików. Wymagane osobne zatwierdzenie aktualnej zawartości (ADOPT).': 'The file inventory is unsealed. Current contents require separate ADOPT approval.',
    'Operacja: {run_id}': 'Operation: {run_id}',
    'Użytkownik: {user}': 'User: {user}',
    'Problem: {code}': 'Issue: {code}',
    'Uprawnienia: {mode}': 'Permissions: {mode}',
    'Nie można automatycznie naprawić. Nie podnoszę uprawnień ani nie omijam kontroli PURGE.': 'This cannot be repaired automatically. No privilege elevation or PURGE safeguard bypass will occur.',
    'Proponowana zmiana: {before} → {after}': 'Proposed change: {before} → {after}',
    'Zmienię tylko wskazane uprawnienia właściciela w kwarantannie. Bez sudo i bez usuwania plików.': "Only the indicated owner permissions inside quarantine will change. No sudo and no file deletion.",
    'Wpisz ACCESS:': 'Type ACCESS:',
    'Zmieniono uprawnienia: {before} → {after}': 'Permissions changed: {before} → {after}',
    'Nie wykonano PURGE. Ponownie sprawdź dostęp i osobno potwierdź usunięcie.': 'PURGE was not performed. Recheck access and confirm deletion separately.',
    'Naprawa zablokowana: {error}': 'Repair blocked: {error}',
    'Sprawdzanie dostępu…': 'Checking access…',
    'Naprawianie dostępu…': 'Repairing access…',
    'Wyczyść całą zakończoną historię…': 'Clear all completed history…',
    'Brak zakończonych operacji do wyczyszczenia. Aktywne i niedokończone pozostają chronione.': 'No completed history to clear. Active and unfinished runs remain protected.',
    'Weryfikacja kwarantanny': 'Quarantine verification',
    'Operacja kwarantanny jest już wykonywana.': 'A quarantine operation is already running.',
    'Błąd operacji kwarantanny: {error}': 'Quarantine operation failed: {error}',
    'Sprawdzanie kwarantanny…': 'Verifying quarantine…',
    'Trwałe usuwanie z kwarantanny…': 'Permanently deleting quarantined data…',
    'Sprawdzanie historii…': 'Verifying history…',
    'Usuwanie historii…': 'Removing history records…',
    'Ta operacja jest zakończona. Użyj opcji Usuń historię.': 'This run is complete. Use Clear history instead.',
    'PURGED': 'PURGED',
    'RESTORED': 'RESTORED',
    'COMPLETED': 'COMPLETED',
    'QUARANTINED': 'QUARANTINED',
    'INCOMPLETE': 'INCOMPLETE',
    'ERROR': 'ERROR',
    'Usuń historię…': 'Clear history…',
    'Wyczyść starą historię…': 'Clear expired history…',
    'Brak wygasłych manifestów.': 'No expired history journals.',
    'Usuń historię': 'Clear history',
    'Zostaną usunięte tylko zakończone dzienniki.': 'Only completed history journals will be deleted.',
    'Wpisz HISTORY:': 'Type HISTORY:',
    'Błąd historii: {error}': 'History error: {error}',
    'Usunięto zakończone manifesty.': 'Completed history journals removed.',
    'Status operacji': 'Operation status',
    'Historia': 'History',
    'Audyt tylko do odczytu · MOVE i PURGE wymagają potwierdzenia': 'Read-only scan · MOVE and PURGE require separate confirmation',
    'Ustaw retencję…': 'Configure retention…',
    'Retencja': 'Retention',
    'Dni przechowywania:': 'Retention days:',
    'Ustawiono retencję: {days} dni': 'Retention set to {days} days',
    'Nie można zapisać retencji: {error}': 'Could not save retention: {error}',
    'Retencja: usuń wygasłe operacje': 'Retention: clean up expired runs',
    'Usuń wygasłe…': 'Purge expired…',
    'Usuń trwale…': 'Purge permanently…',
    'Zablokowano PURGE: {error}': 'Purge blocked: {error}',
    'Trwale usunięto obiektów: ': 'Permanently purged objects: ',
    'Trwałe usunięcie': 'Permanent deletion',
    'Nie można cofnąć tej operacji.': 'This action cannot be undone.',
    'Brak wygasłych kwarantann.': 'No expired quarantine runs.',
    'Błąd retencji: {error}': 'Retention error: {error}',
    'Usuń trwale wybraną…': 'Purge selected…',
    'Nie znaleziono wygasłych kwarantann.': 'No expired quarantine runs found.',
    'Zablokowano PURGE': 'Purge blocked',
    'Trwałe usuwanie': 'Permanent deletion',
    'Tej operacji nie da się cofnąć. Kontynuować?': 'This action cannot be undone. Continue?',
    'Potwierdzenie PURGE': 'Purge confirmation',
    'Wpisz PURGE:': 'Type PURGE:',
    'Usunięto obiektów: ': 'Purged objects: ',
    'Nie ma wygasłych operacji.': 'No expired runs.',
    'Ta operacja jest nieodwracalna. Kontynuować?': 'This action is irreversible. Continue?',
    'Dane aplikacji': 'Application data', 'Anuluj skan': 'Cancel scan',
    'Audyt nie zmienia danych. Kwarantanna wymaga MOVE; można ją przywrócić.':
      'Auditing is read-only. Quarantine requires MOVE and is reversible.',
    'Trwa skanowanie… bez modyfikacji plików': 'Scanning… no files are modified',
    'Pakiety i aplikacje': 'Packages and applications',
    'Katalogi i klasyfikacja': 'Directories and classification',
    'Rozmiary katalogów': 'Directory sizes',
    'Referencje konfiguracji': 'Configuration references',
    'Skanowanie anulowano. Wyniki częściowe nie nadają się do kwarantanny.':
      'Scan cancelled. Partial results cannot be quarantined.',
    'Skanowanie wszystkich lokalizacji — bez zapisywania zmian…':
      'Scanning all locations without modifying files…',
    'Anulowanie skanowania po bieżącym etapie…':
      'Cancelling after the current scan stage…',
    'Przygotowanie audytu…': 'Preparing audit…',
    'Żadnych zmian.': 'No changes.',

    'Historia operacji': 'Operations history',
    'Cache': 'Cache', 'Porównaj raport…': 'Compare report…',
    'Historia bezpiecznych przeniesień': 'Safe transfer history',
    'Przywracanie nigdy nie nadpisuje istniejących plików.': 'Restore never overwrites existing files.',
    'Odśwież listę': 'Refresh list', 'Pokaż zawartość': 'Show contents',
    'Przywróć operację…': 'Restore operation…', 'Przywróć wybraną…': 'Restore selected…',
    '0 wybranych': '0 selected', '0 pozycji': '0 entries',
    'Wybierz pozycję, aby poznać przesłanki.': 'Select an entry to review evidence.',
    'Kandydaci': 'Candidates', 'Do sprawdzenia': 'Review', 'Nieznane': 'Unknown',
    'Aktywne': 'Active', 'Chronione': 'Protected',
    'Wszystko': 'All', 'Konfiguracja': 'Configuration', 'Dane': 'Data', 'Stan': 'State',
    'Flatpak': 'Flatpak', 'Dotfiles': 'Dotfiles', 'Kwarantanna': 'Quarantine',
    'Wyniki audytu': 'Audit results', 'Skanuj ponownie': 'Rescan',
    'Skanowanie…': 'Scanning…', 'Ustawienia': 'Settings',
    '⚙ Ustawienia': '⚙ Settings', 'Nazwa': 'Name', 'Status': 'Status',
    'Rozmiar': 'Size', 'Lokalizacja': 'Location', 'Wybór': 'Select',
    'Szczegóły wyboru': 'Selection details', 'Zamknij szczegóły': 'Close details',
    'Zaznacz kandydatów': 'Select candidates', 'Odznacz': 'Clear selection',
    'Zezwól na REVIEW / UNKNOWN': 'Allow REVIEW / UNKNOWN',
    'Eksport JSON…': 'Export JSON…', 'Przenieś do kwarantanny…': 'Move to quarantine…',
    'Aktywne / chronione': 'Active / protected', 'Szybki skan': 'Quick scan',
    'Zakres początkowy': 'Startup scope', 'Zakres przy uruchomieniu': 'Startup scope',
    'Zakres przy starcie': 'Startup scope',
    'Szybki skan (bez rozmiarów)': 'Quick scan (skip sizes)',
    'Szybki skan (bez liczenia rozmiarów katalogów)': 'Quick scan (skip directory sizes)',
    'Pokazuj aktywne i chronione': 'Show active and protected',
    'Pokazuj aktywne i chronione pozycje': 'Show active and protected items',
    'Zachowaj — jedna nazwa katalogu w linii': 'Keep — one folder name per line',
    'Zachowaj — nazwy katalogów, jedna w linii': 'Keep — one folder name per line',
    'Alias — katalog=wzorzec': 'Alias — folder=pattern',
    'Alias pakietu — katalog=wzorzec, jedna para w linii': 'Package alias — folder=pattern, one per line',
    'Zapisz ustawienia': 'Save settings', 'Zapisz': 'Save', 'Anuluj': 'Cancel',
    'Potwierdź': 'Confirm', 'Podgląd': 'Preview', 'Przywróć…': 'Restore…',
    'Odśwież historię': 'Refresh history', 'Historia przeniesień do kwarantanny': 'Quarantine history',
    'Pokaż zawartość…': 'Show contents…',
    'Wykrywanie motywu…': 'Detecting theme…', 'Zamknij': 'Close',
    'Audyt i bezpieczne porządki w katalogach użytkownika': 'Audit and safely clean user directories',
    'Trwa zbieranie i analizowanie wpisów. Tabela pojawi się po zakończeniu skanowania.':
      'Collecting and analyzing entries. Results will appear as soon as they are classified.',
    'CANDIDATE to sugestia, nie dowód. REVIEW i UNKNOWN wymagają dodatkowej zgody.':
      'CANDIDATE is a suggestion, not proof. REVIEW and UNKNOWN require extra confirmation.',
    'Ustawienia xdg-audit': 'xdg-audit settings',
    'Język / Language': 'Language / Język',
    'Zapis jest wykonywany dopiero po kliknięciu Zapisz.': 'Settings are saved only when you click Save.',
    'Zapisane ustawienia dotyczą tylko Twojego konta.': 'These settings apply only to your account.',
    'Wybierz pozycję z listy, aby sprawdzić przesłanki klasyfikacji.':
      'Select an item to inspect classification evidence.',
    'Szukaj nazwy, lokalizacji lub uzasadnienia…': 'Search names, paths and evidence…',
    'Szukaj nazwy, ścieżki lub przesłanek…': 'Search names, paths and evidence…',

    'Otwórz lokalizację': 'Open location',
    'Otwórz': 'Open',
    'Identyfikator operacji': 'Operation ID',
    'W manifestie': 'In manifest',
    'Przeniesione': 'Moved',
    'Środowisko i motyw wykrywane automatycznie, bez instalowania bibliotek.':
        'Desktop and theme are detected automatically without installing libraries.',
    'Pokaż tylko pozycje: {state}': 'Show only items: {state}',
    'Wymaga zaznaczenia i wpisania MOVE; dane pozostają do przywrócenia.':
        'Select items and type MOVE; the files can be restored.',
    'Audyt tylko do odczytu · przeniesienie wymaga MOVE · bez trwałego kasowania':
        'Read-only audit · moving requires MOVE · no permanent deletion',
    'Tylko przenoszenie · wymaga MOVE · możliwe przywrócenie':
        'Moves only · requires MOVE · reversible',
    'Anulowanie skanu po bieżącym etapie…': 'Cancelling scan after current stage…',
    'Skan anulowany. Częściowe wyniki nie służą do przenoszenia plików.':
        'Scan cancelled. Partial results cannot be moved.',
    'CANDIDATE to sugestia, nie dowód.\nREVIEW i UNKNOWN wymagają dodatkowej zgody.':
        'CANDIDATE is a suggestion, not proof.\nREVIEW and UNKNOWN require extra confirmation.',
    'Skanowanie: {stage}': 'Scanning: {stage}',
    'Zapisano ustawienia': 'Settings saved',
    # Confirmation dialogs, quarantine operations and report messages.
    'Żadne pliki nie zostaną trwale usunięte.': 'No files will be permanently deleted.',
    'Wybierasz {count} REVIEW/UNKNOWN.': 'You selected {count} REVIEW/UNKNOWN items.',
    'Nie ustalono, czy są niepotrzebne. Wpisz UNCERTAIN:':
        'Whether these items are safe to move is unknown. Type UNCERTAIN:',
    'Zamknij powiązane aplikacje. Aby zatwierdzić przeniesienie wpisz MOVE:':
        'Close related applications. Type MOVE to confirm the move:',
    '... i {count} kolejnych': '... and {count} more',
    'Nie nadpisano istniejących plików.': 'No existing files were overwritten.',
    'Zbadano {count}. Żadnych zmian.': 'Scanned {count}. No changes.',
    'Skan ukończony: {count}. Żadnych zmian w plikach.':
        'Scan completed: {count}. No files changed.',
    'Sklasyfikowano {count}; obliczanie rozmiarów…':
        'Classified {count}; calculating sizes…',
    'Przenieś wybrane pliki do kwarantanny, nie usuwaj ich.':
        'Move selected files to quarantine; do not delete them.',
    'Wpisz {token}': 'Type {token}',
    'Nieprawidłowe potwierdzenie. Wpisz {token}.': 'Incorrect confirmation. Type {token}.',
    'Ostateczne potwierdzenie': 'Final confirmation',
    'Plan kwarantanny': 'Quarantine plan',
    'Plan: {count}, {size}.': 'Plan: {count}, {size}.',
    'Dane zostaną PRZENIESIONE, nie usunięte.': 'Files will be MOVED, not deleted.',
    'Dane nie zostaną trwale usunięte.': 'Files will not be permanently deleted.',
    'Zamknij powiązane aplikacje.': 'Close related applications.',
    'Zamknij powiązane aplikacje. Wpisz MOVE, aby przenieść:':
        'Close related applications. Type MOVE to continue:',
    'Zaznacz pozycje checkboxami, aby wykonać kwarantannę.':
        'Select items with the checkboxes before moving them to quarantine.',
    'Kwarantanna: {run_id}, przeniesiono {count}.':
        'Quarantine: {run_id}, moved {count}.',
    'Błąd przenoszenia: {error}': 'Move failed: {error}',
    'Niepewne pozycje': 'Uncertain items',
    'Niepewne dane': 'Uncertain items',
    'UWAGA: {count} pozycji REVIEW/UNKNOWN może należeć do używanych programów.':
        'WARNING: {count} REVIEW/UNKNOWN items may belong to applications still in use.',
    '{count} pozycji ma status REVIEW/UNKNOWN. Wpisz UNCERTAIN:':
        '{count} items are REVIEW/UNKNOWN. Type UNCERTAIN:',
    '…oraz {count} kolejnych.': '…and {count} more.',
    '… oraz {count} innych': '… and {count} more',
    'Brak wyboru': 'No selection',
    'Nie zaznaczono pozycji dostępnych do kwarantanny.':
        'No eligible quarantine items are selected.',
    'Przenieść {count} ({size}) do kwarantanny?':
        'Move {count} ({size}) to quarantine?',
    'Przenieść {count} ({size})?': 'Move {count} ({size})?',
    'Nie udało się przeprowadzić operacji:\n{error}':
        'The operation failed:\n{error}',
    'Operacja {run_id}': 'Operation {run_id}',
    'Przeniesiono {moved}/{total}.': 'Moved {moved}/{total}.',
    'Run ID: {run_id}': 'Run ID: {run_id}',
    'Potwierdzenie': 'Confirmation',
    'Przywracanie': 'Restore',
    'Błąd': 'Error',
    'Błąd: {error}': 'Error: {error}',
    'Błąd skanowania': 'Scan error',
    'Błąd porównania': 'Comparison failed',
    'Błąd porównania: {error}': 'Comparison failed: {error}',
    'Błąd zapisu': 'Save failed',
    'Błąd raportu: {error}': 'Report error: {error}',
    'Błąd przywracania': 'Restore error',
    'Błąd przywracania: {error}': 'Restore error: {error}',
    'Zawartość kwarantanny': 'Quarantine contents',
    'Brak operacji kwarantanny.': 'No quarantine operations found.',
    'Nie znaleziono operacji.': 'No operations found.',
    'Wybierz operację do przywrócenia:': 'Select an operation to restore:',
    'Plan przywracania': 'Restore plan',
    'Istniejące pliki nie zostaną nadpisane.':
        'Existing files will not be overwritten.',
    'Istniejące pliki NIE zostaną nadpisane. Kontynuować?':
        'Existing files will NOT be overwritten. Continue?',
    'Przywrócić operację {run_id}?': 'Restore operation {run_id}?',
    'Przywrócić dane z operacji {run_id}?': 'Restore files from operation {run_id}?',
    'Wpisz RESTORE:': 'Type RESTORE:',
    'Przywrócono: {count}': 'Restored: {count}',
    'Pominięto: {count}': 'Skipped: {count}',
    'Przywrócono {restored}, pominięto {skipped}.':
        'Restored {restored}, skipped {skipped}.',
    'Operacja: {run_id} · {count} przeniesionych':
        'Operation: {run_id} · {count} moved',
    '{count} przeniesionych / {total} w manifest':
        '{count} moved / {total} in manifest',
    '{count} przeniesionych / {total} zapisanych':
        '{count} moved / {total} recorded',
    '(pusty manifest)': '(empty manifest)',
    '(brak danych)': '(no data)',
    'Porównanie raportów': 'Report comparison',
    'Wybierz wcześniejszy raport': 'Choose an earlier report',
    'Eksport raportu': 'Export report',
    'Eksport JSON': 'Export JSON',
    'Zapisać raport do {path}?': 'Save report to {path}?',
    'Istniejący plik nie zostanie nadpisany.':
        'An existing file will not be overwritten.',
    'Raport już istnieje — nie nadpisuję: {path}':
        'Report already exists; not overwriting: {path}',
    'Zapisano: {path}': 'Saved: {path}',
    'Wyeksportowano raport: {path}': 'Exported report: {path}',
    'Istniejące pliki nie są nadpisywane.':
        'Existing files are never overwritten.',
    'Zapis dopiero po kliknięciu Zapisz.':
        'Settings are saved only after clicking Save.',
    'Skanowanie': 'Scanning',
    'Skanowanie trwa. Zamknąć okno?':
        'A scan is in progress. Close the window?',
    'Skanowanie jeszcze trwa. Zamknij okno po zakończeniu.':
        'A scan is still running. Close the window when it finishes.',
    'Ustawienia zapisane. Wyniki audytu zachowane.':
        'Settings saved. Scan results preserved.',
    'Ustawienia zapisane. Ponowne skanowanie…':
        'Settings saved. Rescanning…',
}

def translate(text: str, language: str = 'pl') -> str:
    return EN.get(text, text) if language == 'en' else text


def translate_ui_text(value: str, old: str, new: str) -> str:
    """Translate an existing interface label without rewriting user data.

    Values not in the fixed GUI catalog are unchanged. Intended only for UI
    widgets (never file names, paths, scan evidence or editor contents).
    """
    if old == new:
        return value
    reverse = {translated: original for original, translated in EN.items()}
    original = reverse.get(value) if old == 'en' else value
    if original is None or original not in EN:
        return value
    return translate(original, new)


def entries_count(number: int, language: str) -> str:
    if language == 'en':
        return f"{number} {'entry' if number == 1 else 'entries'}"
    # Polish count forms for concise UI counters.
    word = 'pozycja' if number == 1 else ('pozycje' if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14) else 'pozycji')
    return f'{number} {word}'

def selected_count(number: int, language: str) -> str:
    return f'{number} selected' if language == 'en' else f'{number} wybranych'


def format_message(template: str, language: str = 'pl', **values: object) -> str:
    """Translate a UI message template, preserving supplied paths and tokens."""
    return translate(template, language).format(**values)


# Scan evidence is generated by the core in stable English text. Translate only
# the explanatory phrase for GUI presentation; never rewrite paths, package
# names, manifest records or exported JSON evidence.
_PL_EVIDENCE_EXACT = {
    'entry disappeared / cannot stat safely': 'wpis zniknął / nie można bezpiecznie odczytać metadanych',
    'symlink; no operations on links': 'dowiązanie symboliczne; operacje na dowiązaniach są zablokowane',
    'backup / PSD recovery': 'kopia zapasowa / dane przywracania PSD',
    'name suggests credentials or sensitive user data': 'nazwa sugeruje dane uwierzytelniające lub poufne dane użytkownika',
    'mount point': 'punkt montowania',
    'user allowlist': 'pozycja z listy Zachowaj użytkownika',
    'Flatpak app-id is not currently installed; check manually': 'identyfikator aplikacji Flatpak nie jest zainstalowany; sprawdź ręcznie',
    'pacman package inventory unavailable; cannot confirm removal': 'lista pakietów pacman niedostępna; nie można potwierdzić odinstalowania',
    'native package inventory unavailable; cannot confirm removal': 'natywna lista pakietów niedostępna; nie można potwierdzić odinstalowania',
    'not a canonical Snap instance directory': 'nazwa nie odpowiada katalogowi instancji Snap',
    'Snap instance is not verified as installed; check manually': 'instancja Snap nie jest potwierdzona jako zainstalowana; sprawdź ręcznie',
    'Snap inventory unavailable; cannot verify instance': 'lista aplikacji Snap jest niedostępna; nie można zweryfikować instancji',
    'no verified installed application or owner (NOT proof of orphan)': 'nie ustalono zainstalowanej aplikacji ani właściciela (to NIE dowód osierocenia)',
    'checksum manifest in XDG config, not an application ID; inspect contents': 'manifest sum kontrolnych w konfiguracji XDG; nie jest identyfikatorem aplikacji, sprawdź zawartość',
    'protected: potential account credentials or authentication data (ownership not verified)': 'chronione: potencjalne dane logowania lub uwierzytelniania (właściciel niezweryfikowany)',
    'protected: user backup, game/mod or virtual-machine data (ownership not verified)': 'chronione: kopia danych, zapis gry, modyfikacje lub dane maszyny wirtualnej (właściciel niezweryfikowany)',
    'protected: browser profile / profile-sync-daemon; deletion requires separate audit': 'chronione: profil przeglądarki / profile-sync-daemon; usunięcie wymaga osobnego audytu',
    'protected: desktop/session/shell configuration': 'chronione: konfiguracja pulpitu, sesji lub powłoki',
    'protected: shared system component or manually safeguarded user data (ownership not verified)': 'chronione: współdzielony komponent systemowy lub dane użytkownika objęte ochroną (właściciel niezweryfikowany)',
}
_PL_EVIDENCE_PREFIXES = (
    ('installed pacman package: ', 'zainstalowany pakiet pacman: '),
    ('installed Flatpak: ', 'zainstalowana aplikacja Flatpak: '),
    ('installed Snap: ', 'zainstalowana aplikacja Snap: '),
    ('AppImage found: ', 'znaleziony AppImage: '),
    ('user systemd unit: ', 'usługa systemd użytkownika: '),
    ('running executable: ', 'uruchomiony program: '),
    ('executable on PATH: ', 'program w PATH: '),
    ('desktop entry (supporting evidence): ', 'plik .desktop (dowód pomocniczy): '),
    ('auxiliary installed package, not proof of app: ', 'zainstalowany pakiet pomocniczy; to nie dowód obecności aplikacji: '),
    ('desktop entry exists; may be stale: ', 'istnieje plik .desktop, ale może być nieaktualny: '),
    ('historical removed package: ', 'historycznie odinstalowany pakiet: '),
    ('removed in pacman.log: ', 'odinstalowany według pacman.log: '),
    ('removed in dpkg.log: ', 'odinstalowany według dpkg.log (APT/dpkg): '),
    ('mentioned in user session config: ', 'wzmianka w konfiguracji sesji użytkownika: '),
)


def localize_evidence(reason: str, language: str = 'pl') -> str:
    """Translate known evidence labels for display without altering identifiers."""
    if language != 'pl':
        return reason
    if reason in _PL_EVIDENCE_EXACT:
        return _PL_EVIDENCE_EXACT[reason]
    for english, polish in (
            ('AUR name listed: ', 'Nazwa dostępna w AUR: '),
            ('foreign name not listed in AUR: ', 'Nazwa pakietu spoza repozytoriów nieobecna w AUR: '),
            ('foreign origin unverified: ', 'Niezweryfikowane pochodzenie pakietu spoza repozytoriów: ')):
        if reason.startswith(english):
            return polish + reason[len(english):].replace(
                ' (build origin unverified)', ' (pochodzenie kompilacji niezweryfikowane)').replace(
                ' (local, renamed or removed)', ' (lokalny, przemianowany lub usunięty)')
    for english, polish in _PL_EVIDENCE_PREFIXES:
        if reason.startswith(english):
            remainder = reason[len(english):].replace(' (match: ', ' (dopasowanie: ')
            return polish + remainder
    return reason
