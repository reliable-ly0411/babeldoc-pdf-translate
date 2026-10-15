#!/usr/bin/env python3
"""Reproduce named paper cases; native model calls require explicit --execute.

Provider credentials stay in the installed native client. Each invocation owns
a new destination directory; source/reference PDFs are never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', nargs='+', help='Case IDs from cases/*.json')
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--codex-bin', default='codex')
    parser.add_argument('--dsh-package', type=Path)
    parser.add_argument('--node-bin', default='node')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    available = {p.stem: p for p in (HERE / 'cases').glob('*.json')}
    if len(set(args.case)) != len(args.case) or set(args.case) - available.keys():
        parser.error('Choose unique case IDs: ' + ', '.join(sorted(available)))
    for source in json.loads((HERE / 'sources.json').read_text()):
        data = (HERE / source['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            parser.error('Source hash mismatch: ' + source['id'])
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    failed = False
    for name in args.case:
        path = available[name]
        job = json.loads(path.read_text())
        for key in ('input', 'prompt_file'):
            if key in job:
                job[key] = str((path.parent / job[key]).resolve())
        job['glossaries'] = [str((path.parent / p).resolve()) for p in job.get('glossaries', [])]
        job['output'] = str(destination / name)
        provider = job['provider']
        provider['cache_dir'] = str(destination / 'private-cache' / provider['type'] / Path(job['input']).stem)
        if provider['type'] == 'dsh':
            if args.dsh_package is None:
                parser.error('DSH cases need --dsh-package pointing to the installed CLI package.json')
            provider.update(dsh_package=str(args.dsh_package.resolve()), node_bin=args.node_bin)
        else:
            provider['codex_bin'] = args.codex_bin
        local = destination / (name + '.json')
        local.write_text(json.dumps(job, ensure_ascii=False, indent=2) + '\n')
        command = [sys.executable, str(ROOT / 'scripts/pdf_translate.py'), 'run',
                   str(local), '--engine', args.engine]
        if args.execute:
            command.append('--execute')
        result = subprocess.run(command, capture_output=True, text=True)
        (destination / (name + '.result.json')).write_text(result.stdout)
        (destination / (name + '.stderr.txt')).write_text(result.stderr)
        print(f'{name}: exit={result.returncode}; execute={args.execute}', flush=True)
        if result.returncode:
            failed = True
            break  # Do not spend more quota after an unresolved failure.
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
