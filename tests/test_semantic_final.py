"""Complete-block mapping and durable semantic final gate on actual fake PDFs.

All inference is replaced. PROTOCOL_VALIDATED is patched only for explicit
positive state-machine controls; the on-disk production flag stays false.
"""
import copy
import html
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import pymupdf as fitz
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_receipts as durable
import chat_bridge
import final_audit as final
import semantic_gate as gate
import semantic_mapping as mapping
import semantic_offline_support as fake
import translation_contract as contracts
import visual_review as visual

CLEAR = {'verdict': 'clear', 'issues': []}


def pdf(path, rows, *, pages=1):
    with fitz.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=440, height=300)
            for box, text in rows:
                page.insert_htmlbox(box, '<p>'+html.escape(text)+'</p>',
                    css='body {font-family:sans-serif;font-size:11pt;margin:0;} p {margin:0;}')
        doc.save(path)


class SemanticFinalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='semantic-e2e-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.mono, self.dual = [self.root/name for name in ('source.pdf', 'mono.pdf', 'dual.pdf')]
        self.box = (30, 40, 410, 85)
        pdf(self.source, [(self.box, 'The controller stabilizes the vehicle.')])
        pdf(self.mono, [(self.box, '该控制器使飞行器保持稳定。')])
        self.artifacts = {'mono': self.mono, 'dual': self.dual}
        visual.bilingual(self.source, self.mono, self.dual)
        self.contract = contracts.empty([1])
        self.n = 0
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(chat_bridge.NativeClient, 'invoke', side_effect=AssertionError('REAL MODEL FORBIDDEN')).start()

    def coverage(self):
        return mapping.build(self.source, self.mono, [1])

    def vision(self, packet, budget):
        return budget.invoke('offline-vision', lambda timeout: (copy.deepcopy(CLEAR), {'input_tokens': 1}))

    def run_final(self, **options):
        self.n += 1
        defaults = dict(upstream_ready=True, max_repair_rounds=0, **fake.options())
        defaults.update(options)
        return final.run(self.source, self.artifacts, self.root/('audit%d'%self.n), self.vision, **defaults)

    def test_positive_round_has_visual_plus_every_semantic_unit_and_signed_receipt(self):
        seen = []
        with mock.patch.object(final, 'PROTOCOL_VALIDATED', True):
            result = self.run_final(**fake.options(seen=seen))
            self.assertTrue(result['delivery_allowed'], result)
            self.assertTrue(final.verify_before_delivery(self.source, self.artifacts, result['receipt']))
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(result['semantic_result']['semantic_units'], 1)
        self.assertIn('该控制器', seen[0]['prompt'])
        self.assertNotIn('expected_verdict', seen[0]['prompt'])
        self.assertFalse(result['semantic_result']['quality_passed'])
        self.assertFalse(final.PROTOCOL_VALIDATED)

    def test_complete_coverage_contains_all_blocks_in_both_columns(self):
        boxes = [(30,40,205,85), (235,40,410,85), (30,140,205,185), (235,140,410,185)]
        pdf(self.source, [(box, 'The controller stabilizes the vehicle.') for box in boxes])
        pdf(self.mono, [(box, '控制器使飞行器保持稳定。') for box in boxes])
        coverage = self.coverage()
        self.assertTrue(coverage['coverage_complete'], coverage)
        page = coverage['pages'][0]
        # MuPDF may combine two columns at the same y into one complete block.
        # No source or target block/text may disappear in either representation.
        self.assertGreaterEqual(len(page['units']), 2)
        self.assertEqual(sum(u['source'].count('stabilizes') for u in page['units']),4)
        self.assertEqual(sum(u['target'].count('保持稳定') for u in page['units']),4)
        self.assertEqual(sum(len(u['source_blocks']) for u in page['units']), page['source_block_count'])
        self.assertEqual(sum(len(u['target_blocks']) for u in page['units']), page['target_block_count'])

    def test_source_to_multiple_target_blocks_keeps_complete_ordered_text(self):
        pdf(self.source, [((30,40,410,140),'The controller stabilizes the vehicle. The controller is active. '*7)])
        # Separate drawing objects with overlapping boxes must form one full unit.
        pdf(self.mono, [((30,40,410,70),'控制器使飞行器保持稳定。'), ((30,100,410,130),'控制器处于活动状态。')])
        coverage = self.coverage()
        self.assertTrue(coverage['coverage_complete'], coverage)
        self.assertEqual(len(coverage['pages'][0]['units']), 1)
        unit = coverage['pages'][0]['units'][0]
        self.assertEqual(len(unit['target_blocks']), 2)
        self.assertIn('active.', unit['source'])
        self.assertIn('活动状态', unit['target'])

    def test_missing_untranslated_or_unmapped_prose_blocks_before_any_inference(self):
        for mode in ('missing', 'unchanged', 'unmapped'):
            with self.subTest(mode=mode):
                rows = [] if mode=='missing' else [(self.box, 'The controller stabilizes the vehicle.')] if mode=='unchanged' else [((30,190,410,240),'控制器使飞行器稳定。')]
                pdf(self.mono, rows); visual.bilingual(self.source,self.mono,self.dual)
                result = self.run_final()
                self.assertEqual(result['quality_status'], 'blocked_semantic_coverage', result)
                self.assertEqual(result['model_calls'], 0)

    def test_missing_math_glyphs_and_changed_numeral_block_before_models(self):
        for i, (a,b) in enumerate((('Use α as a bound.', '使用界。'), ('Use x² as a bound.', '使用 x 作为界。'), ('Use 12 samples.', '使用 13 个样本。'), ('The functions W(x) form a basis.', '这些函数构成基。'))):
            with self.subTest(i=i):
                pdf(self.source, [(self.box,a)]); pdf(self.mono,[(self.box,b)])
                self.assertIn('PROTECTED_MATH_GLYPH_INVENTORY_CHANGED', [e['code'] for e in self.coverage()['pages'][0]['errors']])

    def test_image_content_and_duplicate_text_are_not_silently_skipped(self):
        duplicate=self.root/'duplicate.pdf'
        with fitz.open(self.source) as doc:
            doc[0].insert_htmlbox(self.box,'<p>The controller stabilizes the vehicle.</p>',css='body {font-family:sans-serif;font-size:11pt;margin:0;} p {margin:0;}')
            doc.save(duplicate)
        with fitz.open(duplicate) as doc:
            self.assertIn('DUPLICATE_TEXT_BLOCK', [e['code'] for e in mapping.inventory(doc[0])[1]])
        picture=self.root/'image.png'
        with fitz.open(self.source) as doc:
            doc[0].get_pixmap().save(picture)
        image_pdf=self.root/'image.pdf'
        with fitz.open(self.source) as doc:
            doc[0].insert_image((30,150,200,250),filename=picture); doc.save(image_pdf)
        with fitz.open(image_pdf) as doc:
            self.assertIn('UNEXTRACTED_IMAGE_CONTENT', [e['code'] for e in mapping.inventory(doc[0])[1]])

    def test_large_complete_unit_is_blocked_instead_of_truncated(self):
        # Synthetic inventory bypasses page drawing limits, not the actual mapper.
        row={'id':'block_0','bbox':list(self.box),'text':'The controller is active. '*70,'protected':{}}
        target={**row,'text':'控制器保持稳定。'}
        with mock.patch.object(mapping,'inventory',side_effect=[([row],[]),([target],[])]):
            value=mapping.page_units(None,None,1)
        self.assertIn('COMPLETE_UNIT_TOO_LARGE',[e['code'] for e in value['errors']])
        self.assertEqual(value['units'][0]['source'],row['text'])

    def test_relation_change_and_uncertainty_veto_visual_clear(self):
        for verdict in ('different','uncertain'):
            with self.subTest(verdict=verdict):
                result=self.run_final(**fake.options(verdict=verdict))
                self.assertEqual(result['semantic_status'],'SEMANTIC_'+verdict.upper())
                self.assertEqual(result['audit_model_verdict'],'clear')
                self.assertFalse(result['delivery_allowed'])
                self.assertEqual(result['model_calls'],2)

    def test_bad_raw_response_is_preserved_before_parse_and_no_retry(self):
        for raw in (b'not JSON', b'{"verdict":"equivalent","verdict":"different"}', b'\xff'):
            with self.subTest(raw=raw):
                result=self.run_final(**fake.options(raw=raw))
                self.assertEqual(result['execution_status'],'failed_or_incomplete')
                self.assertEqual(result['error_code'],'SEMANTIC_INVALID_RAW_RESPONSE')
                self.assertEqual(result['model_calls'],2)
                folder=self.root/('audit%d'%self.n)/'s00/u0000'
                self.assertEqual((folder/'response.raw').read_bytes(),raw)
                self.assertTrue((folder.parent/'blocked.json').exists())

    def test_no_signature_or_wrong_bound_signature_never_passes(self):
        def wrong(inbox,binding,*args):
            changed=copy.deepcopy(binding);changed['case_id']='wrong'
            fake.adjudicate(inbox,changed,*args)
        for signer in (None,wrong):
            with self.subTest(signer=signer):
                result=self.run_final(semantic_adjudicator=signer)
                self.assertFalse(result['delivery_allowed'])
                self.assertEqual(result['error_code'],'SEMANTIC_ADJUDICATION_NOT_ACCEPTED')
                self.assertEqual(result['model_calls'],2)

    def test_receipt_or_unit_coverage_tamper_invalidates_delivery(self):
        with mock.patch.object(final,'PROTOCOL_VALIDATED',True):
            result=self.run_final()
            self.assertTrue(result['delivery_allowed'],result)
            path=Path(result['receipt']['semantic_folder'])/'manifest.json'
            value=gate.load(path);value['units']=[]
            path.write_bytes(durable.encode(value))
            self.assertFalse(final.verify_before_delivery(self.source,self.artifacts,result['receipt']))

    def test_signed_event_change_or_bad_ready_record_cannot_be_restored_to_pass(self):
        with mock.patch.object(final,'PROTOCOL_VALIDATED',True):
            result=self.run_final();self.assertTrue(result['delivery_allowed'],result)
            inbox=Path(result['receipt']['semantic_folder'])/'u0000/inbox'
            old=(inbox/'decision.ready').read_bytes();(inbox/'decision.ready').write_bytes(b'broken record')
            self.assertFalse(final.verify_before_delivery(self.source,self.artifacts,result['receipt']))
            (inbox/'decision.ready').write_bytes(old)
            self.assertFalse(final.verify_before_delivery(self.source,self.artifacts,result['receipt']))

    def test_source_mono_dual_and_contract_changes_invalidate_bound_audit(self):
        with mock.patch.object(final,'PROTOCOL_VALIDATED',True):
            result=self.run_final();self.assertTrue(result['delivery_allowed'],result)
            for path in (self.source,self.mono,self.dual):
                old=path.read_bytes();path.write_bytes(old+b'\n% offline mutation\n')
                self.assertFalse(final.verify_before_delivery(self.source,self.artifacts,result['receipt']))
                path.write_bytes(old)
            changed=copy.deepcopy(self.contract);changed.pop('sha256');changed['prompt']='Changed user constraint.'
            self.assertFalse(final.verify_before_delivery(self.source,self.artifacts,result['receipt'],translation_contract=contracts.seal(changed)))

    def test_artifact_change_during_semantic_request_fails_and_stops(self):
        original=fake.reviewer()
        def mutate(packet,budget,folder):
            raw=original(packet,budget,folder)
            self.dual.write_bytes(self.dual.read_bytes()+b'\n% mutated during semantic call\n')
            return raw
        result=self.run_final(semantic_auditor=mutate)
        self.assertFalse(result['delivery_allowed'])
        self.assertEqual(result['error_code'],'SEMANTIC_FINAL_ARTIFACT_CHANGED')
        self.assertEqual(result['model_calls'],2)

    def test_missing_semantic_audit_and_unvalidated_protocol_both_block_delivery(self):
        with mock.patch.object(final,'PROTOCOL_VALIDATED',True):
            result=self.run_final(semantic_auditor=None,semantic_adjudicator=None)
            self.assertEqual(result['quality_status'],'blocked_missing_semantic_audit')
        result=self.run_final()
        self.assertEqual(result['quality_status'],'blocked_unvalidated_final_audit')
        self.assertFalse(result['delivery_allowed'])

    def test_whole_round_budget_preflight_includes_all_semantic_requests(self):
        result=self.run_final(max_calls=1)
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['error_code'],'FINAL_AUDIT_BUDGET_EXHAUSTED')

    def test_known_regression_cannot_be_cleared_by_semantic_diagnostic(self):
        result=self.run_final(known_regressions=lambda *args:[{'id':'known-failed-relation'}])
        self.assertEqual(result['semantic_result']['semantic_units'],1)
        self.assertEqual(result['quality_status'],'blocked_known_regression')
        self.assertFalse(result['delivery_allowed'])

    def test_explicit_recovery_signs_durable_response_without_inference(self):
        folder=self.root/'recovery';budget=final.Budget(3,60)
        def interrupt(*args):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            gate.run(self.source,self.artifacts,self.contract,self.coverage(),folder,budget,fake.reviewer(),interrupt,lambda:None)
        self.assertEqual(budget.calls,1)
        never=mock.Mock(side_effect=AssertionError('RECOVERY MUST NOT CALL MODEL'))
        result=gate.run(self.source,self.artifacts,self.contract,self.coverage(),folder,budget,never,fake.adjudicate,lambda:None,resume=True)
        self.assertTrue(result['passed']);self.assertEqual(budget.calls,1);never.assert_not_called()

    def test_unknown_interrupted_inference_cannot_resume_with_new_call(self):
        folder=self.root/'unknown';budget=final.Budget(3,60)
        def interrupted(packet,budget,folder):
            def stop(timeout):raise KeyboardInterrupt()
            return budget.invoke('offline-interrupted',stop)
        with self.assertRaises(KeyboardInterrupt):gate.run(self.source,self.artifacts,self.contract,self.coverage(),folder,budget,interrupted,None,lambda:None)
        never=mock.Mock()
        with self.assertRaisesRegex(ValueError,'SEMANTIC_RECOVERY_HAS_NO_DURABLE_RESPONSE'):
            gate.run(self.source,self.artifacts,self.contract,self.coverage(),folder,budget,never,None,lambda:None,resume=True)
        never.assert_not_called();self.assertEqual(budget.calls,1)

    def test_recovery_keeps_original_deadline_and_artifact_context(self):
        folder=self.root/'deadline';budget=final.Budget(3,60)
        def interrupt(*args):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):gate.run(self.source,self.artifacts,self.contract,self.coverage(),folder,budget,fake.reviewer(),interrupt,lambda:None)
        never=mock.Mock()
        with mock.patch.object(gate.time,'time',return_value=10**12):
            with self.assertRaisesRegex(ValueError,'SEMANTIC_ORIGINAL_DEADLINE_EXPIRED'):
                gate.run(self.source,self.artifacts,self.contract,self.coverage(),folder,final.Budget(3,60),never,fake.adjudicate,lambda:None,resume=True)
        never.assert_not_called()

    def test_original_user_contract_is_in_each_request(self):
        contract=contracts.empty([1]);contract.pop('sha256');contract['prompt']='PREFER_APPROVED_TERM_456';contract=contracts.seal(contract)
        seen=[];result=self.run_final(translation_contract=contract,**fake.options(seen=seen))
        self.assertEqual(result['semantic_result']['semantic_units'],1,result)
        self.assertIn('PREFER_APPROVED_TERM_456',seen[0]['prompt'])

    def test_preserved_page_changes_block_even_if_visual_fake_is_clear(self):
        pdf(self.source,[(self.box,'The controller stabilizes the vehicle.')],pages=2)
        pdf(self.mono,[(self.box,'控制器使飞行器保持稳定。')],pages=2)
        visual.bilingual(self.source,self.mono,self.dual)
        result=self.run_final(translation_pages=[1])
        self.assertEqual(result['quality_status'],'blocked_math_or_preserved_page_integrity',result)
        self.assertEqual(result['model_calls'],2)  # only the two visual requests

    def test_native_semantic_provider_cannot_enable_retries_or_astra(self):
        for provider in ({'type':'codex','model':'gpt-6-luna','retries':1}, {'type':'codex','model':'gpt-6-astra','retries':0}, {'type':'openai-compatible','model':'other','retries':0}):
            with self.assertRaises(ValueError):gate.native_reviewer(provider)

    def test_unreadable_cid_placeholder_blocks_as_extraction_uncertainty(self):
        pdf(self.mono,[(self.box,'控制器使用 (cid:13) 作为界。')])
        coverage=self.coverage()
        self.assertFalse(coverage['coverage_complete'])
        self.assertIn('UNREADABLE_GLYPH',[e['code'] for e in coverage['pages'][0]['errors']])

    def test_native_adapter_captures_raw_before_json_parsing_without_stderr_text(self):
        provider={'type':'codex','model':'offline-semantic','reasoning_effort':'high','retries':0,'timeout_seconds':30}
        client=visual.NativeVision(provider);raw=b'\xff invalid utf8 JSON'
        def invoke(argv,prompt,**options):
            Path(argv[argv.index('-o')+1]).write_bytes(raw)
            self.assertNotIn('--image',argv)
            self.assertIn('--ephemeral',argv)
            self.assertIn('--ignore-user-config',argv)
            return SimpleNamespace(returncode=0,stdout='{"type":"turn.completed","usage":{"input_tokens":7}}\n',stderr='PRIVATE_TRANSPORT_MARKER')
        capture=self.root/'raw-native'
        with mock.patch.object(client.native,'invoke',side_effect=invoke):
            response,usage=client.inspect_raw('source and target',[],30,schema={'type':'object'},record_dir=capture)
        self.assertEqual(response,raw);self.assertEqual(usage,{'input_tokens':7})
        self.assertEqual((capture/'answer.raw').read_bytes(),raw)
        self.assertFalse((capture/'stderr.utf8').exists())
        self.assertNotIn(b'PRIVATE_TRANSPORT_MARKER',(capture/'capture.json').read_bytes())
        metadata=gate.load(capture/'capture.json')
        self.assertEqual(metadata['streams']['stderr']['captured_bytes'],0)
        self.assertFalse(metadata['streams']['stderr']['stored'])

    def test_dry_config_records_explicit_semantic_role_without_calling_native(self):
        cfg={'provider':{'type':'codex','model':'gpt-6-luna','vision':True,'retries':0},
             'semantic':{'provider':{'type':'codex','model':'gpt-6-luna','reasoning_effort':'high','retries':0},'adjudication_wait_seconds':0},
             'max_repair_rounds':0,'limits':{'max_model_calls':4,'max_seconds':90}}
        path=self.root/'config.json';final.save(path,cfg)
        hook=final.from_config(path)
        self.assertTrue(hook.plan['semantic_configured'])
        self.assertEqual(hook.plan['semantic_model'],'gpt-6-luna')
        self.assertFalse(hook.plan['protocol_validated'])

    def test_actual_native_adapter_path_binds_raw_capture_to_final_signed_event(self):
        raw=durable.encode({'verdict':'equivalent','source_meaning':'Offline fixture: controller stabilizes vehicle.',
            'target_meaning':'Offline fixture: controller stabilizes vehicle.','note':'OFFLINE transport double only.'})
        def native(argv,prompt,**kwargs):
            Path(argv[argv.index('-o')+1]).write_bytes(raw)
            return SimpleNamespace(returncode=0,stdout='{"type":"turn.completed","usage":{"input_tokens":9,"output_tokens":4}}\n',stderr='')
        provider={'type':'codex','model':'offline-native','reasoning_effort':'high','retries':0,'timeout_seconds':30}
        with mock.patch.object(chat_bridge.NativeClient,'invoke',side_effect=native),mock.patch.object(final,'PROTOCOL_VALIDATED',True):
            result=self.run_final(semantic_auditor=gate.native_reviewer(provider))
            self.assertTrue(result['delivery_allowed'],result)
            self.assertTrue(final.verify_before_delivery(self.source,self.artifacts,result['receipt']))
            folder=Path(result['receipt']['semantic_folder'])/'u0000'
            self.assertEqual((folder/'response.raw').read_bytes(),raw)
            self.assertIsNotNone(gate.load(folder/'event.json')['native_capture_sha256'])
            self.assertEqual(result['model_ledger'][1]['native_usage']['input_tokens'],9)
            (folder/'native-raw/stdout.utf8').write_bytes(b'changed-event-stream')
            self.assertFalse(final.verify_before_delivery(self.source,self.artifacts,result['receipt']))


if __name__=='__main__':unittest.main()
