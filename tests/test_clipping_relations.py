"""Source clipping is distinct from a candidate defect; neither is waived."""
import copy,sys,tempfile,unittest
from pathlib import Path
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pdf_objects as objects,clipping_relations as clipping,semantic_objects as mapping


class ClippingRelationTests(unittest.TestCase):
    def page(self,*,clipped=True,opacity=1,repeats=1):
        d=fitz.open();self.addCleanup(d.close);p=d.new_page(width=300,height=300)
        for _ in range(repeats):
            p.insert_text((40,80),'q',fontsize=12,fill_opacity=opacity)
            if clipped:
                ref=p.get_contents()[-1];d.update_stream(ref,b'q 40 210 3 30 re W n\n'+d.xref_stream(ref)+b'\nQ')
        return p,objects.inventory(p)

    def test_source_and_target_properties_are_separate_without_a_lineage_waiver(self):
        p,a=self.page();value=clipping.describe(a,a)
        self.assertEqual(value['source_input'][0]['classification'],'source_input_clipping')
        self.assertEqual(value['target_risks'][0]['classification'],'unchanged_native_clipping_signature_lineage_unverified')
        self.assertFalse(value['coverage_waiver'])
        result=mapping.page_units(p,p,1);self.assertFalse(result['coverage_complete'])

    def test_explicit_inherited_link_is_recorded_and_does_not_clear_the_guard(self):
        _,a=self.page();value=clipping.describe(a,a,glyph_links=[['g000000','g000000']])
        self.assertEqual(value['target_risks'][0]['classification'],'inherited_clipping_with_caller_link')
        self.assertFalse(value['coverage_waiver'])

    def test_new_clipping_after_an_unclipped_source_requires_an_explicit_link(self):
        _,a=self.page(clipped=False);_,b=self.page()
        raw=clipping.describe(a,b)['target_risks'][0]
        self.assertEqual(raw['classification'],'target_clipping_origin_unverified')
        linked=clipping.describe(a,b,glyph_links=[['g000000','g000000']])['target_risks'][0]
        self.assertEqual(linked['classification'],'target_clipping_after_unclipped_source_with_caller_link')

    def test_duplicate_paint_signatures_remain_ambiguous(self):
        _,a=self.page(opacity=.5,repeats=2);_,b=self.page(opacity=.5)
        self.assertEqual(clipping.describe(a,b)['target_risks'][0]['classification'],'ambiguous_source_clipping_correspondence')

    def test_unknown_masks_and_unsupported_clips_cannot_prove_inheritance(self):
        _,a=self.page();b=copy.deepcopy(a);b['glyphs'][0]['shape']=None
        self.assertEqual(clipping.describe(a,b)['target_risks'][0]['classification'],'unsupported_or_unavailable_identity')
        b=copy.deepcopy(a);b['glyphs'][0]['clip_uncertain']=True
        self.assertEqual(clipping.describe(a,b)['target_risks'][0]['classification'],'unsupported_or_unavailable_identity')

    def test_invalid_or_duplicate_links_fail_closed(self):
        _,a=self.page()
        for links in [[['missing','g000000']],[['g000000','g000000'],['g000000','g000000']],[[[],'g000000']]]:
            with self.assertRaisesRegex(ValueError,'INVALID_CLIPPING_LINEAGE'):clipping.describe(a,a,glyph_links=links)


if __name__=='__main__':unittest.main()
