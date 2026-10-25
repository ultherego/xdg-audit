"""Pure presentation helpers shared by GTK, Qt and Tk; no GUI dependencies."""
from __future__ import annotations
from collections import Counter
from typing import Any, Iterable


def details_text(items: Iterable[Any], human, focused: Any = None, language: str = "pl") -> str:
    """Show the row explicitly clicked; aggregate when multiple checkboxes are checked.

    A clicked row is navigation and must not be overridden by checkbox choices,
    whether one or many. Calling without `focused` reports checkbox selection,
    including a multi-item summary, per the UI contract.
    """
    selected = list(items)
    if focused is not None:
        selected = [focused]
    if not selected:
        return ''
    if len(selected) == 1:
        it = selected[0]
        if language == 'en':
            reasons = '\n'.join('• ' + str(reason) for reason in it.reasons) or '• No evidence available.'
            return (f'{it.path.name}\n\nStatus: {it.state}\nSize: {human(it.bytes)}\n'
                    f'Scope: {it.scope}\nPath: {it.path}\n\nEvidence:\n{reasons}')
        reasons = '\n'.join('• ' + str(reason) for reason in it.reasons) or '• Nie ustalono przesłanek.'
        return (f'{it.path.name}\n\nStatus: {it.state}\nRozmiar: {human(it.bytes)}\n'
                f'Zakres: {it.scope}\nŚcieżka: {it.path}\n\nPrzesłanki:\n{reasons}')
    total = sum(max(0, it.bytes) for it in selected)
    count = len(selected)
    noun = 'pozycje' if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else 'pozycji'
    counts = Counter(it.state for it in selected)
    mix = ' · '.join(f'{key}: {counts[key]}' for key in
                     ('CANDIDATE','REVIEW','UNKNOWN','ACTIVE','PROTECTED') if counts[key])
    sample = '\n'.join(f'• {it.path.name}  [{it.state}]  {human(it.bytes)}' for it in selected[:25])
    suffix = f'\n… i {len(selected) - 25} dalszych' if len(selected) > 25 else ''
    if language == 'en':
        suffix = f'\n… and {len(selected) - 25} more' if len(selected) > 25 else ''
        return (f'{count} items selected\n\nTotal: {human(total)}\n'
                f'Statuses: {mix}\n\nSelected items:\n{sample}{suffix}\n\n'
                'This is a preview. Moving items to quarantine requires a separate action and confirmation.')
    return (f'Zaznaczono {count} {noun}\n\nŁącznie: {human(total)}\n'
            f'Statusy: {mix}\n\nWybrane elementy:\n{sample}{suffix}\n\n'
            'To podgląd. Przenoszenie do kwarantanny jest osobną operacją i wymaga potwierdzenia.')


def click_is_inside_control(picked: Any, row: Any, control_type: type) -> bool:
    """True if a pointer event targets a checkbox inside a results row.

    This distinguishes a checkbox (bulk selection) from the rest of the row
    (inspector navigation) without relying on pixel-coordinate thresholds.
    """
    while picked is not None:
        if isinstance(picked, control_type):
            return True
        if picked is row:
            break
        picked = picked.get_parent()
    return False


def open_item_location(path, home):
    """Open a user-owned local directory without a shell or URL interpolation.

    The selected entry is *not* opened/executed: only its parent directory.
    Symlinks escaping the user's home and missing entries are rejected.
    """
    from pathlib import Path
    import shutil
    import subprocess
    item, root = Path(path), Path(home).resolve(strict=True)
    if not item.is_absolute() or not item.exists():
        raise ValueError('Item does not exist')
    actual = item.resolve(strict=True)
    if root not in actual.parents or root not in item.resolve(strict=False).parents:
        raise ValueError('Refusing to open a location outside HOME')
    folder = actual.parent
    opener = shutil.which('xdg-open')
    if not opener:
        raise RuntimeError('xdg-open is unavailable')
    # xdg-open delegates to the configured file manager. No shell.
    subprocess.Popen([opener, str(folder)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return folder
