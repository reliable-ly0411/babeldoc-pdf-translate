"""A vision model missing tiny mathematics cannot silently clear that risk."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pymupdf as fitz

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import visual_review as v


def page(doc,size=12,anchor_shift=0,duplicate=False,chars='abgdezhq'):
    p=doc.new_page(width=600,height=800)
    p.insert_text((265,140+anchor_shift),'(18)',fontsize=12)
    if duplicate:p.insert_text((565,140),'(18)',fontsize=12)
    p.insert_text((35,170),'where',fontsize=12)
    p.insert_text((75,170),chars,fontname='symb',fontsize=size)
    p.insert_text((35,210),'The controller includes a predictor and an adaptation law for this system.',fontsize=10)
    return p


class MathScaleTests(unittest.TestCase):
    def check(self,**kwargs):
        with fitz.open() as a,fitz.open() as b:
            left=page(a);right=page(b,**kwargs)
            return v.math_scale_findings(left,right,v.regions(right))

    def test_original_small_math_is_not_flagged(self):
        issues,checks=self.check(size=12)
        self.assertEqual(issues,[])
        self.assertTrue(any(c.get('status')=='checked' and c['median_scale']==1 for c in checks))

    def test_new_shrink_below_existing_font_floor_is_flagged(self):
        issues,checks=self.check(size=9)
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['region_id'],'')
        self.assertEqual(issues[0]['category'],'formula')
        self.assertIn('Equation (18)',issues[0]['reason'])
        self.assertEqual(checks[0]['median_scale'],.75)
        self.assertGreaterEqual(checks[0]['matched_glyphs'],8)

    def test_normal_five_percent_scaling_is_allowed(self):
        self.assertEqual(self.check(size=11.4)[0],[])

    def test_moved_or_ambiguous_anchor_is_never_guessed(self):
        for values,reason in [({'size':9,'anchor_shift':3},'EQUATION_ANCHOR_MOVED'),
                              ({'size':9,'duplicate':True},'AMBIGUOUS_EQUATION_ANCHOR')]:
            with self.subTest(reason=reason):
                issues,checks=self.check(**values)
                self.assertEqual(issues,[])
                self.assertEqual(checks[0]['status'],'not_checked')
                self.assertEqual(checks[0]['reason'],reason)

    def test_insufficient_matching_glyphs_is_unknown_not_a_pass(self):
        issues,checks=self.check(size=9,chars='a')
        self.assertEqual(issues,[])
        self.assertEqual(checks[0]['status'],'not_checked')
        self.assertEqual(checks[0]['reason'],'INSUFFICIENT_MATCHING_MATH')

    def test_blind_page_model_cannot_clear_a_measured_scale_risk(self):
        class Blind:
            def doctor(self):return {'native_version':'fixture'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,size in [('source',12),('translated',9)]:
                with fitz.open() as doc:
                    page(doc,size=size);doc.save(root/(name+'.pdf'))
            cfg={'source':root/'source.pdf','translated':root/'translated.pdf','output':root/'review',
                'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
                'pages':[1],'repair':False,'math_scale_guard':True}
            cfg=v.validate_options(cfg,root)
            def blind(source,target,number,*args):return {'issues':[]},v.regions(target[number-1])
            with patch.object(v,'capability_probe'),patch.object(v,'review_page',side_effect=blind):
                result=v.run(cfg,Blind())
            self.assertEqual(result['status'],'needs_manual_review')
            self.assertEqual(result['pages'][0]['issues'][0]['category'],'formula')
            self.assertEqual(result['model_calls'],0)

    def test_fixed_recheck_requires_source_verification_and_exact_math_counts(self):
        with fitz.open() as a,fitz.open() as b:
            left=page(a);right=page(b)
            box=[32,150,255,185]
            edit={'region':{'bbox':box},'method':'source_prose_slots',
                'source_restore':{'source_protected_spans_verified':8}}
            before=[{'tag':'(18)','risk':True,'bbox':box}]
            objective,checks=v.fixed_math_scale_rechecks(left,right,[edit],before)
            self.assertEqual(objective,{'island_0':True})
            self.assertTrue(checks[0]['same_math_counts'])
            edit['source_restore']={}
            self.assertFalse(v.fixed_math_scale_rechecks(left,right,[edit],before)[0]['island_0'])
        with fitz.open() as a,fitz.open() as b:
            left=page(a);right=page(b,chars='a')
            edit['source_restore']={'source_protected_spans_verified':8}
            objective,checks=v.fixed_math_scale_rechecks(left,right,[edit],before)
            self.assertFalse(objective['island_0'])
            self.assertEqual(checks[0]['status'],'not_checked')


if __name__=='__main__':unittest.main()
