"""Corpus-specific PDF evidence checks; this utility never edits a PDF.

L1Quad v2 p5: compare complete V0 arguments, original B/macron geometry,
delimited Roman math calls and comparison-sentence formula/reference spelling. Rendered review remains
mandatory. These checks do not certify the whole paper or translation meaning.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
import sys
import pymupdf as fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import math_operators

SOURCE_SHA256='94dd7e348e662de63ef01c4cd6c6529b37c464464df989ef3ced35e0f44cb7f3'


def compact(text):return re.sub(r'\s+','',unicodedata.normalize('NFC',text))


def v0_arguments(text):
    text=compact(text);match=re.search(r'V0=V\(',text)
    if not match:raise ValueError('V0_DEFINITION_NOT_EXTRACTABLE')
    start=match.end();depth=1;parts=[];last=start
    for n in range(start,len(text)):
        symbol=text[n]
        if symbol=='(':depth+=1
        elif symbol==')':
            depth-=1
            if not depth:
                parts.append(text[last:n]);return parts
        elif symbol==',' and depth==1:
            parts.append(text[last:n]);last=n+1
    raise ValueError('V0_DEFINITION_UNCLOSED')


def bar_bindings(page):
    anchors=page.search_for('(19)')
    # This printed equation label is unique in the pinned source page.
    if len(anchors)!=1:raise ValueError('EQUATION19_ANCHOR_AMBIGUOUS')
    anchor=anchors[0];half=page.rect.width/2
    x0=0 if anchor.x0<half else half
    area=fitz.Rect(x0,anchor.y1+1,x0+half,min(page.rect.height,anchor.y1+100))
    chars=[]
    for block in page.get_text('rawdict')['blocks']:
        if block['type']!=0:continue
        for line in block['lines']:
            for span in line['spans']:
                for char in span['chars']:
                    if area.contains(fitz.Point(char['origin'])):
                        chars.append({**char,'font':span['font'],'size':span['size']})
    marks=[c for c in chars if c['c'] in {'¯','ˉ','‾','\u0304'}]
    bases=[c for c in chars if c['c']=='B'];result=[];used=set()
    for mark in sorted(marks,key=lambda c:(c['origin'][1],c['origin'][0])):
        options=[]
        for n,base in enumerate(bases):
            dx=(mark['origin'][0]-base['origin'][0])/base['size']
            dy=(mark['origin'][1]-base['origin'][1])/base['size']
            if abs(dx)<.7 and -.8<dy<0:options.append((n,base,dx,dy))
        if len(options)!=1 or options[0][0] in used:
            raise ValueError('BAR_BASE_BINDING_AMBIGUOUS_OR_MISSING')
        n,base,dx,dy=options[0];used.add(n)
        result.append({'bar_origin':list(mark['origin']),'base_origin':list(base['origin']),
            'base_font':base['font'],'base_size':base['size'],
            'normalized_dx':dx,'normalized_dy':dy})
    return result


def audit(source,target,target_page=5):
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_SHA256:raise ValueError('SOURCE_HASH_CHANGED')
    report={'source_sha256':SOURCE_SHA256,'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'source_physical_page':5,'target_physical_page':target_page,'checks':{},
        'scope':'Pinned L1Quad v2 p5 checks only. Not a whole-page/paper or semantic acceptance certificate.'}
    with fitz.open(source) as original,fitz.open(target) as translated:
        a,b=original[4],translated[target_page-1];left,right=a.get_text(),b.get_text()
        for name,fn in [('v0_arguments',v0_arguments),('bar_bindings',None)]:
            try:
                before,after=(fn(left),fn(right)) if fn else (bar_bindings(a),bar_bindings(b))
                if fn:passed=len(before)==4 and before==after
                else:
                    passed=len(before)==len(after)==2 and all(
                        math.isclose(x[key],y[key],abs_tol=.003)
                        for x,y in zip(before,after) for key in ('normalized_dx','normalized_dy'))
                report['checks'][name]={'passed':passed,'source':before,'target':after}
            except ValueError as error:report['checks'][name]={'passed':False,'error_code':str(error)}
        source_text,target_text=compact(left),compact(right)
        operators=math_operators.audit(a,b)
        report['checks']['roman_operator_calls']={'passed':operators['passed'],
            'source':[c['signature'] for c in operators['source']],
            'target':[c['signature'] for c in operators['target']],
            'missing':operators['missing'],'extra':operators['extra'],'not_checked':operators['not_checked']}
        # Spelling/order comes from the actual source, not a regenerated formula.
        assignment=re.search(r'\(σm\)1=\(m−mreal\)fb/mreal',source_text)
        report['checks']['comparison_assignment']={'passed':bool(assignment and assignment.group() in target_text),
            'expected':assignment.group() if assignment else None}
        report['checks']['printed_references']={'passed':all(source_text.count(tag)==target_text.count(tag) for tag in ('(1b)','(13)')),
            'source':{tag:source_text.count(tag) for tag in ('(1b)','(13)')},
            'target':{tag:target_text.count(tag) for tag in ('(1b)','(13)')}}
    report['passed']=all(row['passed'] for row in report['checks'].values())
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('target',type=Path);parser.add_argument('report',type=Path)
    parser.add_argument('--target-page',type=int,default=5)
    args=parser.parse_args();report=audit(args.source,args.target,args.target_page)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'passed':report['passed'],'checks':{k:v['passed'] for k,v in report['checks'].items()}}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
