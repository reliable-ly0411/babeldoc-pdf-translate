"""Scope and preservation instructions must survive the review context boundary."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import translation_contract as contracts


class TranslationContractContextTests(unittest.TestCase):
    def contract(self):
        value = contracts.empty([1, 2])
        value.pop('sha256')
        value['prompt'] = ('Translate body prose into Simplified Chinese. '
            'Preserve reference entries and affiliations in their original English.')
        return contracts.seal(value)

    def test_preservation_scope_survives_without_becoming_only_a_style_preference(self):
        value = self.contract()
        before = copy.deepcopy(value)
        header, payload = contracts.context(value).split('\n', 1)
        self.assertEqual(json.loads(payload), before)
        self.assertEqual(value, before)
        self.assertIn('required scope, preservation', header)
        self.assertIn('retain original-language content', header)
        self.assertNotIn('terminology/style only', header)

    def test_preservation_cannot_override_math_schema_or_source_binding(self):
        header = contracts.context(self.contract()).split('\n', 1)[0]
        self.assertIn('never override math fidelity', header)
        self.assertIn('response schema', header)
        self.assertIn('source binding or program guards', header)

    def test_changed_prompt_is_rejected_before_it_can_enter_a_review_request(self):
        value = self.contract()
        value['prompt'] = 'Preserve the entire untranslated document.'
        with self.assertRaisesRegex(ValueError, 'TRANSLATION_CONTRACT_HASH_CHANGED'):
            contracts.context(value)

    def test_changed_page_scope_is_rejected_instead_of_silently_relaxing_coverage(self):
        value = self.contract()
        value['translated_pages'] = [1]
        with self.assertRaisesRegex(ValueError, 'TRANSLATION_CONTRACT_HASH_CHANGED'):
            contracts.context(value)


if __name__ == '__main__':
    unittest.main()
