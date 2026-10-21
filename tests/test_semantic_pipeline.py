"""Real PDF rerender/geometry, deterministic inference fixtures, no live calls."""
import copy,json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch,Mock
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import semantic_pipeline as p
import semantic_review as s
import chat_bridge as b
import visual_review as v
import translation_corrections as c
import final_audit as final_gate

SOURCE='Use {v1} in{v2} to describe this effect.'
BAD='使用{v1}{v2}描述该效应。'
GOOD='使用{v1}在{v2}中描述该效应。'


class FixtureClient:
    def __init__(self,uncertain=False,fail_final=False):self.uncertain=uncertain;self.fail_final=fail_final;self.screen_calls=0
    def doctor(self):return {'ready':True,'native_version':'semantic-fixture-1'}
    def inspect(self,prompt,images,timeout,schema=None):
        if schema is None:return {'issues':[{'region_id':'','category':'layout','severity':'minor','reason':'A1B2C3D4','replacement':''}]},{'input_tokens':1}
        if 'before' in schema['properties']:
            ids=schema['properties']['before']['properties']['issues']['items']['properties']['region_id']['enum']
            return {'before':{'issues':[{'region_id':key,'category':'translation','severity':'major','reason':'The reference relation is missing.','replacement':''} for key in ids if key!='page_context']},'after':{'issues':[]}},{'input_tokens':4}
        if 'replacements' in schema['properties']:
            return {'replacements':{key:GOOD for key in schema['properties']['replacements']['required']}},{'input_tokens':3}
        pairs=json.loads(prompt.split('\n')[-1])['pairs'];self.screen_calls+=1
        if self.fail_final and self.screen_calls==3:raise b.BridgeError('FIXTURE_FINAL_FAILED')
        rows={}
        for key,row in pairs.items():
            different=row['target']==BAD
            rows[key]={'status':'uncertain' if self.uncertain else 'different' if different else 'equivalent',
                'summary':'Reference relation is absent.' if different else 'Equivalent meaning.',
                'findings':[{'category':'omitted_meaning','severity':'major','source_quote':'in{v2}',
                    'target_quote':'','reason':'The relation to the equation is omitted.'}] if different and not self.uncertain else []}
        return {'pairs':rows},{'input_tokens':2,'output_tokens':1}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        with fitz.open() as doc:
            page=doc.new_page(width=400,height=400);x=30
            for text,font in [('Use ','tiro'),('x','symb'),(' in (2) to describe this effect.','tiro')]:
                page.insert_text((x,80),text,fontname=font,fontsize=11);x+=fitz.get_text_length(text,fontname=font,fontsize=11)
            page.insert_text((30,320),'Outside paragraph.',fontsize=10);doc.save(self.root/'source.pdf')
        self.job={'input':'source.pdf','output':'unused','target_language':'zh-CN','outputs':'both',
            'provider':{'type':'codex','model':'fixture-text','output_contract':'paragraphs','cache_only':True}}
        self.cfg={'translation_job':'translation.json','output':'quality',
            'review':{'provider':{'type':'codex','model':'fixture-quality','vision':True,'retries':0},
                'repair':True,'review_mode':'math_audits','focused_recheck':True,'math_scale_guard':True,
                'limits':{'max_model_calls':6,'max_rounds':1}},
            'semantic':{'max_rounds':1,'max_corrected_rows':4,'fresh_final':True}}
        self.bad_rerender=False;self.save()

    def tearDown(self):self.tmp.cleanup()
    def save(self):
        p.save(self.root/'translation.json',self.job);p.save(self.root/'pipeline.json',self.cfg)

    def translator(self,path,engine,execute=False,native_observer=None):
        if not execute:return {'provider':self.job['provider'],'arguments':['--files',str(self.root/'source.pdf')]}
        job=json.loads(path.read_text(encoding='utf8'));provider=job['provider'];folder=Path(job['output']);folder.mkdir()
        request={'messages':[{'role':'user','content':'Translate to Chinese.\n## Here is the input:\n'+b.canonical([{'id':0,'input':SOURCE}])}]}
        base=b.canonical([{'id':0,'output':BAD}]);content=base;key='a'*64
        if provider.get('quality_corrections_file'):
            content,_=c.apply(c.load(provider['quality_corrections_file']),key,request,base,paragraphs=True)
            if self.bad_rerender:content=b.canonical([{'id':0,'output':BAD}])
        target=json.loads(content)[0]['output']
        with fitz.open() as doc:
            page=doc.new_page(width=400,height=400)
            page.insert_htmlbox(fitz.Rect(30,62,285,100),target.replace('{v1}','x').replace('{v2}','(2)'),css='body {font-size:11pt}')
            page.insert_text((30,320),'Outside paragraph.',fontsize=10);doc.save(folder/'mono.pdf')
        row={'type':'pair','key':'pair_0','source':SOURCE,'target':target,'source_row_id':0,
            'cache_request_sha256':key,'base_content_sha256':c.digest(base),'source_rows_sha256':c.digest(b.canonical([{'id':0,'input':SOURCE}])),
            'base_output_sha256':c.digest(BAD),'source_sha256':c.digest(SOURCE),'target_sha256':c.digest(target),'kind':'batch'}
        Path(provider['translation_pairs_file']).write_bytes(('\n'.join(b.canonical(x) for x in
            [{'type':'start','version':1},row,{'type':'end','completed':True,'recorded_pairs':1}])+'\n').encode())
        return {'status':'needs-review','bridge':{'cache_hits':1,'attempts':0},
            'output_validation':{'files':[{'kind':'mono','valid':True,'file':str(folder/'mono.pdf')}]}}

    def run_pipeline(self,client=None,final_hook=None):
        with patch.object(p.translation,'run_job',side_effect=self.translator),patch.object(v.secrets,'token_hex',return_value='a1b2c3d4'):
            return p.run(self.root/'pipeline.json','fixture',True,client or FixtureClient(),self.translator,final_audit_hook=final_hook)

    def test_complete_bounded_correction_rerender_actual_images_and_final_screen(self):
        result=self.run_pipeline()
        self.assertEqual(result['execution_status'],'completed',result)
        self.assertEqual(result['model_screen_status'],'model_screened')
        self.assertEqual(result['status'],'needs_manual_review')
        self.assertFalse(result['quality_passed'])
        self.assertEqual(result['quality_status'],'blocked_incomplete_evidence')
        self.assertEqual(result['model_calls'],6);self.assertEqual(result['corrected_rows'],1)
        self.assertTrue(result['inputs_unchanged']);self.assertTrue(result['regression_outside_edited_regions'])
        ledger=json.loads((self.root/'quality/call-ledger.json').read_text(encoding='utf8'))
        self.assertEqual(len(ledger['calls']),6);self.assertTrue(all(x['state']=='returned' for x in ledger['calls']))
        pairs=json.loads((self.root/'quality/final-actual-pairs.json').read_text(encoding='utf8'))
        self.assertEqual(pairs['pair_0']['target'],GOOD)
        with fitz.open(self.root/'quality/best.mono.pdf') as doc:self.assertIn('中',doc[0].get_text())

    def test_changed_actual_rerender_target_blocks_before_visual_or_final_acceptance(self):
        self.bad_rerender=True;result=self.run_pipeline()
        self.assertEqual(result['status'],'needs_manual_review',result)
        self.assertEqual(result['error_code'],'RERENDER_TARGET_CHANGED');self.assertEqual(result['model_calls'],4)

    def test_budget_is_shared_and_stops_before_unaffordable_repair(self):
        self.cfg['review']['limits']['max_model_calls']=5;self.save();result=self.run_pipeline()
        self.assertEqual(result['status'],'needs_manual_review',result)
        self.assertEqual(result['model_calls'],2);self.assertEqual(result['error_code'],'VISUAL_BUDGET_EXHAUSTED')

    def test_uncertain_screen_never_becomes_an_automatic_repair(self):
        result=self.run_pipeline(FixtureClient(uncertain=True))
        self.assertEqual(result['error_code'],'SEMANTIC_SCREEN_UNCERTAIN');self.assertEqual(result['model_calls'],2)

    def test_failed_final_call_is_counted_and_keeps_unknown_usage(self):
        result=self.run_pipeline(FixtureClient(fail_final=True))
        self.assertEqual(result['status'],'needs_manual_review',result);self.assertEqual(result['model_calls'],6)
        ledger=json.loads((self.root/'quality/call-ledger.json').read_text(encoding='utf8'))
        self.assertEqual(ledger['calls'][-1]['state'],'failed');self.assertIsNone(ledger['calls'][-1]['native_usage'])

    def test_terminal_audit_reads_actual_rerender_after_semantic_recheck(self):
        packets=[]
        def auditor(packet,budget):
            packets.append(packet)
            return budget.invoke('offline-terminal-fixture',lambda timeout:({'verdict':'clear','issues':[]},{'input_tokens':1,'output_tokens':1}))
        result=self.run_pipeline(final_hook=final_gate.make_pipeline_hook(auditor,max_repair_rounds=0))
        self.assertEqual(result['model_calls'],6)
        self.assertEqual(result['additional_final_model_calls'],1)
        self.assertEqual(result['final_audit']['execution_status'],'completed')
        self.assertEqual(len(packets),1)
        self.assertEqual(len(packets[0]['images']),3)
        self.assertIn('中',packets[0]['prompt'])
        self.assertNotIn('Equivalent meaning.',packets[0]['prompt'])
        self.assertNotIn('Reference relation is absent.',packets[0]['prompt'])
        self.assertFalse(result['delivery_allowed'])
        self.assertEqual(result['quality_status'],'blocked_incomplete_evidence')

    def test_upstream_semantic_failure_never_starts_terminal_audit(self):
        hook=mock_hook=Mock()
        result=self.run_pipeline(FixtureClient(uncertain=True),hook)
        mock_hook.assert_not_called()
        self.assertEqual(result['final_audit']['execution_status'],'not_run_upstream_failed')
        self.assertFalse(result['delivery_allowed'])

    def test_terminal_hook_error_still_saves_semantic_output_and_report(self):
        def failed(*args):raise RuntimeError('offline terminal transport failure')
        result=self.run_pipeline(final_hook=failed)
        self.assertEqual(result['final_audit']['error_code'],'RuntimeError')
        self.assertFalse(result['delivery_allowed'])
        self.assertTrue((self.root/'quality/best.mono.pdf').is_file())
        saved=json.loads((self.root/'quality/pipeline-report.json').read_text(encoding='utf8'))
        self.assertEqual(saved['final_audit']['execution_status'],'failed_or_incomplete')

    def test_repeated_semantic_output_is_refused_before_any_new_fixture_calls(self):
        first=self.run_pipeline()
        ledger=self.root/'quality/call-ledger.json';old=ledger.read_bytes()
        client=FixtureClient()
        with self.assertRaisesRegex(ValueError,'NEEDS_FRESH_OUTPUT'):self.run_pipeline(client)
        self.assertEqual(client.screen_calls,0)
        self.assertEqual(ledger.read_bytes(),old)
        self.assertEqual(first['model_calls'],6)

    def test_receipt_link_uses_request_and_typed_id_instead_of_pair_order(self):
        pairs={'pair_0':{'source':SOURCE,'target':BAD}}
        row={'cache_request_sha256':'a'*64,'source_row_id':0,'base_content_sha256':'b'*64,
            'source_rows_sha256':'c'*64,'base_output_sha256':c.digest(BAD),'source_sha256':c.digest(SOURCE),
            'target_sha256':c.digest(BAD),'kind':'batch'}
        output,links=p.link_rerender(pairs,{'pair_0':row},{'pair_9':pairs['pair_0']},{'pair_9':row},{})
        self.assertEqual(output,pairs);self.assertEqual(links[0]['rendered_pair'],'pair_9')
        for field,value in [('source_row_id','0'),('base_content_sha256','d'*64)]:
            changed={**row,field:value}
            with self.assertRaises(ValueError):p.link_rerender(pairs,{'pair_0':row},{'pair_9':pairs['pair_0']},{'pair_9':changed},{})

    def test_collection_is_batched_completely_and_duplicate_restoration_rejected(self):
        pairs={f'pair_{n}':{'source':'The voltage is stable.','target':'电压稳定。'} for n in range(130)}
        batches=s.batches(pairs);self.assertEqual([len(x) for x in batches],[64,64,2])
        self.assertEqual({key for batch in batches for key in batch},set(pairs))
        restored=p.source_repair.restored_semantic_pair([{'source':'The voltage is stable.','paragraph':0}],['电压稳定。'],[])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            s.reflect_source_restorations({'pair_0':pairs['pair_0']},[restored,restored])

    def test_cache_only_miss_is_never_a_native_invocation(self):
        class Never:
            version='fixture'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):raise AssertionError('Native call forbidden')
        provider=b.validate_provider({'type':'codex','model':'fixture','cache_only':True,'retries':0},self.root)
        with b.ChatBridge(provider,Never()) as bridge:
            with self.assertRaisesRegex(b.BridgeError,'CACHE_ONLY_MISS'):
                bridge.complete({'messages':[{'role':'user','content':'Translate this text'}]})
            self.assertEqual(bridge.stats['attempts'],0)

    def test_real_translation_boundary_shares_the_same_durable_budget(self):
        cfg=v.validate_options(copy.deepcopy(self.cfg['review']),self.root);cfg['output']=self.root/'session';cfg['output'].mkdir()
        cfg['limits']['max_model_calls']=1;session=p.Session(cfg,FixtureClient())
        class Native:
            version='fixture'
            calls=0
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):
                self.calls+=1;self.last_usage={'input_tokens':7};return '译文'
        native=Native()
        with b.ChatBridge({'type':'codex','model':'fixture-text','retries':0},native,observer=session) as bridge:
            bridge.complete({'messages':[{'role':'user','content':'Translate first label'}]})
            bridge.complete({'messages':[{'role':'user','content':'Translate first label'}]})
            with self.assertRaisesRegex(b.BridgeError,'VISUAL_BUDGET_EXHAUSTED'):
                bridge.complete({'messages':[{'role':'user','content':'Translate another label'}]})
        self.assertEqual(native.calls,1);self.assertEqual(session.budget.calls,1)
        self.assertEqual(session.ledger['calls'][0]['native_usage']['input_tokens'],7)

    def test_source_text_cannot_change_under_a_reused_request_and_row_id(self):
        old={'pair_0':{'source':SOURCE,'target':BAD}}
        row={'cache_request_sha256':'a'*64,'source_row_id':0,'base_content_sha256':'b'*64,
            'source_rows_sha256':'c'*64,'base_output_sha256':c.digest(BAD),'source_sha256':c.digest(SOURCE),
            'target_sha256':c.digest(BAD),'kind':'batch'}
        new={'pair_7':{'source':'Another complete source sentence.','target':BAD}}
        updated={**row,'source_sha256':c.digest(new['pair_7']['source'])}
        with self.assertRaisesRegex(ValueError,'SOURCE_OR_BASE_CHANGED'):
            p.link_rerender(old,{'pair_0':row},new,{'pair_7':updated},{})

    def test_all_equivalent_and_no_edits_still_requires_whole_page_and_known_regression_gate(self):
        class AllEquivalent(FixtureClient):
            page_calls=0
            def inspect(self,prompt,images,timeout,schema=None):
                if schema is None and len(images)>1:
                    self.page_calls+=1;return {'issues':[]},{'input_tokens':1}
                if schema and 'pairs' in schema['properties']:
                    keys=schema['properties']['pairs']['required']
                    return {'pairs':{key:{'status':'equivalent','summary':'Claimed equivalent.','findings':[]} for key in keys}},{'input_tokens':1}
                return super().inspect(prompt,images,timeout,schema)
        corpus=self.root/'known.json';p.save(corpus,{'version':1,'failures':[{'id':'fixture-failure','source':SOURCE,'target':BAD,'reason':'Known incorrect reference relation.'}]})
        self.cfg['semantic']['regression_corpora']=[str(corpus)];self.save();client=AllEquivalent();result=self.run_pipeline(client)
        self.assertEqual(client.page_calls,1)
        self.assertEqual(result['execution_status'],'completed',result)
        self.assertEqual(result['model_screen_status'],'model_screened')
        self.assertEqual(result['quality_status'],'blocked_known_regression')
        self.assertFalse(result['quality_passed']);self.assertEqual(result['status'],'needs_manual_review')


if __name__=='__main__':unittest.main()
