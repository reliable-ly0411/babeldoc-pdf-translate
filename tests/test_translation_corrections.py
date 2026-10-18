import copy,hashlib,json,os
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b
import translation_corrections as c


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.source='The functions of {v1} form a basis.'
        self.bad='以{v1}为基底的函数。';self.good='关于{v1}的函数构成一组基。'
        self.rows=[{'id':3,'input':self.source},{'id':4,'input':'Another heading'}]
        self.request={'messages':[{'role':'user','content':'Translate English to Chinese.\n## Here is the input:\n'+b.canonical(self.rows)}]}
        self.content=b.canonical([{'id':3,'output':self.bad},{'id':4,'output':'另一个标题'}])
        self.key='a'*64
        self.data={'version':1,'output_contract':'paragraphs','max_corrected_rows':3,
            'provenance':{'model':'fixture','reasoning_effort':'high','correction_response_sha256':'b'*64,
                'semantic_recheck_sha256':'c'*64,'status':'semantic_screened'},
            'entries':[{'cache_request_sha256':self.key,'base_content_sha256':c.digest(self.content),
                'source_rows_sha256':c.digest(b.canonical(self.rows)),
                'replacements':[{'id':3,'source_sha256':c.digest(self.source),
                    'previous_output_sha256':c.digest(self.bad),'output':self.good}]}]}

    def load(self,root,data=None):
        path=root/'corrections.json';path.write_text(b.canonical(data or self.data),encoding='utf8');os.chmod(path,0o600)
        return c.load(path)

    def test_corrects_only_bound_rows_and_keeps_source_content_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=self.load(Path(tmp));changed,count=c.apply(plan,self.key,self.request,self.content,paragraphs=True)
        self.assertEqual(count,1);self.assertEqual(json.loads(changed)[0]['output'],self.good)
        self.assertEqual(json.loads(changed)[1],json.loads(self.content)[1])
        self.assertEqual(json.loads(self.content)[0]['output'],self.bad)

    def test_changed_source_or_base_response_fails_instead_of_reusing_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=self.load(Path(tmp))
            for request,content in [(self.request,self.content+' '),
                ({'messages':[{'role':'user','content':'Translate.\n## Here is the input:\n'+b.canonical([{'id':3,'input':'Different source'}])}]},self.content)]:
                with self.assertRaisesRegex(ValueError,'BASE_OR_SOURCE_CHANGED'):c.apply(plan,self.key,request,content,paragraphs=True)

    def test_extra_math_and_changed_name_still_fail_current_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=copy.deepcopy(self.data);data['entries'][0]['replacements'][0]['output']='关于{v2}的函数构成基。'
            plan=self.load(Path(tmp),data)
            with self.assertRaises(b.BridgeError):c.apply(plan,self.key,self.request,self.content,paragraphs=True)

    def test_unknown_key_has_no_effect_but_wrong_contract_and_unknown_row_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=self.load(Path(tmp))
            self.assertEqual(c.apply(plan,'d'*64,self.request,self.content,paragraphs=True),(self.content,0))
            with self.assertRaises(ValueError):c.apply(plan,self.key,self.request,self.content,paragraphs=False)
            plan['data']['entries'][0]['replacements'][0]['id']=99
            with self.assertRaisesRegex(ValueError,'UNKNOWN_ROW'):c.apply(plan,self.key,self.request,self.content,paragraphs=True)

    def test_bridge_returns_correction_without_mutating_real_base_cache(self):
        outer=self
        class Client:
            version='fixture'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):return outer.content
        class NoInference(Client):
            def translate(self,request):raise AssertionError('Unexpected new translation')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache'
            provider={'type':'codex','model':'fixture','cache_dir':str(cache),'retries':0,'output_contract':'paragraphs'}
            with b.ChatBridge(provider,Client()) as bridge:self.assertEqual(bridge.complete(self.request),self.content)
            file=next(cache.glob('*.json'));before=file.read_bytes();self.data['entries'][0]['cache_request_sha256']=file.stem
            self.load(root)
            with b.ChatBridge({**provider,'quality_corrections_file':str(root/'corrections.json')},NoInference()) as bridge:
                corrected=bridge.complete(self.request)
                self.assertEqual(bridge.stats['cache_hits'],1)
                self.assertEqual(bridge.stats['corrected_rows'],1)
                self.assertEqual(bridge.stats['live_requests'],0)
                self.assertEqual(json.loads(corrected)[0]['output'],self.good)
                self.assertEqual(bridge.memory[file.stem],self.content)
            self.assertEqual(file.read_bytes(),before)

    def test_extra_fields_and_excess_rows_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=copy.deepcopy(self.data);data['bbox']=[0,0,100,100]
            with self.assertRaises(ValueError):self.load(Path(tmp),data)
            data=copy.deepcopy(self.data);data['max_corrected_rows']=1
            data['entries'][0]['replacements'].append({**data['entries'][0]['replacements'][0],'id':4})
            with self.assertRaisesRegex(ValueError,'ROW_LIMIT'):self.load(Path(tmp),data)


if __name__=='__main__':unittest.main()
