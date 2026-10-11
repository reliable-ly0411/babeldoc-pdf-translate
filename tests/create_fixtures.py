"""Public synthetic technical PDF fixtures; no personal documents."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw

import argparse

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("directory", type=Path)
DEST = p.parse_args().directory.resolve()
DEST.mkdir(parents=True, exist_ok=True)
c = canvas.Canvas(str(DEST / 'technical.pdf'), pagesize=(595, 842), invariant=1)
c.setTitle('Synthetic flight control validation fixture')
c.setAuthor('BabelDOC deployment experiment')

def heading(text, page):
    c.setFillColorRGB(.08, .16, .25)
    c.setFont('Helvetica-Bold', 20)
    c.drawString(48, 782, text)
    c.setFont('Helvetica', 9)
    c.drawString(48, 35, f'Synthetic test document | physical page {page}')
    c.setFillColorRGB(0, 0, 0)

def lines(text, x, y, font='Times-Roman', size=12):
    obj = c.beginText(x, y)
    obj.setFont(font, size)
    obj.setLeading(19)
    for line in text.split('\n'):
        obj.textLine(line)
    c.drawText(obj)

heading('Flight Control Experiment', 1)
lines('The controller improves flight stability. The phase margin is 45 degrees.\nThe landing gear remains retracted during the experiment.\nThe sampling rate is 100 Hz and the measured delay is 0.02 s.', 48, 730)
c.setFont('Helvetica-Bold', 14)
c.drawString(48, 630, 'Transfer function')
lines('G(s) = 1 / (s + 1)       K = 2.5       T = 0.02 s', 75, 591, 'Times-Italic', 16)
lines('Equation 1 describes a first-order system. Preserve all variable names,\nnumbers, units, and mathematical relationships in the translation.', 48, 545)
c.rect(160, 380, 240, 85, stroke=1, fill=0)
c.line(65, 422, 160, 422)
c.line(400, 422, 520, 422)
lines('Controller', 245, 415, 'Helvetica', 12)
lines('Figure 1. A vector block diagram of the controller.', 48, 340)
lines('Reference identifier: CTRL-2026-A. The source PDF must remain unchanged.', 48, 285)
c.showPage()

heading('Measurements and Parameters', 2)
lines('Table 1 summarizes the experiment. The voltage is 12.5 V.\nA negative offset of -0.25 m was measured at 20 degrees Celsius.', 48, 730)
rows = [('Parameter', 'Value', 'Unit'), ('Gain', '2.5', '-'),
        ('Sampling rate', '100', 'Hz'), ('Delay', '0.02', 's'),
        ('Voltage', '12.5', 'V')]
for i, row in enumerate(rows):
    y = 640 - i * 32
    c.rect(48, y-10, 495, 32, stroke=1, fill=0)
    c.line(278, y-10, 278, y+22)
    c.line(408, y-10, 408, y+22)
    for x, value in zip((60, 292, 421), row):
        lines(value, x, y, 'Helvetica-Bold' if i == 0 else 'Helvetica', 11)
lines('Safety note: this document contains invented measurements for testing.\nIt is not a flight procedure or a calibration certificate.', 48, 400)
lines('Configuration example: gain=2.5; sample_rate=100; mode=TEST', 48, 330, 'Courier', 10)
c.showPage()

heading('Figures and Two Columns', 3)
im = Image.new('RGB', (600, 180), '#e7eff5')
draw = ImageDraw.Draw(im)
draw.line([(20, 150), (100, 100), (200, 55), (300, 35), (450, 30), (580, 30)], fill='#17667e', width=6)
draw.text((25, 15), 'RASTER LABEL: KEEP IMAGE', fill='black')
im.save(DEST / 'plot.png')
c.drawImage(ImageReader(im), 48, 530, width=495, height=148.5)
lines('Figure 2. Step response with a preserved raster image.', 48, 506)
lines('The phase margin determines\nrobustness near the crossover\nfrequency. The controller should\nretain stable performance.', 48, 447)
lines('The landing gear is a separate\nmechanical assembly. Domain\nterms should use the approved\nglossary consistently.', 310, 447)
lines('This page checks column order, image preservation, and caption placement.', 48, 310)
c.showPage()
c.save()
(DEST / 'glossary.csv').write_text('source,target,tgt_lng\nphase margin,相位裕度,zh-CN\nlanding gear,起落架,zh-CN\ncontroller,控制器,zh-CN\n', encoding='utf-8')
(DEST / 'style.txt').write_text('Translate faithfully into Simplified Chinese. Preserve all numbers, units, formulas, identifiers and code. Use the supplied glossary.', encoding='utf-8')
print(DEST / 'technical.pdf')
