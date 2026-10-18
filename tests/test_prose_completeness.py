"""Actual independent failures and conservative omission-screen negatives."""
import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b
import prose_completeness as p
import visual_review as v

FIXTURE=Path(__file__).parent/'fixtures/l1quad-prose-semantics.json'


class CompletenessTests(unittest.TestCase):
    def test_actual_three_failures_reproduce_the_limits_of_structural_guards(self):
        data=json.loads(FIXTURE.read_text(encoding='utf8'))
        for row in data['cases']:
            request={'messages':[{'role':'user','content':'Translate English into Chinese.\n## Here is the input:\n'+
                json.dumps([{'id':row['source_row_id'],'input':row['source']}])}]}
            actual=json.dumps([{'id':row['source_row_id'],'output':row['actual_output']}])
            faithful=json.dumps([{'id':row['source_row_id'],'output':row['faithful_counterexample']}])
            # These structural guards deliberately do not claim prose meaning.
            b.checked_content(actual,request,data['protected_identifiers'],paragraphs=True)
            b.checked_content(faithful,request,data['protected_identifiers'],paragraphs=True)
            self.assertEqual(p.unchanged_english(row['source'],row['actual_output']),row['id']=='D01')
            self.assertFalse(p.unchanged_english(row['source'],row['faithful_counterexample']))

    def test_ordinary_unchanged_sentence_is_a_warning(self):
        text='The control system is stable under these conditions.'
        self.assertTrue(p.unchanged_english(text,text))
        self.assertFalse(p.unchanged_english(text,'The control system（控制系统）在这些条件下稳定。'))

    def test_names_metadata_code_labels_and_bilingual_terms_are_negatives(self):
        samples=['J. Smith, A. Kumar, M. Lee and P. Sun',
            'IEEE Transactions on Automatic Control, vol. 10, pp. 2-5, 2024.',
            'quadrotor（四旋翼飞行器）','The input signal','LPF',
            '`The control system is stable under these conditions.`',
            'The author is available at person@example.test for further information.',
            'The code is documented at https://example.test/manual for users.']
        for text in samples:
            with self.subTest(text=text):self.assertFalse(p.unchanged_english(text,text))

    def test_missing_or_repeated_source_evidence_is_not_silently_guessed(self):
        text='The control system is stable under these conditions.'
        self.assertFalse(p.unchanged_english('Other source paragraph.',text))
        self.assertFalse(p.unchanged_english(text+'\n'+text,text))

    def test_normalization_does_not_change_input_or_math(self):
        source='quadrotor’s transla-\ntional dynamics is reflected by'
        target="quadrotor's translational dynamics is reflected by"
        self.assertTrue(p.unchanged_english(source,target))
        self.assertIn('-\n',source)

    def test_blind_image_review_cannot_clear_an_unchanged_source_sentence(self):
        class Blind:
            def doctor(self):return {'native_version':'completeness-fixture'}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);text='The control system is stable under these conditions.'
            for name in ('source','target'):
                with fitz.open() as doc:
                    doc.new_page(width=600,height=800).insert_text((40,100),text,fontsize=10)
                    doc.save(root/(name+'.pdf'))
            cfg=v.validate_options({'source':root/'source.pdf','translated':root/'target.pdf','output':root/'review',
                'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
                'repair':False,'pages':[1],'chinese_prose_guard':True},root)
            def blind(a,z,n,*args):return {'issues':[]},v.regions(z[n-1])
            with patch.object(v,'capability_probe'),patch.object(v,'review_page',side_effect=blind):result=v.run(cfg,Blind())
            self.assertEqual(result['status'],'needs_manual_review')
            self.assertEqual(len(result['pages'][0]['final_prose_completeness_findings']),1)
            self.assertEqual(result['model_calls'],0)

    def test_option_is_explicit_and_validated(self):
        with self.assertRaisesRegex(ValueError,'chinese_prose_guard'):
            v.validate_options({'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
                'chinese_prose_guard':'yes'},Path('.'))


if __name__=='__main__':unittest.main()
