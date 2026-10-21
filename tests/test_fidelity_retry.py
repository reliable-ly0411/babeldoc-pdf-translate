"""Calendar meaning and syntax recovery stay separate, with one bounded retry."""
import json,sys,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b


def request(source):
    return {'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+b.canonical([{'id':0,'input':source}])}]}


class FidelityRetryTests(unittest.TestCase):
    def test_month_hints_cover_all_names_and_never_decode_year(self):
        for n,name in enumerate(b.date_literals.FULL,1):
            self.assertEqual(b.calendar_prompt_hints(name+' {v3}'),
                [{'precision':'month','month_number':n,'year':{'opaque':True}}])

    def test_known_fields_precision_and_duplicates_remain_explicit(self):
        self.assertEqual(b.calendar_prompt_hints('18 September 2025; September 2025'),[
            {'precision':'day','month_number':9,'year':{'value':2025},'day':{'value':18}},
            {'precision':'month','month_number':9,'year':{'value':2025}}])
        self.assertEqual(b.calendar_prompt_hints('{v1} September {v2}'),[
            {'precision':'day','month_number':9,'year':{'opaque':True},'day':{'opaque':True}}])

    def test_hints_do_not_infer_modal_prose_invalid_dates_or_volume_fields(self):
        for text in ('May {v1} be independent?','March {v1} steps','31 September {v3}','Vol 3','2025-09'):
            self.assertEqual(b.calendar_prompt_hints(text),[])
        self.assertEqual(b.calendar_prompt_hints('Nature {v1}Vol {v2}September {v3}'),[
            {'precision':'month','month_number':9,'year':{'opaque':True}}])

    def test_hints_do_not_expose_original_marker_ids_in_masked_paragraphs(self):
        req=request('September {v3}')
        for transform in (b.slot_request,b.paragraph_request):
            wire,_=transform(req)
            data=json.loads(wire['messages'][0]['content'].split('\n',1)[1])
            hint=data['entries'][0]['source_calendar_hints']
            self.assertEqual(hint,[{'precision':'month','month_number':9,'year':{'opaque':True}}])
            self.assertNotIn('{v3}',b.canonical(hint))

    def test_semantic_and_unknown_failures_do_not_force_a_different_schema(self):
        for code,detail in [('PROTECTED_TEXT_CHANGED',{'kind':'numeric_or_unit_count'}),
                ('PROTECTED_TEXT_CHANGED',{'kind':'explicit_name_count'}),
                ('PROTECTED_TEXT_CHANGED',None),('OMITTED_TRANSLATION',None),('SERVER',None)]:
            self.assertFalse(b.retry_needs_slots(code,detail))

    def test_explicit_schema_and_marker_defects_still_get_slot_recovery(self):
        for code,detail in [('INVALID_PARAGRAPHS',None),('INVALID_TEXT_SLOTS',None),
                ('INCOMPLETE_TRANSLATION_BATCH',None),('INVALID_JSON_RESPONSE',None),
                ('PROTECTED_TEXT_CHANGED',{'guard':'paragraph_tokens'}),
                ('PROTECTED_TEXT_CHANGED',{'kind':'math_group_or_style_boundary'}),
                ('PROTECTED_TEXT_CHANGED',{'guard':'opaque_barrier_crossed'})]:
            self.assertTrue(b.retry_needs_slots(code,detail))

    def run_retry(self,second,max_calls=2):
        req=request('Nature {v1}Vol {v2}September {v3}')
        modes=[];feedback=[]
        def translate(client,body,**kwargs):
            modes.append(kwargs.get('force_slots',False));feedback.append(body)
            target='Nature {v1}第 {v2}卷 {v3}年' if len(modes)==1 else second
            return b.canonical([{'id':0,'output':target}])
        provider={'type':'codex','model':'fixture-luna','output_contract':'paragraphs',
            'retries':1,'max_model_calls':max_calls,'timeout_seconds':3}
        with mock.patch.object(b.NativeClient,'doctor',return_value={'native_version':'fixture'}),\
                mock.patch.object(b.NativeClient,'translate',autospec=True,side_effect=translate):
            with b.ChatBridge(provider) as client:
                try:content=client.complete(req);error=None
                except b.BridgeError as exc:content=None;error=exc.code
                stats=json.loads(b.canonical(client.stats))
        return modes,feedback,stats,content,error

    def test_actual_month_omission_gets_one_paragraph_retry_with_guard_feedback(self):
        modes,feedback,stats,content,error=self.run_retry('Nature {v1}第 {v2}卷 9月 {v3}')
        self.assertEqual(modes,[False,False]);self.assertEqual(stats['attempts'],2)
        self.assertIsNone(error);self.assertIn('9月',content)
        self.assertIn('expected_calendar_dates',feedback[1]['messages'][-1]['content'])
        self.assertNotIn('native_schema_fallbacks',stats)

    def test_second_changed_calendar_is_rejected_without_further_calls(self):
        modes,_,stats,content,error=self.run_retry('Nature {v1}第 {v2}卷 10月 {v3}')
        self.assertEqual(modes,[False,False]);self.assertEqual(stats['attempts'],2)
        self.assertEqual(error,'PROTECTED_TEXT_CHANGED');self.assertIsNone(content)

    def test_total_call_cap_applies_before_the_correction(self):
        modes,_,stats,content,error=self.run_retry('Nature {v1}第 {v2}卷 9月 {v3}',max_calls=1)
        self.assertEqual(modes,[False]);self.assertEqual(stats['attempts'],1)
        self.assertEqual(error,'NATIVE_CALL_BUDGET_EXHAUSTED');self.assertIsNone(content)

    def test_added_marker_in_a_fixed_slot_is_still_refused(self):
        _,plan=b.slot_request(request('Nature {v1}Vol {v2}September {v3}'))
        value={'rows':{'row_0':{'slot_0':'《自然》','slot_1':'第 {v2} 卷','slot_2':'9月'}}}
        with self.assertRaisesRegex(b.BridgeError,'INVALID_TEXT_SLOTS'):
            b.restore_slots(b.canonical(value),plan)


if __name__=='__main__':unittest.main()
