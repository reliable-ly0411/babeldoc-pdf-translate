"""Tests execute the patched upstream renderer/typesetter with small IL inputs."""
from types import SimpleNamespace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from babeldoc.format.pdf.document_il import il_version_1 as il
from babeldoc.format.pdf.document_il.backend.pdf_creater import CharacterRenderUnit
from babeldoc.format.pdf.document_il.midend.typesetting import Typesetting, TypesettingUnit
from babeldoc.format.pdf.high_level import merge_watermark_doc
from babeldoc.format.pdf.result_merger import ResultMerger
from babeldoc.format.pdf.translation_config import WatermarkOutputMode, TranslateResult


class RuntimeBehaviorTests(unittest.TestCase):
    def test_merge_watermark_preserves_alternating_pairs_and_other_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.no_watermark.zh-CN.dual.pdf'
            with pymupdf.open() as doc:
                for i in range(6):
                    doc.new_page().insert_text((20, 20), 'page' + str(i))
                doc.save(path)
            with pymupdf.open() as watermarked:
                watermarked.new_page().insert_text((20, 20), 'new-original')
                watermarked.new_page().insert_text((20, 20), 'new-translated-watermark')
                data = io.BytesIO(watermarked.tobytes())
            with patch('babeldoc.format.pdf.high_level.PDFCreater.save_pdf_with_timeout',
                       side_effect=lambda doc, dest, **kw: doc.save(dest)):
                result = merge_watermark_doc(path, data, SimpleNamespace(skip_clean=False), page_index=1)
            with pymupdf.open(result) as doc:
                self.assertEqual([p.get_text().strip() for p in doc],
                                 ['page0', 'page1', 'new-original', 'new-translated-watermark', 'page4', 'page5'])

    def test_split_output_filenames_cover_watermark_modes(self):
        for mode in (WatermarkOutputMode.Both, WatermarkOutputMode.NoWatermark):
            with self.subTest(mode=mode):
                config = SimpleNamespace(input_file='source.pdf', debug=False, lang_out='zh-CN',
                                         no_mono=False, no_dual=False, save_auto_extracted_glossary=False,
                                         watermark_output_mode=mode)
                result = TranslateResult(Path('a.pdf'), Path('b.pdf'), None)
                result.no_watermark_mono_pdf_path = Path('c.pdf') if mode == WatermarkOutputMode.Both else result.mono_pdf_path
                result.no_watermark_dual_pdf_path = Path('d.pdf') if mode == WatermarkOutputMode.Both else result.dual_pdf_path
                with patch.object(ResultMerger, '_merge_pdfs', side_effect=lambda paths, name, **kw: Path(name)):
                    merged = ResultMerger(config).merge_results({0: result})
                self.assertEqual(merged.no_watermark_mono_pdf_path.name, 'source.no_watermark.zh-CN.mono.pdf')
                self.assertEqual(merged.no_watermark_dual_pdf_path.name, 'source.no_watermark.zh-CN.dual.pdf')

    def test_signed_numbers_never_split_across_lines(self):
        font = pymupdf.Font('helv')
        style = il.PdfStyle(font_id='base', font_size=10)
        layout = Typesetting.__new__(Typesetting)
        layout.font_mapper = SimpleNamespace(base_font=font)
        for number in ('-0.25', '+12.5', '1.25e-3', '12,345.67'):
            for english in (True, False):
                with self.subTest(number=number, english=english):
                    text = 'AAAA ' + number + ' m'
                    units = [TypesettingUnit(unicode=c, font=font, font_size=10, style=style, xobj_id=0) for c in text]
                    width = max(40, font.text_length(number, fontsize=10) + 1)
                    placed, fits = layout._layout_typesetting_units(units, il.Box(x=0, y=0, x2=width, y2=100), 1, 1.2,
                                                                    SimpleNamespace(first_line_indent=False), english)
                    self.assertTrue(fits)
                    numeric = [u for u in placed if u.try_get_unicode() in set(number)]
                    self.assertEqual(len({round(u.box.y, 4) for u in numeric}), 1)
                    self.assertTrue(all(u.box.x >= 0 and u.box.x2 <= width + .01 for u in numeric))

    def test_actualtext_keeps_distinct_unicode_values(self):
        for value in ('-', '\u2011', '\u2212', '\U0001f600'):
            with self.subTest(value=value):
                char = il.PdfCharacter(char_unicode=value, pdf_character_id=45, xobj_id=0, vertical=False,
                                       box=il.Box(x=10, y=20, x2=20, y2=30),
                                       pdf_style=il.PdfStyle(font_id='F1', font_size=10))
                context = SimpleNamespace(xobj_encoding_length_map={}, page_encoding_length_map={'F1': 1},
                                          check_font_exists=False, all_encoding_length_map={},
                                          pdf_creator=SimpleNamespace(render_graphic_state=lambda *_: None))
                stream = []
                CharacterRenderUnit(char, 0).render(stream, context)
                data = b''.join(stream)
                self.assertIn((b'\xfe\xff' + value.encode('utf-16-be')).hex().encode(), data)
                self.assertEqual(data.count(b'BDC'), 1)
                self.assertEqual(data.count(b'EMC'), 1)

    def test_missing_font_encoding_leaves_no_open_pdf_state(self):
        char = il.PdfCharacter(char_unicode='A', pdf_character_id=65, xobj_id=0, vertical=False,
                               box=il.Box(x=10, y=20, x2=20, y2=30),
                               pdf_style=il.PdfStyle(font_id='missing', font_size=10))
        context = SimpleNamespace(xobj_encoding_length_map={}, page_encoding_length_map={},
                                  check_font_exists=False, all_encoding_length_map={})
        stream = []
        CharacterRenderUnit(char, 0).render(stream, context)
        self.assertEqual(stream, [])


if __name__ == '__main__':
    unittest.main()
