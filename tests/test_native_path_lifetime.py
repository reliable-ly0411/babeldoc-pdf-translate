"""Repeated native replay must retain interpreter-owned clipping/fill paths."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


PROBE = r'''
import json, sys
import pymupdf as fitz
sys.path.insert(0, sys.argv[1])
import pdf_objects
kind = sys.argv[2]
for iteration in range(30):
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=300)
        page.insert_text((40,80), 'q', fontsize=12)
        if kind == 'clip':
            ref = page.get_contents()[-1]
            doc.update_stream(ref, b'q 40 210 3 30 re W n\n' + doc.xref_stream(ref) + b'\nQ')
        else:
            page.draw_rect(fitz.Rect(200,100,210,110), fill=(1,1,1), color=None)
        before = page.get_pixmap().samples
        first = pdf_objects.inventory(page)
        second = pdf_objects.inventory(page)
        assert first == second
        assert len(first['glyphs']) == 1
        assert first['glyphs'][0]['visibility'] == ('partially_clipped' if kind == 'clip' else 'visible_candidate')
        assert page.get_pixmap().samples == before
print(json.dumps({'completed':30, 'kind':kind}))
'''


class NativePathLifetimeTests(unittest.TestCase):
    def replay(self, kind):
        # A native allocator abort must fail this child rather than kill the
        # complete regression runner and discard its preceding diagnostics.
        result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', PROBE,
            str(Path(__file__).resolve().parents[1] / 'scripts'), kind],
            capture_output=True, text=True, encoding='utf-8', timeout=40)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        self.assertEqual(json.loads(result.stdout), {'completed':30, 'kind':kind})

    def test_clipping_paths_survive_repeated_inventory_and_render(self):
        self.replay('clip')

    def test_fill_paths_survive_repeated_inventory_and_render(self):
        self.replay('fill')


if __name__ == '__main__':
    unittest.main()
