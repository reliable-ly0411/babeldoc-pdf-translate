import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adapter', ROOT / 'scripts/pdf_translate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        # Not a PDF fixture: prepare/dry run deliberately do not parse its content.
        (self.base / 'source.pdf').write_bytes(b'not-a-real-pdf')
        self.job = {'input': 'source.pdf', 'output': 'out', 'target_language': 'zh-CN',
                    'provider': {'base_url': 'https://provider.invalid/v1',
                                 'model': 'test-model', 'api_key_env': 'TEST_PDF_KEY'}}
        self.path = self.base / 'job.json'
    def tearDown(self):
        self.tmp.cleanup()
    def save(self):
        self.path.write_text(json.dumps(self.job), encoding='utf-8')
    def test_layout_and_relative_paths(self):
        self.job.update(outputs='dual', dual_layout='alternating', pages='2-4', selected_pages_only=True)
        self.save()
        _, source, output, args = m.prepare(self.path)
        self.assertEqual(source, self.base / 'source.pdf')
        self.assertIn('--no-mono', args)
        self.assertIn('--use-alternating-pages-dual', args)
        self.assertIn('--only-include-translated-page', args)
    def test_bad_values(self):
        for field, value in [('workers', True), ('qps', 0), ('pages', '4-2'),
                             ('pages', '0'), ('outputs', 'none'), ('auto_terms', 'false')]:
            with self.subTest(field=field, value=value):
                old = self.job.copy()
                self.job[field] = value
                self.save()
                with self.assertRaises(ValueError): m.prepare(self.path)
                self.job = old
    def test_unknown_and_literal_secret(self):
        self.job['invented_option'] = True
        self.save()
        with self.assertRaises(ValueError): m.prepare(self.path)
        del self.job['invented_option']
        self.job['provider']['api_key'] = 'do-not-allow'
        self.save()
        with self.assertRaises(ValueError): m.prepare(self.path)
    def test_glossary_conflicts(self):
        p = self.base / 'terms.csv'
        p.write_text('source,target\nmargin,裕度\nmargin,边距\n', encoding='utf-8')
        with self.assertRaises(ValueError): m.glossary(p)
    def test_unsupported_flags(self):
        self.save()
        with patch.object(m, 'executable', return_value='fake'), patch.object(m, 'probe', return_value=(set(), 'test')):
            with self.assertRaises(ValueError): m.run_job(self.path, 'fake')
    def test_dry_run_never_translates(self):
        self.save()
        _, _, _, args = m.prepare(self.path)
        flags = {x for x in args if x.startswith('--')} | {'--config'}
        with patch.object(m, 'executable', return_value='fake'), patch.object(m, 'probe', return_value=(flags, 'test')), patch.object(m, 'inspect_pdf', return_value={'page_count': 5}), patch.object(m.subprocess, 'run') as child:
            result = m.run_job(self.path, 'fake')
            child.assert_not_called()
        self.assertEqual(result['status'], 'planned')
        self.assertFalse((self.base / 'out').exists())
    def test_execution_manifest_and_secret_cleanup(self):
        self.save()
        _, _, _, args = m.prepare(self.path)
        flags = {x for x in args if x.startswith('--')} | {'--config'}
        secret = 'test-secret-unique'
        configs = []
        def child(argv, **kwargs):
            self.assertNotIn(secret, argv)
            config = Path(argv[argv.index('--config') + 1])
            configs.append(config)
            self.assertIn(secret, config.read_text())
            (self.base / 'out/result.pdf').write_bytes(b'test-output')
            return SimpleNamespace(returncode=0, stdout=secret, stderr='')
        with patch.object(m, 'executable', return_value='fake'), patch.object(m, 'probe', return_value=(flags, 'test')), patch.object(m, 'inspect_pdf', return_value={'page_count': 5}), patch.dict(os.environ, TEST_PDF_KEY=secret), patch.object(m.subprocess, 'run', side_effect=child):
            result = m.run_job(self.path, 'fake', True)
        self.assertEqual(result['status'], 'needs-review')
        self.assertTrue(result['source_unchanged'])
        self.assertFalse(configs[0].exists())
        self.assertNotIn(secret, (self.base / 'out/engine.log').read_text())
        self.assertNotIn(secret, (self.base / 'out/run-manifest.json').read_text())
    def test_real_babeldoc_config_parser(self):
        from babeldoc.main import create_parser
        args = create_parser().parse_args(['--openai'], config_file_contents='[babeldoc]\nopenai-api-key = "dummy"\n')
        self.assertEqual(args.openai_api_key, 'dummy')
    def test_actual_engine_argument_mapping(self):
        from babeldoc.main import create_parser
        self.job.update(outputs='dual', dual_layout='alternating', pages='2-4',
                        selected_pages_only=True, auto_terms=False, translated_first=True,
                        translate_tables=True, save_terms=True, scan_mode='auto', font='serif')
        self.save()
        _, _, _, argv = m.prepare(self.path)
        args = create_parser().parse_args(argv)
        self.assertTrue(args.no_mono)
        self.assertTrue(args.use_alternating_pages_dual)
        self.assertFalse(args.auto_extract_glossary)
        self.assertEqual(args.pages, '2-4')
    def test_page_overflow_rejected_before_execution(self):
        self.job['pages'] = '2-9'
        self.save()
        _, _, _, args = m.prepare(self.path)
        flags = {x for x in args if x.startswith('--')} | {'--config'}
        with patch.object(m, 'executable', return_value='fake'), patch.object(m, 'probe', return_value=(flags, 'test')), patch.object(m, 'inspect_pdf', return_value={'page_count': 5}):
            with self.assertRaisesRegex(ValueError, 'exceeds'):
                m.run_job(self.path, 'fake')

if __name__ == '__main__':
    unittest.main()

