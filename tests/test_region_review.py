"""Real rendered triptychs, bounded fake replies; no model/network calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as bridge
import region_review as r
import source_repair as source
import visual_review as v


ISSUE={'region_id':'block_0','category':'missing_translation','severity':'major',
       'reason':'The source paragraph is still English.','replacement':'电压为5伏。'}
LOCAL={**ISSUE,'region_id':'island_0','replacement':''}


class Client:
    version='focused-fixture-1'
    def __init__(self,initial,focused):self.initial=initial;self.focused=copy.deepcopy(focused);self.attachments=[]
    def doctor(self):return {'ready':True,'native_version':self.version}
    def inspect(self,prompt,images,timeout,schema=None):
        self.attachments.append((len(images),schema is not None))
        if schema is not None:
            assert set(schema['properties'])=={'before','after'}
            assert len(images)==1 and images[0].is_file()
            return self.focused.pop(0),{'input_tokens':30,'output_tokens':10}
        if len(images)==1:
            return {'issues':[{'region_id':'','category':'layout','severity':'minor',
                'reason':'A1B2C3D4','replacement':''}]},{'input_tokens':1}
        return copy.deepcopy(self.initial),{'input_tokens':20}


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for label in ('source','translated'):
            with fitz.open() as doc:
                p=doc.new_page(width=400,height=400)
                p.insert_text((30,80),'The voltage is 5 volts.',fontsize=12)
                p.insert_text((30,300),'Outside paragraph.',fontsize=12)
                doc.save(self.root/(label+'.pdf'))

    def tearDown(self):self.temp.cleanup()

    def config(self,output='review',rounds=1,edits=1,cache=False):
        value={'source':'source.pdf','translated':'translated.pdf','output':output,
            'pages':[1],'repair':True,'focused_recheck':True,
            'provider':{'type':'codex','model':'fixture','vision':True,'retries':0},
            'limits':{'max_rounds':rounds,'max_repairs_per_page':edits,'max_model_calls':6}}
        if cache:value['provider']['cache_dir']='cache'
        path=self.root/'job.json';v.save_json(path,value)
        return v.load_config(path)

    def run_review(self,cfg,client):
        with patch.object(v.secrets,'token_hex',return_value='a1b2c3d4'):return v.run(cfg,client)

    def test_schema_refuses_empty_unknown_or_model_coordinates(self):
        good={'before':{'issues':[LOCAL]},'after':{'issues':[]}}
        self.assertEqual(r.checked(good,v.SCHEMA,['island_0']),good)
        for issue in ({**LOCAL,'region_id':''},{**LOCAL,'region_id':'block_0'},
                      {**LOCAL,'bbox':[0,0,400,400]},{**LOCAL,'replacement':'New text'}):
            with self.assertRaises(ValueError):r.checked({'before':{'issues':[issue]},'after':{'issues':[]}},v.SCHEMA,['island_0'])

    def test_qa_closure_reports_reflowed_graphics_without_authorizing_source_copy(self):
        with fitz.open(self.root/'source.pdf') as a,fitz.open(self.root/'translated.pdf') as b:
            b[0].draw_line((80,75),(100,75))
            before_a=a.tobytes(no_new_id=True);before_b=b.tobytes(no_new_id=True)
            region=r.prose_review_island(a[0],b[0],b[0],'The voltage is 5 volts.')
            self.assertEqual(a.tobytes(no_new_id=True),before_a);self.assertEqual(b.tobytes(no_new_id=True),before_b)
            self.assertLess(region['bbox'][3],200)
            self.assertNotEqual(region['geometry'][0]['drawing_geometry_sha256'],region['geometry'][1]['drawing_geometry_sha256'])
            self.assertTrue(region['before_candidate_drawing_geometry_equal'])
            self.assertEqual(source.derive_island(a[0],b[0],region)[1],'SOURCE_ISLAND_GRAPHICS_DIFFER')

    def test_qa_closure_requires_unique_complete_source_prose_and_matching_page(self):
        with fitz.open(self.root/'source.pdf') as a,fitz.open(self.root/'translated.pdf') as b:
            for text in ('no such source paragraph','voltage is 5 volts.'):
                with self.assertRaises(ValueError):r.prose_review_island(a[0],b[0],b[0],text)
            b[0].set_rotation(90)
            with self.assertRaisesRegex(ValueError,'REVIEW_PAGE_GEOMETRY_CHANGED'):
                r.prose_review_island(a[0],b[0],b[0],'The voltage is 5 volts.')

    def test_repair_acceptance_keeps_outside_and_unmapped_math_findings(self):
        unknown={**ISSUE,'region_id':'','category':'formula','severity':'critical','replacement':''}
        outside={**ISSUE,'region_id':'block_1','category':'header_footer','severity':'minor','replacement':''}
        client=Client({'issues':[ISSUE,unknown,outside]},[{'before':{'issues':[LOCAL]},'after':{'issues':[]}}])
        report=self.run_review(self.config(),client)
        self.assertEqual(report['status'],'needs_manual_review',report)
        self.assertEqual(report['model_calls'],3)
        self.assertEqual(len(report['pages'][0]['accepted_repairs']),1)
        self.assertEqual({i['category'] for i in report['pages'][0]['issues']},{'formula','header_footer'})
        self.assertEqual(report['repair_acceptance_version'],2)
        self.assertTrue((self.root/'review/page-001-round-1/focused-0.png').is_file())
        self.assertTrue(v.regression_check(self.root/'translated.pdf',self.root/'review/best.mono.pdf',1,
            [e['region']['bbox'] for e in report['pages'][0]['accepted_repairs']]))

    def test_partial_overlap_cannot_silently_resolve_whole_original_finding(self):
        region={'id':'block_0','bbox':[20,20,200,200],'text':'entire paragraph'}
        edits=[{'region':{'bbox':[20,20,200,100]}}]
        focused={'before':{'issues':[LOCAL]},'after':{'issues':[]}}
        accepted,retained,_,_=r.assess({'issues':[ISSUE]},focused,[region],[],edits,v.improved)
        self.assertTrue(accepted)
        self.assertEqual(len(retained['issues']),1)
        self.assertTrue(retained['issues'][0]['region_id'].startswith('retained_'))

    def test_one_improved_island_cannot_offset_another_unchanged_or_worse_island(self):
        edits=[{'region':{'bbox':[10,10,100,80]}},{'region':{'bbox':[10,100,100,180]}}]
        other={**LOCAL,'region_id':'island_1'}
        before={'issues':[LOCAL,other]}
        for after in ([{**other,'new_or_worse':False}],
                      [{**other,'severity':'minor','new_or_worse':True}]):
            accepted,_,_,decision=r.assess({'issues':[]},{'before':before,'after':{'issues':after}},[],[],edits,v.improved)
            self.assertFalse(accepted)
            self.assertTrue(decision['per_island'][0]['improved'])

    def test_new_semantic_loss_vetoes_repair_even_in_the_same_category(self):
        focused={'before':{'issues':[LOCAL]},'after':{'issues':[{**LOCAL,
            'severity':'minor','new_or_worse':True}]}}
        accepted,_,_,_=r.assess({'issues':[]},focused,[],[],[{'region':{'bbox':[10,10,100,100]}}],v.improved)
        self.assertFalse(accepted)

    def test_full_page_unmapped_finding_cannot_be_forgotten_after_local_repair(self):
        outside={**LOCAL,'region_id':'page_context','category':'formula','severity':'critical'}
        focused={'before':{'issues':[LOCAL,outside]},'after':{'issues':[]}}
        accepted,retained,_,_=r.assess({'issues':[]},focused,[],[],[{'region':{'bbox':[10,10,100,100]}}],v.improved)
        self.assertTrue(accepted)  # Local repair may improve; document still unresolved.
        self.assertEqual(len(retained['issues']),1)
        self.assertEqual(retained['issues'][0]['region_id'],'')
        self.assertEqual(retained['issues'][0]['severity'],'critical')

    def test_verified_objective_improvement_handles_blind_before_and_after(self):
        edits=[{'region':{'bbox':[10,10,100,100]}}]
        blind={'before':{'issues':[]},'after':{'issues':[]}}
        self.assertFalse(r.assess({'issues':[]},blind,[],[],edits,v.improved)[0])
        accepted,_,_,decision=r.assess({'issues':[]},blind,[],[],edits,v.improved,{'island_0':True})
        self.assertTrue(accepted)
        self.assertTrue(decision['per_island'][0]['objective_improvement'])
        self.assertTrue(decision['per_island'][0]['model_nonworse'])

    def test_objective_improvement_never_overrides_model_regression(self):
        edits=[{'region':{'bbox':[10,10,100,100]}}]
        for after in ([{**LOCAL,'new_or_worse':False}],
                      [{**LOCAL,'severity':'minor','new_or_worse':True}]):
            focused={'before':{'issues':[]},'after':{'issues':after}}
            self.assertFalse(r.assess({'issues':[]},focused,[],[],edits,v.improved,{'island_0':True})[0])

    def test_objective_improvement_must_apply_to_every_edited_island(self):
        edits=[{'region':{'bbox':[10,10,100,80]}},{'region':{'bbox':[10,100,100,180]}}]
        blind={'before':{'issues':[]},'after':{'issues':[]}}
        self.assertFalse(r.assess({'issues':[]},blind,[],[],edits,v.improved,{'island_0':True})[0])

    def test_rejected_candidate_gets_only_one_second_round_from_retained_pdf(self):
        client=Client({'issues':[ISSUE]},[
            {'before':{'issues':[LOCAL]},'after':{'issues':[{**LOCAL,'new_or_worse':False}]}},
            {'before':{'issues':[LOCAL]},'after':{'issues':[]}}])
        report=self.run_review(self.config(rounds=2,edits=2),client)
        self.assertEqual(report['status'],'model_screened',report)
        self.assertEqual([a['accepted'] for a in report['pages'][0]['attempts']],[False,True])
        self.assertEqual(len(report['pages'][0]['accepted_repairs']),1)
        self.assertEqual(report['model_calls'],4)
        self.assertEqual(len(client.focused),0)

    def test_focused_cache_replay_requires_only_fresh_capability_probe(self):
        first=self.run_review(self.config(cache=True),Client({'issues':[ISSUE]},[
            {'before':{'issues':[LOCAL]},'after':{'issues':[]}}]))
        client=Client({'issues':[]},[])
        second=self.run_review(self.config(output='repeat',cache=True),client)
        self.assertEqual(first['status'],second['status'])
        self.assertEqual(second['model_calls'],1)
        self.assertEqual(second['cache_hits'],2)
        self.assertTrue(v.regression_check(self.root/'review/best.mono.pdf',self.root/'repeat/best.mono.pdf',1,[]))

    def test_visual_failed_invocation_is_durably_recorded_with_unknown_usage(self):
        class Failed:
            def inspect(self,*args,**kwargs):raise bridge.BridgeError('QUOTA')
        cfg=self.config();folder=self.root/'failed';folder.mkdir()
        record={'purpose':'focused_repair_comparison','model':'fixture','backend':'codex'}
        with self.assertRaises(bridge.BridgeError):v.call_model(Failed(),'private source',[],cfg,v.Budget(cfg['limits']),folder,record)
        journal=json.loads(next((folder/'attempt-journal').glob('*.json')).read_text(encoding='utf8'))
        self.assertEqual(journal['state'],'returned');self.assertEqual(journal['error_code'],'QUOTA')
        self.assertIsNone(journal['native_usage']);self.assertNotIn('private source',json.dumps(journal))

    def test_explicit_contact_policy_can_restore_original_metadata_without_prose_model(self):
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500)
            p.insert_text((30,430),'A. Smith, Example University, ',fontsize=9)
            p.insert_text((160,430),'a@example.org',fontname='cour',fontsize=8)
            area=fitz.Rect(20,410,380,450)
            default=source.units(p,area,'contact_metadata')
            protected=source.units(p,area,'contact_metadata',preserve_metadata=True)
            self.assertTrue(default);self.assertEqual(protected,[])
            island={'bbox':list(area),'kind':'contact_metadata','preserve_contact_metadata':True}
            with fitz.open() as target:
                target.insert_pdf(doc)
                result=source.restore_region(doc,0,target,0,island,[])
                self.assertEqual(result['slots'],0)
                self.assertGreater(result['source_protected_spans_verified'],0)
                self.assertIn('A. Smith',target[0].get_text());self.assertIn('a@example.org',target[0].get_text())

    def test_removed_adjacent_whitespace_is_not_a_changed_protected_math_glyph(self):
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500)
            p.insert_text((50,100),'Prose ',fontsize=10)
            p.insert_text((80,100),' x',fontname='symb',fontsize=10)
            area=fitz.Rect(40,80,140,120)
            protected=source.protected_signature(p,area,[[50,90,80,105]])
            before=[item for item in protected if item[1]=='x']
            self.assertEqual(len(before),1)
            p.add_redact_annot(fitz.Rect(50,90,80.1,105),fill=False)
            p.apply_redactions(images=0,graphics=0,text=0)
            after=[item for item in source.protected_signature(p,area,[]) if item[1]=='x']
            self.assertEqual(before,after)
            p.add_redact_annot(fitz.Rect(83,90,90,105),fill=False)
            p.apply_redactions(images=0,graphics=0,text=0)
            self.assertNotEqual(before,[item for item in source.protected_signature(p,area,[]) if item[1]=='x'])

    def test_equation_boundary_can_use_source_prose_when_target_cjk_is_fragmented(self):
        with fitz.open() as a,fitz.open() as b:
            for doc in (a,b):
                page=doc.new_page(width=500,height=700)
                page.insert_text((460,140),'(18)',fontsize=10)
                page.insert_text((270,165),'where x = 1',fontsize=10)
                page.insert_text((270,210),'An adaptive controller combines a predictor with a low-pass filter.',fontsize=7)
            issue={**ISSUE,'region_id':'','category':'formula','replacement':'',
                'reason':'The mathematical definitions following equation (18) overlap.'}
            known,mapped,decisions=v.resolve_equation_issues(a[0],b[0],v.regions(b[0]),[issue])
            self.assertEqual(mapped[0]['region_id'],'equation_18')
            self.assertEqual(decisions[0]['boundary_method'],'source_prose_boundary_with_unmoved_unique_anchor')
            self.assertLess(known[-1]['bbox'][3],210)
            b[0].add_redact_annot(fitz.Rect(455,125,490,145));b[0].apply_redactions()
            b[0].insert_text((460,148),'(18)',fontsize=10)
            _,mapped,_=v.resolve_equation_issues(a[0],b[0],v.regions(b[0]),[issue])
            self.assertEqual(mapped[0]['region_id'],'')

    def test_explicit_localized_equation_references_map_the_same_unique_region(self):
        with fitz.open() as a,fitz.open() as b:
            for doc in (a,b):
                p=doc.new_page(width=500,height=700)
                p.insert_text((460,140),'(18)',fontsize=10)
                p.insert_text((270,165),'where x = 1',fontsize=10)
                p.insert_text((270,210),'An adaptive controller combines a predictor with a low-pass filter.',fontsize=7)
            for reason in ('方程(18)后矩阵定义重叠。','公式（18）后的定义重叠。','式18后定义难以对应。'):
                issue={**ISSUE,'region_id':'','category':'formula','replacement':'','reason':reason}
                _,mapped,_=v.resolve_equation_issues(a[0],b[0],v.regions(b[0]),[issue])
                self.assertEqual(mapped[0]['region_id'],'equation_18')

    def test_multiple_or_range_equation_references_remain_ambiguous(self):
        for reason in ('方程(18)和(19)有问题。','方程18与19有问题。','Equation (18)-(19) overlap.',
                       'Eqs. 18 and 19 overlap.','Equation (18) and z(0) differ.'):
            refs=v.equation_references(reason)
            self.assertNotEqual(len(refs),1,reason)

    def test_zero_capacity_connector_keeps_original_glyphs_without_moving_equation_reference(self):
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=500);x=30
            for text,font in [('we can use ','tiro'),('x','symb'),(' in (13) to describe this effect.','tiro')]:
                p.insert_text((x,90),text,fontname=font,fontsize=10)
                x+=fitz.get_text_length(text,fontname=font,fontsize=10)
            area=fitz.Rect(20,70,300,110)
            default=source.units(p,area,'mixed_prose')
            self.assertIn('in',[u['source'] for u in default])
            slots=source.units(p,area,'mixed_prose',preserve_connectors=True)
            self.assertEqual([u['source'] for u in slots],['we can use','to describe this effect.'])
            protected=source.protected_signature(p,area,[b for u in slots for b in u['boxes']])
            self.assertTrue(any(item[1]=='i' for item in protected))
            with fitz.open() as target:
                target.insert_pdf(doc)
                island={'bbox':list(area),'kind':'mixed_prose','preserve_tiny_connectors':True}
                source.restore_region(doc,0,target,0,island,['可用','描述此效应。'])
                text=target[0].get_text()
                self.assertIn('in',text);self.assertIn('(13)',text);self.assertIn('描述',text)
                # Visible original connector/math characters remain identical.
                after=source.protected_signature(target[0],area,[])
                self.assertTrue(all(item in after for item in protected))

    def test_configured_name_cannot_disappear_or_be_expanded_in_source_repair(self):
        plan={'units':[{'source':'If the Lipschitz constant is small','paragraph':1}]}
        with self.assertRaisesRegex(ValueError,'SOURCE_REPAIR_PROTECTED_NAME_CHANGED'):
            v.checked_source_plan({'region_0':{'slot_00':'若常数足够小'}},[plan],['Lipschitz'])
        self.assertEqual(v.checked_source_plan({'region_0':{'slot_00':'若 Lipschitz 常数足够小'}},[plan],['Lipschitz']),
            [['若 Lipschitz 常数足够小']])
        with self.assertRaisesRegex(ValueError,'SOURCE_REPAIR_PROTECTED_NAME_CHANGED'):
            v.checked_source_plan({'region_0':{'slot_00':'LPF 控制器'}},[{'units':[{'source':'controller'}]}],['LPF'])

    def test_signature_ignores_only_blank_font_descent_across_island_edge(self):
        with fitz.open() as doc:
            page=doc.new_page(width=240,height=240)
            page.insert_text((50,100),'real',fontname='tiro',fontsize=10)
            page.insert_text((90,100),'g',fontname='tiro',fontsize=10)
            area=fitz.Rect(40,101,150,110)
            # All font boxes cross this edge; only the g descender has ink in it.
            signature=source.protected_signature(page,area,[])
            self.assertEqual([item[1] for item in signature],['g'])
            page.add_redact_annot(fitz.Rect(89,101,98,104),fill=False,cross_out=False)
            page.apply_redactions(images=0,graphics=0,text=0)
            self.assertNotEqual(signature,source.protected_signature(page,area,[]))

    def test_outside_visible_math_change_still_fails_full_page_pixel_guard(self):
        with fitz.open() as original,fitz.open() as changed:
            page=original.new_page(width=240,height=240)
            page.insert_text((50,100),'real',fontname='tiro',fontsize=10)
            page.insert_text((90,100),'g',fontname='tiro',fontsize=10)
            area=fitz.Rect(40,101,150,110)
            changed.insert_pdf(original)
            redaction=fitz.Rect(49,101,69,103)
            changed[0].add_redact_annot(redaction,fill=False,cross_out=False)
            changed[0].apply_redactions(images=0,graphics=0,text=0)
            self.assertEqual(source.protected_signature(page,area,[]),source.protected_signature(changed[0],area,[]))
            self.assertFalse(source.protected_pixels(page,changed[0],area,[list(redaction)]))


if __name__=='__main__':unittest.main()
