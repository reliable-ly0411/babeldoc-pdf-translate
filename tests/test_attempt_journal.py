"""An abrupt executor loss must leave durable unknown-usage evidence."""
import json,os
from pathlib import Path
import subprocess,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b


class JournalTests(unittest.TestCase):
    def test_abrupt_process_exit_retains_started_unknown_attempt_without_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);script=path/'crash.py'
            script.write_text('''import os,sys
import chat_bridge as b
class C:
 version='fixture'
 def doctor(self):return {'native_version':self.version}
 def translate(self,request):os._exit(23)
with b.ChatBridge({'type':'codex','retries':0,'diagnostics_dir':sys.argv[1]},C()) as bridge:
 bridge.complete({'messages':[{'role':'user','content':'private document text'}],'response_format':None})
''',encoding='utf8')
            env=os.environ.copy();env['PYTHONPATH']=str(Path(b.__file__).parent)
            result=subprocess.run([sys.executable,str(script),str(path/'diagnostics')],env=env,timeout=10)
            self.assertEqual(result.returncode,23)
            records=list((path/'diagnostics/attempt-journal').glob('*.json'));self.assertEqual(len(records),1)
            raw=records[0].read_text(encoding='utf8');record=json.loads(raw)
            self.assertEqual(record['state'],'started');self.assertIsNone(record['native_usage'])
            self.assertNotIn('private document text',raw)
            self.assertNotIn('Bearer',raw)

    def test_returned_failure_keeps_unknown_usage_and_explicit_error(self):
        class Client:
            version='fixture'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):raise b.BridgeError('QUOTA')
        with tempfile.TemporaryDirectory() as tmp:
            with b.ChatBridge({'type':'codex','retries':0,'diagnostics_dir':tmp},Client()) as bridge:
                with self.assertRaisesRegex(b.BridgeError,'QUOTA'):
                    bridge.complete({'messages':[{'role':'user','content':'fixture'}],'response_format':None})
            record=json.loads(next((Path(tmp)/'attempt-journal').glob('*.json')).read_text(encoding='utf8'))
            self.assertEqual(record['state'],'returned');self.assertEqual(record['error_code'],'QUOTA')
            self.assertIsNone(record['native_usage']);self.assertIsNone(record['cost_usd'])


if __name__=='__main__':unittest.main()
