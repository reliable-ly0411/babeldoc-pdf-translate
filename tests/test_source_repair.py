"""Offline regression tests for source-derived, formula-preserving repairs."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import source_repair as r
import visual_review as v


ISSUE={'region_id':'block_0','category':'translation','severity':'critical',
       'reason':'Continuous and bounded are omitted.','replacement':''}


class SourceRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for label in ('source','translated'):
            with fitz.open() as doc:
                p=doc.new_page(width=500,height=500)
                text='Continuous and bounded in' if label=='source' else 'Incorrect translation'
                p.insert_text((30,80),text,fontsize=12)
                p.insert_text((240,80),'x',fontname='symb',fontsize=12)
                p.insert_text((30,180),'Unchanged second paragraph.',fontsize=12)
                p.draw_line((30,230),(300,230),color=(0,0,1))
                doc.new_page(width=500,height=500).insert_text((30,60),'Untouched page.')
                doc.save(self.root/(label+'.pdf'))
        self.source=fitz.open(self.root/'source.pdf');self.target=fitz.open(self.root/'translated.pdf')

    def tearDown(self):self.source.close();self.target.close();self.tmp.cleanup()

    def plan(self):
        known=v.regions(self.target[0]);island,error=r.derive_island(self.source[0],self.target[0],known[0])
        self.assertIsNone(error)
        return island

    def test_original_math_and_other_pixels_survive_source_repair(self):
        island=self.plan();units=r.units(self.source[0],fitz.Rect(island['bbox']),island['kind'])
        self.assertEqual([u['source'] for u in units],['Continuous and bounded in'])
        result=r.restore_region(self.source,0,self.target,0,island,['连续、有界，且关于'])
        self.assertEqual(result['source_protected_spans_verified'],1)
        after=self.root/'after.pdf';self.target.save(after)
        self.assertTrue(v.regression_check(self.root/'translated.pdf',after,1,[island['bbox']]))
        with fitz.open(after) as doc:
            self.assertIn('连续',doc[0].get_text())
            self.assertEqual(r.protected_signature(self.source[0],island['bbox'],[b for u in units for b in u['boxes']]),
                [x for x in r.protected_signature(doc[0],island['bbox'],[]) if x[0]=='Symbol'])

    def test_added_numeric_prefix_and_missing_units_are_refused(self):
        for text,replacement in [('Quad controller','L1Quad 控制器'),('Weight [g]','重量'),('Assumption 1:','假设 2：'),
                                 ('from 1 to 2','从 2 到 1'),('grant 80NSSC22M0070','资助 80nssc22m0070')]:
            self.assertFalse(r.validate_translation({'source':text},replacement))
        self.assertTrue(r.validate_translation({'source':'Quad controller'},'Quad 控制器'))
        self.assertTrue(r.validate_translation({'source':'Weight [g]'},'重量 [g]'))

    def test_new_ink_on_math_is_detected_even_with_same_original_glyph(self):
        island=self.plan();boxes=[box for u in r.units(self.source[0],island['bbox'],island['kind']) for box in u['boxes']]
        with fitz.open() as changed:
            changed.insert_pdf(self.source)
            changed[0].insert_text((240,80),'WRONG',fontsize=12)
            self.assertFalse(r.protected_pixels(self.source[0],changed[0],island['bbox'],boxes))

    def test_blank_font_metric_margin_is_not_mistaken_for_math_ink(self):
        import numpy as np
        page=self.source[0]
        span=next(s for block in r.text_blocks(page) for line in block['lines'] for s in line['spans'] if s['font']=='Symbol')
        box=fitz.Rect(span['bbox']);pix=page.get_pixmap(dpi=144,alpha=False)
        pixels=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        yy,_=np.where(np.any(pixels[int(box.y0*2):int(box.y1*2)+1,int(box.x0*2):int(box.x1*2)+1]<250,axis=2))
        blank_height=float(yy.min())/2
        self.assertGreater(blank_height,2)
        dot=fitz.Rect(box.x0+1,box.y0+.25,box.x0+2,box.y0+1)
        with fitz.open() as changed:
            changed.insert_pdf(self.source)
            changed[0].draw_rect(dot,color=(0,0,0),fill=(0,0,0),width=0)
            self.assertTrue(r.protected_pixels(page,changed[0],box,[list(dot)]))

    def test_graphics_difference_and_oversized_closure_fail_closed(self):
        known=v.regions(self.target[0]);region=known[0]
        self.target[0].draw_line((35,75),(200,75),color=(1,0,0))
        self.assertEqual(r.derive_island(self.source[0],self.target[0],region)[1],'SOURCE_ISLAND_GRAPHICS_DIFFER')
        self.assertEqual(r.derive_island(self.source[0],self.target[0],{'bbox':[0,0,500,500]})[1],
            'SOURCE_ISLAND_TOO_LARGE')

    def test_named_slots_reject_extra_fields_wrong_counts_and_math(self):
        plans=[{'units':[{'source':'bounded in'}]}]
        self.assertEqual(v.checked_source_plan({'region_0':{'slot_00':'有界于'}},plans),[['有界于']])
        for value in ({'regions':[]},{'region_0':{'slot_00':'有界','bbox':[]}},
                      {'region_0':{'slot_00':'有界于 x=5'}},{'region_0':{'slot_00':''}}):
            with self.assertRaises(ValueError):v.checked_source_plan(value,plans)

    def test_more_than_ten_slot_names_keep_numeric_reading_order(self):
        plans=[{'units':[{'source':'word'} for _ in range(18)]}]
        schema=v.source_plan_schema(plans)
        expected=['slot_%02d'%n for n in range(18)]
        fields=schema['properties']['region_0']['properties']
        self.assertEqual(list(fields),expected)
        self.assertEqual(sorted(fields),expected)
        response={'region_0':{name:'词' for name in expected}}
        self.assertEqual(v.checked_source_plan(response,plans),[['词']*18])

    def test_critical_issues_precede_minor_and_duplicate_islands(self):
        known=v.regions(self.target[0]);minor={**ISSUE,'severity':'minor'}
        plans,decisions=r.prepare(self.source[0],self.target[0],known,[minor,ISSUE,ISSUE],3)
        self.assertEqual(len(plans),1)
        self.assertEqual(plans[0]['issue']['severity'],'critical')
        self.assertEqual([x['reason'] for x in decisions],
            ['SOURCE_ISLAND_PREPARED','COVERED_BY_SOURCE_ISLAND','SERIOUS_ISSUES_FIRST'])

    def test_one_call_plan_plus_followup_and_cache_replay(self):
        class Client:
            version='fixture-source-1'
            def doctor(self):return {'native_version':self.version}
            def inspect(self,prompt,images,timeout,schema=None):
                if len(images)==1:return {'issues':[{'region_id':'','category':'layout','severity':'minor','reason':'A1B2C3D4','replacement':''}]},{'input_tokens':1}
                if schema is not None:
                    self.assert_schema=schema
                    return {'region_0':{'slot_00':'连续、有界，且关于'}},{'input_tokens':2}
                return ({'issues':[]} if '连续' in prompt else {'issues':[ISSUE]}),{'input_tokens':3}
        config={'source':'source.pdf','translated':'translated.pdf','output':'review','pages':[1],
            'repair':True,'provider':{'type':'codex','model':'fixture-vision','vision':True,'retries':0,'cache_dir':'cache'},
            'limits':{'max_model_calls':4}}
        path=self.root/'review.json';v.save_json(path,config)
        with patch.object(v.secrets,'token_hex',return_value='a1b2c3d4'):
            result=v.run(v.load_config(path),Client())
            self.assertEqual(result['status'],'sample_model_screened',result)
            self.assertEqual(result['model_calls'],4)
            self.assertEqual(result['pages'][0]['accepted_repairs'][0]['method'],'source_prose_slots')
            config['output']='repeat';v.save_json(path,config)
            replay=v.run(v.load_config(path),Client())
        self.assertEqual(replay['model_calls'],1)
        self.assertEqual(replay['cache_hits'],3)
        self.assertTrue(v.regression_check(self.root/'review/best.mono.pdf',self.root/'repeat/best.mono.pdf',1,[]))

    def test_guard_rejection_gets_only_one_recorded_correction(self):
        for correction_valid in (True,False):
            with self.subTest(correction_valid=correction_valid):
                class Client:
                    version='fixture-correction-1';plans=0
                    def doctor(self):return {'native_version':self.version}
                    def inspect(self,prompt,images,timeout,schema=None):
                        if len(images)==1:return {'issues':[{'region_id':'','category':'layout','severity':'minor','reason':'A1B2C3D4','replacement':''}]},{'input_tokens':1}
                        if schema is not None:
                            self.plans+=1
                            text='连续、有界，且关于' if correction_valid and self.plans==2 else '连续、有界 x=5'
                            return {'region_0':{'slot_00':text}},{'input_tokens':2}
                        return ({'issues':[]} if '连续' in prompt else {'issues':[ISSUE]}),{'input_tokens':3}
                config={'source':'source.pdf','translated':'translated.pdf','output':'correction-'+str(correction_valid),
                    'pages':[1],'repair':True,'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
                    'limits':{'max_model_calls':5}}
                path=self.root/'config.json';v.save_json(path,config);client=Client()
                with patch.object(v.secrets,'token_hex',return_value='a1b2c3d4'):
                    report=v.run(v.load_config(path),client)
                self.assertEqual(client.plans,2)
                self.assertEqual(report['status'],'sample_model_screened' if correction_valid else 'failed')
                self.assertEqual(report['model_calls'],5 if correction_valid else 4)
                self.assertEqual(len(report['requests']),report['model_calls'])
                self.assertIn('region_0/paragraph',report['requests'][2]['error_code'])
                self.assertEqual(report['requests'][3]['purpose'],'source_prose_plan_correction')
                folder=self.root/config['output']/'page-001-round-1'
                self.assertTrue((folder/'source-prose-response-1.json').exists())
                self.assertTrue((folder/'source-prose-response-2.json').exists())
                if not correction_valid:
                    self.assertEqual((self.root/config['output']/'best.mono.pdf').read_bytes(),(self.root/'translated.pdf').read_bytes())

    def test_small_caps_initial_letters_belong_to_translatable_prose(self):
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500)
            p.insert_text((30,80),'IV.',fontsize=10)
            p.insert_text((60,80),'x',fontname='symb',fontsize=10)
            p.insert_text((80,80),'A',fontsize=10)
            p.insert_text((87,80),'DAPTIVE',fontsize=8)
            result=r.units(p,fitz.Rect(29,60,200,90),'mixed_prose')
            self.assertEqual([u['source'] for u in result],['ADAPTIVE'])

    def test_numbers_units_and_grant_ids_are_owned_by_program(self):
        units=[{'source':'Assumption 1 and 2, grant 80NSSC22M0070 in [g]'}]
        self.assertTrue(r.validate_paragraphs(units,['假设 1 和 2，资助 80NSSC22M0070，单位 [g]']))
        for text in ('假设1和2','假设1和2，资助80nssc22m0070，单位[g]',
                     '假设1和2，资助80NSSC22M0070，单位[kg]'):
            self.assertFalse(r.validate_paragraphs(units,[text]))

    def test_chinese_can_reorder_prose_within_a_paragraph_but_not_drop_one(self):
        units=[{'source':'upper bound in','paragraph':1},{'source':'Assumption 2','paragraph':1}]
        self.assertTrue(r.validate_paragraphs(units,['假设2中的上界','']))
        units[1]['paragraph']=2
        self.assertFalse(r.validate_paragraphs(units,['假设2中的上界','']))
        self.assertFalse(r.validate_paragraphs(units,['','']))
        self.assertFalse(r.validate_paragraphs(units,['上界……','假设2']))

    def test_name_suffix_attached_to_math_stays_original(self):
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500)
            p.insert_text((60,80),'x',fontname='symb',fontsize=10)
            edge=60+fitz.get_text_length('x',fontname='symb',fontsize=10)
            p.insert_text((edge+.3,80),'Quad',fontsize=10)
            p.insert_text((edge+30,80),' controller',fontsize=10)
            result=r.units(p,fitz.Rect(50,60,200,90),'mixed_prose')
            self.assertTrue(result)
            self.assertNotIn('Quad',' '.join(x['source'] for x in result))


if __name__=='__main__':unittest.main()
