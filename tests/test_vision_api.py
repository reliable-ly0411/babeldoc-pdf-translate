"""Loopback HTTP protocol fixtures, not claims about a running local LLM."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import unittest
from unittest.mock import patch
import httpx
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import visual_review as v
import pdf_translate as translate
from model_endpoints import validate_api_provider
from vision_backends import CompatibleVision

PROBE={'issues':[{'region_id':'','category':'layout','severity':'minor','reason':'A1B2C3D4','replacement':''}]}
ISSUE={'issues':[{'region_id':'block_0','category':'missing_translation','severity':'major',
                  'reason':'Untranslated text.','replacement':'温度较低，电压为5伏。'}]}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for name in ('source','translated'):
            with pymupdf.open() as doc:
                doc.new_page(width=500,height=300).insert_text((30,60),
                    'The temperature is cold and the voltage is 5 volts.',fontsize=14)
                doc.save(self.root/(name+'.pdf'))
        self.image=self.root/'image.png'
        with pymupdf.open(self.root/'source.pdf') as doc:doc[0].get_pixmap().save(self.image)

    def tearDown(self):self.tmp.cleanup()

    def provider(self,**changes):
        return validate_api_provider({'type':'openai','base_url':'http://127.0.0.1:8080/v1',
            'model':'fixture-local-vision','auth':'none','vision':True,**changes},self.root,vision=True)

    def cfg(self,provider,output='review'):
        p=self.root/'job.json'
        v.save_json(p,{'source':'source.pdf','translated':'translated.pdf','output':output,
                      'provider':provider,'repair':True,'limits':{'max_model_calls':4}})
        return v.load_config(p)

    def test_actual_loopback_images_repair_and_followup_without_credentials(self):
        replies=[PROBE,ISSUE,{'issues':[]}];captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((self.path,request,self.headers.get('Authorization')))
                reply={'choices':[{'message':{'content':json.dumps(replies.pop(0))},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':13,'completion_tokens':7,'total_tokens':20,'prompt_tokens_details':{'cached_tokens':4}}}
                body=json.dumps(reply).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            cfg=self.cfg(self.provider(base_url=f'http://127.0.0.1:{server.server_port}/v1'))
            with patch.object(v.secrets,'token_hex',return_value='a1b2c3d4'):
                report=v.run(cfg)
        finally:
            server.shutdown();server.server_close();thread.join()
        self.assertEqual(report['status'],'model_screened')
        self.assertEqual(report['model_calls'],3)
        self.assertTrue(report['vision_capability_verified'])
        self.assertEqual([len(x[1]['messages'][0]['content'])-1 for x in captured],[1,2,2])
        for path,request,key in captured:
            self.assertEqual(path,'/v1/chat/completions');self.assertIsNone(key)
            self.assertEqual(request['model'],'fixture-local-vision')
            self.assertNotIn('tools',request)
            for part in request['messages'][0]['content'][1:]:
                self.assertTrue(base64.b64decode(part['image_url']['url'].split(',',1)[1]).startswith(b'\x89PNG'))
        self.assertNotIn('A1B2C3D4',captured[0][1]['messages'][0]['content'][0]['text'])
        self.assertEqual(report['requests'][1]['native_usage']['prompt_tokens_details_cached_tokens'],4)
        with pymupdf.open(cfg['output']/'best.mono.pdf') as doc:self.assertIn('温度',doc[0].get_text())

    def test_incompatible_or_redirecting_endpoint_is_not_retried_or_upgraded(self):
        for status in (400,401,429,307):
            calls=[]
            def handler(request):
                calls.append(json.loads(request.content))
                return httpx.Response(status,headers={'Location':'https://example.invalid/steal'},text='test error')
            client=CompatibleVision(self.provider(),v.SCHEMA,httpx.MockTransport(handler))
            with self.subTest(status=status),self.assertRaisesRegex(v.bridge.BridgeError,'VISION_HTTP_'+str(status)):
                client.inspect('Review',[self.image],5)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['model'],'fixture-local-vision')

    def test_schema_modes_are_explicit_and_tools_are_rejected(self):
        for mode in ('json_schema','json_object','none'):
            captured=[]
            def handler(request):
                captured.append(json.loads(request.content))
                return httpx.Response(200,json={'choices':[{'message':{'content':'{"issues":[]}'},'finish_reason':'stop'}]})
            client=CompatibleVision(self.provider(response_format=mode,token_limit_field='max_completion_tokens'),v.SCHEMA,httpx.MockTransport(handler))
            self.assertEqual(client.inspect('Review',[self.image],5)[0],{'issues':[]})
            self.assertEqual(captured[0].get('response_format',{}).get('type'),None if mode=='none' else mode)
            self.assertEqual(captured[0]['max_completion_tokens'],8192)
            self.assertNotIn('max_tokens',captured[0])
        def tool(request):
            return httpx.Response(200,json={'choices':[{'message':{'content':'{}','tool_calls':[{'id':'bad'}]}}]})
        with self.assertRaisesRegex(v.bridge.BridgeError,'UNEXPECTED_TOOL_USE'):
            CompatibleVision(self.provider(),v.SCHEMA,httpx.MockTransport(tool)).inspect('Review',[self.image],5)

    def test_credential_is_header_only_and_no_auth_is_loopback_only(self):
        with self.assertRaises(ValueError):self.provider(base_url='https://example.com/v1')
        with self.assertRaises(ValueError):self.provider(vision=False)
        with self.assertRaises(ValueError):self.provider(response_format=[])
        with self.assertRaises(ValueError):self.provider(token_limit_field={})
        captured=[]
        def handler(request):
            captured.append(request)
            return httpx.Response(200,json={'choices':[{'message':{'content':'{"issues":[]}'}}]})
        provider=self.provider(auth='env',api_key_env='PDF_TEST_ONLY_TOKEN')
        with patch.dict(os.environ,{'PDF_TEST_ONLY_TOKEN':'test-only-not-a-credential'}):
            client=CompatibleVision(provider,v.SCHEMA,httpx.MockTransport(handler))
            self.assertNotIn('test-only',json.dumps(client.doctor()))
            client.inspect('Review',[self.image],5)
        self.assertEqual(captured[0].headers['authorization'],'Bearer test-only-not-a-credential')
        self.assertNotIn(b'test-only-not-a-credential',captured[0].content)

    def test_prose_plan_schema_is_per_call_and_does_not_change_page_review(self):
        schemas=[]
        def handler(request):
            schemas.append(json.loads(request.content)['response_format']['json_schema']['schema'])
            return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
        client=CompatibleVision(self.provider(),v.SCHEMA,httpx.MockTransport(handler))
        custom={'type':'object','properties':{'slot_0':{'type':'string'}},'required':['slot_0'],'additionalProperties':False}
        client.inspect('Plan',[self.image],5,schema=custom)
        client.inspect('Review',[self.image],5)
        self.assertEqual(schemas,[custom,v.SCHEMA])

    def test_existing_translation_api_and_explicit_local_no_auth_are_supported(self):
        for provider in ({'base_url':'https://example.com/v1','model':'text-model','api_key_env':'PDF_TOKEN'},
                         {'type':'openai','base_url':'http://localhost:11434/v1','model':'local-text','auth':'none'}):
            path=self.root/'translation.json'
            v.save_json(path,{'input':'source.pdf','output':'translation','target_language':'zh-CN','provider':provider})
            job,_,_,argv=translate.prepare(path)
            self.assertEqual(job['provider']['type'],'openai')
            self.assertIn(provider['model'],argv)


if __name__=='__main__':unittest.main()
