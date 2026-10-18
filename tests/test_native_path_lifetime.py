"""Repeated native replay must retain interpreter-owned clipping/fill paths."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import weakref
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pdf_objects


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
        if kind == 'fill':
            assert first['vector_paths'][-1]['native_opaque_rectangle']
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

    def test_borrowed_matrix_view_retains_its_owner_during_native_queries(self):
        # SWIG internal() does not keep its parent alive. Model that lifetime
        # explicitly; Windows may leave freed identity bytes readable whereas
        # Linux may reuse them before the low-level query.
        native_matrix=pdf_objects.m.FzMatrix
        class Matrix:
            def __new__(cls,*args):
                return native_matrix(*args) if args else super().__new__(cls)
            def internal(self):return weakref.ref(self)
        seen=[]
        def live(view):
            self.assertIsNotNone(view(), 'borrowed matrix owner was released')
            seen.append('live')
        def rectangle(path, view):live(view);return True
        def bounds(path, stroke, view):live(view);return SimpleNamespace(x0=0,y0=0,x1=10,y1=10)
        device=SimpleNamespace(clip_stack=[],group_stack=[],opaque_covers=[],seqno=0)
        with mock.patch.object(pdf_objects.m,'FzMatrix',Matrix), \
             mock.patch.object(pdf_objects.m,'ll_fz_path_is_rect',side_effect=rectangle), \
             mock.patch.object(pdf_objects.m,'ll_fz_bound_path',side_effect=bounds), \
             mock.patch.object(pdf_objects.m,'fz_device_current_scissor',return_value=SimpleNamespace(x0=0,y0=0,x1=100,y1=100)):
            pdf_objects.GlyphDevice.fill_path(device,None,None,False,
                SimpleNamespace(a=1,b=0,c=0,d=1,e=0,f=0),None,None,1,None)
        self.assertEqual(seen,['live','live'])
        self.assertEqual(len(device.opaque_covers),1)


if __name__ == '__main__':
    unittest.main()
