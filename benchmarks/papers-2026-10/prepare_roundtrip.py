"""Make explicit round-trip inputs from the fixed AI translation references.

BabelDOC intentionally rejects its own Producer marker. This benchmark makes a
new attributed copy for the user's requested reverse-language experiment. The
original reference stays intact; only Producer metadata changes, and every page
must render identically. Never run this implicitly in the translation adapter.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pymupdf

HERE = Path(__file__).resolve().parent
PAIRS = [
 ('roundtrip-swift-zh', 'full-swift-dsh/swift2023.no_watermark.zh-CN.mono.pdf', 'swift2023'),
 ('roundtrip-r1-zh', 'pilot-r1-codex/deepseekr1.no_watermark.zh-CN.mono.pdf', 'deepseekr1'),
 ('roundtrip-fr', 'fragment-en-fr-dsh/fragment-en.no_watermark.fr.mono.pdf', 'fragment-en'),
 ('roundtrip-ja', 'fragment-zh-ja-codex/fragment-zh.no_watermark.ja.mono.pdf', 'fragment-zh')]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pixels(page):return hashlib.sha256(page.get_pixmap(matrix=pymupdf.Matrix(.5,.5),alpha=False).samples).hexdigest()

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--destination',required=True,type=Path,help='New directory; fixed sources are never overwritten')
 parser.add_argument('--references',type=Path,default=HERE/'references')
 args=parser.parse_args()
 args.destination.mkdir(parents=True,exist_ok=False)
 records=[]
 for sid,reference,_ in PAIRS:
  src=args.references/reference;dst=args.destination/(sid+'.pdf')
  with pymupdf.open(src) as d:
   old=dict(d.metadata);expected=[pixels(p) for p in d]
   new=dict(old);new['producer']='Explicit round-trip benchmark input; AI translation originally produced by BabelDOC'
   d.set_metadata(new);d.save(dst,garbage=4,deflate=True)
  with pymupdf.open(dst) as d:
   if expected!=[pixels(p) for p in d]:raise RuntimeError('Metadata-only copy changed rendering: '+sid)
   pages=len(d)
  records.append(dict(id=sid,source='references/'+reference,source_sha256=sha(src),derived=dst.name,derived_sha256=sha(dst),changed_fields=['Producer'],old_producer=old.get('producer'),new_producer=new['producer'],pages=pages,render_identical=True,render_scale=.5))
 (args.destination/'roundtrip-preparation.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
