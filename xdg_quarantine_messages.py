"""Localized quarantine refusal details shared by all graphical backends."""
from xdg_i18n import translate, format_message
from xdg_quarantine_lifecycle import QuarantineIdentityMismatch, LegacyQuarantineJournal


def quarantine_error_details(error, language='pl'):
    def tr(text):
        return translate(text, language)
    if isinstance(error, LegacyQuarantineJournal):
        return (format_message('Operacja: {run_id}', language, run_id=error.run_id) + '\n\n' +
                tr('To starszy dziennik v2, bez zapisanych tożsamości i sum plików. Aby usunąć jego pozostałe dane, użyj „Zatwierdź stan…” (ADOPT), a następnie osobno „Usuń trwale…” (PURGE). Historia stanie się dostępna do wyczyszczenia po usunięciu lub przywróceniu danych.'))
    if isinstance(error, QuarantineIdentityMismatch):
        def identity(label, values):
            return (tr(label) + f' device={values[0]}, inode={values[1]}, type={values[2]}')
        return '\n\n'.join((
            tr('Tożsamość obiektu w kwarantannie nie zgadza się z dziennikiem.'),
            format_message('Operacja: {run_id}', language, run_id=error.run_id) + '\n' + str(error.path),
            identity('Zapisano:', error.expected) + '\n' + identity('Odczytano teraz:', error.actual),
            tr('Sama nazwa ścieżki nie potwierdza tożsamości plików. Skopiowanie lub odtworzenie katalogu może zmienić te numery; sam komunikat nie rozstrzyga przyczyny.'),
            tr('To nie jest błąd uprawnień. ACCESS ani ADOPT nie zatwierdzają podmienionego obiektu. PURGE pozostaje zablokowany.'),
            tr('Skopiuj szczegóły z tego okna do dalszej diagnozy. Nie zmieniaj identyfikatorów w manifest.json.'),
            tr('Jeżeli zmienił się tylko numer urządzenia, użyj „Sprawdź dostęp…”. Osobna operacja REVALIDATE wymaga zgodności pełnego spisu plików i sum SHA-256.')))
    return str(error) + '\n\n' + tr('Operacja została zatrzymana. Sprawdź szczegóły błędu i dziennik przed ponowną próbą.')


def identity_issue_details(issue, run_id, language='pl'):
    if issue.get('expected_identity') is None or issue.get('actual_identity') is None:
        return str(issue.get('code', '')) + '\n' + str(issue.get('path', ''))
    details = quarantine_error_details(QuarantineIdentityMismatch(
        run_id, issue['path'], issue['expected_identity'], issue['actual_identity']), language)
    context = issue.get('filesystem', {})
    mount = context.get('mount') or {}
    binding = context.get('filesystem_identity') or {}
    if mount or binding:
        details += '\n\n' + format_message('System plików: {kind}; UUID: {uuid}; subwolumen: {subvolume}',
            language, kind=mount.get('filesystem_type', binding.get('kind', '?')),
            uuid=binding.get('fsid', '?'), subvolume=binding.get('subvolume_id', '?'))
    if issue.get('revalidation_error'):
        details += '\n\n' + format_message('Ponowna weryfikacja zablokowana: {error}',
                                           language, error=issue['revalidation_error'])
    return details


def device_revalidation_details(plan, language='pl'):
    text = '\n\n'.join((
        format_message('Operacja: {run_id}', language, run_id=plan['run_id']),
        format_message('Numer urządzenia: {before} → {after}; zweryfikowane pozycje: {count}.',
                       language, before=plan['old_device'], after=plan['new_device'], count=plan['entries']),
        translate('Pełny spis nazw, inode, typów, rozmiarów i sum SHA-256 zgadza się po zmianie wyłącznie numeru urządzenia.', language),
        translate('REVALIDATE zapisze zweryfikowaną aktualną tożsamość urządzenia w dzienniku. Nie usunie plików. PURGE wymaga osobnej weryfikacji i osobnego potwierdzenia.', language)))
    if not plan['historical_binding_verified']:
        text += '\n\n' + translate('STARY DZIENNIK: nie zapisano historycznego UUID systemu plików. Zgodność danych i inode nie dowodzi, że to ten sam historyczny system plików. Zatwierdzasz zweryfikowane dane w AKTUALNYM systemie plików.', language)
    return text
