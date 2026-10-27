#!/usr/bin/env python3
"""Reject a release tag that disagrees with the source or package version."""
import os
from pathlib import Path

from install_payload import package_version, version


def check(root, tag=None):
    value = version(root)
    if tag is not None and tag != 'v' + value:
        raise ValueError('Release tag must exactly match source VERSION: v' + value)
    return {family: package_version(value, family) for family in ('deb', 'rpm', 'arch')}


if __name__ == '__main__':
    tag = os.environ.get('GITHUB_REF_NAME') if os.environ.get('GITHUB_REF_TYPE') == 'tag' else None
    print(check(Path(__file__).resolve().parents[1], tag))
