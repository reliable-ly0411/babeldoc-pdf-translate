"""Actual independent cold failure; name accounting must not weaken math/code."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b
import visual_review as v


def request(rows):
    return {'response_format':None,'messages':[{'role':'user','content':
        'Translate English to Chinese.\n## Here is the input:\n'+json.dumps(rows)}]}


class WrappedNameTests(unittest.TestCase):
    def fixture(self):return json.loads((Path(__file__).parent/'fixtures/l1quad-wrapped-name.json').read_text(encoding='utf8'))

    def test_actual_first_reply_passes_with_all_original_objects(self):
        data=self.fixture();req=request(data['rows']);before=b.canonical(req)
        b.checked_content(json.dumps(data['first_restored_reply']),req,data['protected_identifiers'],paragraphs=True)
        self.assertEqual(b.identifier_counts(data['rows'][4]['input'],data['protected_identifiers']),{'Lipschitz':1})
        self.assertEqual(b.canonical(req),before)

    def test_actual_retry_still_rejects_missing_v2(self):
        data=self.fixture();_,plan=b.paragraph_request(request(data['rows']),data['protected_identifiers'])
        with self.assertRaises(b.BridgeError) as error:b.restore_paragraphs(json.dumps(data['retry_native_reply']),plan)
        self.assertEqual(error.exception.detail['guard'],'paragraph_tokens')
        self.assertEqual(error.exception.detail['rows'][0]['missing'],[data['retry_missing_token']])

    def test_only_configured_capitalized_names_and_narrow_breaks_qualify(self):
        for name,source in [('Lipschitz','Lip- schitz'),('Lipschitz','Lip-\nschitz'),
                            ('Lipschitz','Lip\u00adschitz'),('Hurwitz','Hur- witz')]:
            with self.subTest(source=source):self.assertEqual(b.identifier_counts(source,[name]),{name:1})
        self.assertEqual(b.identifier_counts('Lip- schitz',[]),{})
        self.assertEqual(b.identifier_counts('Lip- schitz',['Hurwitz']),{})

    def test_real_hyphens_compound_ids_math_and_prose_prefixes_do_not_join(self):
        cases=[('Lip-schitz',['Lipschitz']),('Lip\u2011 schitz',['Lipschitz']),
            ('Lip\u2212 schitz',['Lipschitz']),('Lip-\u00a0schitz',['Lipschitz']),
            ('MMLU- Pro',['MMLUPro']),('L1- Quad',['L1Quad']),
            ('re- sign',['resign']),('co- operate',['cooperate']),
            ('Lip- {v1}schitz',['Lipschitz']),('Lip- <style id="1">schitz</style>',['Lipschitz']),
            ('Lip- schitz',['Lipschitz','Lip-schitz'])]
        for source,names in cases:
            with self.subTest(source=source):self.assertEqual(b.wrapped_identifier_aliases(source,names),[])
        req=request([{'id':0,'input':'The Lip-schitz condition is safe.'}])
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content(json.dumps([{'id':0,'output':'Lipschitz 条件安全。'}]),req,['Lipschitz'],paragraphs=True)

    def test_assignments_explicit_code_and_urls_do_not_create_aliases(self):
        for text in ('mode=Lip- schitz','`Lip- schitz`','https://example.test/Lip- schitz','x@Lip- schitz'):
            with self.subTest(text=text):self.assertEqual(b.wrapped_identifier_aliases(text,['Lipschitz']),[])
        req=request([{'id':0,'input':'Set mode=Lip- schitz.'}])
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content(json.dumps([{'id':0,'output':'设置 mode=Lipschitz。'}]),req,['Lipschitz'],paragraphs=True)

    def test_missing_duplicate_names_and_changed_math_still_fail(self):
        req=request([{'id':0,'input':'The Lip- schitz constant of {v1} is bounded.'}])
        for text in ('常数 {v1} 有界。','Lipschitz Lipschitz 常数 {v1} 有界。',
                     'Lipschitz 常数 {v2} 有界。','Lipschitz 常数 {v1}+{v2} 有界。'):
            with self.subTest(text=text),self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps([{'id':0,'output':text}]),req,['Lipschitz'],paragraphs=True)

    def test_single_paragraph_route_uses_same_name_accounting(self):
        req={'messages':[{'role':'user','content':';; Treat next line as plain text input and translate it into Chinese.\nInput:\n\nThe Lip- schitz constant of {v1} is bounded.'}]}
        b.checked_content('Lipschitz 常数 {v1} 有界。',req,['Lipschitz'],paragraphs=True)
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content('常数 {v1} 有界。',req,['Lipschitz'],paragraphs=True)

    def test_source_repair_uses_same_accounting_without_dropping_names(self):
        plan={'units':[{'source':'If the Lip- schitz constant is small','paragraph':1}]}
        good={'region_0':{'slot_00':'若 Lipschitz 常数足够小'}}
        self.assertEqual(v.checked_source_plan(good,[plan],['Lipschitz']),[['若 Lipschitz 常数足够小']])
        with self.assertRaisesRegex(ValueError,'SOURCE_REPAIR_PROTECTED_NAME_CHANGED'):
            v.checked_source_plan({'region_0':{'slot_00':'若常数足够小'}},[plan],['Lipschitz'])

    def test_source_repair_never_infers_a_wrap_across_immutable_math_slots(self):
        plan={'units':[{'source':'Lip-','paragraph':1,'right_literal':'{v1}'},
                       {'source':'schitz continuous','paragraph':1,'left_literal':'{v1}'}]}
        with self.assertRaisesRegex(ValueError,'SOURCE_REPAIR_PROTECTED_NAME_CHANGED'):
            v.checked_source_plan({'region_0':{'slot_00':'Lipschitz 连续','slot_01':''}},[plan],['Lipschitz'])

    def test_affected_legacy_cache_is_not_reused_but_new_repeat_hits(self):
        req=request([{'id':0,'input':'The Lip- schitz constant of {v1} is bounded.'}])
        good=json.dumps([{'id':0,'output':'Lipschitz 常数 {v1} 有界。'}])
        class Client:
            version='wrapped-fixture';calls=0
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):self.calls+=1;return good
        with tempfile.TemporaryDirectory() as tmp:
            old={'bridge_version':b.VERSION,'native_version':Client.version,'backend':'codex','model':None,
                'request':req,'reasoning_effort':None,'native_output_contract':b.PARAGRAPH_CONTRACT}
            key=hashlib.sha256(b.canonical(old).encode()).hexdigest()
            bad=json.dumps([{'id':0,'output':'常数 {v1} 有界。'}])
            path=Path(tmp,key+'.json');path.write_text(json.dumps({'request_sha256':key,
                'content_sha256':hashlib.sha256(bad.encode()).hexdigest(),'content':bad}),encoding='utf8')
            before=path.read_bytes();provider={'type':'codex','retries':0,'output_contract':'paragraphs','cache_dir':tmp,'protected_identifiers':['Lipschitz']}
            for expected in (1,0):
                client=Client()
                with b.ChatBridge(provider,client) as server:self.assertEqual(server.complete(req),good)
                self.assertEqual(client.calls,expected)
            self.assertEqual(path.read_bytes(),before)

    def test_real_missing_token_retry_is_bounded_and_preserves_feedback(self):
        data=self.fixture();req=request(data['rows'])
        class Client:
            version='wrapped-retry-fixture';calls=0;requests=[]
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):
                self.calls+=1;self.requests.append(request)
                if self.calls==1:
                    _,plan=b.paragraph_request(request,data['protected_identifiers'])
                    return b.restore_paragraphs(json.dumps(data['retry_native_reply']),plan)
                return json.dumps(data['first_restored_reply'])
        client=Client()
        with b.ChatBridge({'type':'codex','retries':1,'max_model_calls':2,'output_contract':'paragraphs',
                'protected_identifiers':data['protected_identifiers']},client) as server:
            b.checked_content(server.complete(req),req,data['protected_identifiers'],paragraphs=True)
            self.assertEqual(server.stats['attempts'],2)
            self.assertEqual(server.stats['request_metrics'][0]['error_code'],'PROTECTED_TEXT_CHANGED')
        self.assertIn(data['retry_missing_token'],client.requests[1]['messages'][-1]['content'])


if __name__=='__main__':unittest.main()
