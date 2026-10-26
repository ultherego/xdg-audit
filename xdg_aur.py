"""Read public AUR name availability without submitting installed package names.

Availability is a provenance hint, never proof of who built an installed package
and never authorization for quarantine. Cache only in memory; scans write nothing.
"""
from dataclasses import dataclass
import gzip
import io
import re
import threading
import time
import urllib.error
import urllib.request
import zlib

INDEX_URL = 'https://aur.archlinux.org/packages.gz'
MAX_COMPRESSED = 4 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024
_NAME = re.compile(r'[a-z0-9][a-z0-9+_.@-]{0,199}')
_cache = None
_lock = threading.Lock()


@dataclass(frozen=True)
class ForeignClassification:
    status: str
    listed: frozenset[str] = frozenset()
    unlisted: frozenset[str] = frozenset()
    unknown: frozenset[str] = frozenset()
    note: str = ''

    def summary(self):
        return {'status': self.status, 'aur_name_matches': len(self.listed),
                'not_listed_in_aur': len(self.unlisted), 'origin_unknown': len(self.unknown),
                'verified_build_origin': False, 'note': self.note}


def _read_index():
    request = urllib.request.Request(INDEX_URL,
        headers={'User-Agent': 'xdg-audit public AUR name availability', 'Accept-Encoding': 'identity'})
    deadline = time.monotonic() + 8
    data = bytearray()
    with urllib.request.urlopen(request, timeout=3) as response:
        read = getattr(response, 'read1', response.read)
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('AUR metadata time limit exceeded')
            chunk = read(min(64 * 1024, MAX_COMPRESSED + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_COMPRESSED:
                raise ValueError('oversized AUR metadata download')
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as archive:
        expanded = archive.read(MAX_EXPANDED + 1)
    if len(expanded) > MAX_EXPANDED:
        raise ValueError('oversized expanded AUR metadata')
    names = set()
    for line in expanded.decode('ascii').splitlines():
        if not line or line.startswith('#'):
            continue
        if not _NAME.fullmatch(line):
            raise ValueError('invalid AUR metadata record')
        names.add(line)
    if not names:
        raise ValueError('empty AUR metadata index')
    return frozenset(names)


def classify_foreign(names):
    """Compare names to one bounded public index; failures preserve unknown origin."""
    global _cache
    foreign = frozenset(names)
    if not foreign:
        return ForeignClassification('absent', note='no foreign packages to classify')
    with _lock:
        now = time.monotonic()
        if _cache is None or now >= _cache[0]:
            try:
                index = _read_index()
                _cache = (now + 3600, 'ok', index, 'public AUR index; availability is not build provenance')
            except (TimeoutError, urllib.error.URLError, OSError, ValueError, UnicodeError,
                    EOFError, zlib.error) as exc:
                status = 'timeout' if isinstance(exc, TimeoutError) else 'failed'
                _cache = (now + 60, status, frozenset(),
                          'AUR metadata unavailable; foreign origin remains unknown')
        _, status, index, note = _cache
    if status != 'ok':
        return ForeignClassification(status, unknown=foreign, note=note)
    return ForeignClassification('ok', listed=foreign & index, unlisted=foreign - index,
        note='public AUR name availability; unlisted may mean local, renamed or removed; build origin unverified')


def enrich_inventory(inventory):
    """Only scan/diagnostic callers request online hints; MOVE never calls this.

    Legacy caller-created inventories remain offline. Explicit OS-selected
    inventories can carry precomputed metadata for offline integrations.
    """
    if getattr(inventory, 'aur', None) is not None:
        return inventory
    if (getattr(inventory, 'native_source', None) == 'pacman'
            and getattr(inventory, 'native_source_explicit', False)
            and getattr(inventory, 'status', {}).get('pacman_foreign') == 'ok'):
        inventory.aur = classify_foreign(inventory.foreign)
    return inventory


def provenance_summary(inventory):
    metadata = getattr(inventory, 'aur', None)
    if metadata is not None:
        return metadata.summary()
    return ForeignClassification('absent', unknown=frozenset(getattr(inventory, 'foreign', ())),
        note='AUR availability not queried; no build provenance inferred').summary()
