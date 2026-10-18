"""Keep PDF math transcription out of visual evidence; bound detail crops."""
import copy
from pathlib import Path
import sys
import unittest
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import visual_review as v


class EvidenceTests(unittest.TestCase):
    def test_unchanged_outside_findings_are_retained_and_unmapped_new_ones_veto(self):
        def issue(key,category='layout',severity='major'):
            return {'region_id':key,'category':category,'severity':severity,'reason':'Visible defect','replacement':''}
        regions=[{'id':'a','bbox':[10,10,90,50],'text':'edited'},
                 {'id':'b','bbox':[10,90,90,150],'text':'unchanged'}]
        edits=[{'region':{'bbox':[9,9,91,51]}}]
        before={'issues':[issue('a','formula'),issue('b','figure_text')]}
        after={'issues':[issue('b','translation')]}
        accepted,retained,decision=v.assess_candidate(before,after,regions,regions,edits)
        self.assertTrue(accepted)
        self.assertEqual({i['category'] for i in retained['issues']},{'translation','figure_text'})
        self.assertEqual(decision['carried_findings'][0]['from_region_id'],'b')
        for bad in (issue('a','translation'),issue('','translation')):
            self.assertFalse(v.assess_candidate(before,{'issues':[bad]},regions,regions,edits)[0])
        # A neighbor's blank font ascent margin is not visible ink in the edit.
        margin=[regions[0],{**regions[1],'bbox':[10,49,90,75],'ink_bbox':[10,53,90,72]}]
        self.assertTrue(v.assess_candidate(before,after,margin,margin,edits)[0])

    def test_unmapped_equation_requires_unique_printed_tag_and_body_boundary(self):
        with fitz.open() as s,fitz.open() as t:
            a=s.new_page(width=500,height=500);b=t.new_page(width=500,height=500)
            for p,y in ((a,180),(b,180)):p.insert_text((450,y),'(7)',fontsize=10)
            known=[{'id':'block_0','bbox':[270,181,475,205],'text':'matrix','font_size':4},
                {'id':'block_1','bbox':[270,220,475,245],'text':'这是下一段足够长的正文用于确定公式定义范围。','font_size':10}]
            issue={'region_id':'','category':'formula','severity':'major','reason':'式 (7) 下方定义不可读。','replacement':''}
            extra,mapped,decisions=v.resolve_equation_issues(a,b,known,[issue])
            self.assertEqual(mapped[0]['region_id'],'equation_7')
            self.assertEqual(issue['region_id'],'')
            self.assertEqual(extra[-1]['bbox'],known[0]['bbox'])
            self.assertEqual(decisions[0]['target_block_ids'],['block_0'])
            # Ambiguous printed labels and absent prose boundaries cannot be guessed.
            a.insert_text((450,280),'(7)',fontsize=10)
            self.assertEqual(v.resolve_equation_issues(a,b,known,[issue])[1][0]['region_id'],'')
            self.assertEqual(v.resolve_equation_issues(b,b,known[:1],[issue])[1][0]['region_id'],'')
            unknown={**issue,'reason':'公式很小，但没有明确编号。'}
            self.assertEqual(v.resolve_equation_issues(b,b,known,[unknown])[1][0]['region_id'],'')

    def test_model_sees_prose_and_ids_but_not_pdf_math_transcription(self):
        class Page:
            def get_text(self,mode):
                def block(font,text,y):
                    return {'type':0,'bbox':[10,y,100,y+12],'lines':[{'dir':(1.,0.),'spans':[
                        {'font':font,'size':10,'flags':0,'color':0,'text':text}]}]}
                return {'blocks':[block('Helvetica','Continuous and bounded.',20),block('CMEX10','(cid:13)',50)]}
        raw=v.regions(Page());model=v.model_regions(Page())
        self.assertEqual([r['id'] for r in raw],[r['id'] for r in model])
        self.assertEqual(model[0]['text'],'Continuous and bounded.')
        self.assertEqual(model[1]['text'],'')
        self.assertIn('(cid:13)',raw[1]['text'])
        self.assertNotIn('sha256',model[0])

    def test_equation_detail_aligns_by_label_after_reflow(self):
        with fitz.open() as s,fitz.open() as t:
            a=s.new_page(width=500,height=500);b=t.new_page(width=500,height=500)
            a.insert_text((450,150),'(7)',fontsize=10)
            b.insert_text((450,180),'(7)',fontsize=10)
            b.insert_text((320,200),'Tiny matrix',fontsize=3)
            windows=v.detail_windows(a,b,v.regions(b))
            self.assertEqual(len(windows),1)
            self.assertEqual(windows[0]['tag'],'(7)')
            self.assertNotEqual(windows[0]['source_bbox'][1],windows[0]['target_bbox'][1])
            self.assertTrue(a.rect.contains(fitz.Rect(windows[0]['source_bbox'])))
            self.assertTrue(b.rect.contains(fitz.Rect(windows[0]['target_bbox'])))

    def test_crops_are_bounded_and_do_not_modify_pages(self):
        with fitz.open() as s,fitz.open() as t:
            a=s.new_page(width=500,height=500);b=t.new_page(width=500,height=500)
            a.draw_rect((40,40,200,140),color=(1,0,0),fill=(1,.8,.8))
            for y in (200,350,450):
                b.insert_text((320,y),'Tiny label',fontsize=3)
            hashes=[v.digest(p.get_pixmap().samples) for p in (a,b)]
            windows=v.detail_windows(a,b,v.regions(b))
            self.assertLessEqual(len(windows),3)
            self.assertEqual(windows[0]['kind'],'figure')
            self.assertEqual([v.digest(p.get_pixmap().samples) for p in (a,b)],hashes)
            for window in windows:
                self.assertTrue(a.rect.contains(fitz.Rect(window['source_bbox'])))
                self.assertTrue(b.rect.contains(fitz.Rect(window['target_bbox'])))


if __name__=='__main__':unittest.main()
