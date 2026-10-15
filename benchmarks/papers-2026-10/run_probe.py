#!/usr/bin/env python3
"""Explicit bounded compatibility probe; not a new stable job parameter."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import pdf_translate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path, help='Locally prepared job with a new output directory')
    parser.add_argument('--engine', required=True)
    parser.add_argument('--probe', required=True, choices=('skip-formula-offset-calculation', 'disable-rich-text-translate'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    original = pdf_translate.prepare
    def prepare(path):
        job, source, output, flags = original(path)
        flags.append('--' + args.probe)
        return job, source, output, flags
    pdf_translate.prepare = prepare
    result = pdf_translate.run_job(args.job, args.engine, args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get('status') == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
