"""Reviewed R1 figure labels/raster-table supplement, not generic OCR support.

Original plots/images/equations come from the pinned source. Only catalogued
English label boxes are covered; curves, ticks, values and model IDs remain.
The original English page is retained in the bilingual output.
"""
import argparse
import hashlib
import html
import json
from collections import Counter
from pathlib import Path
import re
import unicodedata
import pymupdf

SOURCE_HASH = '916fdaafc3b44143a9744481d079744f773d73d06372f82b1dba1076525927f2'
FONT_FILE = None
FONT = None
ARCHIVED_MONO_SHA256 = 'd887f122016c263de4d7bc34cfca4d591fdd245309ff6642fc7e8fa1fc266a7c'


def checked_raster_transcription(catalog):
    """R1-specific source review guard, not general OCR or semantic validation.

    The fixed source's p11 image says least integer. The archived catalog had
    already transcribed largest before translation, so token/cache validation
    could not detect that meaning reversal. Refuse that known-invalid catalog.
    """
    rows = [r for r in catalog['rows'] if r['source'].startswith('Let b ≥ 2 be an integer.')]
    if len(rows) != 1 or 'Find the least integer' not in rows[0]['source']:
        raise ValueError('R1 p11 source transcription must match the reviewed raster: least integer')
    if '最小整数' not in rows[0]['translation'] or '最大整数' in rows[0]['translation']:
        raise ValueError('R1 p11 translation reverses least integer')
    return rows[0]['translation']


def require_unrepaired_input(doc):
    if any('非官方英中翻译与排版修订样稿' in page.get_text() for page in doc):
        raise ValueError('Use raw mono output; applying paper-region overlays twice is unsupported')


