from test_multifeed import run_ui
from pathlib import Path
"""Run with python test_contrast.py; no network or terminal required."""
import asyncio
import random
import runpy
from rich.style import Style
from textual._xterm_parser import XTermParser
from textual import events

m=runpy.run_path(str(Path(__file__).resolve().parents[1] / 'caltui'))
def palette(fg,bg,blue,cyan,white):
 return dict(zip(('10','11','4;4','4;6','4;15'),(fg,bg,blue,cyan,white)))
palettes=[
 palette((230,235,245),(16,22,38),(45,70,110),(120,200,220),(255,255,255)),
 palette((30,30,30),(245,245,245),(170,190,225),(0,90,110),(255,255,255)),
 palette((125,125,125),(128,128,128),(120,120,120),(130,130,130),(125,125,125)),
 palette((255,255,255),(0,0,0),(0,0,100),(0,255,255),(255,255,255)),
]
random.seed(42)
palettes += [palette(*(tuple(random.randrange(256) for _ in range(3)) for _ in range(5))) for _ in range(200)]
for p in palettes:
 colors=m['text_colors'](p)
 for name,color in colors.items():
  bg=p['4;4'] if name=='selection' else p['11']
  assert m['contrast'](color,bg)>=4.5,(name,color,bg)
 for role,key,bg in [('primary','10','11'),('accent','4;6','11'),('selection','4;15','4;4')]:
  if m['contrast'](p[key],p[bg])>=4.5:
   assert colors[role]==p[key]
 secondary=colors['secondary']
 for step in range(256):
  candidate=m['blend'](p['11'],colors['primary'],step)
  if candidate==secondary: break
  assert m['contrast'](candidate,p['11'])<4.5
assert abs(m['contrast']((0,0,0),(255,255,255))-21)<1e-12
assert m['luminance']((0,0,0))==0

# Fragmentation, both OSC terminators, valid keys, mouse, and bracketed paste.
reply='\x1b]10;rgb:eeee/aaaa/0000\x1b\\'
reply2='\x1b]11;rgb:ff/ff/ff\a'
raw='c'+reply+'\x1b[C'+reply2+'\x1b[<0;4;5M'+'a'
expected='c\x1b[C\x1b[<0;4;5Ma'
for cut in range(len(raw)+1):
 reports=[]; filt=m['ColorReplies'](reports.append)
 assert filt.feed(raw[:cut])+filt.feed(raw[cut:])==expected
 assert [(r.key,r.color) for r in reports]==[('10',(238,170,0)),('11',(255,255,255))]
filt=m['ColorReplies'](lambda _: (_ for _ in ()).throw(AssertionError('paste parsed')))
paste='\x1b[200~'+reply+'abc\x1b[201~'
assert ''.join(filt.feed(c) for c in paste)==paste
filt=m['ColorReplies'](lambda _: None)
assert filt.feed('\x1b]10;rgb:'+'r'*10000+'\a'+'q')=='q'
assert len(filt.pending)<256
filt.feed('\x1b]10;rgb:')
filt.since-=1
assert filt.tick()==''
assert filt.feed('q')=='q', 'unterminated response captured keyboard input'
parser=XTermParser()
messages=list(parser.feed(expected))
assert [e.key for e in messages if isinstance(e,events.Key)]==['c','right','a']
assert any(isinstance(e,events.MouseDown) for e in messages)

async def ui():
 app=m['CalTUI'](demo=True,agenda=True)
 async with app.run_test(size=(100,24)) as pilot:
  for p in palettes[:4]:
   app.apply_palette(p); await pilot.pause()
   assert app.query_one('#status').styles.color.hex==app.secondary.upper()
   for page in app.pages:
    for span in page.spans:
     style=Style.parse(span.style) if isinstance(span.style,str) else span.style
     if style.color:
      rgb=tuple(style.color.get_truecolor())
      assert m['contrast'](rgb,p['11'])>=4.5
   assert app.secondary in str(app.pages[0].spans)
  # A dense day fills every page exactly, so the reserved row cannot be
  # accidentally supplied by spare lines in a short demo agenda.
  rows=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//contrast test//EN']
  today=m['date'].today()
  for i in range(100):
   start=m['datetime'].combine(today,m['time'](8))+m['timedelta'](minutes=i)
   end=start+m['timedelta'](minutes=1)
   rows += ['BEGIN:VEVENT',f'UID:dense-{i}',f'DTSTART:{start:%Y%m%dT%H%M%S}',
            f'DTEND:{end:%Y%m%dT%H%M%S}','SUMMARY:Appointment','END:VEVENT']
  rows+=['END:VCALENDAR']
  app.feed_query=m['parse_feed'](('\r\n'.join(rows)+'\r\n').encode())
  app.render_view();await pilot.pause()
  for size in [(120,35),(100,24),(60,35),(60,20),(45,18),(36,27),(91,19),(20,10),(5,4),(100,24)]:
   await pilot.resize_terminal(*size); await pilot.pause()
   body=app.query_one('#agenda-body');status=app.query_one('#status');keys=app.query_one('#keys')
   assert keys.region.bottom==size[1]
   assert status.region.bottom==keys.region.y
   if size[1]>=6:
    assert body.region.bottom <= status.region.y-1,(size,body.region,status.region)
   if body.content_size.width>=24 and body.content_size.height>=3:
    assert any(len(page.plain.splitlines())==body.content_size.height for page in app.pages)
    # Pages are complete appointments, including each location on the same page.
    for page in app.pages:
     lines=page.plain.splitlines()
     assert len(lines)<=body.content_size.height
     for i,line in enumerate(lines):
      if '↳' in line:
       assert i>0 and lines[i-1].strip() and '↳' not in lines[i-1]
  # A theme update doesn't change navigation or the page's first appointment.
  await pilot.resize_terminal(60,35);await pilot.pause()
  await pilot.press('down');await pilot.pause()
  state=(app.view,app.month,app.anchor,app.page_starts[app.page])
  for key,color in palettes[0].items(): app.post_message(m['PaletteReport'](key,color))
  await pilot.pause()
  assert state==(app.view,app.month,app.anchor,app.page_starts[app.page])
run_ui(ui())
print('204 palettes, OSC/input separation, live palette messages and footer geometry passed')
