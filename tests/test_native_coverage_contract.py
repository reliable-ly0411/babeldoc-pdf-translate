"""Native PDF coverage controls; no inference, OCR or production approval."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pdf_objects as objects
import engine_source_map as engine
import semantic_objects as mapping


class NativeCoverageTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='native-coverage-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def native(self,text='D'):
        doc=fitz.open();self.addCleanup(doc.close);page=doc.new_page(width=300,height=300)
        page.insert_text((40,80),text,fontsize=12)
        return page,objects.inventory(page)

    def ir(self,inventory,*,expected='D',mask=True):
        g=next(g for g in inventory['glyphs'] if g['unicode']==expected);box=g['ink_bbox']
        # A different BaseFont/native program name reproduces the real Type1
        # resource-name mismatch; only the actual resource mask may bind it.
        inv=copy.deepcopy(inventory);inv['font_resources']=[{'basefont':'ResourceRoman2','native_program_name':'OtherProgram2 Regul',
            'font_program_sha256':'a'*64,'unicode_glyph_masks':{expected:g['shape']} if mask else {}}]
        char={'char_unicode':expected,'pdf_style':{'font_id':'F1','font_size':g['size']},'xobj_id':0,
            'box':{'x':box[0],'y':300-box[3],'x2':box[2],'y2':300-box[1]}}
        value={'page':[{'page_number':0,'pdf_font':[{'font_id':'F1','name':'ResourceRoman2'}],
            'pdf_paragraph':[{'debug_id':'p','unicode':expected,'layout_label':'text',
                'pdf_paragraph_composition':[{'pdf_character':char}]}],'pdf_character':[]}]}
        path=self.root/'source-ir.json';path.write_bytes(json.dumps(value).encode())
        return inv,path,g

    def test_resource_glyph_mask_proves_font_binding_without_name_guessing(self):
        _,inv=self.native();inv,path,g=self.ir(inv)
        result=engine.load(path,0,inv,300)
        self.assertFalse(result['errors']);self.assertEqual(result['matched_source_glyphs'],1)
        proof=result['actual_source_glyph_mask_font_bindings'];self.assertEqual(proof[0]['native_id'],g['id'])
        self.assertEqual(proof[0]['font_program_sha256'],['a'*64])

    def test_resource_font_suffix_alone_and_wrong_mask_cannot_bind(self):
        _,inv=self.native();inv,path,g=self.ir(inv,mask=False)
        result=engine.load(path,0,inv,300);self.assertEqual(result['matched_source_glyphs'],0)
        inv['font_resources'][0]['unicode_glyph_masks']['D']='0'*64
        result=engine.load(path,0,inv,300);self.assertEqual(result['matched_source_glyphs'],0)
        self.assertTrue(result['errors'])

    def test_ordinary_roman_prose_stays_prose_without_formula_membership(self):
        text='The controller stabilizes the vehicle.'
        rows=[{'id':'g%d'%i,'unicode':c,'font':'CMR10','shape':'a'*64} for i,c in enumerate(text)]
        group={'glyph_ids':[g['id'] for g in rows],'reading_segments':[{'text':text,'glyph_ids':[g['id'] for g in rows]}]}
        self.assertEqual(mapping.prose_text(group,{'glyphs':rows}),text)
        self.assertFalse(mapping.formula_role_candidate([group],{'glyphs':rows},text,text))
        self.assertFalse(mapping.formula_role_candidate([group],{'glyphs':rows},'The bound x = 1 is valid.','The bound x = 1 is valid.'))

    def test_unchanged_formula_candidate_requires_role_lineage(self):
        text='Reward = Reward + Reward';rows=[{'id':'g%d'%i,'unicode':c,'font':'STIXGeneral-Regular'} for i,c in enumerate(text)]
        group={'glyph_ids':[g['id'] for g in rows]}
        self.assertTrue(mapping.formula_role_candidate([group],{'glyphs':rows},text,text))
        self.assertFalse(mapping.formula_role_candidate([group],{'glyphs':rows},text,text+'new'))

    def test_complete_dates_normalize_but_changed_month_or_extra_number_does_not(self):
        def facts(text):return mapping.protected({'text':text,'glyph_ids':[]},{'glyphs':[]})
        for target in ['18 2025年9月','18 9月 2025','2025年9月18日']:
            self.assertEqual(facts('18 September 2025'),facts(target))
        self.assertNotEqual(facts('18 September 2025'),facts('18 2025年10月'))
        self.assertNotEqual(facts('18 September 2025'),facts('18 2025年9月 9'))
        self.assertEqual(facts('GPT-4o (2024-05-13)'),facts('GPT‑4o (2024‑05‑13)'))
        self.assertEqual(facts('LiveCodeBench (2024-08–2025-01)'),facts('LiveCodeBench (2024‑08– 2025‑01)'))
        self.assertNotEqual(facts('2024-08'),facts('2024‑09'))
        self.assertNotEqual(facts('2024-08'),facts('2024‑08 8'))
        self.assertNotEqual(facts('2024-08'),facts('2024‑13'))
        self.assertNotEqual(facts('x = -5'),facts('x = +5'))
        self.assertNotEqual(facts('Table 1'),facts('表 11'))

    def test_native_clip_masks_are_placed_at_actual_origin(self):
        font=fitz.Font('helv');gid=font.has_glyph(ord('M'),fallback=False)
        a=objects.sampled_clip_ink(font.this,gid,objects.m.FzMatrix(12,0,0,-12,0,0),fitz.Rect(-5,-20,20,5))
        b=objects.sampled_clip_ink(font.this,gid,objects.m.FzMatrix(12,0,0,-12,100,200),fitz.Rect(95,180,120,205))
        self.assertTrue(a['all_sampled_ink_inside_clip']);self.assertTrue(b['all_sampled_ink_inside_clip'])
        for left,right in zip(a['samples'],b['samples']):
            expected=fitz.Rect(left['nonzero_ink_bbox'])+(100,200,100,200)
            self.assertEqual(list(expected),right['nonzero_ink_bbox'])
            self.assertEqual(left['mask_sha256'],right['mask_sha256'])

    def test_real_clipped_ink_and_unusable_resolution_are_refused(self):
        font=fitz.Font('helv');gid=font.has_glyph(ord('M'),fallback=False)
        result=objects.sampled_clip_ink(font.this,gid,objects.m.FzMatrix(12,0,0,-12,100,200),fitz.Rect(100,180,103,205))
        self.assertFalse(result['all_sampled_ink_inside_clip'])
        with mock.patch.object(objects.m,'fz_render_glyph_pixmap',side_effect=AssertionError('UNBOUNDED RENDER')):
            with self.assertRaisesRegex(ValueError,'RESOLUTION_LIMIT'):
                objects.sampled_clip_ink(font.this,gid,objects.m.FzMatrix(1000,0,0,-1000,0,0),fitz.Rect(0,0,10,10))

    def test_nonrectangular_clip_is_explicit_uncertainty_and_keeps_ledger(self):
        doc=fitz.open();self.addCleanup(doc.close);page=doc.new_page(width=300,height=300)
        page.insert_text((40,240),'VISIBLE',fontsize=12)
        xref=page.get_contents()[-1];raw=doc.xref_stream(xref)
        doc.update_stream(xref,b'q 0 0 m 100 0 l 100 100 l h W n\n'+raw+b'\nQ')
        inv=objects.inventory(page)
        self.assertEqual(len(inv['glyphs']),7);self.assertTrue(any(g['clip_uncertain'] for g in inv['glyphs']))

    def test_opaque_duplicate_paints_are_counted_and_translucent_ones_not_aliased(self):
        page,_=self.native('TEXT');page.insert_text((40,80),'TEXT',fontsize=12)
        inv=objects.inventory(page);self.assertEqual(len(inv['glyphs']),8)
        self.assertEqual(inv['counts'].get('opaque_paint_alias'),4)
        doc=fitz.open();self.addCleanup(doc.close);p=doc.new_page()
        for _ in range(2):p.insert_text((40,80),'TEXT',fontsize=12,fill_opacity=.5)
        self.assertNotIn('opaque_paint_alias',objects.inventory(p)['counts'])

if __name__=='__main__':unittest.main()
