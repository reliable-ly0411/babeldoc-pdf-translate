import json,os
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b
import semantic_review as s


class PairReceiptTests(unittest.TestCase):
    def test_opt_in_records_actual_batch_and_single_source_target_without_prompt(self):
        class Client:
            version='fixture'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):
                batch=b.translation_batch(request)
                return b.canonical([{'id':x['id'],'output':'译文'} for x in batch[2]]) if batch else '单段译文'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);os.chmod(root,0o700);file=root/'pairs.jsonl'
            provider={'type':'codex','retries':0,'translation_pairs_file':str(file)}
            batch={'messages':[{'role':'user','content':'PRIVATE PROMPT\n## Here is the input:\n'+
                b.canonical([{'id':2,'input':'An example heading'}])}]}
            single={'messages':[{'role':'user','content':';; Treat next line as plain text input and translate it into Chinese.\nInput:\n\nAn ordinary label'}]}
            with b.ChatBridge(provider,Client()) as bridge:
                bridge.complete(batch);bridge.complete(single)
            pairs,metadata=s.load_translation_pairs(file)
            self.assertEqual(len(pairs),2)
            self.assertEqual({p['target'] for p in pairs.values()},{'译文','单段译文'})
            self.assertEqual({m['kind'] for m in metadata.values()},{'batch','single'})
            self.assertNotIn('PRIVATE PROMPT',file.read_text(encoding='utf8'))

    def test_incomplete_or_failed_transcript_cannot_be_screened_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'pairs.jsonl'
            for ending in (None,{'type':'end','completed':False,'recorded_pairs':1}):
                rows=[{'type':'start','version':1},{'type':'pair','key':'pair_0','source':'Source','target':'目标'}]
                if ending:rows.append(ending)
                file.write_text('\n'.join(b.canonical(x) for x in rows),encoding='utf8')
                with self.assertRaisesRegex(ValueError,'INCOMPLETE'):s.load_translation_pairs(file)

    def test_existing_receipt_is_not_overwritten(self):
        class Client:
            version='fixture'
            def doctor(self):return {'native_version':self.version}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'pairs.jsonl';file.write_bytes(b'original receipt')
            with self.assertRaisesRegex(b.BridgeError,'FRESH_PRIVATE'):
                with b.ChatBridge({'type':'codex','translation_pairs_file':str(file)},Client()):pass
            self.assertEqual(file.read_bytes(),b'original receipt')


if __name__=='__main__':unittest.main()
