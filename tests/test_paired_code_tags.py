"""A rendered R1 failure: paired tag names hidden between PDF math markers."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b

SOURCE='Use designated tags, specifically {v1}think{v2} and {v3}/think{v4}.'
BAD='使用指定标签，即 {v1}思考{v2} 和 {v3}/思考{v4}。'
GOOD='使用指定标签，即 {v1}think{v2} 和 {v3}/think{v4}。'

def request(source):
    return {'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+b.canonical([{'id':0,'input':source}])}]}
def answer(target):return b.canonical([{'id':0,'output':target}])
def doctor(client):client.version='fixture';return {'native_version':'fixture'}

class PairedCodeTagTests(unittest.TestCase):
    def test_actual_failure_shape_rejected_in_both_output_contracts(self):
        for paragraphs in (False,True):
            with self.assertRaises(b.BridgeError) as caught:b.checked_content(answer(BAD),request(SOURCE),paragraphs=paragraphs)
            self.assertEqual(caught.exception.detail['kind'],'paired_code_tag')
            self.assertEqual(b.checked_content(answer(GOOD),request(SOURCE),paragraphs=paragraphs),answer(GOOD))

    def test_masking_hides_only_literal_keeps_formula_binding_and_roundtrips(self):
        req=request(SOURCE);before=b.canonical(req);masked,protected=b.mask_code(req)
        text=b.translation_batch(masked)[2][0]['input']
        self.assertNotIn('think',text);self.assertEqual(b.canonical(req),before)
        self.assertEqual([x for x in b.MARKER.findall(text) if x.startswith('{v')],['{v1}','{v2}','{v3}','{v4}'])
        self.assertEqual(b.restore_code(answer(text),req,protected),answer(SOURCE))

    def test_source_tag_spelling_case_slash_and_anchor_are_exact(self):
        for changed in (GOOD.replace('think','Think'),GOOD.replace('/think','think'),
                        GOOD.replace('{v1}think{v2}','{v3}think{v4}')):
            with self.assertRaises(b.BridgeError):b.check_paired_tags(SOURCE,changed,0)

    def test_multiple_pairs_including_literal_markup_are_protected(self):
        source=SOURCE+' Also <answer>text</answer>.'
        masked,protected=b.mask_code(request(source));text=b.translation_batch(masked)[2][0]['input']
        self.assertNotIn('think',text);self.assertNotIn('<answer>',text)
        self.assertEqual(b.restore_code(answer(text),request(source),protected),answer(source))
        with self.assertRaises(b.BridgeError):b.check_paired_tags(source,source.replace('</answer>','</答案>'),0)

    def test_adjacent_tags_share_marker_without_losing_closing_name(self):
        source='Use tags {v1}think{v2}/think{v3} and {v4}answer{v5}/answer{v6}.'
        self.assertEqual(len(b.paired_tag_spans(source)),4)
        masked,protected=b.mask_code(request(source));text=b.translation_batch(masked)[2][0]['input']
        self.assertNotIn('think',text);self.assertNotIn('answer',text)
        self.assertEqual(b.restore_code(answer(text),request(source),protected),answer(source))
        with self.assertRaises(b.BridgeError):b.check_paired_tags(source,source.replace('/think','/思考'),0)

    def test_math_and_unpaired_words_are_not_guessed_as_code(self):
        for source in ('Compute {v1}x{v2} + {v3}/x{v4}.',
                       'A tag for {v1}state{v2} is useful.',
                       'Use tags {v1}start{v2} and {v3}/end{v4}.',
                       'The implementation of the {v3}Quad controller.'):
            self.assertEqual(b.paired_tag_spans(source),[])

    def test_single_request_fidelity_still_applies_without_batch_masking(self):
        req={'messages':[{'role':'user','content':';; Treat next line as plain text input and translate it into Chinese.\nInput:\n\n'+SOURCE}]}
        self.assertTrue(b.has_paired_tags(req))
        with self.assertRaises(b.BridgeError):b.checked_content(BAD,req)

    def bridge(self,provider,req,translate):
        with mock.patch.object(b.NativeClient,'doctor',autospec=True,side_effect=doctor),\
             mock.patch.object(b.NativeClient,'translate',autospec=True,side_effect=translate):
            with b.ChatBridge(provider) as client:
                content=client.complete(req);stats=json.loads(b.canonical(client.stats))
        return content,stats

    def test_affected_old_bad_cache_is_not_reused_or_rewritten(self):
        with tempfile.TemporaryDirectory() as temp:
            provider={'type':'codex','model':'fixture-luna','output_contract':'paragraphs','retries':0,
                      'max_model_calls':1,'timeout_seconds':3,'cache_dir':temp}
            with mock.patch.object(b,'paired_tag_spans',return_value=[]):
                self.bridge(provider,request(SOURCE),lambda *_a,**_k:answer(BAD))
            old={p.name:p.read_bytes() for p in Path(temp).glob('*.json')};self.assertEqual(len(old),1)
            def translate(_client,req,**kwargs):
                masked=b.translation_batch(req)[2][0]['input'];self.assertNotIn('think',masked)
                return answer(masked.replace('Use designated tags, specifically','使用指定标签，即').replace(' and ',' 和 '))
            content,stats=self.bridge(provider,request(SOURCE),translate)
            self.assertIn('think',content);self.assertNotIn('思考',content)
            self.assertEqual(stats['attempts'],1);self.assertEqual(stats['cache_hits'],0)
            self.assertEqual(len(list(Path(temp).glob('*.json'))),2)
            self.assertTrue(all((Path(temp)/name).read_bytes()==data for name,data in old.items()))

    def test_affected_but_valid_old_cache_is_rechecked_and_not_called_again(self):
        with tempfile.TemporaryDirectory() as temp:
            provider={'type':'codex','model':'fixture-luna','output_contract':'paragraphs','retries':0,
                      'max_model_calls':1,'timeout_seconds':3,'cache_dir':temp}
            with mock.patch.object(b,'paired_tag_spans',return_value=[]):
                self.bridge(provider,request(SOURCE),lambda *_a,**_k:answer(GOOD))
            old={p.name:p.read_bytes() for p in Path(temp).glob('*.json')}
            def unexpected(*_a,**_k):raise AssertionError('REPEATED_VALID_TRANSLATION')
            content,stats=self.bridge(provider,request(SOURCE),unexpected)
            self.assertEqual(content,answer(GOOD));self.assertEqual(stats['attempts'],0)
            self.assertEqual(stats['legacy_cache_hits'],1)
            self.assertTrue(all((Path(temp)/name).read_bytes()==data for name,data in old.items()))

    def test_unaffected_cache_still_avoids_every_native_call(self):
        with tempfile.TemporaryDirectory() as temp:
            provider={'type':'codex','model':'fixture-luna','output_contract':'paragraphs','retries':0,
                      'max_model_calls':1,'timeout_seconds':3,'cache_dir':temp}
            req=request('Hello.')
            self.bridge(provider,req,lambda *_a,**_k:answer('你好。'))
            def unexpected(*_a,**_k):raise AssertionError('UNEXPECTED_NATIVE_CALL')
            content,stats=self.bridge(provider,req,unexpected)
            self.assertEqual(stats['cache_hits'],1);self.assertEqual(stats['attempts'],0)

    def test_missing_opaque_tag_token_fails_without_expanding_budget(self):
        provider={'type':'codex','model':'fixture-luna','output_contract':'paragraphs','retries':1,
                  'max_model_calls':1,'timeout_seconds':3}
        calls=[]
        def bad(_client,req,**kwargs):calls.append(req);return answer(BAD)
        with self.assertRaises(b.BridgeError) as caught:self.bridge(provider,request(SOURCE),bad)
        self.assertEqual(caught.exception.code,'NATIVE_CALL_BUDGET_EXHAUSTED')
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
