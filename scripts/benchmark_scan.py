#!/usr/bin/env python3
"""Synthetic, temporary-home scan benchmark. Never touches the real HOME."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xdg_audit as engine


def benchmark(count):
    if not 1 <= count <= 10000:
        raise ValueError('count must be between 1 and 10000')
    with tempfile.TemporaryDirectory(prefix='xdg-audit-benchmark-') as temp:
        home = Path(temp)
        config = home / '.config'
        config.mkdir()
        session = config / 'niri'
        session.mkdir()
        (session / 'config.kdl').write_text('spawn "alpha-browser"\n')
        for n in range(count):
            folder = config / f'bench-app-{n:05}'
            folder.mkdir()
            (folder / 'settings.ini').write_text(f'key={n}\n')
        packages = {'unrelated-installed-package'}
        names = (packages, set(), set(), set(), set(), set(), set(), {'unrelatedinstalledpackage'})
        start = time.perf_counter()
        with patch.object(engine, 'read_active_names', return_value=names), \
             patch.object(engine, 'parse_removals', return_value={}):
            items, _, stats = engine.scan(home, ['config'], set(), {}, True)
        seconds = time.perf_counter() - start
        assert len(items) == count + 1
        return {
            'benchmark': 'synthetic-quick-scan',
            'items': len(items),
            'seconds': round(seconds, 5),
            'items_per_second': round(len(items) / seconds, 1),
            'phase_times_ms': stats.get('phase_times_ms', {}),
            'writes_to_real_home': False,
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=350)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.count), indent=2, sort_keys=True))
