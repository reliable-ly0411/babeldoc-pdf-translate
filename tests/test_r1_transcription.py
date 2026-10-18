"""Real archived raster-transcription regression, distinct from Luna output."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import unicodedata
import pymupdf
from evidence_support import evidence_file
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import repair_r1_regions as repair


class TranscriptionTests(unittest.TestCase):
    def test_prose_redaction_keeps_new_font_resources_readable(self):
        # Reproduces the stale-font-resource failure after redaction/reinsertion.
        with tempfile.TemporaryDirectory() as tmp:
            font = Path(tmp)/'Serif-Regular.ttf'
            font.write_bytes(pymupdf.Font('china-s').buffer)
            font.with_name('Serif-Bold.ttf').write_bytes(font.read_bytes())
            with pymupdf.open() as source, pymupdf.open() as translated:
                sp=source.new_page()
                sp.insert_text((40,40),'conversational thinking process and language consistency.',fontsize=7)
                sp.insert_text((40,60),'Table 1 | An interesting version of DeepSeek-R1-Zero',fontsize=7)
                page=translated.new_page()
                page.insert_text((40,58),'表 1 | DeepSeek-R1-Zero 顿悟时刻',fontname='china-s',fontsize=9)
                page.insert_text((40,303),'。随后 SFT，详见第 2.3.3 节和第 2.4.4 节。',fontname='china-s',fontsize=8.25)
                edits=repair.repair_p3_prose(sp,page,font)
                path=Path(tmp)/'saved.pdf'
                translated.subset_fonts()
                translated.save(path)
            with pymupdf.open(path) as verified:
                text=unicodedata.normalize('NFKC',verified[0].get_text()).replace('\n','')
                self.assertIn('对话式思考过程和语言一致性。随后',text)
                self.assertEqual(text.count('中间版本'),1)
                self.assertIn('2.3.3',text)
                self.assertIn('2.4.4',text)
                self.assertNotIn('Zero 版本',text)
                self.assertEqual(len(edits),2)

    def test_prose_repair_refuses_unreviewed_source(self):
        with pymupdf.open() as source, pymupdf.open() as translated:
            sp=source.new_page();page=translated.new_page()
            sp.insert_text((40,40),'An unrelated source page')
            with self.assertRaisesRegex(ValueError,'Unexpected R1 p3 source'):
                repair.repair_p3_prose(sp,page,Path('unused-Regular.ttf'))

    def test_already_repaired_pdf_cannot_be_overlaid_twice(self):
        with pymupdf.open(evidence_file('benchmarks/r1-linux-2026-10-14/deepseek-r1.zh-CN.sample.pdf')) as doc:
            with self.assertRaisesRegex(ValueError, 'overlays twice'):
                repair.require_unrepaired_input(doc)
    def test_archived_source_transcription_error_is_refused(self):
        original = json.loads(evidence_file('benchmarks/r1-linux-2026-10-14/figure-text.json').read_text(encoding='utf-8'))
        with self.assertRaisesRegex(ValueError, 'least integer'):
            repair.checked_raster_transcription(original)

    def test_reviewed_source_and_translation_polarity_both_required(self):
        corrected = json.loads(evidence_file('benchmarks/windows-stability-2026-10-15/corrected-figure-text.json').read_text(encoding='utf-8'))
        self.assertIn('最小整数', repair.checked_raster_transcription(corrected))
        invalid = copy.deepcopy(corrected)
        row = next(r for r in invalid['rows'] if r['source'].startswith('Let b ≥ 2 be an integer.'))
        row['translation'] = row['translation'].replace('最小整数', '最大整数')
        with self.assertRaisesRegex(ValueError, 'reverses'):
            repair.checked_raster_transcription(invalid)


if __name__ == '__main__':
    unittest.main()
