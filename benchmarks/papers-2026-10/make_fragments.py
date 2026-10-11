"""Create project-authored short multilingual controls; requires ReportLab."""
import argparse
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--destination',required=True,type=Path,help='New directory for generated sources and prompts')
args=parser.parse_args()
HERE=args.destination.resolve()
HERE.mkdir(parents=True,exist_ok=False)
(HERE/'sources').mkdir()
(HERE/'prompts').mkdir()
TEXT = {
 'fragment-en': ('Short flight-control translation fixture', [
  'The controller tracks a reference trajectory using feedback.',
  'A positive stability margin does not guarantee safety under every disturbance.',
  'The sampling rate is 100 Hz and the measured delay is 0.02 s.',
  'Keep the identifier CTRL-2026-A and the signed value -0.25 unchanged.',
  'The reinforcement learning policy minimizes tracking error.']),
 'fragment-zh': ('飞行控制短片段翻译测试', [
  '控制器使用反馈跟踪参考轨迹。',
  '正的稳定裕度不能保证在所有扰动下都安全。',
  '采样率为 100 Hz，测得的延迟为 0.02 s。',
  '标识符 CTRL-2026-A 和带符号数值 -0.25 必须保持不变。',
  '强化学习策略使跟踪误差最小化。'])}
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
for name,(title,lines) in TEXT.items():
 path=HERE/'sources'/(name+'.pdf')
 c=canvas.Canvas(str(path), pagesize=(612,792), invariant=1)
 c.setTitle(title);c.setAuthor('babeldoc-pdf-translate benchmark')
 font='STSong-Light' if name.endswith('zh') else 'Helvetica'
 c.setFont(font,18);c.drawString(48,730,title)
 c.setFont(font,12)
 for i,line in enumerate(lines):c.drawString(48,670-i*35,line)
 c.setFont('Courier',12);c.drawString(48,440,'J = 0.25 * e^2 + 0.02 * u^2')
 c.setFont('Helvetica',9);c.drawString(48,60,'Project-authored synthetic fixture. MIT. Not a quotation from a paper.')
 c.showPage();c.save()
 (HERE/'prompts'/(name+'.txt')).write_text(title+'\n'+'\n'.join(lines)+'\nJ = 0.25 * e^2 + 0.02 * u^2\n',encoding='utf-8')
