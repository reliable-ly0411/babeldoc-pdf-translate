"""Production orchestration and role separation; deterministic inference fixtures."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
from unittest.mock import patch
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pdf_pipeline as p
import visual_review as v


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'source.pdf';self.mono=self.root/'translated.pdf'
        for path in (self.source,self.mono):
            with pymupdf.open() as doc:
                doc.new_page(width=500,height=300).insert_text((30,60),'The voltage is 5 volts.',fontsize=14)
                doc.save(path)
        self.translation={'input':'source.pdf','output':'translation','target_language':'zh-CN','outputs':'both',
                          'provider':{'type':'codex','model':'low-cost-text'}}
        self.job={'translation_job':'translation.json','output':'production',
                  'review':{'provider':{'type':'codex','model':'low-cost-vision','vision':True,'retries':0},
                            'repair':True,'limits':{'max_model_calls':4}}}
        self.path=self.root/'pipeline.json'
        self.save()

    def tearDown(self):self.tmp.cleanup()
    def save(self):
        v.save_json(self.root/'translation.json',self.translation);v.save_json(self.path,self.job)
    def translator(self,path,engine,execute=False):
        if not execute:
            return {'provider':{'type':'codex','model':'low-cost-text'},'arguments':['--files',str(self.source)]}
        return {'status':'needs-review','output_validation':{'files':[{'kind':'mono','valid':True,'file':str(self.mono)}]}}

    def test_separate_models_complete_review_repair_recheck_and_keep_inputs(self):
        models=[]
        class Vision:
            version='fixture'
            def __init__(self,provider):self.calls=0;models.append(provider['model'])
            def doctor(self):return {'ready':True,'native_version':'fixture'}
            def inspect(self,prompt,images,timeout):
                self.calls+=1
                if len(images)==1:
                    return {'issues':[{'region_id':'','category':'layout','severity':'minor','reason':'A1B2C3D4','replacement':''}]},None
                if self.calls==2:
                    return {'issues':[{'region_id':'block_0','category':'missing_translation','severity':'major','reason':'Still English.','replacement':'电压为5伏。'}]},None
                return {'issues':[]},None
        before=self.mono.read_bytes()
        with patch.object(p.translate,'run_job',side_effect=self.translator),patch.object(v,'NativeVision',Vision),patch.object(v.secrets,'token_hex',return_value='a1b2c3d4'):
            report=p.run(self.path,'fixture-engine',execute=True)
        self.assertEqual(report['status'],'model_screened')
        self.assertEqual(report['translation_model'],'low-cost-text')
        self.assertEqual(report['review_model'],'low-cost-vision')
        self.assertEqual(models,['low-cost-vision'])
        self.assertEqual(report['model_calls'],3)
        self.assertEqual(self.mono.read_bytes(),before)
        with pymupdf.open(self.root/'production/best.mono.pdf') as doc:self.assertIn('电压',doc[0].get_text())
        self.assertEqual(json.loads((self.root/'production/visual/review-report.json').read_text(encoding='utf8'))['purpose'],'production')

    def test_translation_failure_does_not_start_vision_or_any_fallback(self):
        def failed(path,engine,execute=False):
            return {'status':'failed'} if execute else self.translator(path,engine)
        with patch.object(p.translate,'run_job',side_effect=failed),patch.object(v,'run') as review:
            result=p.run(self.path,'fixture-engine',True)
        self.assertEqual(result['status'],'failed');review.assert_not_called()

    def test_final_audit_hook_reads_actual_outputs_after_normal_recheck(self):
        captured=[]
        def reviewed(cfg):
            cfg['output'].mkdir()
            shutil.copyfile(self.mono,cfg['output']/'best.mono.pdf')
            v.bilingual(self.source,self.mono,cfg['output']/'best.dual.pdf')
            return {'status':'model_screened','model_calls':3,'vision_capability_verified':True,
                    'execution_status':'completed','quality_status':'model_screen_only_pending_independent_acceptance','selected_pages':[1]}
        def terminal(source,artifacts,output,upstream):
            captured.append((source,{k:p.read_bytes() for k,p in artifacts.items()},upstream['review_model']))
            return {'execution_status':'completed','quality_passed':False,'delivery_allowed':False,
                    'final_artifacts':{k:str(p) for k,p in artifacts.items()},'receipt':None,'model_calls':1,'cost_usd':None}
        with patch.object(p.translate,'run_job',side_effect=self.translator),patch.object(v,'run',side_effect=reviewed):
            result=p.run(self.path,'fixture',True,final_audit_hook=terminal)
        self.assertEqual(len(captured),1)
        self.assertEqual(captured[0][0],self.source)
        self.assertEqual(captured[0][2],'low-cost-vision')
        self.assertTrue(all(captured[0][1].values()))
        self.assertEqual(result['model_calls'],3)
        self.assertEqual(result['additional_final_model_calls'],1)
        self.assertFalse(result['delivery_allowed'])

    def test_production_translation_and_review_reject_astra(self):
        self.translation['provider']['model']='gpt-6-astra';self.save()
        with patch.object(p.translate,'run_job') as translator:
            with self.assertRaisesRegex(ValueError,'development acceptance'):p.prepare(self.path,'fixture')
            translator.assert_not_called()
        self.translation['provider']['model']='low-cost-text'
        self.job['review']['provider']['model']='gpt-6-astra';self.save()
        with patch.object(p.translate,'run_job') as translator:
            with self.assertRaisesRegex(ValueError,'development acceptance'):p.prepare(self.path,'fixture')
            translator.assert_not_called()

    def test_invalid_vision_and_implicit_translation_model_fail_before_inference(self):
        with patch.object(p.translate,'run_job') as translator:
            self.job['review']['provider']['vision']=False;self.save()
            with self.assertRaisesRegex(ValueError,'vision=true'):p.prepare(self.path,'fixture-engine')
            translator.assert_not_called()
            self.job['review']['provider']['vision']=True
            self.translation['provider'].pop('model');self.save()
            with self.assertRaisesRegex(ValueError,'explicitly'):p.prepare(self.path,'fixture-engine')

    def test_development_acceptance_cannot_act_as_production_repair(self):
        with self.assertRaisesRegex(ValueError,'cannot repair'):
            v.validate_options({'provider':self.job['review']['provider'],'repair':True,'purpose':'development_acceptance'},self.root)

    def test_optional_math_scale_guard_is_validated_before_translation(self):
        self.job['review']['math_scale_guard']=True;self.save()
        with patch.object(p.translate,'run_job',side_effect=self.translator):
            self.assertTrue(p.prepare(self.path,'fixture')[2]['math_scale_guard'])
        self.job['review']['math_scale_guard']='yes';self.save()
        with patch.object(p.translate,'run_job') as translator:
            with self.assertRaisesRegex(ValueError,'math_scale_guard must be a boolean'):p.prepare(self.path,'fixture')
            translator.assert_not_called()

    def test_targeted_math_mode_is_explicit_and_keeps_its_limited_budget(self):
        self.job['review'].update(review_mode='math_audits',focused_recheck=True,math_operator_guard=True,
            limits={'max_model_calls':1})
        self.save()
        with patch.object(p.translate,'run_job',side_effect=self.translator):
            review=p.prepare(self.path,'fixture')[2]
        self.assertEqual(review['review_mode'],'math_audits')
        self.assertEqual(review['limits']['max_model_calls'],1)

    def test_chinese_pipeline_enables_prose_screen_without_forcing_other_targets(self):
        with patch.object(p.translate,'run_job',side_effect=self.translator):
            self.assertTrue(p.prepare(self.path,'fixture')[2]['chinese_prose_guard'])
            self.translation['target_language']='en';self.save()
            self.assertFalse(p.prepare(self.path,'fixture')[2].get('chinese_prose_guard',False))

    def test_unsupported_final_audit_language_is_rejected_before_translation_calls(self):
        import final_audit
        self.translation['target_language']='fr';self.save()
        with patch.object(p.translate,'run_job',side_effect=self.translator) as translator:
            hook=final_audit.make_pipeline_hook(lambda *args:None,max_repair_rounds=0)
            with self.assertRaisesRegex(ValueError,'REQUIRES_ENGLISH_TO_SIMPLIFIED_CHINESE'):
                p.run(self.path,'fixture',True,final_audit_hook=hook)
        self.assertEqual(translator.call_count,1)
        self.assertFalse(translator.call_args.kwargs['execute'])

    def test_review_uses_same_prompt_glossary_and_refuses_changed_preferences(self):
        (self.root/'prompt.txt').write_text('Keep English technical terms followed by Chinese glosses.',encoding='utf8')
        (self.root/'terms.csv').write_text('source,target\nstate predictor,state predictor（状态预测器）\n',encoding='utf8')
        self.translation.update(prompt_file='prompt.txt',glossaries=['terms.csv']);self.save()
        with patch.object(p.translate,'run_job',side_effect=self.translator):
            _,_,review,_=p.prepare(self.path,'fixture')
        self.assertIn('state predictor（状态预测器）',review['translation_context'])
        self.assertIn('English technical terms',review['translation_context'])
        def changed(path,engine,execute=False):
            result=self.translator(path,engine,execute)
            if execute:(self.root/'prompt.txt').write_text('Changed style.',encoding='utf8')
            return result
        with patch.object(p.translate,'run_job',side_effect=changed),patch.object(v,'run') as model:
            result=p.run(self.path,'fixture',True)
        self.assertEqual(result['status'],'failed')
        self.assertIn('preferences changed',result['error_code'])
        model.assert_not_called()


if __name__=='__main__':unittest.main()
