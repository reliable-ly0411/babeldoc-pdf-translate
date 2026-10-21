"""Optional real-document evidence stays separate from the public source distribution."""
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def evidence_file(relative):
    path = ROOT / relative
    if path.is_file():
        return path
    external = os.environ.get('BABELDOC_EXTRA_TEST_DATA')
    if external:
        path = Path(external) / relative
        if path.is_file():
            return path
    raise unittest.SkipTest('External real-document evidence not bundled: ' + relative +
        '; set BABELDOC_EXTRA_TEST_DATA to its independently verified root')
