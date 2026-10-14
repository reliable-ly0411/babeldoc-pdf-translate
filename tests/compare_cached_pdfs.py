"""Compare cached-run PDF content/rendering; do not certify translation quality."""
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

import pymupdf


def compare(first, second, dpi=72):
    rows = []
    with pymupdf.open(first) as a, pymupdf.open(second) as b:
        count_equal = len(a) == len(b)
        for i, (x, y) in enumerate(zip(a, b)):
            text = unicodedata.normalize('NFC', x.get_text())
            other = unicodedata.normalize('NFC', y.get_text())
            pix = x.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
            other_pix = y.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
            rows.append({'page': i + 1, 'text_equal': text == other,
                         'dimensions_equal': x.rect == y.rect,
                         'pixels_equal': pix.samples == other_pix.samples,
                         'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                         'pixels_sha256': hashlib.sha256(pix.samples).hexdigest()})
    return {'first_sha256': hashlib.sha256(first.read_bytes()).hexdigest(),
            'second_sha256': hashlib.sha256(second.read_bytes()).hexdigest(),
            'byte_equal': first.read_bytes() == second.read_bytes(),
            'page_counts_equal': count_equal, 'dpi': dpi, 'pages': rows,
            'passed': count_equal and all(r['text_equal'] and r['pixels_equal'] and r['dimensions_equal'] for r in rows),
            'scope': 'Fixed-cache content/pixel comparison only; byte metadata may differ. Visual and semantic QA are separate.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--dpi', type=int, default=72, choices=[72, 100, 150])
    args = parser.parse_args()
    result = compare(args.first, args.second, args.dpi)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'pages'}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
