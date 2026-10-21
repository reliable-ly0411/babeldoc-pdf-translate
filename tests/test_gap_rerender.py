"""Engine reflow adapter must preserve math identity and all native prose gaps."""
from pathlib import Path
import copy,json,sys,tempfile,unittest
from unittest import mock
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gap_rerender as gap
import chat_bridge as bridge
import pdf_translate,semantic_pipeline,semantic_review,source_repair,visual_review


def unit(text,left='',right='',paragraph=0):
    return {'source':text,'paragraph':paragraph,'fidelity_scope':'source_gap_v2',
        'left_literal':left,'right_literal':right}


class GapRerenderTests(unittest.TestCase):
    def example(self):
        template=("<style id='1'>For each question </style><style id='3'>q</style>"
            "<style id='5'>, collect outputs {</style><style id='7'>o</style>{v9}"
            "<style id='10'>from the old policy </style>{v11}"
            "<style id='12'>then optimize the current policy </style>{v13}"
            "<style id='14'>by the objective:</style>")
        units=[unit('For each question',right='q,'),unit('collect outputs','q,','{o1}'),
            unit('from the old policy','{o1}','πold'),unit('then optimize the current policy','πold','π'),
            unit('by the objective:','π')]
        return template,units,['对每个问题','采样输出','来自旧策略','随后优化当前策略','以如下目标：']

    def test_reflow_changes_prose_only_and_keeps_math_on_its_original_side(self):
        template,units,texts=self.example();target,proof=gap.rebuild(template,units,texts)
        self.assertEqual(bridge.MARKER.findall(target),bridge.MARKER.findall(template))
        self.assertIn("<style id='3'>q</style>",target)
        self.assertIn("<style id='7'>o</style>{v9}",target)
        self.assertIn('来自旧策略 </style>{v11}',target)
        self.assertIn('随后优化当前策略 </style>{v13}',target)
        self.assertTrue(proof['all_native_prose_gaps_linked'])

    def test_unknown_unmapped_body_cannot_hide_as_a_literal_or_partial_match(self):
        for template,units,texts in [('The controller measures error',[unit('controller')],['控制器']),
                ('Before q and omit this condition',[unit('Before',right='q')],['此前'])]:
            with self.assertRaisesRegex(ValueError,'GAP_UNACCOUNTED_SOURCE_PROSE'):gap.rebuild(template,units,texts)

    def test_ambiguous_repetition_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError,'GAP_PROSE_LINK_NOT_UNIQUE'):
            gap.rebuild('Measure x then Measure y',[unit('Measure',right='x y')],['测量'])

    def test_prose_cannot_cross_an_opaque_placeholder(self):
        with self.assertRaisesRegex(ValueError,'GAP_PROSE_LINK_NOT_UNIQUE'):
            gap.rebuild('Optimize {v1} policy',[unit('Optimize policy')],['优化策略'])

    def test_source_order_cannot_change_even_when_tokens_match(self):
        template,units,texts=self.example()
        with self.assertRaisesRegex(ValueError,'GAP_SOURCE_ORDER_CHANGED'):
            gap.rebuild(template,list(reversed(units)),list(reversed(texts)))

    def test_numeric_and_added_math_guards_are_not_relaxed_for_reflow(self):
        for output in ('计数2','计数1 π',''):
            with self.assertRaisesRegex(ValueError,'GAP_TRANSLATION_FIDELITY'):
                gap.rebuild('Count 1',[unit('Count 1')],[output])

    def test_line_whitespace_and_style_boundaries_can_be_aligned_without_touching_markers(self):
        text="<style id='1'>A useful\n</style><style id='2'> property </style>{v1}"
        result,_=gap.rebuild(text,[unit('A useful property')],['一项有用性质'])
        self.assertIn('一项有用性质',result)
        self.assertEqual(bridge.MARKER.findall(result),bridge.MARKER.findall(text))

    def test_unlinked_source_group_is_reported_and_not_applied(self):
        pairs={'pair_0':{'source':'Another body paragraph','target':'另一段正文'}}
        proposals,decisions=gap.propose(pairs,[unit('A missing sentence')],['缺失的句子'])
        self.assertEqual(proposals,{})
        self.assertEqual(decisions[0]['status'],'not_linked')


class EngineGapControlTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.before=self.root/'before.pdf'
        with fitz.open() as doc:
            doc.new_page().insert_text((30,60),'Incorrect translation.')
            doc.new_page().insert_text((30,60),'Second page stays exactly the same.')
            doc.save(self.before)
        self.doc=fitz.open(self.before);self.addCleanup(self.doc.close)
        self.folder=self.root/'attempt';self.folder.mkdir();self.after=self.folder/'candidate.pdf'
        self.cfg={'source':self.before,'engine_job':str(self.root/'base-job.json'),'engine':'fixture',
            'provider':{'model':'fixture-luna','type':'codex','reasoning_effort':'high'},
            'limits':{'max_model_calls':6,'max_seconds':30}}
        self.base={'input':str(self.before),'output':str(self.root/'old-output'),'timeout_seconds':30,
            'provider':{'translation_pairs_file':str(self.root/'pairs.json'),'cache_only':False}}
        self.units=[unit('Measure feedback')]
        self.plan={'units':self.units,'issue':{'region_id':'block_0'},'bbox':[20,30,250,100],'kind':'prose'}
        self.pairs={'pair_0':{'source':'Measure feedback','target':'错误'}}
        self.budget=visual_review.Budget(self.cfg['limits']);self.records=[]
        self.prepare=mock.patch.object(pdf_translate,'prepare',return_value=(self.base,self.before,None,None));self.prepare.start();self.addCleanup(self.prepare.stop)
        patch=mock.patch.object(semantic_review,'load_translation_pairs',side_effect=[(self.pairs,{}),
            ({'pair_0':{'source':'Measure feedback','target':'测量反馈'}},{})]);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(source_repair,'prepare',return_value=([self.plan],[]));patch.start();self.addCleanup(patch.stop)
        def source_plan(*args,**kwargs):
            self.assertEqual(args[5]['_source_followup_reserve'],2)
            (self.folder/'source-prose-plan.json').write_text('{}',encoding='utf-8')
            return [['测量反馈']]
        self.source_plan=mock.patch.object(visual_review,'request_source_plan',side_effect=source_plan);self.source_plan.start();self.addCleanup(self.source_plan.stop)

    def invoke(self,status='equivalent'):
        return lambda *a,**k:({'pairs':{'pair_0':{'status':status,'summary':'Fixture meaning judgment.','findings':[]}}},
            {'input_tokens':12,'output_tokens':4})

    def call(self,invoke):
        return gap.patch(self.doc,self.before,self.after,1,[],[],1,self.folder,self.cfg,None,self.budget,self.records,invoke)

    def test_source_mismatch_precedes_source_plan_or_any_model_request(self):
        self.prepare.stop()
        with mock.patch.object(pdf_translate,'prepare',return_value=(self.base,self.root/'foreign.pdf',None,None)),\
             mock.patch.object(visual_review,'request_source_plan',side_effect=AssertionError('UNEXPECTED ROLE')):
            with self.assertRaisesRegex(ValueError,'GAP_ENGINE_SOURCE_CHANGED'):self.call(self.invoke())

    def test_insufficient_semantic_plus_visual_budget_cannot_spend_a_model_call(self):
        self.budget.calls=5
        with self.assertRaisesRegex(bridge.BridgeError,'VISUAL_BUDGET_EXHAUSTED'):
            self.call(lambda *a,**k: self.fail('MODEL CALLED'))

    def test_uncertain_semantics_vetoes_engine_and_preserves_previous_pdf(self):
        before=self.before.read_bytes()
        with mock.patch.object(pdf_translate,'run_job',side_effect=AssertionError('ENGINE CALLED')):
            with self.assertRaisesRegex(ValueError,'GAP_ENGINE_SEMANTIC_PRECHECK_FAILED'):self.call(self.invoke('uncertain'))
        self.assertEqual(self.before.read_bytes(),before);self.assertFalse(self.after.exists())
        self.assertEqual(self.records[0]['native_usage']['output_tokens'],4)

    def fake_engine(self,regress=False):
        def run(path,*a):
            job=json.loads(Path(path).read_text(encoding='utf-8'))
            self.assertTrue(job['provider']['cache_only'])
            self.assertNotEqual(job['output'],self.base['output'])
            self.assertTrue(Path(job['provider']['quality_corrections_file']).is_file())
            out=Path(job['output']);out.mkdir()
            with fitz.open(self.before) as doc:
                doc[0].insert_text((30,120),'Local candidate.')
                if regress:doc[1].insert_text((30,120),'REGRESSION')
                doc.save(out/'fixture.mono.pdf')
            return {'status':'completed','native_calls':0}
        return run

    def test_engine_is_forced_cache_only_and_reports_whole_page_reflow(self):
        with mock.patch.object(semantic_pipeline,'correction_receipt',return_value={'fixture':True}),\
             mock.patch.object(semantic_pipeline,'link_rerender',return_value=({},[])),\
             mock.patch.object(pdf_translate,'run_job',side_effect=self.fake_engine()):
            edits,_=self.call(self.invoke())
        self.assertEqual(edits[0]['method'],'native_engine_gap_rerender')
        self.assertEqual(edits[0]['region']['bbox'],list(self.doc[0].rect))
        self.assertTrue(edits[0]['other_page_pixels_unchanged'])

    def test_changed_other_page_pixels_reject_even_when_pair_receipt_matches(self):
        with mock.patch.object(semantic_pipeline,'correction_receipt',return_value={'fixture':True}),\
             mock.patch.object(semantic_pipeline,'link_rerender',return_value=({},[])),\
             mock.patch.object(pdf_translate,'run_job',side_effect=self.fake_engine(True)):
            with self.assertRaisesRegex(ValueError,'GAP_ENGINE_CHANGED_OTHER_PAGE_PIXELS'):self.call(self.invoke())


if __name__=='__main__':unittest.main()
