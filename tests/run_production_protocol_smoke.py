"""Real BabelDOC + local HTTP protocol fixtures. No actual LLM or inference fee.

Requires generated create_fixtures.py assets and the installed engine/fonts.
The service replies are deterministic fixtures, not a local-model acceptance.
"""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import pdf_pipeline as pipeline
import visual_review as visual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixtures',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--engine',required=True)
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=args.fixtures.resolve()/'technical.pdf'
    translations=json.loads((ROOT/'tests/fixtures/translations.json').read_text(encoding='utf-8'))
    calls=[];errors=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                parts=request['messages'][-1]['content'];model=request['model']
                if model=='fixture-text':
                    assert self.headers.get('Authorization')=='Bearer local-no-auth'
                    rows=json.loads(parts.split('## Here is the input:')[-1])
                    value=[{'id':r['id'],'output':translations[r['input']]} for r in rows]
                    calls.append({'role':'translation','model':model,'rows':len(rows)})
                else:
                    assert model=='fixture-vision' and self.headers.get('Authorization') is None
                    images=len(parts)-1
                    value={'issues':[]} if images==2 else {'issues':[{'region_id':'','category':'layout',
                        'severity':'minor','reason':'ABCDEF12','replacement':''}]}
                    calls.append({'role':'vision','model':model,'images':images})
                payload={'choices':[{'message':{'content':json.dumps(value,ensure_ascii=False)},'finish_reason':'stop'}],
                         'usage':{'prompt_tokens':0,'completion_tokens':0}}
                status=200
            except Exception as error:
                errors.append(type(error).__name__);status=400;payload={'error':'FIXTURE_REQUEST_REJECTED'}
            data=json.dumps(payload).encode()
            self.send_response(status);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    endpoint=f'http://127.0.0.1:{server.server_port}/v1'
    visual.save_json(out/'translation.json',{'input':str(source),'output':'translation','source_language':'en',
        'target_language':'zh-CN','outputs':'both','watermark':'no_watermark','auto_terms':False,
        'ignore_cache':True,'translate_tables':True,'provider':{'type':'openai','base_url':endpoint,'model':'fixture-text','auth':'none'}})
    visual.save_json(out/'pipeline.json',{'translation_job':'translation.json','output':'pipeline',
        'review':{'provider':{'type':'openai','base_url':endpoint,'model':'fixture-vision','auth':'none','vision':True,
                             'retries':0,'response_format':'json_object','max_model_calls':4},
                  'repair':True,'limits':{'max_rounds':1,'max_model_calls':4}}})
    try:
        with patch.object(visual.secrets,'token_hex',return_value='abcdef12'):
            result=pipeline.run(out/'pipeline.json',args.engine,execute=True)
        with pymupdf.open(out/'pipeline/best.mono.pdf') as doc:
            pages=len(doc)
            text=''.join(p.get_text() for p in doc)
        summary={'kind':'Deterministic protocol fixture with real BabelDOC; no local LLM quality claim',
                 'actual_model_inference_calls':0,'status':result['status'],'pages':pages,'cjk_present':'控制' in text,
                 'vision_calls':result.get('model_calls'),'requests':calls,'errors':errors}
        visual.save_json(out/'protocol-summary.json',summary)
        print(json.dumps(summary,ensure_ascii=False))
        assert result['status']=='model_screened' and pages==3 and summary['cjk_present'] and not errors
        assert sum(r['role']=='vision' for r in calls)==4
    finally:
        server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
