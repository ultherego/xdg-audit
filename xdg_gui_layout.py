"""Toolkit-independent layout policy; importing this module never opens a GUI."""

DIALOG_PADDING = 20
SCREEN_MARGIN = 24
OPTIONAL_SCOPES = frozenset(('flatpak', 'snap'))


def visible_optional_scopes(items, stats):
    """Hide absent integrations only when their user-data scope is empty.

    Failed or unknown probes remain visible. Leftovers must remain accessible
    even when the corresponding package manager has been uninstalled.
    Call after a complete scan, independently of search/status filters.
    """
    populated = {item.scope for item in items}
    health = stats.get('installed_sources', {})
    return {scope for scope in OPTIONAL_SCOPES
            if scope in populated or health.get(scope) != 'absent'}


def dialog_limits(width, height):
    """Leave screen-edge space and room for window decorations."""
    return max(160, width - 2 * SCREEN_MARGIN), max(120, height - 2 * SCREEN_MARGIN - 48)
