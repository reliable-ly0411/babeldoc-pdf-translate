"""Keep the installable nested skill byte-identical to the standalone sources."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
FILES = ['SKILL.md', 'requirements.txt', 'scripts/pdf_translate.py']
DIRS = ['references', 'assets', 'agents']

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    destination = ROOT / 'skills' / 'babeldoc-pdf-translate'
    paths = [ROOT / f for f in FILES]
    paths += [f for d in DIRS for f in (ROOT/d).rglob('*') if f.is_file()]
    for source in paths:
        target = destination / source.relative_to(ROOT)
        if args.check:
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise SystemExit(f'Out of sync: {target.relative_to(ROOT)}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    print(f'{len(paths)} skill resources verified' if args.check else f'{len(paths)} skill resources synchronized')

if __name__ == '__main__':
    main()
