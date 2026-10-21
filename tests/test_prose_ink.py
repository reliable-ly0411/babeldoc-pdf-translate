"""Native fallback-font clipping after actual writes, with immutable old PDFs."""
import sys,unittest
from pathlib import Path
from unittest import mock
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import source_repair as source,prose_ink,pdf_objects as objects


class ProseInkTests(unittest.TestCase):
    def page(self):
        d=fitz.open();self.addCleanup(d.close);return d.new_page(width=300,height=300)

    def test_real_cjk_ink_overflow_is_not_layout_success(self):
        p=self.page();result=p.insert_htmlbox((40,50,65,62.4),'其中',
            css='body{margin:0;padding:0;font-family:sans-serif;font-size:10pt;line-height:1;}',scale_low=1)
        self.assertGreaterEqual(result[0],0)
        check=prose_ink.check(p);self.assertFalse(check['passed'])
        self.assertIn('NEW_PROSE_CLIPPED_INK',[e['code'] for e in check['issues']])

    def test_new_fit_checks_actual_cjk_paint_after_commit(self):
        p=self.page();unit={'source':'Among','font_size':10,'boxes':[[40,51.2,65,61.2]]}
        fit=source.fit_prose(p,unit,'其中',commit=True,validated=True)
        self.assertIsNotNone(fit);self.assertTrue(fit['native_ink']['passed'])
        self.assertTrue(prose_ink.check(p)['passed']);self.assertIn('其中',p.get_text())

    def test_old_inherited_clipping_is_not_mislabeled_as_new_prose(self):
        p=self.page();p.insert_text((40,80),'q',fontsize=12)
        ref=p.get_contents()[-1];p.parent.update_stream(ref,b'q 40 210 3 30 re W n\n'+p.parent.xref_stream(ref)+b'\nQ')
        boundary=prose_ink.glyph_count(p)
        p.insert_htmlbox((40,110,200,150),'这是新文字。',css='body{font-size:10pt;line-height:1.2;}')
        self.assertFalse(prose_ink.check(p)['passed'])
        self.assertTrue(prose_ink.check(p,first_glyph=boundary)['passed'])

    def test_missing_masks_do_not_pass_a_successful_layout(self):
        p=self.page();p.insert_text((40,80),'TEXT')
        with mock.patch.object(objects.GlyphDevice,'outline',return_value=None):check=prose_ink.check(p)
        self.assertFalse(check['passed']);self.assertIn('NEW_PROSE_UNREADABLE_GLYPH',[e['code'] for e in check['issues']])

    def test_empty_output_and_invalid_append_boundary_are_rejected(self):
        p=self.page();self.assertFalse(prose_ink.check(p)['passed'])
        with self.assertRaisesRegex(ValueError,'INVALID_NEW_PROSE_GLYPH_BOUNDARY'):prose_ink.check(p,first_glyph=1)


if __name__=='__main__':unittest.main()
