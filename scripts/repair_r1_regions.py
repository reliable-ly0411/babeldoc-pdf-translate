"""Reviewed R1 figure labels/raster-table supplement, not generic OCR support.

Original plots/images/equations come from the pinned source. Only catalogued
English label boxes are covered; curves, ticks, values and model IDs remain.
The original English page is retained in the bilingual output.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import re
import unicodedata
import pymupdf

SOURCE_HASH = '916fdaafc3b44143a9744481d079744f773d73d06372f82b1dba1076525927f2'
FONT_FILE = None
FONT = None


def text_box(page, box, text, size=8, color=(0, 0, 0), rotate=0, align=1):
    rect = pymupdf.Rect(box)
    for f in [size, size - .3, size - .6]:
        # The return value is checked; no clipped text can silently become a result.
        shape = page.new_shape()
        remaining = shape.insert_textbox(rect, text, fontname='R1CJK', fontfile=str(FONT_FILE), fontsize=f,
                                         color=color, align=align, rotate=rotate)
        if remaining >= 0:
            shape.commit()
            return f
    raise ValueError('Text did not fit a reviewed label box: ' + text)


def apply(source, mono, catalog, output, font_file):
    global FONT_FILE, FONT
    FONT_FILE = font_file.resolve()
    FONT = pymupdf.Font(fontfile=str(FONT_FILE))
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError('Source does not match the fixed 11-page Nature R1')
    mapping = {r['source']: r['translation'] for r in catalog['rows']}
    edits = []
    with pymupdf.open(source) as original, pymupdf.open(mono) as doc:
        if len(original) != 11 or len(doc) != 11:
            raise ValueError('Expected all 11 source/translated pages')
        # The custom prompt requests bibliographic/credit material in English.
        # Preserve the exact source content rather than relying on model compliance.
        retained = [(4,(39,630,297,746)), (4,(305,46,564,623)),
                    (5,(305,98,564,146)), (7,(305,341,564,464))]
        for index, box in retained:
            region=pymupdf.Rect(box)
            doc[index].draw_rect(region,color=None,fill=(1,1,1),overlay=True)
            doc[index].show_pdf_page(region,original,index,clip=region)
            edits.append({'page':index+1,'retained_source_region':box,
                          'reason':'References, affiliations, publisher/license/copyright text retained in English.'})
        # Reflow only the surrounding Chinese on two crowded inline-equation rows.
        # Equations are copied from the source as PDF objects at original scale.
        p=doc[2]
        p.draw_rect(pymupdf.Rect(39,77,294,90),color=None,fill=(1,1,1),overlay=True)
        text_box(p,(39.7,78,135,90),'问题：若 a > 1，则方程',6.7,align=0)
        math=pymupdf.Rect(206.9,76.5,255.4,90)
        target=pymupdf.Rect(135,76.5,183.5,90)
        p.show_pdf_page(target,original,2,clip=math)
        text_box(p,(185,78,294,90),'的实数解之和为',6.7,align=0)
        p.draw_rect(pymupdf.Rect(39,102.5,294,114.2),color=None,fill=(1,1,1),overlay=True)
        text_box(p,(39.7,104,108,116),'为求解方程',6.7,align=0)
        math=pymupdf.Rect(109.1,102,154.25,114.2)
        p.show_pdf_page(math,original,2,clip=math)
        text_box(p,(156,104,294,116),'，先将等式两边平方……',6.7,align=0)
        edits.append({'page':3,'inline_equation_reflow':'Two rows: source equation objects at original scale; surrounding Chinese reordered for grammar/spacing.'})
        # Two parser fragments had independently shrunk the table's explanatory
        # note to 6/4.5 pt. Reflow the existing Luna translation as a single note.
        note=re.sub(r'\s+','',p.get_text(clip=pymupdf.Rect(39,255,294,281)))
        if not 25<=len(note)<=150 or '模型' not in note:
            raise ValueError('Unexpected translated table note')
        p.draw_rect(pymupdf.Rect(39,255,294,282),color=None,fill=(1,1,1),overlay=True)
        f=text_box(p,(39.7,256,294,279),note,6.4,align=0)
        p.draw_line((39,281),(294,281),color=(0,0,0),width=.5)
        edits.append({'page':3,'table_note_reflow':True,'font_pt':f,
                      'translation_sha256':hashlib.sha256(note.encode()).hexdigest(),
                      'reason':'Existing Luna words retained; unify 6/4.5 pt fragments at a readable note size.'})
        # Figures 1/2 have vector text; re-use the source figure before label edits.
        for index, box in [(1, (39, 45, 562, 240)), (2, (81, 514, 522, 721))]:
            p, src = doc[index], original[index]
            region = pymupdf.Rect(box)
            p.draw_rect(region, color=None, fill=(1, 1, 1), overlay=True)
            p.show_pdf_page(region, original, index, clip=region)
            pix = src.get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False)
            for block in src.get_text('dict')['blocks']:
                if block['type'] != 0:
                    continue
                for line in block['lines']:
                    for span in line['spans']:
                        key = unicodedata.normalize('NFKC', span['text']).strip()
                        r = pymupdf.Rect(span['bbox'])
                        if key not in mapping or not region.contains(r):
                            continue
                        sample_x = max(0, min(pix.width - 1, int((r.x0 + 1) * 2)))
                        sample_y = max(0, min(pix.height - 1, int((r.y0 - .5) * 2)))
                        fill = tuple(v / 255 for v in pix.pixel(sample_x, sample_y))
                        p.draw_rect(r, color=None, fill=fill, overlay=True)
                        rotation = 90 if abs(line['dir'][0]) < .5 else 0
                        width = FONT.text_length(mapping[key], fontsize=6.2) + 2
                        if rotation:
                            target = pymupdf.Rect(r.x0 - 2, (r.y0+r.y1-width)/2,
                                                 r.x1 + 3, (r.y0+r.y1+width)/2 + 2)
                        else:
                            width = max(width, r.width + 2)
                            target = pymupdf.Rect((r.x0+r.x1-width)/2, r.y0 - 1,
                                                 (r.x0+r.x1+width)/2, r.y0 + 12)
                        foreground = tuple(((span['color'] >> shift) & 255) / 255 for shift in (16, 8, 0))
                        f = text_box(p, target, mapping[key], size=6.2, color=foreground, rotate=rotation)
                        edits.append({'page': index + 1, 'source': key, 'translation': mapping[key], 'mask': list(r), 'font_pt': f})
        # Raster plot labels: explicitly reviewed masks leave plotted data/ticks intact.
        p = doc[8]
        for key, mask, target, rotation in [
            ('The Frequency of Reflection Words', (116.5, 66, 125.5, 196), (114, 66, 130, 196), 90),
            ("The Frequency of Word 'Wait'", (307, 66, 317, 196), (305, 66, 321, 196), 90),
            ('Steps', (212, 213, 235, 222), (202, 211, 244, 225), 0),
            ('Steps', (401, 213, 428, 222), (393, 211, 441, 225), 0)]:
            p.draw_rect(pymupdf.Rect(mask), color=None, fill=(1, 1, 1), overlay=True)
            f = text_box(p, target, mapping[key], 7, rotate=rotation)
            edits.append({'page':9, 'source':key, 'translation':mapping[key], 'mask':mask, 'font_pt':f})
        # Raster PPO/GRPO nodes: coordinates are paper-specific, never inferred OCR.
        p, src = doc[9], original[9]
        pix = src.get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False)
        nodes = [('Policy Model',(113.5,84.5,169,103)), ('Reference Model',(234,54,290,72)),
                 ('Reward Model',(234,76,290,93)), ('Value Model',(234,98,290,114)),
                 ('Policy Model',(113.5,165,169,182)), ('Reference Model',(234,142,290,159)),
                 ('Reward Model',(234,164,290,180)), ('Group Computation',(356,163,399,178)),
                 ('Trained Models',(478,99,527,121)), ('Frozen Models',(478,132,527,154))]
        for key, box in nodes:
            r = pymupdf.Rect(box)
            samples = [pix.pixel(int(x*2),int(y*2)) for x in range(int(r.x0)+2,int(r.x1)-2,2)
                       for y in range(int(r.y0)+2,int(r.y1)-2,2)]
            fill = tuple(v / 255 for v in Counter(samples).most_common(1)[0][0])
            p.draw_rect(r, color=None, fill=fill, overlay=True)
            f = text_box(p,r,mapping[key],7.5)
            edits.append({'page':10,'source':key,'translation':mapping[key],'mask':box,'font_pt':f})
        # Translate complete cross-column captions before distributing a/b panels.
        # The original stream breaks "human participants" between two columns.
        # Independent paragraph slots otherwise leave a dangling Chinese fragment.
        for row in catalog['rows']:
            if row.get('kind') != 'caption' or row.get('page') not in (2,9):
                continue
            number=row['page'];p=doc[number-1]
            boundary=re.search(r'b[，,.、：:]\s*',row['translation'])
            if not boundary:
                raise ValueError('Reviewed caption has no b-panel boundary')
            first=row['translation'][:boundary.start()].strip()
            second=row['translation'][boundary.start():].strip()
            y0,y1=(245,296) if number==2 else (230,301)
            p.draw_rect(pymupdf.Rect(39,y0,563,y1),color=None,fill=(1,1,1),overlay=True)
            left=text_box(p,(39.7,y0,296,y1),first,6.8,align=0)
            right=text_box(p,(306.1,y0,562,y1),second,6.8,align=0)
            edits.append({'page':number,'complete_caption_reflow':True,
                          'source_text_sha256':hashlib.sha256(row['source'].encode()).hexdigest(),
                          'translation_text_sha256':hashlib.sha256(row['translation'].encode()).hexdigest(),
                          'font_pt':[left,right]})
        # Preserve the original raster table; provide a complete Chinese transcription
        # beneath it rather than claiming its pixels were automatically OCR-translated.
        p = doc[10]
        p.draw_rect(pymupdf.Rect(39,227,555,461), color=None, fill=(.97,.98,1), overlay=True)
        text_box(p,(48,237,545,259),'扩展数据表 1：图片表格的中文译文',11)
        text_box(p,(48,266,545,284),mapping['PROMPT'],10)
        prompt_text = catalog['rows'][37]['translation'].replace('(6 3)₁₃','63（13 进制）')
        text_box(p,(48,288,545,373),prompt_text,10)
        text_box(p,(48,383,545,402),mapping['Evaluation'],10)
        text_box(p,(48,407,545,451),catalog['rows'][38]['translation'],10)
        note=('非官方英中翻译与排版修订样稿。原文：Guo et al., Nature 645, 633–638 (2025). '
              'DOI: 10.1038/s41586-025-09422-z。© The Author(s) 2025。许可：CC BY 4.0，'
              'https://creativecommons.org/licenses/by/4.0/。译文使用 gpt-6-luna；数学对象保留原字形，'
              '图内文字按审阅坐标替换，图片表格提供中文转录（基数下标改写为“13进制”说明，数学含义不变）；'
              '这些改动不表示作者或出版商认可。')
        text_box(p,(48,490,545,580),note,9)
        output.mkdir(parents=True, exist_ok=False)
        mono_path = output/'deepseek-r1.zh-CN.reviewed-candidate.mono.pdf'
        doc.subset_fonts()
        doc.save(mono_path, garbage=4, deflate=True)
        dual = pymupdf.open()
        for i, src in enumerate(original):
            page=dual.new_page(width=2*src.rect.width,height=src.rect.height)
            page.show_pdf_page(src.rect, original, i)
            page.show_pdf_page(pymupdf.Rect(src.rect.width,0,2*src.rect.width,src.rect.height),doc,i)
        dual.save(output/'deepseek-r1.en-zh.reviewed-candidate.dual.pdf',garbage=4,deflate=True)
        dual.close()
        (output/'region-edits.json').write_text(json.dumps({'source_sha256':SOURCE_HASH,'model':'gpt-6-luna','edits':edits,
            'font_sha256':hashlib.sha256(FONT_FILE.read_bytes()).hexdigest(),
            'notation_edit':'The raster-table transcription writes (6 3) subscript 13 as 63 (base 13), preserving its value and meaning.',
            'raster_table':'English raster retained; complete Chinese transcription added below; not automatic OCR.'},ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('mono',type=Path);p.add_argument('catalog',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--font-file',type=Path,required=True)
    a=p.parse_args();apply(a.source,a.mono,json.loads(a.catalog.read_text()),a.output,a.font_file)


if __name__=='__main__':
    main()
