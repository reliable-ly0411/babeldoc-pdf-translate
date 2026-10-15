#!/usr/bin/env python3
"""Screen mono translation PDFs; this never certifies semantic or formula accuracy."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import pymupdf

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def stats(page):
 text=page.get_text()
 images=page.get_image_info(hashes=True)
 return dict(characters=len(text),cjk_characters=sum('\u4e00'<=c<='\u9fff' for c in text),replacement_characters=text.count('\ufffd'),
             image_instances=len(images),image_digests=Counter(i['digest'].hex() for i in images),vector_paths=len(page.get_drawings()),
             numeric_tokens=Counter(re.findall(r'(?<![A-Za-z])[-−]?\d+(?:\.\d+)?',text)))

def audit(source,output,pages):
 with pymupdf.open(source) as src,pymupdf.open(output) as dst:
  selected=pages or list(range(1,len(src)+1))
  if len(selected)!=len(dst):raise ValueError('Expected mono pages to match the selected source pages')
  records=[]
  for i,number in enumerate(selected):
   a,b=stats(src[number-1]),stats(dst[i]);missing=a['image_digests']-b['image_digests']
   records.append(dict(source_page=number,output_page=i+1,source=a,output=b,missing_decoded_image_instances=sum(missing.values()),
                       dimensions_match=abs(src[number-1].rect.width-dst[i].rect.width)<2 and abs(src[number-1].rect.height-dst[i].rect.height)<2))
  return dict(source=source.name,source_sha256=digest(source),output=output.name,output_sha256=digest(output),pages=records,
              repaired=dst.is_repaired,note='Screening only. Image digests describe decoded raster resources, not vectors or text in images. Numeric extraction is not a formula correctness test. Visual and semantic review remain separate.')

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--pages');p.add_argument('--report',required=True,type=Path);a=p.parse_args()
 pages=[int(n) for n in a.pages.split(',')] if a.pages else None
 a.report.write_text(json.dumps(audit(a.source,a.output,pages),ensure_ascii=False,indent=2)+'\n')
