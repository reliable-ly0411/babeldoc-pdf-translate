"""Legitimate date aliases cannot waive wrong dates, scalars, units or math."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as bridge,date_literals as dates,source_repair as source


def checked(original,target):
    request={'messages':[{'role':'user','content':'Translate English to Chinese.\n## Here is the input:\n'+
        bridge.canonical([{'id':1,'input':original}])}]}
    return bridge.checked_content(bridge.canonical([{'id':1,'output':target}]),request,paragraphs=True)


class DateLiteralTests(unittest.TestCase):
    def test_actual_header_date_alias_preserves_all_opaque_markers(self):
        before='{v1}Nature {v2}Vol {v3}September 2025'
        after='{v1}《自然》{v2}卷{v3}2025年9月'
        self.assertTrue(checked(before,after))
        self.assertEqual(bridge.MARKER.findall(before),bridge.MARKER.findall(after))

    def test_all_months_have_exact_arabic_and_chinese_month_aliases(self):
        for number,name in enumerate(dates.FULL,1):
            for month in (str(number),dates.CN[number-1]):
                with self.subTest(month=name,target=month):
                    self.assertTrue(checked(name+' 2025','2025年'+month+'月'))

    def test_wrong_month_or_year_is_rejected_in_words_and_digits(self):
        for text in ('2025年8月','2024年9月','August 2025','September 2024','2025年十月'):
            with self.subTest(text=text),self.assertRaises(bridge.BridgeError):checked('September 2025',text)

    def test_extra_or_omitted_numeric_values_remain_protected(self):
        for text in ('2025年9月 9','9月','2025年9月 1 [s]','2025年9月9日'):
            with self.subTest(text=text),self.assertRaises(bridge.BridgeError):checked('September 2025',text)

    def test_month_precision_cannot_be_promoted_to_a_day_or_dropped_from_a_day(self):
        for original,target in [('September 2025','2025年9月1日'),('18 September 2025','2025年9月')]:
            with self.assertRaises(bridge.BridgeError):checked(original,target)

    def test_complete_dates_support_gregorian_precision_and_source_gap_order(self):
        for original in ('18 September 2025','September 18, 2025'):
            for target in ('2025年9月18日','2025年九月十八日','18 2025年9月'):
                self.assertTrue(checked(original,target))
        self.assertTrue(source.validate_translation({'source':'On 18 September 2025'},'在2025年9月18日'))
        self.assertFalse(source.validate_translation({'source':'May 2024 then September 2025'},'2025年9月然后2024年5月'))

    def test_impossible_full_date_is_not_reinterpreted_as_month_plus_scalar(self):
        facts,remaining=dates.extract('30 February 2025',numeric_iso=False)
        self.assertEqual(facts,[]);self.assertEqual(remaining,'30 February 2025')
        for target in ('2025年2月30日','2025年9月31日'):
            facts,remaining=dates.extract(target,numeric_iso=False)
            self.assertEqual(facts,[]);self.assertEqual(remaining,target)

    def test_lowercase_modal_may_and_attached_identifiers_are_not_month_exemptions(self):
        for text in ('may 2025 people','XSeptember 2025','September2025','September 2025.25'):
            self.assertEqual(dates.extract(text,numeric_iso=False)[0],[])
        with self.assertRaises(bridge.BridgeError):checked('may 2025 people','2025年5月的人')

    def test_bare_numeric_iso_is_not_a_bridge_exemption_for_subtraction(self):
        self.assertEqual(dates.extract('2025-09',numeric_iso=False)[0],[])
        self.assertTrue(bridge.paragraph_literals_equal('2025-09','2025-09'))
        self.assertFalse(bridge.paragraph_literals_equal('2025-09','2025年9月'))
        self.assertFalse(bridge.paragraph_literals_equal('x = -5','x = +5'))

    def test_legacy_audit_iso_aliases_stay_supported_without_losing_extra_numbers(self):
        self.assertEqual(dates.extract('2025-09')[0],['month:2025-09'])
        self.assertEqual(dates.extract('2025-09-18')[0],['2025-09-18'])
        self.assertEqual(dates.extract('2025年9月18日 9')[1].strip(),'9')

    def test_plain_scalars_units_table_numbers_and_identifiers_are_unchanged(self):
        for original,target in [('Table 1','表11'),('5 [m/s]','5 [m]'),('DeepSeek-R1','DeepSeek-R2'),
                ('September 2025, count 4','2025年9月，计数5')]:
            with self.assertRaises(bridge.BridgeError):checked(original,target)

    def test_source_gap_accepts_only_same_date_and_local_numeric_order(self):
        self.assertTrue(source.validate_translation({'source':'September 2025, count 1 then 2'},'2025年9月，计数1再2'))
        self.assertFalse(source.validate_translation({'source':'September 2025, count 1 then 2'},'2025年9月，计数2再1'))
        self.assertFalse(source.validate_translation({'source':'September 2025'},'2025年8月'))

    def test_calendar_failure_detail_explains_same_digits_with_different_month_words(self):
        with self.assertRaises(bridge.BridgeError) as caught:checked('September 2025','October 2025')
        self.assertEqual(caught.exception.detail['expected_calendar_dates'],{'month:2025-09':1})
        self.assertEqual(caught.exception.detail['actual_calendar_dates'],{'month:2025-10':1})

    def test_disk_cache_is_revalidated_without_a_new_call_or_global_key_change(self):
        request={'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+
            bridge.canonical([{'id':1,'input':'September 2025'}])}]}
        good=bridge.canonical([{'id':1,'output':'2025年9月'}])
        class Client:
            version='calendar-fixture-1'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):return good
        class NoInference(Client):
            def translate(self,request):raise AssertionError('CACHE MUST NOT INVOKE MODEL')
        with tempfile.TemporaryDirectory() as tmp:
            provider={'type':'codex','model':'fixture','cache_dir':str(Path(tmp)/'cache'),'retries':0,'output_contract':'paragraphs'}
            with bridge.ChatBridge(provider,Client()) as client:self.assertEqual(client.complete(request),good)
            file=next((Path(tmp)/'cache').glob('*.json'));old=file.read_bytes()
            with bridge.ChatBridge({**provider,'cache_only':True},NoInference()) as client:
                self.assertEqual(client.complete(request),good);self.assertEqual(client.stats['cache_hits'],1)
                self.assertEqual(client.stats['attempts'],0)
            self.assertEqual(file.read_bytes(),old)
            value=json.loads(old);value['content']=bridge.canonical([{'id':1,'output':'August 2025'}])
            value['content_sha256']=hashlib.sha256(value['content'].encode()).hexdigest()
            file.write_bytes(bridge.canonical(value).encode())
            with bridge.ChatBridge({**provider,'cache_only':True},NoInference()) as client:
                with self.assertRaises(bridge.BridgeError) as caught:client.complete(request)
                self.assertEqual(caught.exception.code,'INVALID_CACHE');self.assertEqual(client.stats['attempts'],0)


if __name__=='__main__':unittest.main()
