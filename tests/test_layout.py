from test_multifeed import run_ui
from pathlib import Path
import asyncio, runpy
m=runpy.run_path(str(Path(__file__).resolve().parents[1] / 'caltui'))
async def test():
 app=m['CalTUI'](demo=True)
 async with app.run_test(size=(120,35)) as pilot:
  for size,mode in [((120,35),'wide'),((100,24),'wide'),((60,35),'stacked'),((60,20),'compact'),((45,18),'compact'),((20,10),'compact'),((120,35),'wide')]:
   await pilot.resize_terminal(*size)
   await pilot.pause()
   print(size,app.layout_mode,app.query_one('#calendar').size,app.query_one('#agenda-body').content_size,len(app.pages),app.page)
   assert app.layout_mode==mode
   if mode!='compact':
    assert app.query_one('#calendar').display and app.query_one('#agenda').display
    assert app.query_one('#agenda-body').content_size==app._agenda_size
  await pilot.press('right'); await pilot.pause()
  assert app.month==m['month_shift'](m['date'].today().replace(day=1),1)
  month=app.month
  await pilot.press('a','c'); assert app.month==month
  day=next(c for c in app.query('.day') if c.day is not None)
  chosen=day.day
  await pilot.click(day); await pilot.pause()
  assert app.anchor==chosen and app.query_one('#calendar').display
  await pilot.press('down'); await pilot.pause()
  assert app.page>0
  anchor,month=app.anchor,app.month
  for size in [(60,35),(60,20),(45,18),(100,24)]:
   await pilot.resize_terminal(*size); await pilot.pause()
   assert (app.anchor,app.month)==(anchor,month)
  await pilot.press('t'); assert app.anchor==m['date'].today()
  await pilot.resize_terminal(60,20); await pilot.pause()
  await pilot.press('a'); await pilot.pause()
  assert app.view=='agenda' and not app.query_one('#calendar').display
  await pilot.press('down','up','c'); await pilot.pause()
  assert app.view=='calendar' and not app.query_one('#agenda').display
  await pilot.press('q')
run_ui(test())

async def check_geometry():
 app=m['CalTUI'](demo=True, agenda=True)
 app.load_feed=lambda: (_ for _ in ()).throw(AssertionError('network worker invoked'))
 async with app.run_test(size=(60,35)) as pilot:
  nodes=list(app.query('*'))
  for size in [(91,18),(90,26),(36,26),(60,20),(45,18),(20,10),(5,4),(120,35)]:
   await pilot.resize_terminal(*size); await pilot.pause()
   assert nodes==list(app.query('*')), 'widget tree recreated'
   if app.layout_mode!='compact':
    headings=list(app.query('#weekdays Static'))
    cells=list(app.query('.day'))
    assert [w.region.x for w in headings]==[w.region.x for w in cells[:7]]
   body=app.query_one('#agenda-body')
   if body.content_size.width>=24 and body.content_size.height>=3:
    for page in app.pages:
     assert len(page.plain.splitlines())<=body.content_size.height
     assert all(len(line)<=body.content_size.width for line in page.plain.splitlines())
  await pilot.resize_terminal(60,35); await pilot.pause()
  await pilot.press('down'); await pilot.pause()
  position=app.page_starts[app.page]
  await pilot.resize_terminal(20,10); await pilot.pause()
  await pilot.resize_terminal(60,35); await pilot.pause()
  assert app.page_starts[app.page]==position
  await pilot.press('r'); await pilot.pause()
  assert app.view=='agenda'
run_ui(check_geometry())
