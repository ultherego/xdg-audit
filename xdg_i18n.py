"""Tiny built-in PL/EN UI catalog. Status identifiers and file paths stay untranslated.

Language is a user preference, not inferred from the GUI backend. Fallback to
source Polish for missing keys so the GUI never loses a label.
"""
from __future__ import annotations

LANGUAGES = {'pl': 'Polski', 'en': 'English'}
EN = {
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
    'Błąd skanowania': 'Scan error',
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
        return f'{number} entries'
    # Polish count forms for concise UI counters.
    word = 'pozycja' if number == 1 else ('pozycje' if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14) else 'pozycji')
    return f'{number} {word}'

def selected_count(number: int, language: str) -> str:
    return f'{number} selected' if language == 'en' else f'{number} wybranych'
