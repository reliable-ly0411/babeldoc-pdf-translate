"""Independent rc14 counterexamples, reproduced with actual synthetic PDFs.

All role calls are forbidden except explicit offline doubles; no source paper
or user PDF is changed. Graphics enumeration is not semantic certification.
"""
import html,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
import pymupdf as fitz
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).parent)]
import pdf_objects as objects,semantic_objects as mapping,translation_contract as contracts
import final_audit as final,visual_review as visual


class CoverageReviewFaultTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='coverage-fault-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def textpdf(self,name,text):
        path=self.root/name
        with fitz.open() as doc:
            page=doc.new_page(width=440,height=230)
            page.insert_htmlbox((30,40,410,140),'<p>'+html.escape(text)+'</p>',
                css='body {font-family:sans-serif;font-size:16pt;}')
            doc.save(path)
        return path

    def vectorpdf(self,name,text):
        forms={'S':[[(18,0),(0,0),(0,15),(18,15),(18,30),(0,30)]],
            'T':[[(0,0),(20,0)],[(10,0),(10,30)]],
            'O':[[(0,0),(18,0),(18,30),(0,30),(0,0)]],
            'P':[[(0,30),(0,0),(18,0),(18,15),(0,15)]],
            'G':[[(18,0),(0,0),(0,30),(18,30),(18,15),(10,15)]]}
        path=self.root/name
        with fitz.open() as doc:
            page=doc.new_page(width=440,height=230);shape=page.new_shape()
            for index,char in enumerate(text):
                for points in forms[char]:shape.draw_polyline([(60+index*32+x,70+y) for x,y in points])
            shape.finish(color=(0,0,0),width=2);shape.commit();doc.save(path)
        return path

    def context(self,a,b,quote,role='original_english_scope'):
        with fitz.open(a) as doc:
            ids=[g['id'] for g in objects.inventory(doc[0])['glyphs'] if g['visibility'] in mapping.ACTIVE]
        context={'version':mapping.CONTEXT_VERSION,'source_sha256':mapping.sha(a),'target_sha256':mapping.sha(b),
            'pages':[{'page':1,'retained_source_roles':[{'role':role,'contract_quote':quote,'source_glyph_ids':ids}]}]}
        body={k:v for k,v in contracts.empty([1]).items() if k!='sha256'};body['prompt']=quote
        return context,contracts.seal(body)

    def test_c01_unavailable_native_mask_cannot_be_shared_unknown_identity(self):
        a=self.textpdf('a.pdf','\ufffd');b=self.textpdf('b.pdf','\ufffd')
        with mock.patch.object(objects.GlyphDevice,'outline',return_value=None):
            value=mapping.build(a,b,[1])
        self.assertFalse(value['coverage_complete']);page=value['pages'][0]
        self.assertTrue(page['native_accounting_complete'])
        errors=[e for e in page['errors'] if e['code']=='NATIVE_GLYPH_MASK_UNAVAILABLE']
        self.assertEqual({e['side'] for e in errors},{'source','target'})
        self.assertTrue(all(e['glyph_ids'] for e in errors))

    def test_c02_vector_labels_are_nonempty_unclassified_content(self):
        a=self.vectorpdf('a.pdf','STOP');b=self.vectorpdf('b.pdf','GO')
        before={p:mapping.sha(p) for p in (a,b)};value=mapping.build(a,b,[1]);page=value['pages'][0]
        self.assertFalse(value['coverage_complete']);self.assertEqual(page['units'],[])
        self.assertEqual(len(page['source_native_ledger']['glyphs']),0)
        self.assertEqual(len(page['source_native_ledger']['images']),0)
        self.assertTrue(page['source_native_ledger']['vector_paths'])
        self.assertIn('NONEMPTY_PAGE_WITHOUT_SEMANTIC_DISPOSITION',[e['code'] for e in page['errors']])
        self.assertIn('UNCLASSIFIED_VECTOR_CONTENT',[e['code'] for e in page['errors']])
        self.assertEqual(before,{p:mapping.sha(p) for p in (a,b)})

    def test_c02_terminal_gate_blocks_before_any_role_call_even_with_fake_protocol(self):
        a=self.vectorpdf('a.pdf','STOP');b=self.vectorpdf('b.pdf','GO');dual=self.root/'dual.pdf'
        visual.bilingual(a,b,dual)
        def forbidden(*args,**kwargs):raise AssertionError('ROLE CALL BEFORE COVERAGE')
        with mock.patch.object(final,'PROTOCOL_VALIDATED',True):
            result=final.run(a,{'mono':b,'dual':dual},self.root/'audit',forbidden,
                upstream_ready=True,max_repair_rounds=0,max_calls=4,max_seconds=60,
                semantic_auditor=forbidden,semantic_adjudicator=forbidden)
        self.assertFalse(result['delivery_allowed']);self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['quality_status'],'blocked_semantic_coverage')
        self.assertFalse(final.PROTOCOL_VALIDATED)

    def test_identical_unclassified_vector_labels_still_need_a_verified_role(self):
        a=self.vectorpdf('a.pdf','STOP');b=self.vectorpdf('b.pdf','STOP')
        self.assertFalse(mapping.build(a,b,[1])['coverage_complete'])

    def test_blank_page_is_distinct_from_nonempty_zero_unit_page(self):
        a=self.root/'a.pdf'
        with fitz.open() as doc:doc.new_page();doc.save(a)
        value=mapping.build(a,a,[1]);self.assertTrue(value['coverage_complete'])
        self.assertEqual(value['pages'][0]['units'],[])

    def test_c03_translation_command_never_authorizes_unchanged_body(self):
        text='The controller stabilizes the vehicle and records the measured error.'
        a=self.textpdf('a.pdf',text);b=self.textpdf('b.pdf',text)
        quote='Translate every body paragraph into Simplified Chinese.'
        context,contract=self.context(a,b,quote)
        self.assertFalse(mapping.build(a,b,[1],translation_contract=contract)['coverage_complete'])
        with self.assertRaisesRegex(ValueError,'RETAINED_ROLE_NOT_AUTHORIZED_BY_CONTRACT'):
            mapping.build(a,b,[1],context=context,translation_contract=contract)

    def test_affirmative_name_grant_allows_identical_names_only_for_that_role(self):
        a=self.textpdf('a.pdf','Wenjun Gao');b=self.textpdf('b.pdf','Wenjun Gao')
        quote='Preserve author names in their original English.'
        context,contract=self.context(a,b,quote,'author_names')
        value=mapping.build(a,b,[1],context=context,translation_contract=contract)
        self.assertTrue(value['coverage_complete']);self.assertEqual(value['pages'][0]['units'],[])
        context['pages'][0]['retained_source_roles'][0]['role']='affiliations'
        with self.assertRaisesRegex(ValueError,'RETAINED_ROLE_NOT_AUTHORIZED_BY_CONTRACT'):
            mapping.build(a,b,[1],context=context,translation_contract=contract)

    def test_negated_or_unsupported_grant_grammar_fails_closed(self):
        for quote in ['Do not preserve authors in English.','Preserve body prose in English.',
            'If convenient, preserve authors in English.','Translate authors into English.']:
            self.assertEqual(mapping.preservation_grants(quote),set())

    def test_affirmative_substring_of_negation_is_not_a_contract_sentence(self):
        a=self.textpdf('a.pdf','Wenjun Gao');b=self.textpdf('b.pdf','Wenjun Gao')
        context,contract=self.context(a,b,'Preserve author names in English.','author_names')
        body={k:v for k,v in contract.items() if k!='sha256'}
        body['prompt']='Do not '+body['prompt'];contract=contracts.seal(body)
        with self.assertRaisesRegex(ValueError,'RETAINED_ROLE_NOT_AUTHORIZED_BY_CONTRACT'):
            mapping.build(a,b,[1],context=context,translation_contract=contract)


if __name__=='__main__':unittest.main()
