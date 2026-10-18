"""Both actual engine views propose full review pairs; no semantic waiver."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
import pymupdf as fitz
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).parent)]
import engine_source_map as engine,semantic_objects as mapping,pdf_objects as objects


class TargetContextTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='target-context-');self.addCleanup(t.cleanup);self.root=Path(t.name)

    def fixture(self,name,point):
        file=self.root/(name+'.pdf')
        with fitz.open() as d:
            p=d.new_page(width=300,height=300);p.insert_text(point,'A',fontsize=12);d.save(file)
        with fitz.open(file) as d:inv=objects.inventory(d[0])
        g=inv['glyphs'][0];box=g['ink_bbox'];x,y=g['origin']
        c={'char_unicode':'A','xobj_id':0,'pdf_style':{'font_id':'helv','font_size':12},
           'box':{'x':x,'y':300-y,'x2':x+g['size'],'y2':300-y+1},
           'visual_bbox':{'box':{'x':box[0],'y':300-box[3],'x2':box[2],'y2':300-box[1]}}}
        ir=self.root/(name+'.json');ir.write_bytes(json.dumps({'page':[{'page_number':0,
            'pdf_font':[{'font_id':'helv','name':'Helvetica'}], 'pdf_character':[],
            'pdf_paragraph':[{'debug_id':'owned-a','unicode':'A','pdf_paragraph_composition':[{'pdf_character':c}]}]}]}).encode())
        return file,ir

    def context(self,a,b,source_ir,target_ir):
        return {'version':mapping.CONTEXT_VERSION,'source_sha256':mapping.sha(a),'target_sha256':mapping.sha(b),
            'pages':[{'page':1,'engine_source':{'path':str(source_ir),'sha256':mapping.sha(source_ir),'engine_page':0},
                      'engine_target':{'path':str(target_ir),'sha256':mapping.sha(target_ir),'engine_page':0}}]}

    def test_actual_engine_membership_pairs_a_moved_complete_paragraph(self):
        a,si=self.fixture('a',(40,80));b,ti=self.fixture('b',(180,180))
        self.assertFalse(mapping.build(a,b,[1],chinese=False)['coverage_complete'])
        result=mapping.build(a,b,[1],chinese=False,context=self.context(a,b,si,ti))
        self.assertTrue(result['coverage_complete'],result['pages'][0]['errors'])
        unit=result['pages'][0]['units'][0]
        self.assertEqual((unit['source'],unit['target']),('A','A'))
        self.assertIn('controller correspondence candidate',unit['mapping_basis'])
        self.assertEqual(result['pages'][0]['engine_target']['matched_target_glyphs'],1)

    def test_stale_target_ir_fails_even_with_a_matching_debug_id(self):
        a,si=self.fixture('a',(40,80));b,ti=self.fixture('b',(180,180))
        ctx=self.context(a,b,si,ti);body=json.loads(ti.read_text())
        body['page'][0]['pdf_paragraph'][0]['pdf_paragraph_composition'][0]['pdf_character']['box']['x']+=1
        ti.write_bytes(json.dumps(body).encode());ctx['pages'][0]['engine_target']['sha256']=mapping.sha(ti)
        result=mapping.build(a,b,[1],chinese=False,context=ctx)
        self.assertFalse(result['coverage_complete'])
        self.assertIn('ENGINE_TARGET_MEMBER_NOT_FOUND',[e['code'] for e in result['pages'][0]['errors']])

    def test_context_hash_is_path_independent_but_binds_target_ir_bytes(self):
        a,si=self.fixture('a',(40,80));b,ti=self.fixture('b',(180,180));ctx=self.context(a,b,si,ti)
        _,expected=mapping.validate_context(ctx,a,b,[1],None)
        new=self.root/'relocated.json';new.write_bytes(ti.read_bytes())
        other=copy.deepcopy(ctx);other['pages'][0]['engine_target']['path']=str(new)
        self.assertEqual(mapping.validate_context(other,a,b,[1],None)[1],expected)
        new.write_bytes(new.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'ENGINE_TARGET_ARTIFACT_CHANGED'):
            mapping.validate_context(other,a,b,[1],None)


if __name__=='__main__':unittest.main()
