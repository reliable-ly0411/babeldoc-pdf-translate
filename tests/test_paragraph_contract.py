"""Whole paragraph order, with immutable names/markers and strict batch rows."""
import json
import hashlib
from collections import Counter
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b


def request(rows):
    return {'messages':[{'role':'user','content':'Translate English to Chinese.\n## Here is the input:\n'+json.dumps(rows)}]}


def opaque(plan,text,row=0):
    for token,run in plan[row]['math_groups'].items():text=text.replace(run,token)
    return text


class ParagraphTests(unittest.TestCase):
    def test_chinese_can_move_words_around_immutable_math(self):
        source=request([{'id':7,'input':'If the Lipschitz constant of {v1} with respect to {v2} is small enough.'}])
        transformed,plan=b.paragraph_request(source)
        value={'rows':{'row_0':opaque(plan,'若 {v1} 关于 {v2} 的 Lipschitz 常数足够小。')}}
        content=b.restore_paragraphs(json.dumps(value),plan)
        b.checked_content(content,source,paragraphs=True)
        self.assertEqual(json.loads(content)[0]['id'],7)
        self.assertIn('Lipschitz',json.loads(content)[0]['output'])

    def test_missing_empty_merged_and_extra_rows_are_rejected(self):
        source=request([{'id':'a','input':'Title'},{'id':'b','input':'Another title'}])
        _,plan=b.paragraph_request(source)
        for rows in ({'row_0':'标题'}, {'row_0':'两个标题','row_1':''},
                     {'row_0':'标题','row_1':'另一标题','row_2':'额外'},
                     {'row_0':{'source':'bad'},'row_1':'标题'}):
            with self.assertRaisesRegex(b.BridgeError,'INVALID_PARAGRAPHS'):
                b.restore_paragraphs(json.dumps({'rows':rows}),plan)

    def test_math_markers_order_spelling_and_numeric_fragments_stay_protected(self):
        source=request([{'id':0,'input':'Text {v1} 0.005 {v2} end'}])
        _,plan=b.paragraph_request(source)
        for text in ('文本 {v2} 0.005 {v1} 末尾','文本 {v1} 0.05 {v2} 末尾',
                     '文本 {v1} 0.005 {v2} {v3} 末尾','文本 {v1} 0.005 {v2} <style id=foo>末尾'):
            with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.restore_paragraphs(json.dumps({'rows':{'row_0':text}}),plan)
        altered=json.dumps([{'id':0,'output':'文本 {v1} 0.05 {v2} 末尾'}])
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content(altered,source,paragraphs=True)

    def test_literal_only_rows_are_reconstructed_without_model_fields(self):
        source=request([{'id':0,'input':'{v1} 0.005'},{'id':1,'input':'Title'}])
        _,plan=b.paragraph_request(source)
        content=b.restore_paragraphs(json.dumps({'rows':{'row_1':'标题'}}),plan)
        self.assertEqual(json.loads(content)[0]['output'],'{v1} 0.005')
        self.assertEqual(list(b.paragraph_schema(plan)['properties']['rows']['properties']),['row_1'])

    def test_split_name_is_still_program_owned_and_added_full_name_refused(self):
        source=request([{'id':0,'input':'The implementation of {v3}Quad controller.'}])
        masked,protected=b.mask_code(source,['L1Quad'])
        _,plan=b.paragraph_request(masked)
        text=opaque(plan,plan[0]['source'].replace('The implementation of','实现'))
        result=b.restore_code(b.restore_paragraphs(json.dumps({'rows':{'row_0':text}}),plan),source,protected)
        b.checked_content(result,source,['L1Quad'],paragraphs=True)
        bad=json.loads(result);bad[0]['output']='L1Quad '+bad[0]['output']
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content(json.dumps(bad),source,['L1Quad'],paragraphs=True)

    def test_complete_math_group_can_move_but_internal_order_cannot(self):
        source=request([{'id':0,'input':'The system state {v1}({v2}) stays close for all {v3}.'}])
        _,plan=b.paragraph_request(source)
        text=opaque(plan,'对所有 {v3}，系统状态 {v1}({v2}) 保持接近。')
        out=b.restore_paragraphs(json.dumps({'rows':{'row_0':text}}),plan)
        b.checked_content(out,source,paragraphs=True)
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):b.checked_content(out,source)
        for bad in ('对所有 {v3}，状态 {v2}({v1}) 保持接近。','对所有 {v3}，状态 {v1}{v2} 保持接近。'):
            self.assertFalse(b.same_math_groups(b.translation_batch(source)[2][0]['input'],bad))

    def test_style_boundary_and_bracket_syntax_cannot_be_crossed_or_lost(self):
        source="<style id='1'>Text {v1}</style> and ({v2})"
        self.assertFalse(b.same_math_groups(source,"<style id='1'>文本 {v2}</style> 且 ({v1})"))
        self.assertFalse(b.same_math_groups('({v1}) and {v2}','{v1}() 且 {v2}'))
        self.assertFalse(b.same_math_groups('{v1}(<style id=\'1\'>,</style>{v2})',
                                          '{v1}(<style id=\'1\'>，</style>{v2})'))

    def test_adjacent_complete_objects_keep_every_internal_math_character(self):
        source='The state {v1} is the estimate of {v2}({v3}) for this system.'
        self.assertTrue(b.same_math_groups(source,'该系统状态由 {v1}{v2}({v3}) 表示。'))
        self.assertTrue(b.same_math_groups(source,'该系统状态由 {v1} {v2}({v3}) 表示。'))
        for bad in ('{v1}+{v2}({v3})','{v1}{v2}{v3}','{v1}{v3}({v2})','{v1}{v2}({v3}))',
                    '{v1}{v2}({v3}){v4}'):
            self.assertFalse(b.same_math_groups(source,bad),bad)

    def test_real_l1quad_word_interrupted_by_pdf_object_replays_without_new_inference(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/l1quad-adjacent-math.json').read_text(encoding='utf8'))
        source=request(fixture['rows']);names=['L1Quad','PID','DOB']
        masked,protected=b.mask_code(source,names);_,plan=b.paragraph_request(masked,names)
        for response in fixture['responses']:
            out=b.restore_code(b.restore_paragraphs(json.dumps(response),plan),source,protected)
            b.checked_content(out,source,names,paragraphs=True)
            restored=json.loads(out)
            for a,z in zip(fixture['rows'],restored):
                self.assertEqual(Counter(b.MARKER.findall(a['input'])),Counter(b.MARKER.findall(z['output'])))
            altered=json.loads(out);altered[1]['output']=altered[1]['output'].replace('{v8}(','{v8}+(',1)
            with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps(altered),source,names,paragraphs=True)

    def test_prose_numeric_values_and_units_are_exact_within_each_row(self):
        source=request([{'id':0,'input':'Assumption 2: Weight [g] is 5.'}])
        for text in ('假设3：重量[g]为5。','假设2：重量[kg]为5。','假设2：重量[g]为6。'):
            with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps([{'id':0,'output':text}]),source,paragraphs=True)

    def test_generated_prose_cannot_add_math_braces_operators_or_unmatched_parentheses(self):
        source=request([{'id':0,'input':'The value {v1} is an estimate of {v2}.'}])
        valid='该数值 {v1} 是 {v2} 的估计（estimate）。'
        b.checked_content(json.dumps([{'id':0,'output':valid}]),source,paragraphs=True)
        for bad in (valid+'}',valid+')',valid+'[',valid+'=',valid+'{}'):
            with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps([{'id':0,'output':bad}]),source,paragraphs=True)

    def test_legacy_cache_migration_revalidates_answers_but_never_accepts_corruption(self):
        source=request([{'id':0,'input':'The value {v1} is safe.'}]);source['response_format']=None
        valid=json.dumps([{'id':0,'output':'数值 {v1} 安全（safe）。'}])
        class Client:
            version='fixture-legacy';calls=0
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):self.calls+=1;return valid
        for mode in ('valid','new_guard_refusal','corrupt'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                identity={'bridge_version':b.VERSION,'native_version':Client.version,'backend':'codex',
                    'model':None,'request':source,'reasoning_effort':None,'native_output_contract':'named-paragraphs-schema-3'}
                key=hashlib.sha256(b.canonical(identity).encode()).hexdigest()
                content=valid if mode!='new_guard_refusal' else json.dumps([{'id':0,'output':'数值 {v1} 安全。}' }])
                record={'request_sha256':key,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'content':content}
                if mode=='corrupt':record['content_sha256']='0'*64
                path=Path(tmp,key+'.json');path.write_text(json.dumps(record),encoding='utf8');before=path.read_bytes()
                client=Client();provider={'type':'codex','retries':0,'output_contract':'paragraphs','cache_dir':tmp}
                with b.ChatBridge(provider,client) as server:
                    if mode=='corrupt':
                        with self.assertRaisesRegex(b.BridgeError,'INVALID_CACHE'):server.complete(source)
                        self.assertEqual(client.calls,0)
                    else:
                        server.complete(source)
                        self.assertEqual(client.calls,int(mode=='new_guard_refusal'))
                        self.assertEqual(server.stats['legacy_cache_hits'],int(mode=='valid'))
                        self.assertEqual(server.stats['legacy_cache_refusals'],int(mode=='new_guard_refusal'))
                self.assertEqual(before,path.read_bytes())

    def test_short_table_headers_keep_all_token_order(self):
        source=request([{'id':0,'input':'Weight [g] {v1}off {v2}on {v3}PID'}])
        _,plan=b.paragraph_request(source)
        self.assertFalse(plan[0]['math_may_reorder'])
        text=opaque(plan,'重量 [g] {v2}on {v1}off {v3}PID')
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.restore_paragraphs(json.dumps({'rows':{'row_0':text}}),plan)

    def test_explicit_name_prefix_style_moves_with_its_math_not_as_prose(self):
        text="We can validate the performance of <style id='12'>L</style>{v13}Quad through experiments{v14} for eleven uncertainties."
        source=request([{'id':0,'input':text}]);names=['L1Quad']
        masked,protected=b.mask_code(source,names)
        _,plan=b.paragraph_request(masked,names)
        self.assertNotIn("<style id='12'>",plan[0]['model_source'])
        # Use the same exact math/name data that a model sees, not raw markers.
        complete=plan[0]['source'].replace('We can validate the performance of ','')
        compound=complete.split(' through experiments',1)[0]
        target='我们通过实验{v14}验证'+compound+'控制器在十一类不确定性下的性能。'
        encoded=opaque(plan,target)
        out=b.restore_code(b.restore_paragraphs(json.dumps({'rows':{'row_0':encoded}}),plan),source,protected)
        b.checked_content(out,source,names,paragraphs=True)
        self.assertTrue(b.has_math_prefix(source,names))
        self.assertFalse(b.has_math_prefix(source,['MMLU']))
        bad=json.loads(out);bad[0]['output']=bad[0]['output'].replace('>L</style>','>R</style>')
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content(json.dumps(bad),source,names,paragraphs=True)

    def test_configured_acronym_glued_to_prose_is_counted_and_restored(self):
        source=request([{'id':0,'input':'The DOB and DOBmethods operate safely.'}]);names=['DOB']
        self.assertEqual(b.identifier_pattern(names).findall(b.translation_batch(source)[2][0]['input']),['DOB','DOB'])
        masked,protected=b.mask_code(source,names)
        self.assertEqual(len(protected['0']),2)
        row=b.translation_batch(masked)[2][0]
        self.assertNotIn('DOB',row['input'])
        out=json.dumps([{'id':0,'output':row['input'].replace('The ','').replace(' and ',' 和 ').replace('methods operate safely.','方法安全运行。')}])
        restored=b.restore_code(out,source,protected)
        b.checked_content(restored,source,names,paragraphs=True)
        self.assertEqual(b.glued_identifiers(source,names),['DOB'])
        self.assertEqual(b.identifier_pattern(['MMLU']).findall('MMLU-Pro'),[])
        self.assertEqual(b.identifier_pattern(['MMLU','MMLU-Pro']).findall('MMLU-Pro'),['MMLU-Pro'])

    def test_glued_revision_invalidates_only_the_affected_legacy_checkpoint(self):
        class Client:
            version='fixture';calls=0
            def doctor(self):return {'native_version':self.version,'ready':True}
            def translate(self,req):
                self.calls+=1
                return json.dumps([{'id':r['id'],'output':r['input']} for r in b.translation_batch(req)[2]])
        req=request([{'id':0,'input':'The DOB and DOBmethods operate safely.'}]);req['response_format']=None
        with tempfile.TemporaryDirectory() as tmp:
            provider={'type':'codex','retries':0,'cache_dir':tmp,'protected_identifiers':['DOB']}
            old={'bridge_version':b.VERSION,'native_version':'fixture','backend':'codex','model':None,
                'request':req,'reasoning_effort':None,'protected_identifiers':['DOB'],'protected_identifier_revision':1}
            key=hashlib.sha256(b.canonical(old).encode()).hexdigest()
            content=json.dumps([{'id':0,'output':'DOB 方法安全运行。'}])
            Path(tmp,key+'.json').write_text(json.dumps({'request_sha256':key,
                'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'content':content}),encoding='utf8')
            first=Client()
            with b.ChatBridge(provider,first) as server:server.complete(req)
            self.assertEqual(first.calls,1)
            again=Client()
            with b.ChatBridge(provider,again) as server:server.complete(req)
            self.assertEqual(again.calls,0)

    def test_single_paragraph_route_uses_the_same_group_fidelity(self):
        source='The system state {v1}({v2}) always stays close for all {v3}.'
        req={'messages':[{'role':'user','content':';; Treat next line as plain text input and translate it into Chinese.\nInput:\n\n'+source}]}
        target='对所有 {v3}，系统状态 {v1}({v2}) 始终保持接近。'
        b.checked_content(target,req,paragraphs=True)
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):b.checked_content(target,req)

    def test_output_contract_is_explicit_native_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=b.validate_provider({'type':'codex','model':'fixture','output_contract':'paragraphs'},Path(tmp))
            self.assertEqual(provider['output_contract'],'paragraphs')
            default=b.validate_provider({'type':'codex','model':'fixture'},Path(tmp))
            self.assertNotIn('output_contract',default)
            for invalid in ('auto',[],True):
                with self.assertRaises(ValueError):b.validate_provider({'type':'codex','output_contract':invalid},Path(tmp))

    def test_token_fidelity_feedback_locates_all_rows_without_weakening_guard(self):
        source=request([{'id':0,'input':'The {v1} adaptive controller is safe.'},
                        {'id':1,'input':'where {v1} is the prediction error.'}])
        transformed,plan=b.paragraph_request(source)
        first=next(iter(plan[0]['math_groups']));second=next(iter(plan[1]['math_groups']))
        bad={'rows':{'row_0':'控制器安全。','row_1':'其中 '+first+' 为误差。'}}
        with self.assertRaises(b.BridgeError) as raised:b.restore_paragraphs(json.dumps(bad),plan)
        detail=raised.exception.detail
        self.assertEqual(detail['guard'],'paragraph_tokens')
        self.assertEqual(detail['rows'],[{'row':'row_0','missing':[first],'extra':[]},
            {'row':'row_1','missing':[second],'extra':[first]}])
        self.assertIn('required_tokens',transformed['messages'][0]['content'])

    def test_paragraph_cache_is_separate_and_default_cache_unchanged(self):
        class Client:
            version='fixture';calls=0
            def doctor(self):return {'native_version':self.version,'ready':True}
            def translate(self,req):
                self.calls+=1
                return json.dumps([{'id':r['id'],'output':r['input']} for r in b.translation_batch(req)[2]])
        req=request([{'id':0,'input':'Text {v1}'}]);req['response_format']=None
        with tempfile.TemporaryDirectory() as tmp:
            base={'type':'codex','retries':0,'cache_dir':tmp}
            for config,expected in ((base,1),({**base,'output_contract':'text_slots'},0),
                                    ({**base,'output_contract':'paragraphs'},1),({**base,'output_contract':'paragraphs'},0)):
                client=Client()
                with b.ChatBridge(config,client) as server:server.complete(req)
                self.assertEqual(client.calls,expected)


if __name__=='__main__':unittest.main()