def correct_archived_transcription(source, mono, catalog, output, font_file):
    """One reviewed word correction on the exact archived R1 sample; never generic."""
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH or hashlib.sha256(mono.read_bytes()).hexdigest() != ARCHIVED_MONO_SHA256:
        raise ValueError('Expected the pinned source and exact archived R1 mono sample')
    checked_raster_transcription(catalog)
    locations = []
    with pymupdf.open(mono) as doc:
        page = doc[10]
        for block in page.get_text('rawdict')['blocks']:
            if block['type'] != 0:
                continue
            for line in block['lines']:
                for span in line['spans']:
                    text = ''.join(c['c'] for c in span['chars'])
                    start = text.find('最大整数')
                    if start >= 0:
                        chars = span['chars'][start:start+4]
                        rect = pymupdf.Rect(chars[0]['bbox'])
                        for char in chars[1:]:
                            rect |= pymupdf.Rect(char['bbox'])
                        locations.append((rect, chars[0]['origin'], span['size']))
        if len(locations) != 1:
            raise ValueError('Archived correction is ambiguous')
        rect, origin, size = locations[0]
        # Remove actual old glyphs, not just paint over a searchable wrong answer.
        page.add_redact_annot(rect, fill=False, cross_out=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        page.insert_text(origin, '最小整数', fontname='R1TRANSCRIPTFIX', fontfile=str(font_file), fontsize=size)
        output.mkdir(parents=True, exist_ok=False)
        result = output/'deepseek-r1.transcription-corrected.mono.pdf'
        doc.save(result, garbage=2, deflate=True)
    from visual_review import bilingual, regression_check
    if not regression_check(mono, result, 11, [rect], dpi=144):
        raise ValueError('Archived correction changed pixels outside the reviewed word')
    with pymupdf.open(result) as verified:
        if '最大整数' in verified[10].get_text() or '最小整数' not in verified[10].get_text():
            raise ValueError('Archived correction did not replace the actual text layer')
    bilingual(source, result, output/'deepseek-r1.transcription-corrected.dual.pdf')
    (output/'correction.json').write_text(json.dumps({'source_sha256':SOURCE_HASH,
        'input_mono_sha256':ARCHIVED_MONO_SHA256,'physical_page':11,'bbox':list(rect),
        'before':'最大整数','after':'最小整数','font_sha256':hashlib.sha256(font_file.read_bytes()).hexdigest(),
        'pixels_outside_word_equal_dpi':144,'kind':'Source-reviewed paper-specific correction; not automatic translation or generic OCR.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


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


def repair_p3_prose(source_page, page, font_file):
    """Two source-reviewed R1 corrections, with exact text/geometry guards.

    These repairs are deliberately outside the generic visual-review pipeline.
    The source SHA is checked by apply(); neither wording nor coordinates are
    proposed by a model. Delete old glyphs so an invisible wrong title cannot
    survive below a white rectangle.
    """
    source = re.sub(r'\s+', ' ', source_page.get_text())
    if ('conversational thinking process and language consistency.' not in source
            or 'An interesting' not in source or 'version of DeepSeek-R1-Zero' not in source):
        raise ValueError('Unexpected R1 p3 source prose')
    blocks = [b for b in page.get_text('blocks') if b[6] == 0]
    bodies = [b for b in blocks if all(s in b[4] for s in ('2.3.3', '2.4.4', 'SFT'))]
    titles = [b for b in blocks if all(s in b[4] for s in ('表', '顿悟时刻', 'DeepSeek-R1-Zero'))]
    if len(bodies) != 1 or len(titles) != 1:
        raise ValueError('Ambiguous R1 p3 prose/title blocks')
    body, title = bodies[0], titles[0]
    before = body[4].replace('\n', '').strip()
    if before.startswith('。随后'):
        after = '对话式思考过程和语言一致性' + before
    elif before.startswith('和语言一致性。随后'):
        after = '对话式思考过程' + before
    elif before.startswith('对话式思考过程和语言一致性。随后'):
        after = before
    else:
        raise ValueError('Unreviewed R1 p3 paragraph prefix; manual review required')
    bold = font_file.with_name(font_file.name.replace('-Regular', '-Bold'))
    if bold == font_file or not bold.is_file():
        raise ValueError('Matching bold serif font is required for the R1 table title')
    specs = [(body, after, pymupdf.Rect(body[0], body[1] - .5, 294, 416), font_file, 8.25, 'R1P3BODY'),
             (title, '表 1 | DeepSeek-R1-Zero 中间版本的一个有趣“顿悟时刻”',
              pymupdf.Rect(title[0], title[1] - .5, 294, 72), bold, 9, 'R1P3TITLE')]
    edits = []
    for block, replacement, target, font, size, alias in specs:
        old = pymupdf.Rect(block[:4])
        if not (39 <= old.x0 < 42 and old.x1 <= 295 and target.contains(old)):
            raise ValueError('R1 p3 prose moved outside its reviewed column')
        page.add_redact_annot(old, fill=False, cross_out=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        # Redaction rebuilds page resources. Create the new shape afterwards;
        # a pre-redaction shape can retain a stale font resource and emit garbage.
        if alias == 'R1P3BODY':
            css = ('@font-face {font-family: R1ReviewSerif; src: url("' + font.name + '");}'
                   'body {margin:0; font-family:R1ReviewSerif; font-size:8.25pt; line-height:1.5;}')
            spare, scale = page.insert_htmlbox(target, '<div>' + html.escape(replacement) + '</div>',
                                               css=css, archive=pymupdf.Archive(str(font.parent)), scale_low=1)
            if spare < 0 or scale != 1:
                raise ValueError('R1 p3 correction does not fit without shrinking')
        else:
            shape = page.new_shape()
            remaining = shape.insert_textbox(target, replacement, fontname=alias,
                                             fontfile=str(font), fontsize=size, lineheight=1.5)
            if remaining < 0:
                raise ValueError('R1 p3 correction does not fit without shrinking')
            shape.commit()
        edits.append({'page': 3, 'kind': 'source-reviewed-prose', 'bbox': list(target),
                      'before': block[4], 'after': replacement, 'font_pt': size,
                      'source': 'conversational thinking process and language consistency.'
                                if alias == 'R1P3BODY' else 'Table 1 title, complete source phrase',
                      'automatic': False})
    return edits


# Tight interiors of the ten raster labels on this exact R1 source. The old
# catalog used whole-node masks that crossed rounded borders. The new masks
# leave the original frame, arrows and surrounding raster pixels untouched.
R1_NODE_LABELS = [
    ('Policy Model', (116, 87, 166, 100.5)),
    ('Reference Model', (237, 55.6, 288, 72.2)),
    ('Reward Model', (237, 77, 288, 93.5)),
    ('Value Model', (237, 99.5, 288, 112.8)),
    ('Policy Model', (116, 165, 166, 178.2)),
    ('Reference Model', (236, 142.5, 287.5, 158.7)),
    ('Reward Model', (236, 164, 287.5, 179.5)),
    ('Group Computation', (357.5, 163, 397.3, 179.5)),
    ('Trained Models', (480.7, 101, 525.3, 119.3)),
    ('Frozen Models', (480, 131, 523.3, 148.5)),
]


def centered_raster_label(page, rect, text, fill):
    size = min(7.5, (rect.width - 1) / FONT.text_length(text, fontsize=1))
    if size < 6 or (FONT.ascender - FONT.descender) * size > rect.height:
        raise ValueError('R1 raster label cannot fit its frame-safe interior')
    width = FONT.text_length(text, fontsize=size)
    origin = (rect.x0 + (rect.width - width) / 2,
              (rect.y0 + rect.y1 + (FONT.ascender + FONT.descender) * size) / 2)
    page.draw_rect(rect, color=None, fill=fill, overlay=True)
    page.insert_text(origin, text, fontname='R1CJK', fontfile=str(FONT_FILE), fontsize=size)
    return size


def repair_r1_caption_and_metadata(original, doc, catalog, font_file):
    """Use the already-reviewed complete caption, not two translated fragments."""
    edits = []
    rows = [r for r in catalog['rows'] if r.get('kind') == 'caption' and r.get('page') == 10]
    if len(rows) != 1 or 'proposed GRPO for RL-based training.' not in rows[0]['source']:
        raise ValueError('Expected the complete reviewed R1 p10 caption')
    text = rows[0]['translation']
    boundary = 'GRPO 直接根据组内奖励分布估计优势。'
    if text.count(boundary) != 1:
        raise ValueError('R1 p10 caption has no unambiguous cross-column boundary')
    split = text.index(boundary)
    parts = [text[:split], text[split:]]
    page = doc[9]
    blocks = [b for b in page.get_text('blocks') if b[6] == 0 and 'GRPO' in b[4] and 205 < b[1] < 215]
    if len(blocks) != 2:
        raise ValueError('Unexpected R1 p10 caption geometry')
    for block in blocks:
        page.add_redact_annot(pymupdf.Rect(block[:4]), fill=False, cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    bold = font_file.with_name(font_file.name.replace('-Regular', '-Bold'))
    css = ('@font-face {font-family:R1Caption; src:url("' + font_file.name + '");}'
           '@font-face {font-family:R1Caption; font-weight:bold; src:url("' + bold.name + '");}'
           'body {margin:0; font-family:R1Caption; font-size:7pt; line-height:1.35;}')
    for i, (part, box) in enumerate(zip(parts, [(39.7,210,296,290),(306.1,210,562,290)])):
        content = html.escape(part)
        if i == 0:
            title, rest = content.split('。', 1)
            content = '<b>' + title + '。</b>' + rest
        spare, scale = page.insert_htmlbox(pymupdf.Rect(box), content, css=css,
                                           archive=pymupdf.Archive(str(font_file.parent)), scale_low=1)
        if spare < 0 or scale != 1:
            raise ValueError('R1 p10 complete caption does not fit without shrinking')
    edits.append({'page':10,'kind':'complete-reviewed-caption','automatic':False,
                  'source_sha256':hashlib.sha256(rows[0]['source'].encode()).hexdigest(),
                  'translation_sha256':hashlib.sha256(text.encode()).hexdigest(),
                  'font_pt':7,'columns':2})
    # <think> is literal example content in the source, not a word to translate.
    page = doc[2]
    if 'Response: <think>' not in original[2].get_text():
        raise ValueError('Unexpected R1 thinking-marker source')
    hits = page.search_for('<思考>')
    if len(hits) != 1:
        raise ValueError('Expected exactly one mistranslated R1 thinking marker')
    rect = hits[0]
    size = 7
    target = pymupdf.Rect(rect)
    target.x1 = max(target.x1,target.x0+FONT.text_length('<think>',fontsize=size)+.5)
    if target.x1 > 100 or target.x1-rect.x1 > 8 or not 90 < rect.y0 < 103:
        raise ValueError('R1 thinking marker moved outside its reviewed table row')
    page.add_redact_annot(rect, fill=False, cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    page.insert_text((rect.x0,rect.y0+FONT.ascender*size),'<think>',fontname='R1THINK',
                     fontfile=str(font_file),fontsize=size)
    edits.append({'page':3,'kind':'literal-source-marker','before':'<思考>','after':'<think>',
                  'bbox':list(target),'automatic':False})
    # Bibliographic footers are explicitly retained by the R1 job prompt.
    for i, src in enumerate(original):
        footer = pymupdf.Rect(0,752,src.rect.width,src.rect.height)
        if not src.get_text(clip=footer).strip():
            continue
        page=doc[i]
        page.add_redact_annot(footer,fill=(1,1,1),cross_out=False)
        page.apply_redactions(images=0,graphics=0,text=0)
        page.show_pdf_page(footer,original,i,clip=footer)
        edits.append({'page':i+1,'kind':'source-bibliographic-footer','bbox':list(footer),
                      'automatic':False})
    return edits


def apply(source, mono, catalog, output, font_file):
    global FONT_FILE, FONT
    FONT_FILE = font_file.resolve()
    FONT = pymupdf.Font(fontfile=str(FONT_FILE))
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError('Source does not match the fixed 11-page Nature R1')
    reviewed_prompt = checked_raster_transcription(catalog)
    mapping = {r['source']: r['translation'] for r in catalog['rows']}
    edits = []
    with pymupdf.open(source) as original, pymupdf.open(mono) as doc:
        if len(original) != 11 or len(doc) != 11:
            raise ValueError('Expected all 11 source/translated pages')
        require_unrepaired_input(doc)
        edits.extend(repair_p3_prose(original[2], doc[2], FONT_FILE))
        edits.extend(repair_r1_caption_and_metadata(original, doc, catalog, FONT_FILE))
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
        for key, box in R1_NODE_LABELS:
            r = pymupdf.Rect(box)
            samples = [pix.pixel(int(x*2),int(y*2)) for x in range(int(r.x0)+2,int(r.x1)-2,2)
                       for y in range(int(r.y0)+2,int(r.y1)-2,2)]
            fill = tuple(v / 255 for v in Counter(samples).most_common(1)[0][0])
            f = centered_raster_label(p, r, mapping[key], fill)
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
        prompt_text = reviewed_prompt.replace('(6 3)₁₃','63（13 进制）')
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
    p.add_argument('--correct-archived-transcription-only',action='store_true')
    a=p.parse_args()
    action = correct_archived_transcription if a.correct_archived_transcription_only else apply
    action(a.source,a.mono,json.loads(a.catalog.read_text(encoding='utf-8')),a.output,a.font_file)


if __name__=='__main__':
    main()
