"""Replay public R1 geometry; formula glyphs must never be retyped or moved."""
import dataclasses
import json
from pathlib import Path
import typing
import unittest

from babeldoc.format.pdf.document_il import il_version_1 as il
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas


def decode(kind, value):
    if value is None:
        return None
    origin = typing.get_origin(kind)
    args = typing.get_args(kind)
    if origin is list:
        return [decode(args[0], x) for x in value]
    if args and type(None) in args:
        return decode(next(t for t in args if t is not type(None)), value)
    if dataclasses.is_dataclass(kind) and isinstance(value, dict):
        hints = typing.get_type_hints(kind)
        return kind(**{key: decode(hints[key], val) for key, val in value.items()})
    return value


def glyphs(page):
    result = []
    for p in page.pdf_paragraph:
        for c in p.pdf_paragraph_composition:
            obj = c.pdf_line or c.pdf_formula
            if obj:
                result.extend(obj.pdf_character)
    return result


def signature(c):
    return (c.xobj_id, c.render_order, c.pdf_character_id, c.char_unicode,
            c.pdf_style.font_id, c.box.x, c.box.y, c.box.x2, c.box.y2)


class TableMathTests(unittest.TestCase):
    def fixture(self):
        from evidence_support import evidence_file
        data = json.loads(evidence_file('tests/fixtures/r1-math-geometry.json').read_text(encoding='utf-8'))
        return decode(il.Document, data).page[0]

    def test_real_fragmented_equations_retain_all_unique_source_glyph_coordinates(self):
        page = self.fixture()
        before = {signature(c) for c in glyphs(page) if not (c.char_unicode or '').isspace()}
        StylesAndFormulas.preserve_table_math_geometry(page)
        after = {signature(c) for c in glyphs(page) if not (c.char_unicode or '').isspace()}
        self.assertEqual(before, after)
        formulas = [c.pdf_formula for p in page.pdf_paragraph for c in p.pdf_paragraph_composition if c.pdf_formula]
        self.assertGreaterEqual(len(formulas), 5)
        self.assertTrue(any(len(f.pdf_character) > 40 for f in formulas))
        self.assertGreater(sum(len(f.pdf_curve) for f in formulas), 20)

    def test_no_table_detection_leaves_original_geometry_unmodified(self):
        page = self.fixture(); page.page_layout = []
        before = [signature(c) for c in glyphs(page)]
        StylesAndFormulas.preserve_table_math_geometry(page)
        self.assertEqual(before, [signature(c) for c in glyphs(page)])

    def test_original_prose_remains_translatable_and_curves_have_unique_ownership(self):
        page = self.fixture()
        original_curves = len(page.pdf_curve)
        StylesAndFormulas.preserve_table_math_geometry(page)
        prose = [p for p in page.pdf_paragraph if (p.unicode or '').startswith('First')]
        self.assertTrue(prose)
        self.assertTrue(any(c.pdf_line for c in prose[0].pdf_paragraph_composition))
        curves = list(page.pdf_curve) + [curve for p in page.pdf_paragraph for c in p.pdf_paragraph_composition
                   if c.pdf_formula for curve in c.pdf_formula.pdf_curve]
        self.assertEqual(len(curves), original_curves)
        self.assertEqual(len({id(c) for c in curves}), original_curves)

    def test_geometry_operation_is_idempotent(self):
        page = self.fixture()
        StylesAndFormulas.preserve_table_math_geometry(page)
        before = [signature(c) for c in glyphs(page)]
        StylesAndFormulas.preserve_table_math_geometry(page)
        self.assertEqual(before, [signature(c) for c in glyphs(page)])

    def test_split_prose_does_not_begin_inside_preserved_inline_math(self):
        page = self.fixture()
        before = StylesAndFormulas.source_glyph_signature(page)
        StylesAndFormulas.preserve_table_math_geometry(page)
        prose = next(p for p in page.pdf_paragraph
                     if (p.unicode or '').lstrip().startswith(', let’s start'))
        visible = [c for part in prose.pdf_paragraph_composition if part.pdf_line
                   for c in part.pdf_line.pdf_character if (c.char_unicode or '').strip()]
        self.assertEqual(prose.box.x, min(c.visual_bbox.box.x for c in visible))
        neighbors = [p for p in page.pdf_paragraph if p is not prose
                     and any(c.pdf_formula for c in p.pdf_paragraph_composition)
                     and p.box.y < prose.box.y2 and p.box.y2 > prose.box.y
                     and p.box.x < prose.box.x]
        self.assertTrue(neighbors)
        self.assertTrue(all(p.box.x2 <= prose.box.x for p in neighbors))
        self.assertEqual(before, StylesAndFormulas.source_glyph_signature(page))


if __name__ == '__main__':
    unittest.main()
