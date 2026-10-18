"""Actual final-font/baseline/ActualText binding, never a semantic waiver."""
import copy,hashlib,json,math,struct,sys,tempfile,unittest
from pathlib import Path
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pdf_objects as objects,engine_source_map as engine


def font_with_cmap(raw,mapping):
    """Small real sfnt fixture: retain glyphs/name, replace only Unicode cmap.

    No optional font editing dependency is required by the regression suite.
    Format12 records deliberately reproduce a discarded ASCII cmap alias.
    """
    count=struct.unpack_from('>H',raw,4)[0];tables={}
    for i in range(count):
        tag,_,offset,size=struct.unpack_from('>4sIII',raw,12+i*16)
        tables[tag]=raw[offset:offset+size]
    groups=b''.join(struct.pack('>III',c,c,g) for c,g in sorted(mapping.items()))
    sub=struct.pack('>HHIII',12,0,16+len(groups),0,len(mapping))+groups
    tables[b'cmap']=struct.pack('>HHHHIHHI',0,2,0,4,20,3,10,20)+sub
    head=bytearray(tables[b'head']);head[8:12]=b'\0'*4;tables[b'head']=bytes(head)
    power=2**int(math.log2(count));header=raw[:4]+struct.pack('>HHHH',count,power*16,int(math.log2(power)),count*16-power*16)
    directory=bytearray();data=bytearray();offset=12+count*16;head_at=None
    def checksum(body):
        padded=body+b'\0'*((-len(body))%4)
        return sum(struct.unpack('>'+str(len(padded)//4)+'I',padded))&0xffffffff
    for tag,body in sorted(tables.items()):
        directory.extend(struct.pack('>4sIII',tag,checksum(body),offset,len(body)))
        if tag==b'head':head_at=offset
        padded=body+b'\0'*((-len(body))%4);data.extend(padded);offset+=len(padded)
    result=bytearray(header+directory+data)
    struct.pack_into('>I',result,head_at+8,(0xb1b0afba-checksum(result))&0xffffffff)
    return bytes(result)


class TargetWriterTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='target-writer-');self.addCleanup(t.cleanup);self.root=Path(t.name)

    def pdf(self,text='q',*,marked=None,cmap=None):
        doc=fitz.open();self.addCleanup(doc.close);p=doc.new_page(width=300,height=300)
        font=fitz.Font('helv');xref=p.insert_font(fontname='WriterFont.ttf',fontbuffer=font.buffer)
        p.insert_text((40,80),text,fontname='WriterFont.ttf',fontsize=12)
        if marked is not None:
            ref=p.get_contents()[-1];raw=doc.xref_stream(ref)
            actual=(b'\xfe\xff'+marked.encode('utf-16-be')).hex().encode()
            doc.update_stream(ref,b'/Span <</ActualText <'+actual+b'>>> BDC\n'+raw+b'\nEMC')
        if cmap is not None:
            gid=font.has_glyph(ord(text),fallback=False)
            stream=b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Test def /CMapType 2 def 1 begincodespacerange <0000> <ffff> endcodespacerange 1 beginbfchar <'+format(gid,'04x').encode()+b'> <'+cmap.encode('utf-16-be').hex().encode()+b'> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end'
            ref=doc.get_new_xref();doc.update_object(ref,'<< >>');doc.update_stream(ref,stream)
            doc.xref_set_key(xref,'ToUnicode',str(ref)+' 0 R')
        return p,objects.inventory(p)

    def ir(self,inv,text='q',*,dx=0,dy=0,font='WriterFont.ttf'):
        g=next(g for g in inv['glyphs'] if not g.get('logical_only'))
        value={'page':[{'page_number':0,'pdf_font':[],'pdf_paragraph':[{'debug_id':'p','unicode':text,
            'pdf_paragraph_composition':[{'pdf_character':{'char_unicode':text,'pdf_style':{'font_id':font,'font_size':12},
                'xobj_id':0,'visual_bbox':None,'box':{'x':40+dx,'y':220+dy,'x2':48+dx,'y2':221+dy}}}]}],'pdf_character':[]}]}
        p=self.root/'typesetting.json';p.write_bytes(json.dumps(value).encode());return p

    def test_descender_uses_emitted_baseline_not_source_ink_box_overlap(self):
        _,inv=self.pdf();p=self.ir(inv)
        self.assertGreater(inv['glyphs'][0]['ink_bbox'][3],80)
        result=engine.load_target(p,0,inv,300)
        self.assertEqual(result['errors'],[]);self.assertEqual(result['matched_target_glyphs'],1)
        self.assertEqual(result['actual_resource_font_bindings'][0]['ir_font_id'],'WriterFont.ttf')

    def test_stale_baseline_does_not_get_a_source_metric_delta_waiver(self):
        _,inv=self.pdf();p=self.ir(inv,dx=.01)
        self.assertEqual(engine.load_target(p,0,inv,300)['matched_target_glyphs'],0)

    def test_unknown_font_resource_name_is_not_guessed_from_suffix(self):
        _,inv=self.pdf();p=self.ir(inv,font='WriterFont2.ttf')
        self.assertTrue(engine.load_target(p,0,inv,300)['errors'])

    def test_ambiguous_actual_program_for_one_resource_is_rejected(self):
        _,inv=self.pdf();p=self.ir(inv);r=copy.deepcopy(inv['font_resources'][0]);r['font_program_sha256']='f'*64
        inv['font_resources'].append(r)
        self.assertEqual(engine.load_target(p,0,inv,300)['matched_target_glyphs'],0)

    def test_wrong_unicode_and_wrong_text_direction_cannot_bind(self):
        _,inv=self.pdf();p=self.ir(inv,text='p')
        self.assertEqual(engine.load_target(p,0,inv,300)['matched_target_glyphs'],0)
        p=self.ir(inv);inv['glyphs'][0]['direction']=[-1.,0.]
        self.assertEqual(engine.load_target(p,0,inv,300)['matched_target_glyphs'],0)

    def test_actualtext_cmap_alias_needs_the_actual_font_mask(self):
        _,inv=self.pdf('-',marked='-',cmap='\u2011');g=inv['glyphs'][0]
        self.assertEqual(g['unicode'],'\u2011');self.assertEqual(objects.content_unicode(g),'-')
        self.assertTrue(g['marked_text_matches_native_mask'])
        result=engine.load_target(self.ir(inv,text='-'),0,inv,300);self.assertEqual(result['errors'],[])

    def test_false_actualtext_label_cannot_change_the_painted_letter(self):
        _,inv=self.pdf('A',marked='B');g=inv['glyphs'][0]
        self.assertFalse(g['marked_text_matches_native_mask']);self.assertEqual(objects.content_unicode(g),'A')
        self.assertTrue(engine.load_target(self.ir(inv,text='B'),0,inv,300)['errors'])

    def test_actualtext_paragraph_is_not_a_single_glyph_binding(self):
        _,inv=self.pdf('A',marked='The whole paragraph is translated.')
        self.assertIsNone(inv['glyphs'][0]['marked_actual_text'])
        self.assertEqual(objects.content_unicode(inv['glyphs'][0]),'A')

    def alias_asset(self):
        full=fitz.Font('cjk');asset=self.root/'writer-full.ttf';asset.write_bytes(full.buffer)
        embedded=font_with_cmap(full.buffer,{0x2011:full.has_glyph(45,fallback=False),65:full.has_glyph(65,fallback=False)})
        doc=fitz.open();self.addCleanup(doc.close);p=doc.new_page(width=300,height=300)
        p.insert_font(fontname='WriterFont.ttf',fontbuffer=embedded)
        p.insert_text((40,80),'\u2011',fontname='WriterFont.ttf',fontsize=12)
        ref=p.get_contents()[-1]
        doc.update_stream(ref,b'/Span <</ActualText <feff002d>>> BDC\n'+doc.xref_stream(ref)+b'\nEMC')
        inv=objects.inventory(p)
        return inv,{'WriterFont.ttf':{'path':str(asset),'sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}}

    def test_discarded_subset_alias_requires_the_full_registered_font(self):
        inv,assets=self.alias_asset();g=inv['glyphs'][0];path=self.ir(inv,text='-')
        self.assertEqual(objects.content_unicode(g),'\u2011')
        self.assertFalse(g['marked_text_matches_native_mask'])
        self.assertTrue(engine.load_target(path,0,inv,300)['errors'])
        result=engine.load_target(path,0,inv,300,font_assets=assets)
        self.assertEqual(result['errors'],[]);self.assertEqual(len(result['verified_target_text_aliases']),1)
        adjusted=engine.apply_verified_aliases(inv,result)
        self.assertEqual(objects.content_unicode(adjusted['glyphs'][0]),'-')
        self.assertEqual(inv['glyphs'][0]['unicode'],'\u2011')
        self.assertNotIn('writer_font_alias',inv['glyphs'][0])

    def test_changed_font_asset_or_wrong_same_family_mask_is_rejected(self):
        inv,assets=self.alias_asset();path=self.ir(inv,text='-')
        bad=copy.deepcopy(assets);bad['WriterFont.ttf']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'TARGET_FONT_ASSET_CHANGED'):
            engine.load_target(path,0,inv,300,font_assets=bad)
        full=fitz.Font(fontbuffer=Path(assets['WriterFont.ttf']['path']).read_bytes())
        wrong=self.root/'same-family-wrong.ttf'
        wrong.write_bytes(font_with_cmap(full.buffer,{45:full.has_glyph(65,fallback=False),65:full.has_glyph(65,fallback=False)}))
        assets['WriterFont.ttf']={'path':str(wrong),'sha256':hashlib.sha256(wrong.read_bytes()).hexdigest()}
        self.assertTrue(engine.load_target(path,0,inv,300,font_assets=assets)['errors'])

    def test_alias_proof_cannot_be_reused_for_a_different_native_paint(self):
        inv,assets=self.alias_asset();result=engine.load_target(self.ir(inv,text='-'),0,inv,300,font_assets=assets)
        inv['glyphs'][0]['shape']='0'*64
        with self.assertRaisesRegex(ValueError,'INVALID_VERIFIED_TARGET_ALIAS'):
            engine.apply_verified_aliases(inv,result)

    def test_duplicate_ir_owners_and_repeated_physical_members_are_errors(self):
        _,inv=self.pdf();path=self.ir(inv);body=json.loads(path.read_text())
        paragraph=body['page'][0]['pdf_paragraph'][0]
        paragraph['pdf_paragraph_composition']*=2;path.write_bytes(json.dumps(body).encode())
        self.assertIn('ENGINE_TARGET_MEMBER_REPEATED',[e['code'] for e in engine.load_target(path,0,inv,300)['errors']])
        paragraph['pdf_paragraph_composition']=paragraph['pdf_paragraph_composition'][:1]
        body['page'][0]['pdf_paragraph'].append(copy.deepcopy(paragraph));path.write_bytes(json.dumps(body).encode())
        self.assertIn('ENGINE_TARGET_PARAGRAPH_ID_AMBIGUOUS',[e['code'] for e in engine.load_target(path,0,inv,300)['errors']])


if __name__=='__main__':unittest.main()
