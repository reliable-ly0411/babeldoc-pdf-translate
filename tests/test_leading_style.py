"""Source-owned format restoration and one bounded native schema correction."""
import copy,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b


def request(text):
    return {'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+b.canonical([{'id':0,'input':text}])}]}


class LeadingStyleTests(unittest.TestCase):
    def test_only_unique_missing_initial_opener_is_restored_without_changing_prose(self):
        source="<style id='1'>Before </style>{v3}<style id='4'>after</style>"
        target="此前 </style>{v3}<style id='4'>之后</style>"
        value,proof=b.restore_leading_style(source,target)
        self.assertEqual(value,"<style id='1'>"+target)
        self.assertEqual(value[len("<style id='1'>"):],target)
        self.assertEqual(proof['before_sha256'],hashlib.sha256(target.encode()).hexdigest())
        self.assertEqual(b.MARKER.findall(value),b.MARKER.findall(source))

    def test_complete_style_or_ambiguous_missing_inner_closing_math_tokens_are_not_inferred(self):
        source="<style id='1'>Before </style>{v3}<style id='4'>after</style>"
        cases=[source,source.replace("<style id='4'>",''),source.replace('</style>','',1),
            source.replace('{v3}',''),source.replace("<style id='1'>",'').replace("<style id='4'>",''),
            "</style>{v3}<style id='4'>之后</style>",
            "此前 </style><style id='4'>之后</style>{v3}"]
        for target in cases:
            with self.subTest(target=target):self.assertEqual(b.restore_leading_style(source,target),(target,None))

    def test_source_with_unstyled_prefix_or_nested_span_is_not_repaired(self):
        for source,target in [("Intro <style id='1'>word</style>","引言 词</style>"),
                ("<style id='1'><style id='2'>word</style></style>","<style id='2'>词</style></style>")]:
            self.assertEqual(b.restore_leading_style(source,target),(target,None))

    def test_decoder_logs_exact_restoration_and_runs_original_guards(self):
        source="<style id='1'>Use </style>{v3}<style id='4'>then stop.</style>"
        req,plan=b.paragraph_request(request(source));model=plan[0]['model_source']
        target=model.replace("<style id='1'>",'',1).replace('Use ','使用 ').replace('then stop.','随后停止。')
        repairs=[];wire=b.restore_paragraphs(b.canonical({'rows':{'row_0':target}}),plan,repairs)
        self.assertTrue(b.checked_content(wire,request(source),paragraphs=True))
        self.assertEqual(len(repairs),1);self.assertEqual(repairs[0]['row'],'row_0')

    def test_restored_format_cannot_hide_changed_number_or_new_identifier(self):
        for source,target,ids in [("<style id='1'>Count 3</style>","计数4</style>",()),
                ("<style id='1'>Quad controller</style>","L1Quad控制器</style>",('L1Quad',))]:
            _,plan=b.paragraph_request(request(source),ids)
            value=b.restore_paragraphs(b.canonical({'rows':{'row_0':target}}),plan,[])
            with self.assertRaises(b.BridgeError):b.checked_content(value,request(source),ids,paragraphs=True)

    def test_altered_math_token_still_rejects_before_any_repair(self):
        source="<style id='1'>Use </style>{v3}"
        _,plan=b.paragraph_request(request(source))
        with self.assertRaises(b.BridgeError):
            b.restore_paragraphs(b.canonical({'rows':{'row_0':'使用 </style>{v9}'}}),plan,[])


class SchemaCorrectionTests(unittest.TestCase):
    def run_retry(self,bad_second=False,transient=False):
        req=request("<style id='1'>Count 3</style>")
        provider={'type':'codex','model':'fixture-luna','output_contract':'paragraphs','retries':1,'timeout_seconds':3,'max_model_calls':2}
        modes=[]
        def translate(client,body,**kwargs):
            modes.append(kwargs.get('force_slots',False))
            if len(modes)==1:
                raise b.BridgeError('SERVER' if transient else 'PROTECTED_TEXT_CHANGED',{'guard':'paragraph_tokens'})
            return b.canonical([{'id':0,'output':"<style id='1'>计数"+('4' if bad_second else '3')+'</style>'}])
        with mock.patch.object(b.NativeClient,'doctor',return_value={'native_version':'fixture'}),\
             mock.patch.object(b.NativeClient,'translate',autospec=True,side_effect=translate):
            with b.ChatBridge(provider) as client:
                if bad_second:
                    with self.assertRaises(b.BridgeError):client.complete(req)
                else:client.complete(req)
                return modes,copy.deepcopy(client.stats)

    def test_format_correction_uses_fixed_slots_once_with_same_model_and_budget(self):
        modes,stats=self.run_retry()
        self.assertEqual(modes,[False,True]);self.assertEqual(stats['attempts'],2)
        self.assertTrue(stats['native_schema_fallbacks'][0]['validated'])

    def test_retry_still_rejects_changed_scalar_and_stops_at_two_attempts(self):
        modes,stats=self.run_retry(bad_second=True)
        self.assertEqual(modes,[False,True]);self.assertEqual(stats['attempts'],2)
        self.assertFalse(stats['native_schema_fallbacks'][0]['validated'])

    def test_transport_retry_keeps_original_schema(self):
        modes,stats=self.run_retry(transient=True)
        self.assertEqual(modes,[False,False]);self.assertNotIn('native_schema_fallbacks',stats)

    def test_force_slots_selects_real_fixed_field_schema_without_a_native_process(self):
        client=b.NativeClient({'type':'codex','model':'fixture','output_contract':'paragraphs','timeout_seconds':5},None)
        req=request("<style id='1'>Before </style>{v1}<style id='2'>after</style>")
        observed=[]
        def invoke(argv,prompt='',**kwargs):
            schema=json.loads(Path(argv[argv.index('--output-schema')+1]).read_text(encoding='utf-8'))
            row=schema['properties']['rows']['properties']['row_0'];observed.append(row['type'])
            response={'rows':{'row_0':{key:'译文' for key in row['properties']}}}
            Path(argv[argv.index('-o')+1]).write_bytes(b.canonical(response).encode())
            stdout=b.canonical({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}})+'\n'
            return subprocess.CompletedProcess(argv,0,stdout,'')
        with mock.patch.object(b,'executable',return_value='offline-codex'), mock.patch.object(client,'invoke',side_effect=invoke):
            content=client.translate(req,force_slots=True)
        self.assertEqual(observed,['object'])
        self.assertEqual(b.MARKER.findall(json.loads(content)[0]['output']),b.MARKER.findall(b.translation_batch(req)[2][0]['input']))


if __name__=='__main__':unittest.main()
