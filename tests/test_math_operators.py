"""Real PDF glyph geometry: delimited math calls, ordinary prose negatives."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import tempfile
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import math_operators as m
import source_repair as s
import visual_review as v


def page(doc,operator='max',argument='(a,b)',math=True):
    p=doc.new_page(width=600,height=800)
    p.insert_text((35,100),'where ',fontname='tiro',fontsize=12)
    p.insert_text((80,100),operator,fontname='tiro',fontsize=12)
    x=80+fitz.get_text_length(operator,fontname='tiro',fontsize=12)+.5
    p.insert_text((x,100),argument,fontname='symb' if math else 'tiro',fontsize=12)
    return p


class OperatorTests(unittest.TestCase):
    def targeted(self,operator='max'):
        class Client:
            def doctor(self):return {'native_version':'operator-fixture'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,op in [('source','max'),('translated',operator)]:
                with fitz.open() as doc:page(doc,op);doc.save(root/(name+'.pdf'))
            cfg=v.validate_options({'source':root/'source.pdf','translated':root/'translated.pdf','output':root/'review',
                'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},'repair':False,
                'pages':[1],'review_mode':'math_audits','focused_recheck':True,'math_operator_guard':True},root)
            with patch.object(v,'capability_probe'),patch.object(v,'review_page',side_effect=AssertionError('Unexpected whole-page call')):
                return v.run(cfg,Client())

    def test_targeted_math_mode_never_claims_whole_page_model_screening(self):
        result=self.targeted()
        self.assertEqual(result['status'],'program_math_audits_passed')
        self.assertIn('No whole-page',result['review_scope'])
        self.assertEqual(result['model_calls'],0)

    def test_targeted_math_mode_still_keeps_an_unmapped_missing_operator(self):
        result=self.targeted('and')
        self.assertEqual(result['status'],'needs_manual_review')
        self.assertTrue(result['pages'][0]['issues'])

    def test_targeted_mode_requires_guard_focus_and_production_scope(self):
        for override in ({'math_operator_guard':False},{'focused_recheck':False},{'purpose':'development_acceptance'}):
            cfg={'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
                'repair':False,'review_mode':'math_audits','math_operator_guard':True,'focused_recheck':True,**override}
            with self.subTest(override=override),self.assertRaises(ValueError):v.validate_options(cfg,Path('.'))

    def test_blind_page_review_cannot_clear_missing_max(self):
        class Blind:
            def doctor(self):return {'native_version':'operator-fixture'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,operator in [('source','max'),('translated','and')]:
                with fitz.open() as doc:page(doc,operator);doc.save(root/(name+'.pdf'))
            cfg=v.validate_options({'source':root/'source.pdf','translated':root/'translated.pdf','output':root/'review',
                'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
                'repair':False,'pages':[1],'math_operator_guard':True},root)
            def blind(a,b,n,*args):return {'issues':[]},v.regions(b[n-1])
            with patch.object(v,'capability_probe'),patch.object(v,'review_page',side_effect=blind):result=v.run(cfg,Blind())
            self.assertEqual(result['status'],'needs_manual_review')
            self.assertFalse(result['pages'][0]['final_operator_audit']['passed'])
            self.assertTrue(any(i['severity']=='critical' for i in result['pages'][0]['issues']))

    def test_supported_operators_have_real_math_context_and_exact_arguments(self):
        for name in m.OPERATORS:
            with self.subTest(name=name),fitz.open() as a,fitz.open() as b:
                left=page(a,name);right=page(b,name)
                result=m.audit(left,right)
                self.assertTrue(result['passed'])
                self.assertEqual(len(result['source']),1)
                self.assertTrue(result['source'][0]['signature'].startswith(name+'('))

    def test_missing_or_changed_operator_and_argument_cannot_pass(self):
        for operator,argument in [('min','(a,b)'),('max','(a,c)'),('max','(b,a)')]:
            with self.subTest(operator=operator,argument=argument),fitz.open() as a,fitz.open() as b:
                self.assertFalse(m.audit(page(a),page(b,operator,argument))['passed'])
        with fitz.open() as a,fitz.open() as b:
            left=page(a);right=page(b,'and')
            self.assertFalse(m.audit(left,right)['passed'])

    def test_ordinary_words_and_prose_parentheses_are_not_math_calls(self):
        for name,arg,math in [('maximum','(a,b)',True),('log',' files',True),
                              ('min',' speed',True),('sin',' (religion)',False),('log',' (files)',False)]:
            with self.subTest(name=name,arg=arg),fitz.open() as doc:
                self.assertEqual(m.functions(page(doc,name,arg,math))[0],[])

    def test_unclosed_math_argument_is_unknown_not_a_pass(self):
        with fitz.open() as a,fitz.open() as b:
            result=m.audit(page(a,argument='(a,b'),page(b,argument='(a,b'))
            self.assertFalse(result['passed'])
            self.assertTrue(result['not_checked']['source'])

    def test_source_repair_preserves_operator_as_original_glyphs(self):
        with fitz.open() as doc:
            p=page(doc);keys=m.protected_glyph_keys(p)
            self.assertEqual(len(keys),3)
            units=s.units(p,fitz.Rect(20,80,250,120),'mixed_prose')
            self.assertFalse(any('max' in u['source'] for u in units))
            self.assertTrue(any('where' in u['source'] for u in units))
            signature=s.protected_signature(p,fitz.Rect(20,80,250,120),[box for u in units for box in u['boxes']])
            self.assertTrue(all(any(item[1]==letter for item in signature) for letter in 'max'))

    def test_objective_recovery_requires_source_verification_and_exact_call(self):
        with fitz.open() as a,fitz.open() as b,fitz.open() as c:
            left=page(a);bad=page(b,'and');good=page(c)
            before=m.audit(left,bad)
            edit={'region':{'bbox':[20,80,250,120]},'method':'source_prose_slots',
                'source_restore':{'source_protected_spans_verified':12}}
            objective,checks=v.fixed_operator_rechecks(left,good,[edit],before)
            self.assertTrue(objective['island_0'])
            self.assertTrue(checks[0]['audit']['passed'])
            self.assertFalse(v.fixed_operator_rechecks(left,bad,[edit],before)[0]['island_0'])
            edit['source_restore']={}
            self.assertFalse(v.fixed_operator_rechecks(left,good,[edit],before)[0]['island_0'])


if __name__=='__main__':unittest.main()
