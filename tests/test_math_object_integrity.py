"""Real source IL: conserve argument commas and accent/base relationships."""
import copy
import json
from pathlib import Path
import unittest
from babeldoc.format.pdf.document_il import il_version_1 as il
from babeldoc.format.pdf.document_il.midend.styles_and_formulas import StylesAndFormulas as S
from test_table_math_geometry import decode,signature,glyphs


def objects(paragraph):
    return [c.pdf_formula or c.pdf_line for c in paragraph.pdf_paragraph_composition
            if c.pdf_formula or c.pdf_line]


def prediction(page):return next(p for p in page.pdf_paragraph if 'prediction error' in (p.unicode or ''))
def proposition(page):return next(p for p in page.pdf_paragraph if 'Proposition 1' in (p.unicode or ''))


class MathIntegrityTests(unittest.TestCase):
    def fixture(self):
        from evidence_support import evidence_file
        value=json.loads(evidence_file('tests/fixtures/l1quad-inline-math.json').read_text(encoding='utf8'))
        return decode(il.Page,value['page'])

    def test_function_arguments_are_complete_original_objects(self):
        page=self.fixture();before=S.source_glyph_signature(page)
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        worker=S.__new__(S);worker.process_comma_formulas(page)
        formula=next(c.pdf_formula for c in proposition(page).pdf_paragraph_composition
                     if c.pdf_formula and ''.join(x.char_unicode or '' for x in c.pdf_formula.pdf_character).startswith('V0'))
        text=''.join(c.char_unicode or '' for c in formula.pdf_character)
        self.assertEqual(text.count(','),3)
        self.assertIn('V (ep(0),ev(0),eR(0),eΩ(0))',text)
        self.assertEqual(before,S.source_glyph_signature(page))

    def test_real_roman_max_operator_is_inside_original_formula_not_prose(self):
        page=self.fixture();before=S.source_glyph_signature(page);curves=S.source_curve_signature(page)
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        p=proposition(page)
        prose=''.join(c.char_unicode or '' for comp in p.pdf_paragraph_composition if comp.pdf_line for c in comp.pdf_line.pdf_character)
        formulas=[''.join(c.char_unicode or '' for c in comp.pdf_formula.pdf_character) for comp in p.pdf_paragraph_composition if comp.pdf_formula]
        self.assertNotIn('max',prose)
        self.assertTrue(any('c4 ≜ max{c1/m,1}' in text for text in formulas))
        self.assertEqual(before,S.source_glyph_signature(page));self.assertEqual(curves,S.source_curve_signature(page))

    def test_roman_ordinary_words_and_different_lines_remain_boundaries(self):
        for word,separate_line in [('log files',False),('maximum',False),('max',True)]:
            with self.subTest(word=word,line=separate_line):
                page=self.fixture();p=proposition(page)
                i=next(i for i,c in enumerate(p.pdf_paragraph_composition) if c.pdf_line and ''.join(x.char_unicode or '' for x in c.pdf_line.pdf_character)=='max')
                line=p.pdf_paragraph_composition[i].pdf_line
                template=line.pdf_character[0]
                line.pdf_character=[copy.deepcopy(template) for _ in word]
                for char,value in zip(line.pdf_character,word):char.char_unicode=value
                if separate_line:p.pdf_paragraph_composition[i+1].pdf_formula.line_id=99
                before=S.source_glyph_signature(page)
                S.coalesce_inline_math(page)
                prose=''.join(c.char_unicode or '' for comp in p.pdf_paragraph_composition if comp.pdf_line for c in comp.pdf_line.pdf_character)
                self.assertIn(word,prose);self.assertEqual(before,S.source_glyph_signature(page))

    def test_macrons_and_hat_bind_to_their_geometric_bases_without_coordinate_changes(self):
        page=self.fixture();before=S.source_glyph_signature(page)
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        paragraph=prediction(page);macrons=[]
        for comp in paragraph.pdf_paragraph_composition:
            if comp.pdf_formula:
                chars=comp.pdf_formula.pdf_character
                for accent in chars:
                    if accent.char_unicode=='¯':
                        bases=[c for c in chars if c.char_unicode=='B' and abs(c.box.x-accent.box.x)<4]
                        self.assertEqual(len(bases),1)
                        self.assertAlmostEqual(accent.box.y-bases[0].box.y,2.519,places=3)
                        macrons.append(accent)
                if any(c.char_unicode=='ˆ' for c in chars):
                    self.assertIn('z',[c.char_unicode for c in chars])
        self.assertEqual(len(macrons),2)
        self.assertEqual(before,S.source_glyph_signature(page))
        self.assertFalse(any(all(not c.char_unicode or c.char_unicode.isspace() or c.char_unicode=='¯'
            for c in obj.pdf_character) for obj in objects(paragraph)))

    def test_leading_and_consecutive_commas_never_disappear(self):
        page=self.fixture();paragraph=proposition(page);comp=next(c for c in paragraph.pdf_paragraph_composition
                                     if c.pdf_formula and c.pdf_formula.pdf_character[0].char_unicode==',')
        comma=copy.deepcopy(comp.pdf_formula.pdf_character[0])
        comp.pdf_formula.pdf_character.insert(0,comma)
        paragraph.pdf_paragraph_composition=[comp]
        page.pdf_paragraph=[paragraph]
        before=S.source_glyph_signature(page);worker=S.__new__(S)
        worker.process_comma_formulas(page)
        self.assertEqual(sum(c.char_unicode==',' for c in glyphs(page)),2)
        self.assertEqual(before,S.source_glyph_signature(page))

    def test_ordinary_prose_and_different_formula_lines_remain_boundaries(self):
        page=self.fixture();S.bind_math_accents(page);S.coalesce_inline_math(page)
        prose=''.join(c.char_unicode or '' for comp in prediction(page).pdf_paragraph_composition
                      if comp.pdf_line for c in comp.pdf_line.pdf_character)
        self.assertIn('prediction error',prose)
        self.assertIn('Hurwitz matrix',prose)
        for comp in prediction(page).pdf_paragraph_composition:
            if comp.pdf_formula:
                text=''.join(c.char_unicode or '' for c in comp.pdf_formula.pdf_character)
                self.assertNotIn('prediction',text)
                self.assertNotIn('repre',text)

    def test_roman_delimiters_are_bound_to_function_without_consuming_following_prose(self):
        page=self.fixture();before=S.source_glyph_signature(page)
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        formulas=[''.join(c.char_unicode or '' for c in comp.pdf_formula.pdf_character)
                  for comp in prediction(page).pdf_paragraph_composition if comp.pdf_formula]
        self.assertIn('¯B(R(t))σ(t,x(t))',formulas)
        prose=''.join(c.char_unicode or '' for comp in prediction(page).pdf_paragraph_composition
                      if comp.pdf_line for c in comp.pdf_line.pdf_character)
        self.assertIn(', and ',prose)
        self.assertNotIn('))',prose)
        self.assertEqual(before,S.source_glyph_signature(page))

    def test_ambiguous_accent_is_not_attached_to_a_guessed_base(self):
        page=self.fixture();p=prediction(page)
        base=next(c for comp in p.pdf_paragraph_composition if comp.pdf_formula
                  for c in comp.pdf_formula.pdf_character if c.char_unicode=='B')
        p.pdf_paragraph_composition.append(il.PdfParagraphComposition(pdf_formula=il.PdfFormula(
            pdf_character=[copy.deepcopy(base)],line_id=99)))
        S.bind_math_accents(page)
        accents=[comp.pdf_formula for comp in p.pdf_paragraph_composition if comp.pdf_formula
                 and any(c.char_unicode=='¯' for c in comp.pdf_formula.pdf_character)]
        self.assertTrue(any(not any(c.char_unicode=='B' for c in f.pdf_character) for f in accents))

    def test_curve_only_formula_keeps_its_original_owner_without_empty_character_failure(self):
        page=self.fixture();curve=il.PdfCurve();formula=il.PdfFormula(pdf_character=[],pdf_curve=[curve],line_id=90)
        page.pdf_paragraph[0].pdf_paragraph_composition.insert(0,il.PdfParagraphComposition(pdf_formula=formula))
        before=S.source_curve_signature(page)
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        self.assertEqual(S.source_curve_signature(page),before)
        self.assertIs(page.pdf_paragraph[0].pdf_paragraph_composition[0].pdf_formula,formula)

    def test_greek_variable_in_a_roman_font_cannot_split_a_matrix_math_object(self):
        page=self.fixture();before=S.source_glyph_signature(page)
        paragraph=next(p for p in page.pdf_paragraph if 'initial state vector' in (p.unicode or ''))
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        prose=''.join(c.char_unicode or '' for comp in paragraph.pdf_paragraph_composition
                      if comp.pdf_line for c in comp.pdf_line.pdf_character)
        self.assertNotIn('Ω',prose)
        formulas=[''.join(c.char_unicode or '' for c in comp.pdf_formula.pdf_character)
                  for comp in paragraph.pdf_paragraph_composition if comp.pdf_formula]
        self.assertTrue(any('Ω×JΩ' in text.replace(' ','') for text in formulas))
        self.assertIn('initial state vector',prose)
        self.assertEqual(before,S.source_glyph_signature(page))

    def test_reference_parentheses_and_assignment_openings_are_original_math_objects(self):
        page=self.fixture();before=S.source_glyph_signature(page)
        paragraph=next(p for p in page.pdf_paragraph if (p.unicode or '').startswith('Comparing the above equation'))
        S.bind_math_accents(page);S.coalesce_inline_math(page)
        formulas=[''.join(c.char_unicode or '' for c in comp.pdf_formula.pdf_character).replace(' ','')
                  for comp in paragraph.pdf_paragraph_composition if comp.pdf_formula]
        self.assertIn('(1b)',formulas)
        self.assertIn('(13)',formulas)
        self.assertTrue(any(text.startswith('(σm)1=') for text in formulas))
        self.assertTrue(any(text.startswith('(m−mreal)fb/mreal') for text in formulas))
        self.assertFalse(any(text.startswith('(σm)1=(') for text in formulas))
        self.assertEqual(before,S.source_glyph_signature(page))


if __name__=='__main__':unittest.main()
