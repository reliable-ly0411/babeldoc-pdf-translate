"""Typed date fields preserve native identities, values, precision and math."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as bridge,date_literals as dates,source_repair as source

def checked(original,target):
    request={'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+bridge.canonical([{'id':0,'input':original}])}]}
    return bridge.checked_content(bridge.canonical([{'id':0,'output':target}]),request,paragraphs=True)

class CalendarFragmentTests(unittest.TestCase):
    def test_all_named_months_abbreviations_and_chinese_aliases_with_hidden_year(self):
        for number,names in enumerate(zip(dates.FULL,dates.SHORT),1):
            for name in (*names,names[1]+'.'):
                for month in (str(number),dates.CN[number-1]):
                    for target in (month+'月 {v3}','{v3}年'+month+'月','{v3}'+month+'月',month+'月份 {v3}'):
                        with self.subTest(source=name,target=target):self.assertTrue(checked(name+' {v3}',target))
        self.assertTrue(checked('Sept. {v3}','九月 {v3}'))

    def test_actual_header_and_styles_keep_original_opaque_field_identity(self):
        self.assertTrue(checked('Nature {v1}Vol {v2}September {v3}','《自然》 {v1}第 {v2}9月 {v3}'))
        self.assertTrue(checked("<style id='1'>September </style>{v3}","<style id='1'>9月 </style>{v3}"))
        before,_=dates.protected('September {v3}',bridge.MARKER)
        after,_=dates.protected('9月 {v3}',bridge.MARKER)
        self.assertEqual(before,after);self.assertIn('year={v3}',before[0])

    def test_day_and_year_can_each_be_opaque_but_roles_are_exact(self):
        for original,target in [('18 September {v3}','{v3}年9月18日'),
                ('September 18, {v3}','9月18日 {v3}年'),
                ('{v1} September 2025','9月{v1}日2025年'),
                ('{v1} September {v2}','9月{v1}日{v2}年'),
                ('September {v1}, {v2}','9月{v1}日{v2}年')]:
            with self.subTest(original=original):self.assertTrue(checked(original,target))

    def test_unchanged_marker_order_does_not_allow_day_year_role_swap(self):
        original='{v1} September {v2}';bad='{v1}年9月{v2}日'
        self.assertEqual(bridge.MARKER.findall(original),bridge.MARKER.findall(bad))
        with self.assertRaises(bridge.BridgeError):checked(original,bad)

    def test_hidden_field_cannot_be_decoded_duplicated_changed_or_dropped(self):
        for target in ('2025年9月','{v2}年9月','9月 {v3} {v3}','{v3}年9月 2025','{v3}年9月 9'):
            with self.subTest(target=target),self.assertRaises(bridge.BridgeError):checked('September {v3}',target)

    def test_month_and_known_day_changes_fail_for_every_month(self):
        for n,name in enumerate(dates.FULL,1):
            with self.subTest(month=n),self.assertRaises(bridge.BridgeError):checked(name+' {v3}',str(n%12+1)+'月{v3}')
        for target in ('{v3}年9月17日','{v3}年10月18日','{v3}年9月19日'):
            with self.assertRaises(bridge.BridgeError):checked('18 September {v3}',target)

    def test_precision_cannot_be_added_or_removed(self):
        for original,target in [('September {v3}','{v3}年9月1日'),('18 September {v3}','{v3}年9月'),
                ('September {v3}','9月'),('September {v3}','{v3}年'),
                ('September {v3}, count 18','{v3}9月18日'),('September {v3}, count 18','{v3} September 18')]:
            with self.subTest(original=original,target=target),self.assertRaises(bridge.BridgeError):checked(original,target)

    def test_impossible_date_does_not_fall_back_to_a_shorter_fragment(self):
        for text in ('30 February {v3}','31 September {v3}','{v3}年2月30日','{v3}年13月'):
            facts,remaining=dates.extract(text,numeric_iso=False,opaque_fields=True)
            self.assertEqual(facts,[]);self.assertEqual(remaining,text)
        self.assertTrue(checked('29 February {v3}','{v3}年2月29日'))
        with self.assertRaises(bridge.BridgeError):checked('29 February {v3}','{v3}年2月28日')

    def test_opaque_name_code_and_identifiers_are_not_calendar_year_fields(self):
        for text in ('XSeptember {v3}','September2025','may {v3} people','September {pdftranslate_name_0123456789abcdef}'):
            self.assertEqual(dates.protected(text,bridge.MARKER)[0],[])
        with self.assertRaises(bridge.BridgeError):checked('may {v3} people','{v3}年5月的人')
        with self.assertRaises(bridge.BridgeError):checked('September {pdftranslate_name_0123456789abcdef}','9月 {pdftranslate_name_0123456789abcdef}')

    def test_calendar_fields_cannot_conceal_math_changes_or_other_scalars(self):
        for original,target in [('September {v3}, x = -5','9月 {v3}，x = +5'),
                ('September {v3}, {v4}+{v5}','9月 {v3}，{v4}-{v5}'),
                ('September {v3}, count 4','9月 {v3}，计数5'),
                ('September {v3}, 3 [m/s]','9月 {v3}，3 [m]'),
                ('September {v3}, Table 1','9月 {v3}，表11')]:
            with self.subTest(original=original),self.assertRaises(bridge.BridgeError):checked(original,target)

    def test_signed_dates_and_source_gap_numbers_do_not_lose_sign_or_exponent(self):
        for original,target in [('-18 September 2025','+18 September 2025'),
                ('-18 September {v3}','18 September {v3}'),('2025-09','2025年9月')]:
            with self.assertRaises(bridge.BridgeError):checked(original,target)
        for original,target in [('value -5','值+5'),('value 1e-3','值1e3'),('value −5','值5')]:
            self.assertFalse(source.validate_translation({'source':original},target))

    def test_source_omissions_and_missing_markers_still_fail(self):
        for target in ('9月 {v3} [已省略]','9月 {v3} ...','9月'):
            with self.subTest(target=target),self.assertRaises(bridge.BridgeError):checked('September {v3}; full result follows',target)

    def test_modal_and_verb_month_spellings_do_not_acquire_date_roles(self):
        for original,target in [('May {v1} be independent?','可以{v1}独立吗？'),('March {v1} steps','前进{v1}步')]:
            self.assertEqual(dates.protected(original,bridge.MARKER)[0],[])
            self.assertTrue(checked(original,target))
        self.assertTrue(checked('In May {v1} we observed 3 events','{v1}年5月观察到3次事件'))

    def test_native_paragraph_schema_keeps_two_calendar_fields_independent(self):
        request={'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+bridge.canonical([{'id':0,'input':'September {v1}, {v2}'}])}]}
        _,plan=bridge.paragraph_request(request,())
        groups=plan[0]['math_groups'];self.assertEqual(len(groups),2)
        tokens=[next(k for k,v in groups.items() if v==field) for field in ('{v1}','{v2}')]
        raw=bridge.canonical({'rows':{'row_0':'9月'+tokens[0]+'日'+tokens[1]+'年'}})
        content=bridge.restore_paragraphs(raw,plan)
        self.assertTrue(bridge.checked_content(content,request,paragraphs=True))
        self.assertEqual(json.loads(content)[0]['output'],'9月{v1}日{v2}年')

    def test_noncalendar_tuple_and_operator_boundaries_are_unchanged(self):
        for original,target in [('September({v1}, {v2})','九月({v1}{v2})'),
                ('September {v1}+{v2}','9月 {v1}-{v2}'),
                ('September {v1}, {v2}','9月{v1}日{v2}年 ...')]:
            with self.assertRaises(bridge.BridgeError):checked(original,target)
        self.assertTrue(checked('Values ... are listed for September {v3}','数值……列在9月{v3}'))

    def test_name_repetition_is_diagnosed_without_waiving_its_numeric_content(self):
        with self.assertRaises(bridge.BridgeError) as caught:
            checked('Dev1 improves compared with Dev2','Dev1 与 Dev2 相比，Dev1 有提升')
        self.assertEqual(caught.exception.detail['identifier_occurrence_differences'],
            [{'literal':'Dev1','source_count':1,'target_count':2}])
        self.assertTrue(checked('Dev1 improves compared with Dev2','Dev1 与 Dev2 相比，它有提升'))
        with self.assertRaises(bridge.BridgeError):checked('{v3}Quad controller','{v3}L1Quad 控制器')

    def test_identifier_count_metadata_is_program_owned_for_both_native_schemas(self):
        req=request={'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+bridge.canonical([{'id':0,'input':'Dev1 improves over Dev2. Dev1 remains stable.'}])}]}
        for transform in (bridge.slot_request,bridge.paragraph_request):
            transformed,_=transform(req)
            payload=json.loads(transformed['messages'][0]['content'].split('\n',1)[1])
            self.assertEqual(payload['entries'][0]['source_identifier_counts'],{'Dev1':2,'Dev2':1})

    def test_unicode_mathematical_minus_preserves_value_and_rejects_sign_loss(self):
        for original,target in [('value −5','值5'),('value 1e−3','值1e3'),('value −5','值+5')]:
            with self.assertRaises(bridge.BridgeError):checked(original,target)
            self.assertFalse(source.validate_translation({'source':original},target))
        for original,target in [('value −5','值-5'),('value 1e−3','值1e-3')]:
            self.assertTrue(checked(original,target))
            self.assertTrue(source.validate_translation({'source':original},target))

    def test_neighboring_volume_page_and_formula_fields_are_not_days_or_years(self):
        for n,name in enumerate(dates.FULL,1):
            for label,value in [('Vol','{v2}'),('Volume','{v2}'),('Page','{v2}'),('Issue','18'),('Vol','1')]:
                for year in ('2025','{v3}'):
                    original=label+' '+value+' '+name+' '+year
                    target='编号'+value+' '+(year+'年'+str(n)+'月')
                    with self.subTest(original=original):self.assertTrue(checked(original,target))
            self.assertTrue(checked('Nature {v1}Vol {v2}'+name+' {v3}',
                'Nature {v1}第 {v2}卷 {v3}'+dates.CN[n-1]+'月'))
            self.assertTrue(checked('{v1}Nature {v2}Vol {v3}'+name+' 2025',
                '{v1}Nature {v2}第{v3}卷2025年'+str(n)+'月'))
        for text in ('Vol {v2} September {v3}','x={v2} September {v3}'):
            facts,_=dates.protected(text,bridge.MARKER)
            self.assertEqual(facts,['calendar:month:year={v3};month=9'])

    def test_cache_only_accepts_equivalence_but_rejects_changed_calendar_identity(self):
        request={'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+bridge.canonical([{'id':0,'input':'September {v3}'}])}]}
        class Fixture:
            version='calendar-fragment-fixture'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):return bridge.canonical([{'id':0,'output':'9月 {v3}'}])
        class NoInference(Fixture):
            def translate(self,request):raise AssertionError('No new call permitted')
        with tempfile.TemporaryDirectory() as tmp:
            cfg={'type':'codex','model':'fixture','cache_dir':str(Path(tmp)/'cache'),'output_contract':'paragraphs','retries':0}
            with bridge.ChatBridge(cfg,Fixture()) as b:b.complete(request)
            p=next((Path(tmp)/'cache').glob('*.json'));initial=p.read_bytes()
            with bridge.ChatBridge({**cfg,'cache_only':True},NoInference()) as b:
                b.complete(request);self.assertEqual(b.stats['attempts'],0)
            self.assertEqual(p.read_bytes(),initial)
            d=json.loads(initial);d['content']=bridge.canonical([{'id':0,'output':'8月 {v3}'}]);d['content_sha256']=hashlib.sha256(d['content'].encode()).hexdigest();p.write_text(bridge.canonical(d),encoding='utf-8')
            with bridge.ChatBridge({**cfg,'cache_only':True},NoInference()) as b:
                with self.assertRaises(bridge.BridgeError) as caught:b.complete(request)
                self.assertEqual(caught.exception.code,'INVALID_CACHE');self.assertEqual(b.stats['attempts'],0)

if __name__=='__main__':unittest.main()
