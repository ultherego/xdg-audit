"""Pure report comparison formatting, independent from all GUI frameworks."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path


def suggested_export_path(home: Path, when: datetime | None = None) -> Path:
    timestamp = (when or datetime.now()).strftime('%Y%m%d-%H%M%S-%f')
    return home / f'xdg-audit-{timestamp}.json'


def summary(changes: list[dict], lang: str = 'pl') -> str:
    if not changes:
        return 'No classification or evidence changes.' if lang == 'en' else 'Brak zmian klasyfikacji lub przesłanek.'
    header = (f'{len(changes)} differences:' if lang == 'en' else f'{len(changes)} zmian:')
    details = []
    for change in changes:
        details.append(f"{change['old_state']} → {change['new_state']}  {change['path']}")
        details += [f'  - {r}' for r in change.get('old_reasons',[]) if r not in change.get('new_reasons',[])]
        details += [f'  + {r}' for r in change.get('new_reasons',[]) if r not in change.get('old_reasons',[])]
    return header + '\n\n' + '\n'.join(details)
