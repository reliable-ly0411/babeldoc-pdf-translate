"""Opt-in private real-PDF corpus, enabled explicitly in the Windows full run.

The PDFs are not bundled with the public plugin. The manifest contains actual
read-only source paths, hashes and original user role contracts, never verdicts
from models. Expected text-mapping controls and true candidate negatives are fixed.
"""
from collections import Counter
import gzip,hashlib,json,os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import semantic_objects as mapping
import final_audit

@unittest.skipUnless(os.environ.get('BABELDOC_COVERAGE_CORPUS'),'Private real-PDF corpus not configured')
class RealNativeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads(Path(os.environ['BABELDOC_COVERAGE_CORPUS']).read_text(encoding='utf-8'))
        cls.before={row['path']:hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() for row in cls.manifest['inputs']}
        assert cls.before=={row['path']:row['sha256'] for row in cls.manifest['inputs']}
        cls.results={};cls.coverage={}
        for job in cls.manifest['jobs']:
            context=json.loads(Path(job['context_file']).read_text(encoding='utf-8'))
            contract=json.loads(Path(job['contract_file']).read_text(encoding='utf-8'))
            value=mapping.build(job['source'],job['mono'],job['pages'],context=context,translation_contract=contract)
            cls.coverage[job['id']]=value
            for page in value['pages']:cls.results[job['id']+'-p%02d'%page['page']]=page
        if os.environ.get('BABELDOC_COVERAGE_OUTPUT'):
            output=Path(os.environ['BABELDOC_COVERAGE_OUTPUT']);output.mkdir(exist_ok=False)
            for name,value in cls.coverage.items():
                with gzip.GzipFile(filename=str(output/(name+'-coverage.private.json.gz')),mode='wb',mtime=0) as stream:
                    stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
            rows=[{'id':key,'coverage_complete':p['coverage_complete'],'native_accounting_complete':p['native_accounting_complete'],
                'text_mapping_complete':p['text_mapping_complete'],
                'paired_visible_coverage_complete':p['paired_visible_coverage_complete'],
                'semantic_units':sum(u['kind']=='semantic' for u in p['units']),
                'errors_by_code':dict(Counter(e['code'] for e in p['errors'])),'errors':p['errors'],
                'engine_errors':None if p['engine_source'] is None else len(p['engine_source']['errors']),
                'source_counts':p['source_native_ledger']['counts'],'target_counts':p['target_native_ledger']['counts'],
                'source_vectors':len(p['source_native_ledger']['vector_paths']),'target_vectors':len(p['target_native_ledger']['vector_paths'])}
                for key,p in cls.results.items()]
            (output/'SUMMARY.json').write_bytes((json.dumps({'new_external_model_calls':0,'pages':rows},ensure_ascii=False,indent=2)+'\n').encode())

    def test_text_mapping_controls_do_not_hide_unclassified_graphics(self):
        self.assertEqual(len(self.results),12)
        self.assertEqual([key for key,p in self.results.items() if p['text_mapping_complete']],['r1-p04','r1-p05'])
        self.assertFalse(any(p['coverage_complete'] for p in self.results.values()))
        for page in self.results.values():
            self.assertIn('UNCLASSIFIED_VECTOR_CONTENT',[e['code'] for e in page['errors']])

    def test_table_11_is_an_expected_candidate_negative(self):
        page=self.results['r1-p02'];self.assertFalse(page['coverage_complete'])
        errors=[e for e in page['errors'] if e['code']=='PROTECTED_MATH_GLYPH_INVENTORY_CHANGED']
        self.assertTrue(any(e['source_only'].get('number:1')==1 and e['target_only'].get('number:11')==1 for e in errors))
        self.assertIn('表11',''.join(''.join(u['target'].split()) for u in page['units']))

    def test_partially_translated_author_name_is_an_expected_candidate_negative(self):
        page=self.results['r1-p06'];self.assertFalse(page['coverage_complete'])
        self.assertIn('RETAINED_SOURCE_CONTENT_NOT_IDENTICAL',[e['code'] for e in page['errors']])
        self.assertIn('温军',''.join(u['target'] for u in page['units']))

    def test_all_native_paints_have_a_disposition_even_on_blocked_pages(self):
        self.assertTrue(all(p['native_accounting_complete'] for p in self.results.values()))
        for page in self.results.values():
            for side in ('source','target'):
                counts=page[side+'_projection']
                self.assertEqual(counts['raw_native_glyphs'],counts['visible_ids']+counts['omitted_role_ids']+counts['nonvisible_and_alias_ids'])
                self.assertEqual(counts['assigned_visible_ids'],counts['visible_ids'])

    def test_actual_source_ir_font_masks_resolve_the_real_font_alias(self):
        page=self.results['r1-p03'];self.assertEqual(page['engine_source']['errors'],[])
        proof=page['engine_source']['actual_source_glyph_mask_font_bindings']
        self.assertGreaterEqual(len(proof),400)
        self.assertTrue(all(len(row['glyph_mask_sha256'])==64 and row['font_program_sha256'] for row in proof))
        self.assertEqual(self.results['l1quad-p01']['engine_source']['errors'],[])

    def test_user_pdfs_and_production_veto_remain_unchanged(self):
        self.assertEqual(self.before,{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in self.before})
        self.assertFalse(final_audit.PROTOCOL_VALIDATED)

if __name__=='__main__':unittest.main()
