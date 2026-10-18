"""A completed recovered stream still requires schema/fidelity validation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b


class TransportTests(unittest.TestCase):
    def test_recovered_error_before_completion_retains_usage_and_only_safe_metadata(self):
        events=[{'type':'error','message':'stream disconnected private-document-text'},
                {'type':'turn.completed','usage':{'input_tokens':123,'output_tokens':8}}]
        turn,meta=b.native_completion(events)
        self.assertEqual(turn['usage']['input_tokens'],123)
        self.assertEqual(meta['recovered_error_events'][0]['code'],'STREAM_CLOSED')
        self.assertNotIn('private-document-text',json.dumps(meta))
        self.assertEqual(len(meta['recovered_error_events'][0]['event_sha256']),64)

    def test_unknown_fatal_and_post_completion_errors_still_fail_closed(self):
        completed={'type':'turn.completed','usage':{'input_tokens':12}}
        for message,code in [('unknown failure','NATIVE_FAILED'),('401 unauthorized','AUTH'),
                ('usage limit exceeded','QUOTA'),('approval rejected','APPROVAL_REJECTED'),
                ('maximum context length','CONTEXT_LIMIT')]:
            with self.subTest(code=code),self.assertRaises(b.BridgeError) as raised:
                b.native_completion([{'type':'turn.failed','error':message},completed])
            self.assertEqual(raised.exception.code,code)
            self.assertEqual(raised.exception.native_usage,completed['usage'])
        with self.assertRaisesRegex(b.BridgeError,'STREAM_CLOSED'):
            b.native_completion([completed,{'type':'error','message':'stream closed'}])
        with self.assertRaisesRegex(b.BridgeError,'RATE_LIMIT'):
            b.native_completion([{'type':'error','message':'429 rate limit'}])
        with self.assertRaisesRegex(b.BridgeError,'INCOMPLETE_TURN'):b.native_completion([])

    def test_failure_without_response_is_reproducible_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            b.save_failure({'diagnostics_dir':tmp},{'messages':[]},None,'NATIVE_FAILED')
            value=json.loads(next(Path(tmp).glob('*.json')).read_text(encoding='utf8'))
            self.assertIsNone(value['reply'])
            self.assertEqual(value['reply_shape']['json_type'],'absent')


if __name__=='__main__':unittest.main()
