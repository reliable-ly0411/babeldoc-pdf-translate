"""Cross-branch regression checks for prose masking and omission refusal."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as b


class PortTests(unittest.TestCase):
    def test_author_names_and_inline_prose_are_translatable(self):
        for source in ('Daya Guo{v1}Dejian Yang{v2}Haowei Zhang{v3}',
                       'open{v1}loop{v2}gain', 'takes{v1} milliseconds'):
            self.assertFalse(b.CODE.search(source))
        self.assertTrue(b.CODE.search('DataRate = 3'))

    def test_omission_notices_and_reordered_controls_are_refused(self):
        source = 'voltage {v1} and current {v2}'
        request = {'messages': [{'role': 'user', 'content': '## Here is the input:\n' + json.dumps([{'id': 1, 'input': source}])}]}
        for output in ('[已省略] {v1} {v2}', '电压 {v2} 电流 {v1}'):
            with self.assertRaises(b.BridgeError):
                b.checked_content(json.dumps([{'id': 1, 'output': output}]), request)

    def test_private_diagnostic_is_atomic_on_windows_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'private'
            b.save_failure({'diagnostics_dir': str(folder)}, {'messages': []}, 'rejected reply', 'INVALID_TEXT_SLOTS')
            files = list(folder.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text(encoding='utf-8'))['error'], 'INVALID_TEXT_SLOTS')

    def test_real_r1_mmlu_omission_is_refused_and_literal_names_are_restored(self):
        source = ("<style id='1'>We evaluate our models on MMLU</style>{v3}"
                  "<style id='4'>MMLU-Redux</style>{v6}<style id='7'>MMLU-Pro</style>{v9}")
        request = {'messages': [{'role': 'user', 'content': '## Here is the input:\n' + json.dumps([{'id': 1, 'input': source}])}]}
        omission = source.replace('We evaluate our models on MMLU', '我们在以下基准上评估模型')
        names = ['MMLU', 'MMLU-Redux', 'MMLU-Pro']
        with self.assertRaisesRegex(b.BridgeError, 'PROTECTED_TEXT_CHANGED'):
            b.checked_content(json.dumps([{'id': 1, 'output': omission}]), request, names)
        masked, protected = b.mask_code(request, names)
        self.assertEqual(set(protected['1'].values()), {'MMLU', 'MMLU-Redux', 'MMLU-Pro'})
        _, plan = b.slot_request(masked)
        reply = b.restore_slots(json.dumps({'rows': {'row_0': {'slot_0': '我们评估模型所用的基准有'}}}), plan)
        restored = b.restore_code(reply, request, protected)
        b.checked_content(restored, request, names)
        self.assertEqual(json.loads(restored)[0]['output'].count('MMLU'), 3)

    def test_identifier_configuration_is_explicit_and_never_freezes_headings(self):
        for value in ('MMLU', [True], ['MMLU', 'MMLU'], ['invalid\nname'], ['<style>']):
            with self.assertRaises(ValueError):
                b.validate_provider({'type':'codex','protected_identifiers':value}, Path.cwd())
        request = {'messages':[{'role':'user','content':'## Here is the input:\n'+json.dumps([{'id':1,'input':'TABLE{v1}'}])}]}
        _, protected = b.mask_code(request)
        self.assertFalse(protected)

    def test_identifier_configuration_invalidates_only_affected_checkpoints(self):
        source = "We evaluate MMLU{v1}, MMLU-Redux{v2}, MMLU-Pro{v3}"
        request = {'messages':[{'role':'user','content':'## Here is the input:\n'+json.dumps([{'id':1,'input':source}])}], 'response_format':None}
        class Fake:
            version = 'fixture-1'
            def __init__(self, omit=False): self.calls, self.omit = 0, omit
            def doctor(self): return {'native_version':self.version,'ready':True}
            def translate(self, request):
                self.calls += 1
                rows = b.translation_batch(request)[2]
                return json.dumps([{'id':r['id'],'output':r['input'].replace('We evaluate MMLU','我们评估') if self.omit else r['input']} for r in rows])
        with tempfile.TemporaryDirectory() as tmp:
            provider = {'type':'codex','retries':0,'cache_dir':tmp}
            old = Fake(omit=True)
            with b.ChatBridge(provider, old) as bridge:
                bridge.complete(request)  # Reproduce the formerly accepted semantic omission.
            configured = {**provider,'protected_identifiers':['MMLU','MMLU-Redux','MMLU-Pro']}
            new = Fake()
            with b.ChatBridge(configured, new) as bridge:
                self.assertEqual(json.loads(bridge.complete(request))[0]['output'].count('MMLU'),3)
            self.assertEqual(new.calls,1)
            replay = Fake()
            with b.ChatBridge(configured,replay) as bridge:
                bridge.complete(request)
            self.assertEqual(replay.calls,0)


if __name__ == '__main__':
    unittest.main()
