"""L1Quad failure reported by independent 3a12dd8 acceptance; no guard removal.

Includes the reported prefix and exact row0 from both captured failure replies.
Original diagnostic hashes are retained without private paths or cached prompts.
"""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import chat_bridge as b

SOURCE="<style id='1'>Remark 2: </style>The implementation of the {v3}Quad controller is discussed here."


def request(source=SOURCE):
    return {'messages':[{'role':'user','content':'Translate English to Chinese.\n## Here is the input:\n'+
                         json.dumps([{'id':0,'input':source}])}]}


class FragmentTests(unittest.TestCase):
    def test_both_actual_independent_failure_replies_remain_rejected(self):
        data=json.loads((Path(__file__).parent/'fixtures/l1quad-fragment-failure.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['bad_outputs']),2)
        for output in data['bad_outputs']:
            with self.subTest(output=output),self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps([{'id':0,'output':output}]),request(data['source']),['L1Quad'])
            with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps([{'id':0,'output':output}]),request(data['source']),['L1Quad'],paragraphs=True)

    def test_added_full_name_still_rejected_with_original_marker_present(self):
        bad=SOURCE.replace('The implementation of the','L1Quad 的实现涉及')
        with self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
            b.checked_content(json.dumps([{'id':0,'output':bad}]),request(),['L1Quad'])

    def test_literal_fragment_translation_and_reordering_also_refused(self):
        for bad in (SOURCE.replace('{v3}Quad','{v3}四元'),SOURCE.replace('{v3}Quad','Quad{v3}')):
            with self.subTest(bad=bad),self.assertRaisesRegex(b.BridgeError,'PROTECTED_TEXT_CHANGED'):
                b.checked_content(json.dumps([{'id':0,'output':bad}]),request(),['L1Quad'])

    def test_program_restores_partial_name_without_repeating_formula_prefix(self):
        original=request()
        masked,protected=b.mask_code(original,['L1Quad'])
        prepared,plan=b.slot_request(masked)
        slots=json.loads(prepared['messages'][0]['content'].split('\n',1)[1])['entries'][0]['text_slots']
        self.assertFalse(any('Quad' in value for value in slots.values()))
        reply={'rows':{'row_0':{key:'备注 2：' if 'Remark' in val else '该控制器的实现如下。' for key,val in slots.items()}}}
        restored=b.restore_code(b.restore_slots(json.dumps(reply),plan),original,protected)
        b.checked_content(restored,original,['L1Quad'])
        out=json.loads(restored)[0]['output']
        self.assertEqual(out.count('{v3}Quad'),1)
        self.assertNotIn('L1Quad',out)

    def test_duplicate_fragments_receive_independent_immutable_tokens(self):
        original=request('{v3}Quad and {v3}Quad')
        masked,protected=b.mask_code(original,['L1Quad'])
        row=b.translation_batch(masked)[2][0]
        self.assertEqual(len(protected['0']),2)
        restored=b.restore_code(json.dumps([{'id':0,'output':row['input']}]),original,protected)
        self.assertEqual(json.loads(restored)[0]['output'],'{v3}Quad and {v3}Quad')

    def test_only_explicit_names_enable_fragment_protection(self):
        self.assertEqual(b.identifier_fragments(SOURCE,[]),[])
        self.assertEqual(b.request_fragments(request(),['OtherName']),[])
        self.assertEqual(b.request_fragments(request(),['L1Quad']),['{v3}Quad'])


if __name__=='__main__':unittest.main()
