"""Controlled source-copy fixtures, owned covers and saved-artifact binding."""
import copy,hashlib,json,sys,tempfile,unittest
from unittest import mock
from pathlib import Path
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pdf_objects as objects,render_lineage as lineage,prose_ink,source_repair,visual_review


class RenderLineageTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='writer-lineage-');self.addCleanup(t.cleanup);self.root=Path(t.name)

    def page(self):
        d=fitz.open();self.addCleanup(d.close);return d,d.new_page(width=300,height=300)

    def test_cover_is_inside_its_native_frame_at_difficult_float_coordinates(self):
        d,p=self.page();p.insert_text((40,80),'Original')
        area=fitz.Rect(33.123456789,50.0000001,275.987654321,62.4000001)
        cover=lineage.opaque_cover(p,area)
        self.assertTrue(area.contains(fitz.Rect(cover['native_bbox'])))
        self.assertNotEqual(cover['native_bbox'],[round(x,6) for x in area])
        inv=objects.inventory(p);self.assertTrue(inv['vector_paths'][-1]['native_opaque_rectangle'])

    def test_physical_roundoff_is_bounded_without_changing_glyph_or_math_role(self):
        from copy import deepcopy
        a={'shape':'original-shape','unicode':'π','font':'MathItalic','size':8.4975,
            'origin':[275.4521484375,152.265625],'paint_type':0,'opacity':1,'color':[0,0,0],'direction':[1,0]}
        b=deepcopy(a);b['origin'][0]=275.45196533203125
        self.assertTrue(lineage.same_paint(a,b))
        self.assertLess(abs(a['origin'][0]-b['origin'][0]),lineage.POSITION_ROUNDING_PT)
        for field,value in [('unicode','θ'),('shape','different-shape'),('font','OtherFont'),
                            ('size',8.5),('direction',[-1,0]),('opacity',.5),('color',[1,0,0])]:
            changed=deepcopy(b);changed[field]=value
            self.assertFalse(lineage.same_paint(a,changed),field)
        for offset in (.001,.01,1,1.44,2.016):
            for axis in (0,1):
                changed=deepcopy(a);changed['origin'][axis]+=offset
                self.assertFalse(lineage.same_paint(a,changed),(offset,axis))
        changed=deepcopy(a);changed['origin'][0]=float('nan')
        self.assertFalse(lineage.same_paint(a,changed))

    def test_copy_records_actual_prose_and_keeps_graphics_unresolved(self):
        a,p=self.page();p.draw_line((40,120),(240,120));fit=source_repair.fit_prose(p,
            {'source':'New words','font_size':10,'boxes':[[40,51.2,200,61.2]]},'新文字。',commit=True,validated=True)
        self.assertIsNotNone(fit)
        b,q=self.page();area=fitz.Rect(30,30,270,160);lineage.opaque_cover(q,area)
        boundary=prose_ink.glyph_count(q);q.show_pdf_page(area,a,0,clip=area)
        result=lineage.observe_copy(p,q,area,first_glyph=boundary,prose_ids=[g['id'] for g in fit['native_ink']['native_glyphs']])
        self.assertTrue(result['passed'],result['issues']);self.assertTrue(result['glyph_links'])
        self.assertEqual(result['source_graphics_roles'],'unresolved');self.assertFalse(result['coverage_waiver'])

    def test_source_paint_crossing_copy_clip_is_rejected(self):
        a,p=self.page();p.insert_text((40,80),'q',fontsize=12)
        b,q=self.page();area=fitz.Rect(40,60,43,100);lineage.opaque_cover(q,area)
        boundary=prose_ink.glyph_count(q);q.show_pdf_page(area,a,0,clip=area)
        result=lineage.observe_copy(p,q,area,first_glyph=boundary)
        self.assertFalse(result['passed']);self.assertIn('COPY_INTRODUCES_SOURCE_INK_CLIP',[e['code'] for e in result['issues']])

    def test_source_repair_returns_a_final_object_frame_that_can_be_sealed(self):
        d,p=self.page();p.insert_text((40,80),'The controller measures the error.',fontsize=10)
        source_path=self.root/'source.pdf';d.save(source_path)
        original=fitz.open(source_path);self.addCleanup(original.close)
        target=fitz.open(source_path);self.addCleanup(target.close)
        area=fitz.Rect(30,50,275,120);slots=source_repair.units(original[0],area,'prose')
        self.assertEqual(len(slots),1)
        result=source_repair.restore_region(original,0,target,0,{'bbox':list(area),'kind':'prose'},['控制器测量误差。'])
        self.assertIn('render_lineage',result)
        mono=self.root/'mono.pdf';target.save(mono)
        record=lineage.seal(source_path,mono,[result['render_lineage']],self.root/'lineage.json')
        self.assertEqual(record['target_sha256'],hashlib.sha256(mono.read_bytes()).hexdigest())
        self.assertFalse(record['delivery_authorized'])
        self.assertEqual(record['source_graphics_roles'],'unresolved')

    def test_changed_final_cover_is_not_accepted_as_the_original_operation(self):
        d,p=self.page();p.insert_text((40,80),'The controller measures the error.',fontsize=10)
        src=self.root/'source.pdf';d.save(src)
        original=fitz.open(src);self.addCleanup(original.close);target=fitz.open(src);self.addCleanup(target.close)
        area=fitz.Rect(30,50,275,120)
        result=source_repair.restore_region(original,0,target,0,{'bbox':list(area),'kind':'prose'},['控制器测量误差。'])
        frame=copy.deepcopy(result['render_lineage']);frame['opaque_cover']['geometry_sha256']='0'*64
        mono=self.root/'mono.pdf';target.save(mono)
        with self.assertRaisesRegex(ValueError,'LINEAGE_OWNED_COVER_CHANGED'):
            lineage.seal(src,mono,[frame],self.root/'reject.json')
        self.assertFalse((self.root/'reject.json').exists())


    def test_saved_copy_binds_original_math_and_rejects_changed_source_id(self):
        d,p=self.page();p.insert_text((40,80),'The controller measures the error.',fontsize=10)
        p.insert_text((230,80),'x',fontname='symb',fontsize=10)
        src=self.root/'source.pdf';d.save(src)
        original=fitz.open(src);self.addCleanup(original.close);target=fitz.open(src);self.addCleanup(target.close)
        result=source_repair.restore_region(original,0,target,0,{'bbox':[30,50,275,120],'kind':'prose'},['控制器测量误差。'])
        copied=[r for r in result['render_lineage']['copy']['glyph_links'] if r['role']=='source_paint_preserved']
        self.assertEqual(len(copied),1);self.assertIn('original_source_glyph_id',copied[0])
        mono=self.root/'mono.pdf';target.save(mono);receipt=self.root/'lineage.json'
        sealed=lineage.seal(src,mono,[result['render_lineage']],receipt)
        self.assertEqual(lineage.verify(receipt,src,mono),sealed)
        for row in sealed['frames'][0]['copy']['glyph_links']:
            if row['role']=='source_paint_preserved':row['original_source_glyph_id']='g999999'
        receipt.write_bytes(json.dumps(sealed).encode())
        with self.assertRaisesRegex(ValueError,'LINEAGE_ORIGINAL_NATIVE_BINDING_CHANGED'):
            lineage.verify(receipt,src,mono)

    def test_path_failure_precedes_any_source_repair_role_call(self):
        d,p=self.page();p.insert_text((40,80),'Original sentence.')
        src=self.root/'source.pdf';d.save(src);source=fitz.open(src);self.addCleanup(source.close)
        with mock.patch.object(lineage.os,'link',side_effect=OSError('fixture path unsupported')), mock.patch.object(visual_review,'request_source_plan',side_effect=AssertionError('ROLE CALLED')):
            with self.assertRaisesRegex(ValueError,'FINAL_WRITER_DURABLE_PATH_UNSUPPORTED'):
                visual_review.patch_from_source(source,src,self.root/'after.pdf',1,[],[],1,self.root/'review',{},None,None,[])
        self.assertFalse((self.root/'after.pdf').exists())
        self.assertEqual(list((self.root/'review').iterdir()),[])

    def test_failed_actual_commit_cannot_publish_partial_candidate(self):
        d,p=self.page();p.insert_text((40,80),'Original sentence.')
        src=self.root/'source.pdf';d.save(src);source=fitz.open(src);self.addCleanup(source.close)
        plan={'units':[{'source':'Original sentence.'}],'issue':{'region_id':'block_0'}}
        def changed_then_failed(a,ai,b,bi,island,text):
            b[bi].insert_text((40,160),'PARTIAL WRITE MUST BE DISCARDED')
            raise source_repair.SourceRepairCommitError('SOURCE_COPY_COMMIT_FAILED_DISCARD_CANDIDATE')
        with mock.patch.object(source_repair,'prepare',return_value=([plan],[])), mock.patch.object(visual_review,'request_source_plan',return_value=[['原句。']]), mock.patch.object(source_repair,'restore_region',side_effect=changed_then_failed):
            with self.assertRaises(source_repair.SourceRepairCommitError):
                visual_review.patch_from_source(source,src,self.root/'after.pdf',1,[],[],1,self.root/'review',{},None,None,[])
        self.assertFalse((self.root/'after.pdf').exists())
        self.assertFalse((self.root/'review/source-copy-provenance.json').exists())
        with fitz.open(src) as unchanged:self.assertNotIn('PARTIAL',unchanged[0].get_text())


if __name__=='__main__':unittest.main()
