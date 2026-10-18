"""Synthetic native glyph ownership and strict source-gap fidelity regressions."""
from pathlib import Path
import os
import json
import re
import sys
import unittest
import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_fragments as fragments
import source_repair as source
import source_redaction
import visual_review as visual


def span(text, x=20, y=80, size=12, flags=0, font='Plain'):
    chars = [{'c': c, 'origin': (x+i*size*.5, y),
              'bbox': (x+i*size*.5, y-size, x+(i+1)*size*.5, y+size*.2)}
             for i, c in enumerate(text)]
    return {'text': text, 'font': font, 'size': size, 'flags': flags,
            'bbox': (x, y-size, x+len(text)*size*.5, y+size*.2),
            'origin': (x,y), 'chars': chars}


def split(*values):
    return fragments.fragments({'spans': list(values)}, source.MATH_FONT,
                               source.OPAQUE_MATH, source.CONTACT)


class SourceFragmentTests(unittest.TestCase):
    def page(self, text=None):
        d=fitz.open();self.addCleanup(d.close);p=d.new_page(width=500,height=400)
        if text:p.insert_text((25,80),text,fontsize=12)
        return d,p

    def test_braces_protect_only_the_literal_group(self):
        values=split(span('Before {x} after'))
        self.assertEqual(''.join(v['text'] for v in values),'Before {x} after')
        self.assertEqual(''.join(v['text'] for v in values if v.get('_source_literal')),'{x}')
        self.assertEqual([v['text'] for v in values if v['text'].strip() and not v.get('_source_literal')],['Before','after'])

    def test_code_tags_are_literal_but_surrounding_english_is_editable(self):
        values=split(span('Use <think> and </think> tags.'))
        self.assertEqual([v['text'] for v in values if v.get('_source_literal')],['<think>','</think>'])
        self.assertIn('Use',[v['text'] for v in values if not v.get('_source_literal')])

    def test_nested_braces_keep_all_original_native_members(self):
        values=split(span('Use {a_{old},b} here'))
        self.assertEqual(''.join(v['text'] for v in values if v.get('_source_literal')),'{a_{old},b}')

    def test_brace_state_survives_lines_and_math_font_spans(self):
        block={'lines':[{'spans':[span('Before {')]},
                        {'spans':[span('x}',font='Symbol')]},
                        {'spans':[span('after')]}]}
        fragments.annotate_block(block,source.MATH_FONT,source.OPAQUE_MATH,source.CONTACT)
        self.assertFalse(block['_source_literal_scope_unclosed'])
        self.assertFalse(block['lines'][-1]['_source_fragments'][0].get('_source_literal'))

    def test_isolated_italic_variable_stays_source_owned(self):
        values=split(span('question '),span('q',x=80,flags=2))
        self.assertEqual(values[-1]['_source_literal'],'italic_letter')
        self.assertFalse(values[0].get('_source_literal'))

    def test_italic_english_words_remain_editable(self):
        values=split(span('a useful property',flags=2))
        self.assertFalse(any(v.get('_source_literal') for v in values))

    def test_displaced_subscript_extends_greek_literal(self):
        values=split(span('π',x=20,size=12,flags=2),
                     span('θ',x=26,y=82.5,size=8,flags=2),
                     span('old',x=30,y=84,size=6),
                     span(' and optimize',x=40,size=12))
        self.assertEqual([v['text'] for v in values if v.get('_source_literal')],['π','θ','old'])
        self.assertFalse(next(v for v in values if v['text']=='and').get('_source_literal'))

    def test_body_sized_old_is_not_mistaken_for_subscript(self):
        values=split(span('π',x=20,size=12),span('old policy',x=27,size=12))
        self.assertFalse(next(v for v in values if v['text']=='old').get('_source_literal'))

    def test_superscript_citation_is_not_an_alphanumeric_prose_name(self):
        values=split(span('LLMs',x=20),span('32',x=44,y=76,size=7,flags=1),span(' are used',x=51))
        self.assertEqual(next(v for v in values if v['text']=='32')['_source_literal'],'script')

    def test_native_pdf_units_expose_prose_and_retain_braces(self):
        _,p=self.page('Before {x} after')
        units=source.units(p,p.rect,'mixed_prose')
        self.assertEqual([u['source'] for u in units],['Before','after'])
        self.assertEqual(units[0]['right_literal'],'{x}')
        self.assertTrue(source.validate_paragraphs(units,['之前','之后']))

    def test_native_repair_keeps_original_literal_glyphs(self):
        d,p=self.page('Before {x} after');target=fitz.open();self.addCleanup(target.close)
        target.new_page(width=500,height=400).insert_text((25,80),'Incorrect text')
        known=visual.regions(target[0]);island,error=source.derive_island(p,target[0],known[0])
        self.assertIsNone(error)
        result=source.restore_region(d,0,target,0,island,['之前','之后'])
        self.assertGreaterEqual(result['source_protected_glyphs_verified'],3)
        self.assertTrue(result['render_lineage']['copy']['passed'])
        self.assertIn('之前',target[0].get_text());self.assertIn('x',target[0].get_text())

    def test_source_gap_cannot_be_emptied_into_another_gap(self):
        _,p=self.page('Before {x} after');units=source.units(p,p.rect,'mixed_prose')
        self.assertFalse(source.validate_paragraphs(units,['','之前及之后']))

    def test_numbers_cannot_move_across_immutable_objects(self):
        units=[{'source':'Count 1','paragraph':0,'fidelity_scope':'source_gap_v2'},
               {'source':'Count 2','paragraph':0,'fidelity_scope':'source_gap_v2'}]
        self.assertFalse(source.validate_paragraphs(units,['数量2','数量1']))
        self.assertTrue(source.validate_paragraphs(units,['数量1','数量2']))

    def test_copied_math_context_cannot_be_typed_again_in_prose(self):
        _,p=self.page('Before {x} after');units=source.units(p,p.rect,'mixed_prose')
        self.assertFalse(source.validate_paragraphs(units,['之前 x','之后']))
        self.assertEqual(source.paragraph_errors(units,['之前 x','之后'])[0]['kind'],'copied_immutable_context_in_prose')

    def test_new_greek_or_math_alphabet_in_prose_is_rejected(self):
        for text in ['控制器π','控制器θ','控制器𝑞']:
            self.assertFalse(source.validate_translation({'source':'controller'},text))
        self.assertTrue(source.validate_translation({'source':'controller'},'控制器'))

    def test_source_plan_failure_contains_bounded_slot_evidence(self):
        units=[{'source':'Count 1','paragraph':0,'fidelity_scope':'source_gap_v2'}]
        with self.assertRaises(visual.SourcePlanValidationError) as caught:
            visual.checked_source_plan({'region_0':{'slot_00':'数量2'}},[{'units':units}])
        detail=caught.exception.detail['failures'][0]
        self.assertEqual(detail['slot'],0)
        self.assertEqual(detail['source_digits'],['1']);self.assertEqual(detail['candidate_digits'],['2'])

    def test_unclosed_group_fails_before_translation(self):
        _,p=self.page('Before {x after')
        with self.assertRaisesRegex(ValueError,'SOURCE_LITERAL_GROUP_UNCLOSED'):
            source.units(p,p.rect,'mixed_prose')

    def test_heading_and_body_are_separate_nonempty_source_gaps(self):
        _,p=self.page()
        p.insert_text((25,70),'GRPO',fontname='hebo',fontsize=12)
        p.insert_text((25,84),'GRPO is used.',fontsize=12)
        units=source.units(p,p.rect,'mixed_prose')
        self.assertEqual([u['source'] for u in units],['GRPO','GRPO is used.'])
        self.assertTrue(units[0]['bold']);self.assertFalse(units[1]['bold'])
        self.assertFalse(source.validate_paragraphs(units,['','GRPO被使用。']))

    def test_safe_native_redaction_retains_scripts_crossing_the_next_line_box(self):
        d,p=self.page()
        p.insert_text((25,80),'Before ',fontsize=12)
        p.insert_text((100,80),'p',fontname='symb',fontsize=12)
        p.insert_text((107,84),'old',fontname='tiro',fontsize=8)
        p.insert_text((25,94),'Following text on the next line.',fontsize=12)
        units=source.units(p,p.rect,'mixed_prose');owned=source_redaction.owned_keys(units)
        self.assertNotIn('old',' '.join(u['source'] for u in units))
        before=source.protected_signature(p,p.rect,[],editable_glyph_keys=owned)
        protected=[box for key,box in source_redaction.native_glyphs(p,p.rect) if key not in owned]
        naive=[fitz.Rect(box) for u in units for box in u['boxes']]
        self.assertTrue(any(a.intersects(b) for a in naive for b in protected))
        actual=source_redaction.apply(p,p.rect,units)
        self.assertTrue(actual)
        self.assertEqual(source.protected_signature(p,p.rect,[]),before)
        self.assertFalse(any(fitz.Rect(a).intersects(b) for a in actual for b in protected))

    def test_completely_overlapped_editable_glyph_cannot_delete_math(self):
        _,p=self.page()
        p.insert_text((100,90),'p',fontname='symb',fontsize=30)
        p.insert_text((102,90),'i',fontsize=8)
        units=source.units(p,p.rect,'mixed_prose')
        with self.assertRaisesRegex(ValueError,'SOURCE_EDITABLE_GLYPH_HAS_NO_SAFE_REDACTION'):
            source_redaction.boxes(p,p.rect,units)


@unittest.skipUnless(os.environ.get('BABELDOC_SLOT_PILOT'), 'private real p7 pilot not configured')
class ActualPilotSlotTests(unittest.TestCase):
    def test_actual_source_fragments_are_literals_and_body_is_editable(self):
        root=Path(os.environ['BABELDOC_SLOT_PILOT'])
        observed=json.loads((root/'t16/p7/SOURCE-ISLAND-PREFLIGHT.private.json').read_text(encoding='utf-8'))
        with fitz.open(root/'validation/deepseekr1.pdf') as doc:
            units=source.units(doc[6],observed['plans'][0]['bbox'],'mixed_prose')
        prose=' '.join(u['source'] for u in units)
        for literal in ('q','o1','o2','oG'):
            self.assertIsNone(re.search(r'\b'+literal+r'\b',prose))
        self.assertIn('GRPO samples a group of outputs',prose)
        self.assertTrue(any('πθold' in u['left_literal']+u['right_literal'] for u in units))
        self.assertTrue(all(u['fidelity_scope']=='source_gap_v2' for u in units))
