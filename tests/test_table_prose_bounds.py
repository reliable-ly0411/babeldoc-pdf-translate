"""Synthetic table math splits must not borrow blank space inside formulas."""
import copy
import unittest

from babeldoc.format.pdf.document_il import il_version_1 as il
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas as S


def char(text, x, width=4, index=0):
    box = il.Box(x=x, y=20, x2=x + width, y2=27)
    return il.PdfCharacter(char_unicode=text, box=box,
        visual_bbox=il.VisualBbox(box=copy.deepcopy(box)),
        pdf_style=il.PdfStyle(font_id='roman', font_size=7),
        pdf_character_id=index, render_order=index)


def paragraph(name, chars):
    box = il.Box(x=min(c.box.x for c in chars), y=20,
                 x2=max(c.box.x2 for c in chars), y2=27)
    return il.PdfParagraph(debug_id=name, box=box, layout_label='fallback_line',
        unicode=''.join(c.char_unicode for c in chars),
        pdf_paragraph_composition=[il.PdfParagraphComposition(
            pdf_line=il.PdfLine(box=copy.deepcopy(box), pdf_character=chars))])


def page_with(prose, formula):
    return il.Page(pdf_paragraph=[prose, formula], pdf_font=[il.PdfFont(font_id='roman', name='Roman')],
        page_layout=[il.PageLayout(id=1, class_name='table', box=il.Box(x=0, y=0, x2=300, y2=100))])


class TableProseBoundsTests(unittest.TestCase):
    def test_leading_space_left_by_math_split_cannot_start_prose_inside_formula(self):
        # PDF extraction order contains an invisible spacing run between + and =.
        # The retained prose starts after the separate formula's last x.
        chars = [char('+', 30, index=1), char(' ', 34, 12, 2), char('=', 46, index=3),
                 char(',', 56, index=4), char(' ', 60, 2, 5)]
        chars += [char(t, 62 + i * 4, index=6 + i) for i, t in enumerate('continue')]
        prose = paragraph('mixed', chars)
        formula = paragraph('math', [char('x', 20, index=30), char('x', 51, index=31),
                                     char('−', 25, index=32)])
        page = page_with(prose, formula)
        before = S.source_glyph_signature(page)
        S.preserve_table_math_geometry(page)
        self.assertGreaterEqual(prose.box.x, formula.box.x2)
        self.assertEqual(prose.box.x, 56)
        self.assertEqual(before, S.source_glyph_signature(page))
        remaining = prose.pdf_paragraph_composition[0].pdf_line.pdf_character
        self.assertIs(remaining[0], chars[1])  # Keep source objects, including spaces.
        self.assertEqual(prose.unicode, ' , continue')
        snapshot = copy.deepcopy(page)
        S.preserve_table_math_geometry(page)
        self.assertEqual(page, snapshot)

    def test_trailing_space_left_by_math_split_cannot_expand_prose_into_formula(self):
        chars = [char(t, 10 + i * 4, index=i) for i, t in enumerate('before')]
        chars += [char(' ', 34, 16, 7), char('+', 50, index=8)]
        prose = paragraph('mixed', chars)
        formula = paragraph('math', [char('x', 42, index=20), char('=', 55, index=21)])
        page = page_with(prose, formula)
        before = S.source_glyph_signature(page)
        S.preserve_table_math_geometry(page)
        self.assertLessEqual(prose.box.x2, formula.box.x)
        self.assertEqual(prose.box.x2, 34)
        self.assertEqual(before, S.source_glyph_signature(page))

    def test_unrelated_prose_keeps_its_original_spacing_bounds(self):
        prose = paragraph('ordinary', [char(' ', 1, 9)] +
            [char(t, 10 + i * 4, index=i + 1) for i, t in enumerate('ordinary')])
        formula = paragraph('math', [char('x', 180, index=30), char('=', 185, index=31)])
        page = page_with(prose, formula)
        before = copy.deepcopy(prose)
        S.preserve_table_math_geometry(page)
        self.assertEqual(prose, before)

    def test_absent_table_detection_keeps_every_object_unchanged(self):
        prose = paragraph('mixed', [char('+', 10), char(' ', 14, 20)] +
            [char(t, 34 + i * 4, index=i + 2) for i, t in enumerate('continue')])
        page = page_with(prose, paragraph('math', [char('x', 20), char('=', 24)]))
        page.page_layout = []
        before = copy.deepcopy(page)
        S.preserve_table_math_geometry(page)
        self.assertEqual(page, before)

    def test_untouched_line_rebuilds_native_unicode_without_changing_bounds(self):
        chars = [char(t, 10 + i * 4, index=i) for i, t in enumerate('continue…')]
        prose = paragraph('ordinary', chars)
        prose.unicode = 'continue...'
        original_box = copy.deepcopy(prose.box)
        page = page_with(prose, paragraph('math', [char('x', 180), char('=', 185)]))
        S.preserve_table_math_geometry(page)
        self.assertEqual(prose.unicode, 'continue…')
        self.assertEqual(prose.box, original_box)


if __name__ == '__main__':
    unittest.main()
