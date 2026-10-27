"""Localized quarantine refusal details shared by all graphical backends."""
from xdg_i18n import translate, format_message
from xdg_quarantine_lifecycle import QuarantineIdentityMismatch


def quarantine_error_details(error, language='pl'):
    def tr(text):
        return translate(text, language)
    if isinstance(error, QuarantineIdentityMismatch):
        def identity(label, values):
            return (tr(label) + f' device={values[0]}, inode={values[1]}, type={values[2]}')
        return '\n\n'.join((
            tr('Tożsamość obiektu w kwarantannie nie zgadza się z dziennikiem.'),
            format_message('Operacja: {run_id}', language, run_id=error.run_id) + '\n' + str(error.path),
            identity('Zapisano:', error.expected) + '\n' + identity('Odczytano teraz:', error.actual),
            tr('Sama nazwa ścieżki nie potwierdza tożsamości plików. Skopiowanie lub odtworzenie katalogu może zmienić te numery; sam komunikat nie rozstrzyga przyczyny.'),
            tr('To nie jest błąd uprawnień. ACCESS ani ADOPT nie zatwierdzają podmienionego obiektu. PURGE pozostaje zablokowany.'),
            tr('Skopiuj szczegóły z tego okna do dalszej diagnozy. Nie zmieniaj identyfikatorów w manifest.json.')))
    return str(error) + '\n\n' + tr('Operacja została zatrzymana. Sprawdź szczegóły błędu i dziennik przed ponowną próbą.')


def identity_issue_details(issue, run_id, language='pl'):
    if issue.get('expected_identity') is None or issue.get('actual_identity') is None:
        return str(issue.get('code', '')) + '\n' + str(issue.get('path', ''))
    return quarantine_error_details(QuarantineIdentityMismatch(
        run_id, issue['path'], issue['expected_identity'], issue['actual_identity']), language)
