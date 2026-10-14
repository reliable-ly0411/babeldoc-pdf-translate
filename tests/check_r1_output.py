"""Task-specific coverage gate; it never certifies mathematical/visual quality."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import pymupdf

SOURCE_HASH = '916fdaafc3b44143a9744481d079744f773d73d06372f82b1dba1076525927f2'


def inspect(source, output):
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError('Use the fixed Nature 11-page R1 source')
    issues, rows = [], []
    with pymupdf.open(source) as original, pymupdf.open(output) as translated:
        if len(original) != 11 or len(translated) != 11:
            raise ValueError('Expected 11 physical pages in this side-by-side/mono sample')
        for i, (src, dst) in enumerate(zip(original, translated)):
            dual = abs(dst.rect.width - 2 * src.rect.width) < 2
            clip = pymupdf.Rect(src.rect.width, 0, dst.rect.width, dst.rect.height) if dual else dst.rect
            text = dst.get_text(clip=clip)
            cjk = sum('\u4e00' <= c <= '\u9fff' for c in text)
            leak = bool(re.search(r'\{v\d+\}|pdftranslate_code_|<\s*/?\s*style\b', text))
            required = i != 5  # Physical p6 is the intentionally retained author/affiliation list.
            if required and cjk < 20:
                issues.append({'page': i + 1, 'kind': 'missing Chinese coverage', 'cjk_chars': cjk})
            if leak:
                issues.append({'page': i + 1, 'kind': 'PDF markup leaked'})
            spans = [s for b in dst.get_text('dict', clip=clip)['blocks'] if b['type'] == 0
                     for line in b['lines'] for s in line['spans'] if any('\u4e00' <= c <= '\u9fff' for c in s['text'])]
            rows.append({'page': i + 1, 'cjk_chars': cjk, 'minimum_cjk_font_pt': min([s['size'] for s in spans], default=None),
                         'image_objects': len(dst.get_images()), 'requires_visual_review': True})
    return {'source_sha256': SOURCE_HASH, 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'coverage_passed': not issues, 'pages': rows, 'issues': issues,
            'scope': 'Coverage and leaked-markup screen only; all output pages still require visual/semantic review.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path); p.add_argument('output', type=Path); p.add_argument('report', type=Path)
    a = p.parse_args(); r = inspect(a.source, a.output)
    a.report.write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'coverage_passed': r['coverage_passed'], 'issues': r['issues']}, ensure_ascii=False))
    return 0 if r['coverage_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
