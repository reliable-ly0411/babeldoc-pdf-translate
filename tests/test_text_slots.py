"""PDF markup stays immutable even when model replies lose/invent markup."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as bridge


def request(rows):
    return {'messages': [{'role': 'user', 'content':
            'Translate into zh-CN.\n## Here is the input:\n' + json.dumps(rows)}], 'response_format': None}


class SlotTests(unittest.TestCase):
    def test_formula_styles_and_whitespace_are_restored_by_program(self):
        original = " Question: <style id='2'>Find</style> {v1} and {v1}. "
        r = request([{'id': 4, 'input': original}])
        transformed, plan = bridge.slot_request(r)
        self.assertEqual(r['messages'][0]['content'], request([{'id': 4, 'input': original}])['messages'][0]['content'])
        self.assertEqual(transformed['response_format'], {'type': 'json_object'})
        reply = json.dumps({'rows': [{'id': 4, 'texts': ['问题：', '求', '和', '。']}]})
        restored = bridge.restore_slots(reply, plan)
        self.assertEqual(json.loads(restored), [{'id': 4, 'output': " 问题： <style id='2'>求</style> {v1} 和 {v1}。 "}])
        bridge.checked_content(restored, r)

    def test_plain_short_rows_require_complete_nonempty_translations(self):
        r = request([{'id': 'PROMPT', 'input': 'PROMPT'}, {'id': 'eval', 'input': 'Evaluation'}])
        _, plan = bridge.slot_request(r)
        for rows in [[{'id': 'PROMPT', 'texts': ['提示']}],
                     [{'id': 'PROMPT', 'texts': ['提示']}, {'id': 'eval', 'texts': ['']}]]:
            with self.subTest(rows=rows), self.assertRaisesRegex(bridge.BridgeError, 'INVALID_TEXT_SLOTS'):
                bridge.restore_slots(json.dumps({'rows': rows}), plan)

    def test_duplicate_coerced_and_unknown_ids_are_rejected(self):
        _, plan = bridge.slot_request(request([{'id': 1, 'input': 'Voltage'}]))
        for rows in [[{'id': '1', 'texts': ['电压']}], [{'id': 2, 'texts': ['电压']}],
                     [{'id': 1, 'texts': ['电压']}, {'id': 1, 'texts': ['电压']}]]:
            with self.subTest(rows=rows), self.assertRaisesRegex(bridge.BridgeError, 'INVALID_TEXT_SLOTS'):
                bridge.restore_slots(json.dumps({'rows': rows}), plan)

    def test_injected_or_broken_markup_and_wrong_slot_counts_fail(self):
        _, plan = bridge.slot_request(request([{'id': 1, 'input': 'Use {v1} here'}]))
        for texts in [['使用', '这里', '多余'], ['使用 {v99}', '这里'], ['使用', "{style id='5'>这里"], ['使用']]:
            with self.subTest(texts=texts), self.assertRaisesRegex(bridge.BridgeError, 'INVALID_TEXT_SLOTS'):
                bridge.restore_slots(json.dumps({'rows': [{'id': 1, 'texts': texts}]}), plan)

    def test_code_and_marker_only_rows_preserve_exact_bytes(self):
        r = request([{'id': 3, 'input': 'Configuration: gain=2.5; sample_rate=100; mode=TEST'},
                     {'id': 7, 'input': '{v1}\n{v2}'}])
        masked, protected = bridge.mask_code(r)
        _, plan = bridge.slot_request(masked)
        reply = json.dumps({'rows': [{'id': 7, 'texts': []}, {'id': 3, 'texts': ['配置：']}]})
        restored = bridge.restore_code(bridge.restore_slots(reply, plan), r, protected)
        self.assertEqual(json.loads(restored)[0]['output'], '配置： gain=2.5; sample_rate=100; mode=TEST')
        self.assertEqual(json.loads(restored)[1]['output'], '{v1}\n{v2}')
        bridge.checked_content(restored, r)

    def test_extra_formula_tokens_cannot_pass_legacy_validation(self):
        r = request([{'id': 1, 'input': 'Use {v1} here'}])
        with self.assertRaisesRegex(bridge.BridgeError, 'PROTECTED_TEXT_CHANGED'):
            bridge.checked_content(json.dumps([{'id': 1, 'output': '使用 {v1} 和 {v999}'}]), r)

    def test_nonbatch_requests_keep_their_original_contract(self):
        r = {'messages': [{'role': 'user', 'content': 'Extract a glossary'}], 'response_format': {'type': 'json_object'}}
        transformed, plan = bridge.slot_request(r)
        self.assertEqual(transformed, r)
        self.assertIsNone(plan)
        self.assertEqual(bridge.restore_slots('{"terms":[]}', plan), '{"terms":[]}')

    def test_real_r1_decimal_footnote_tail_is_immutable(self):
        source = "Numbers in bold denote that the performance is statistically significant (<style id='1'>t</style>-test with <style id='3'>P</style> {v5}.01)."
        r = request([{'id': 0, 'input': source}])
        transformed, plan = bridge.slot_request(r)
        self.assertEqual(plan[0]['text_count'], 4)
        self.assertTrue(bridge.has_numeric_fragment(r))
        reply = {'rows': {'row_0': {'slot_0': '粗体数字表示性能具有统计显著性（',
                                  'slot_1': 't', 'slot_2': '检验，', 'slot_3': 'P'}}}
        restored = json.loads(bridge.restore_slots(json.dumps(reply), plan))[0]['output']
        self.assertTrue(restored.endswith("<style id='3'>P</style> {v5}.01)."))
        self.assertFalse(bridge.has_numeric_fragment(request([{'id': 0,'input': 'Voltage is 12.5 V'}])))

    def test_invalid_reasoning_options_fail_during_validation(self):
        for value in [True, [], 'ultra']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.validate_provider({'type': 'codex', 'reasoning_effort': value}, Path('.'))

    def test_real_r1_failure_is_complete_json_but_merges_slots(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/r1-slot-failure.json').read_text(encoding='utf-8'))
        r = request(fixture['rows'])
        _, plan = bridge.slot_request(r)
        self.assertEqual([row['text_count'] for row in plan], [2, 3])
        self.assertEqual([len(row['texts']) for row in fixture['rejected_reply']['rows']], [2, 2])
        with self.assertRaisesRegex(bridge.BridgeError, 'INVALID_TEXT_SLOTS'):
            bridge.restore_slots(json.dumps(fixture['rejected_reply']), plan)
        schema = bridge.slot_schema(plan)
        required = schema['properties']['rows']['properties']['row_1']['required']
        self.assertEqual(required, ['slot_0', 'slot_1', 'slot_2'])

    def test_named_schema_restores_ids_and_each_original_formula_position(self):
        r = request([{'id': 'x', 'input': 'Before {v3} after'}, {'id': 7, 'input': '{v2}'}])
        _, plan = bridge.slot_request(r)
        reply = {'rows': {'row_0': {'slot_0': '之前', 'slot_1': '之后'}}}
        restored = bridge.restore_slots(json.dumps(reply), plan)
        self.assertEqual(json.loads(restored), [{'id': 'x', 'output': '之前 {v3} 之后'}, {'id': 7, 'output': '{v2}'}])
        bridge.checked_content(restored, r)
        del reply['rows']['row_0']['slot_1']
        with self.assertRaisesRegex(bridge.BridgeError, 'INVALID_TEXT_SLOTS'):
            bridge.restore_slots(json.dumps(reply), plan)

    def test_real_r1_title_continuation_cannot_be_merged_into_previous_row(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/r1-batch-failure.json').read_text(encoding='utf-8'))
        r = request(fixture['rows'])
        self.assertEqual(len(fixture['rejected_reply']), len(fixture['rows']))
        self.assertEqual(fixture['rejected_reply'][1]['output'], '')
        with self.assertRaisesRegex(bridge.BridgeError, 'INCOMPLETE_TRANSLATION_BATCH'):
            bridge.checked_content(json.dumps(fixture['rejected_reply']), r)


if __name__ == '__main__':
    unittest.main()
