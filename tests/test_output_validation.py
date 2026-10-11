import importlib.util
from pathlib import Path
import tempfile
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('validation_adapter', ROOT / 'scripts/pdf_translate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OutputValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / 'source.pdf'
        with pymupdf.open() as doc:
            for _ in range(3):
                doc.new_page(width=200, height=300)
            doc.save(self.source)
        self.output = self.base / 'out'
        self.output.mkdir()
        self.inspection = m.inspect_pdf(self.source)
        self.job = {'target_language': 'zh-CN', 'outputs': 'mono', 'watermark': 'no_watermark'}

    def tearDown(self):
        self.tmp.cleanup()

    def pdf(self, mode='mono', watermark='no_watermark', pages=3, width=None):
        suffix = '.no_watermark' if watermark == 'no_watermark' else ''
        path = self.output / f'source{suffix}.zh-CN.{mode}.pdf'
        with pymupdf.open() as doc:
            for _ in range(pages):
                doc.new_page(width=width or (400 if mode == 'dual' else 200), height=300)
            doc.save(path)
        return path

    def validate(self):
        return m.validate_outputs(self.job, self.source, self.output, self.inspection)

    def test_valid_variants(self):
        for mode in ('mono', 'dual', 'both'):
            for watermark in ('no_watermark', 'watermarked', 'both'):
                with self.subTest(mode=mode, watermark=watermark):
                    for p in self.output.iterdir():
                        p.unlink()
                    self.job.update(outputs=mode, watermark=watermark)
                    for k in ('mono', 'dual') if mode == 'both' else (mode,):
                        for w in ('watermarked', 'no_watermark') if watermark == 'both' else (watermark,):
                            self.pdf(k, w)
                    self.assertTrue(self.validate()['valid'])

    def test_corrupt_pdf_is_not_reviewable(self):
        p = self.output / 'source.no_watermark.zh-CN.mono.pdf'
        for content in (b'NOT A PDF', b'', b'%PDF-1.7\n%%EOF'):
            with self.subTest(content=content):
                p.write_bytes(content)
                self.assertFalse(self.validate()['valid'])

    def test_missing_requested_watermark_variant_fails(self):
        self.job['watermark'] = 'both'
        self.pdf()
        self.assertFalse(self.validate()['valid'])

    def test_partial_mono_dual_fails(self):
        self.job['outputs'] = 'both'
        self.pdf()
        self.assertFalse(self.validate()['valid'])

    def test_wrong_page_count_or_dimensions_fails(self):
        p = self.pdf(pages=1)
        self.assertFalse(self.validate()['valid'])
        p.unlink()
        self.pdf(width=999)
        self.assertFalse(self.validate()['valid'])

    def test_selected_alternating_counts_unique_physical_pages(self):
        self.job.update(outputs='dual', dual_layout='alternating', pages='3,1,1', selected_pages_only=True)
        self.pdf('dual', pages=4, width=200)
        self.assertTrue(self.validate()['valid'])

    def test_unselected_pages_retained(self):
        self.job.update(pages='1', selected_pages_only=False)
        self.pdf()
        self.assertTrue(self.validate()['valid'])

    def test_encrypted_pdf_fails(self):
        p = self.output / 'source.no_watermark.zh-CN.mono.pdf'
        with pymupdf.open(self.source) as doc:
            doc.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw='test-only', owner_pw='owner-only')
        self.assertFalse(self.validate()['valid'])

    def test_unexpected_artifact_fails(self):
        self.pdf()
        (self.output / 'unexpected.pdf').write_bytes(self.source.read_bytes())
        self.assertFalse(self.validate()['valid'])
