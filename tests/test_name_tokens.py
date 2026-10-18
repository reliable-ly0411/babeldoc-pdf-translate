"""Names may follow Chinese grammar; actual code/style barriers stay strict."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as b


def request(source):
    return {'messages': [{'role': 'user', 'content':
        'Translate English to Chinese.\n## Here is the input:\n' +
        json.dumps([{'id': 4, 'input': source}])}]}


def prepare(source):
    original = request(source)
    masked, protected = b.mask_code(original, ['Lipschitz', 'L1Quad'])
    transformed, plan = b.paragraph_request(masked, ['Lipschitz', 'L1Quad'])
    return original, protected, transformed, plan


def encode(plan, target):
    for token, value in plan[0]['math_groups'].items():
        target = target.replace(value, token)
    return json.dumps({'rows': {'row_0': target}})


class NameTokenTests(unittest.TestCase):
    def test_name_is_not_a_math_barrier_in_natural_chinese_order(self):
        original, protected, transformed, plan = prepare(
            "<style id='1'>Remark 1: </style>If the Lipschitz constant of {v3} "
            'with respect to the state {v4} is small enough.')
        name = next(iter(protected['4']))
        self.assertTrue(b.NAME_MARKER.fullmatch(name))
        self.assertNotIn(name, json.loads(transformed['messages'][0]['content'].split('\n', 1)[1])['entries'][0]['barrier_tokens'])
        target = "<style id='1'>注1: </style>若 {v3} 关于状态 {v4} 的 " + name + ' 常数足够小。'
        restored = b.restore_code(b.restore_paragraphs(encode(plan, target), plan), original, protected)
        b.checked_content(restored, original, ['Lipschitz'], paragraphs=True)
        self.assertIn('Lipschitz', json.loads(restored)[0]['output'])

    def test_missing_or_repeated_name_and_math_still_fail(self):
        _, protected, _, plan = prepare('If the Lipschitz constant of {v3} with respect to {v4} is small enough.')
        name = next(iter(protected['4']))
        target = '若 {v3} 关于 {v4} 的 ' + name + ' 常数足够小。'
        for bad in (target.replace(name, ''), target + name, target.replace('{v3}', ''), target + '{v3}'):
            with self.subTest(bad=bad), self.assertRaises(b.BridgeError) as raised:
                b.restore_paragraphs(encode(plan, bad), plan)
            self.assertEqual(raised.exception.detail['guard'], 'paragraph_tokens')

    def test_actual_code_barrier_cannot_be_crossed_by_math(self):
        _, protected, _, plan = prepare('The gain=2.5 setting is used with {v1} for this system.')
        code = next(iter(protected['4']))
        self.assertTrue(code.startswith('{pdftranslate_code_'))
        target = '该系统使用 {v1} 和设置 ' + code + '。'
        with self.assertRaises(b.BridgeError) as raised:
            b.restore_paragraphs(encode(plan, target), plan)
        self.assertEqual(raised.exception.detail['guard'], 'opaque_barrier_crossed')
        self.assertEqual(raised.exception.detail['expected'], [code])
        self.assertEqual(raised.exception.detail['actual'], [])

    def test_name_and_math_cannot_cross_style_boundary(self):
        _, protected, _, plan = prepare("<style id='1'>The Lipschitz constant is small.</style> The state {v1} is safe.")
        name = next(iter(protected['4']))
        targets = ["<style id='1'>常数很小。</style>" + name + ' 状态 {v1} 安全。',
                   "<style id='1'>" + name + ' 常数 {v1} 很小。</style>状态安全。']
        for target, guard in zip(targets, ('external_token_order', 'opaque_barrier_crossed')):
            with self.subTest(guard=guard), self.assertRaises(b.BridgeError) as raised:
                b.restore_paragraphs(encode(plan, target), plan)
            self.assertEqual(raised.exception.detail['guard'], guard)

    def test_short_header_keeps_name_math_order(self):
        _, protected, _, plan = prepare('Lipschitz {v1} setting')
        name = next(iter(protected['4']))
        self.assertFalse(plan[0]['math_may_reorder'])
        with self.assertRaises(b.BridgeError) as raised:
            b.restore_paragraphs(encode(plan, '{v1} ' + name + ' 设置'), plan)
        self.assertEqual(raised.exception.detail['guard'], 'short_text_token_order')

    def test_adjacent_name_math_compound_cannot_be_split(self):
        _, protected, _, plan = prepare('The Lipschitz{v1} constant is safe for this system.')
        name = next(iter(protected['4']))
        self.assertIn(name + '{v1}', plan[0]['math_groups'].values())
        with self.assertRaises(b.BridgeError):
            b.restore_paragraphs(encode(plan, name + ' 常数 {v1} 对该系统安全。'), plan)

    def test_split_name_fragment_remains_bound_to_math(self):
        _, protected, _, plan = prepare('The implementation of {v3}Quad controller is stable in this setting.')
        fragment = next(iter(protected['4']))
        self.assertTrue(fragment.startswith('{pdftranslate_code_'))
        self.assertIn('{v3}' + fragment, plan[0]['math_groups'].values())
        with self.assertRaises(b.BridgeError):
            b.restore_paragraphs(encode(plan, '{v3} 实现 ' + fragment + ' 控制器稳定。'), plan)

    def test_actual_rejected_responses_distinguish_missing_math_from_name_order(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/l1quad-name-barrier.json').read_text(encoding='utf8'))
        original, protected, _, plan=prepare(fixture['row']['input'])
        for response in fixture['responses']:
            content=json.dumps({'rows':{'row_0':response['text']}})
            if response['expected']=='missing_math_rejected':
                with self.assertRaises(b.BridgeError) as raised:b.restore_paragraphs(content,plan)
                detail=raised.exception.detail
                self.assertEqual(detail['guard'],'paragraph_tokens')
                self.assertEqual(detail['rows'][0]['missing'],['{pdftranslate_code_e80f755da5b41126}'])
            else:
                restored=b.restore_code(b.restore_paragraphs(content,plan),original,protected)
                b.checked_content(restored,original,['Lipschitz'],paragraphs=True)

    def test_v4_verified_checkpoint_is_reused_unchanged(self):
        original=request('If the Lipschitz constant of {v3} with respect to {v4} is small enough.')
        original['response_format']=None
        content=json.dumps([{'id':4,'output':'若 {v3} 关于 {v4} 的 Lipschitz 常数足够小。'}])
        class NoCalls:
            version='v4-fixture'
            def doctor(self):return {'native_version':self.version}
            def translate(self,request):raise AssertionError('Valid v4 checkpoint must avoid new model calls')
        with tempfile.TemporaryDirectory() as tmp:
            identity={'bridge_version':b.VERSION,'native_version':NoCalls.version,'backend':'codex','model':None,
                'request':original,'reasoning_effort':None,'native_output_contract':'named-paragraphs-schema-4',
                'protected_identifiers':['Lipschitz'],'protected_identifier_revision':1}
            key=hashlib.sha256(b.canonical(identity).encode()).hexdigest()
            record={'request_sha256':key,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'content':content}
            path=Path(tmp,key+'.json');path.write_text(json.dumps(record),encoding='utf8');path.chmod(0o600);before=path.read_bytes()
            with b.ChatBridge({'type':'codex','retries':0,'output_contract':'paragraphs','cache_dir':tmp,
                    'protected_identifiers':['Lipschitz']},NoCalls()) as server:
                self.assertEqual(server.complete(original),content)
                self.assertEqual(server.stats['cache_hits'],1)
                self.assertEqual(server.stats['legacy_cache_hits'],1)
                self.assertEqual(server.stats['attempts'],0)
            self.assertEqual(path.read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
