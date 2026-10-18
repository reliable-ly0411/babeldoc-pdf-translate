"""Rendered synthetic PDFs and fake review replies; no paid inference."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf as fitz
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as b
import visual_review as v


ISSUE = {'region_id': 'block_0', 'category': 'missing_translation', 'severity': 'major',
         'reason': 'The paragraph is still English.', 'replacement': '温度较低，电压为5伏。'}


class FakeVision:
    version = 'fixture-1'
    def __init__(self, replies):
        self.replies = copy.deepcopy(replies)
        self.calls = 0
    def doctor(self):
        return {'ready': True, 'native_version': self.version}
    def inspect(self, prompt, images, timeout):
        if len(images)==1:
            self.calls+=1
            return {'issues':[{'region_id':'','category':'layout','severity':'minor','reason':'A1B2C3D4','replacement':''}]},{'input_tokens':12}
        assert len(images) == 2 and all(path.is_file() for path in images)
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10}


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.probe_nonce=patch.object(v.secrets,'token_hex',return_value='a1b2c3d4')
        self.probe_nonce.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for label in ('source', 'translated'):
            with fitz.open() as doc:
                doc.new_page(width=500, height=300).insert_text((30, 60),
                    'The temperature is cold and the voltage is 5 volts.', fontsize=14)
                doc.new_page(width=500, height=300).insert_text((30, 60), 'Unchanged second page.', fontsize=14)
                doc.save(self.root / (label + '.pdf'))
        self.config = {'source': 'source.pdf', 'translated': 'translated.pdf', 'output': 'out',
                       'provider': {'type': 'codex', 'model': 'fixture-vision', 'vision':True, 'retries': 0},
                       'pages': [1], 'repair': True, 'limits': {'max_model_calls': 4}}

    def tearDown(self):
        self.probe_nonce.stop()
        self.tmp.cleanup()

    def cfg(self, **updates):
        value = {**self.config, **updates}
        path = self.root / 'review.json'
        v.save_json(path, value)
        return v.load_config(path)

    def test_round_trip_repairs_text_and_preserves_other_pixels(self):
        before = (self.root / 'translated.pdf').read_bytes()
        report = v.run(self.cfg(), FakeVision([{'issues': [ISSUE]}, {'issues': []}]))
        self.assertEqual(report['status'], 'sample_model_screened')
        self.assertTrue(report['inputs_unchanged'])
        self.assertEqual(report['model_calls'], 3)
        self.assertIsNone(report['cost_usd'])
        with fitz.open(self.root / 'out/best.mono.pdf') as doc:
            self.assertIn('温度', doc[0].get_text())
            self.assertIn('5', doc[0].get_text())
            self.assertEqual(doc[1].get_text().strip(), 'Unchanged second page.')
        self.assertEqual((self.root / 'translated.pdf').read_bytes(), before)
        self.assertTrue(report['pages'][0]['accepted_repairs'])

    def test_no_followup_budget_means_no_edit(self):
        cfg = self.cfg(limits={'max_model_calls': 2})
        report = v.run(cfg, FakeVision([{'issues': [ISSUE]}]))
        self.assertEqual(report['status'], 'budget_exhausted')
        self.assertEqual(report['model_calls'], 2)
        self.assertEqual((cfg['output'] / 'best.mono.pdf').read_bytes(), cfg['translated'].read_bytes())

    def test_no_improvement_keeps_previous_pdf(self):
        cfg = self.cfg()
        reply = {'issues': [ISSUE]}
        report = v.run(cfg, FakeVision([reply, reply]))
        self.assertEqual(report['status'], 'sample_needs_manual_review')
        self.assertFalse(report['pages'][0]['attempts'][0]['accepted'])
        self.assertEqual((cfg['output'] / 'best.mono.pdf').read_bytes(), cfg['translated'].read_bytes())

    def test_edit_limit_applies_across_both_rounds(self):
        cfg=self.cfg(limits={'max_model_calls':5,'max_repairs_per_page':1})
        report=v.run(cfg,FakeVision([{'issues':[ISSUE,ISSUE]},{'issues':[ISSUE]}]))
        self.assertEqual(report['model_calls'],3)
        self.assertEqual(len(report['pages'][0]['accepted_repairs']),1)
        self.assertEqual(report['pages'][0]['attempts'][1]['status'],'repair_region_limit')

    def test_changed_numbers_formulas_graphics_and_rotated_text_refused(self):
        with fitz.open(self.root / 'translated.pdf') as doc:
            page = doc[0]
            region = v.regions(page)[0]
            self.assertTrue(v.repairable(page, region, ISSUE))
            for replacement in ('电压为6伏。', '电压为5伏 {v1}', '[已省略] 5'):
                self.assertFalse(v.repairable(page, region, {**ISSUE, 'replacement': replacement}))
            self.assertFalse(v.repairable(page, region, {**ISSUE, 'category': 'formula'}))
            self.assertFalse(v.repairable(page, {**region, 'horizontal': False}, ISSUE))
            page.draw_line((10, 55), (480, 55))
            self.assertFalse(v.repairable(page, region, ISSUE))

    def test_invalid_and_unknown_model_regions_fail_closed(self):
        for reply in ({'issues': [{**ISSUE, 'region_id': '../../outside'}]},
                      {'issues': [{**ISSUE, 'bbox': [0, 0, 500, 300]}]},
                      {'issues': [{**ISSUE, 'severity': 'pass'}]}):
            with self.assertRaises(ValueError):
                v.checked_review(reply, [{'id': 'block_0'}])

    def test_new_serious_category_is_a_regression(self):
        self.assertFalse(v.improved({'issues': [{**ISSUE, 'severity': 'critical'}]},
            {'issues': [{**ISSUE, 'category': 'formula', 'severity': 'major'}]}))

    def test_page_cache_replay_spends_only_fresh_probe_and_preserves_pixels(self):
        provider = {**self.config['provider'], 'cache_dir': 'cache'}
        first = v.run(self.cfg(provider=provider), FakeVision([{'issues': [ISSUE]}, {'issues': []}]))
        fake = FakeVision([])
        second = v.run(self.cfg(provider=provider, output='repeat'), fake)
        self.assertEqual(first['status'], second['status'])
        self.assertEqual(second['cache_hits'], 2)
        self.assertEqual(second['model_calls'], 1)  # Fresh image capability probe only.
        self.assertEqual(fake.calls, 1)
        self.assertTrue(v.regression_check(self.root / 'out/best.mono.pdf', self.root / 'repeat/best.mono.pdf', 1, []))

    def test_failed_native_attempt_is_charged_and_not_retried(self):
        report = v.run(self.cfg(), FakeVision([b.BridgeError('QUOTA')]))
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['model_calls'], 2)
        self.assertEqual(report['requests'][1]['error_code'], 'QUOTA')
        self.assertIsNone(report['requests'][1]['native_usage'])

    def test_second_page_mutation_is_detected(self):
        changed = self.root / 'changed.pdf'
        with fitz.open(self.root / 'translated.pdf') as doc:
            doc[1].insert_text((30, 100), 'Unexpected mutation')
            doc.save(changed)
        self.assertFalse(v.regression_check(self.root / 'translated.pdf', changed, 1, [[0, 0, 500, 300]]))

    def test_invalid_config_and_in_place_output_refused(self):
        for changes in ({'output': '.'}, {'pages': [1, 1]}, {'pages': [True]}, {'pages': [{}]},
                        {'provider': {'type': 'codex', 'model': 'gpt-6-astra', 'retries': 1}},
                        {'limits': {'max_rounds': 3}}, {'shell': 'never'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.cfg(**changes)

    def test_provider_call_budget_is_also_honored(self):
        cfg = self.cfg(provider={**self.config['provider'], 'max_model_calls': 1})
        self.assertEqual(cfg['limits']['max_model_calls'], 1)

    def test_model_which_ignores_images_fails_before_document_review(self):
        fake=FakeVision([])
        fake.inspect=lambda prompt,images,timeout:({'issues':[]},{'input_tokens':12})
        report=v.run(self.cfg(),fake)
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['error_code'],'VISION_CAPABILITY_PROBE_FAILED')
        self.assertEqual(report['model_calls'],1)
        self.assertEqual(report['pages'],[])
        self.assertFalse(report['requests'][0]['verified'])

    def test_vision_declaration_is_required_and_false_is_refused(self):
        for value in (False,None):
            provider={**self.config['provider'],'vision':value}
            with self.assertRaisesRegex(ValueError,'vision=true'):
                self.cfg(provider=provider)

    def test_native_cli_attaches_images_with_tools_disabled(self):
        native = v.NativeVision(b.validate_provider({'type': 'codex', 'model': 'gpt-6-astra',
            'reasoning_effort':'max','timeout_seconds': 5,'retries':0},self.root))
        def invoke(argv, prompt='', **kwargs):
            self.assertEqual(argv.count('--image'), 2)
            self.assertIn('read-only', argv)
            self.assertIn('features.shell_tool=false', argv)
            self.assertIn('features.multi_agent=false', argv)
            self.assertIn('model_reasoning_effort="max"', argv)
            Path(argv[argv.index('-o') + 1]).write_text('{"issues": []}', encoding='utf-8')
            return subprocess.CompletedProcess(argv, 0, '{"type":"turn.completed","usage":{"input_tokens":12}}', '')
        with patch.object(native.native, 'invoke', side_effect=invoke), patch.object(b, 'executable', return_value='fixture'):
            reply, usage = native.inspect('Review only.', [self.root / 'source.pdf', self.root / 'translated.pdf'], 5)
        self.assertEqual(reply, {'issues': []})
        self.assertEqual(usage, {'input_tokens': 12})


if __name__ == '__main__':
    unittest.main()
