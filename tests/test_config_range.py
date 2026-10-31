"""Optional settings, bounded recurrence windows and shared freshness policy."""
from datetime import date, timedelta
from unittest.mock import patch
import unittest
import test_multifeed as fixtures
from test_multifeed import m, g, A, B, ics, event, run_ui

class ConfigRange(unittest.TestCase):
 setUp=fixtures.MultiFeed.setUp
 tearDown=fixtures.MultiFeed.tearDown
 configure=fixtures.MultiFeed.configure
 store=fixtures.MultiFeed.store
 titles=fixtures.MultiFeed.titles
 def test_defaults_and_partial(self):
  self.configure(A)
  self.assertEqual(m['read_config']()[2],m['Settings']())
  for section,key,value in [('agenda','days_back',2),('agenda','days_forward',3),('refresh','minutes',4)]:
   self.configure(A)
   with self.config.open('a') as f:f.write(f'[{section}]\n{key}={value}\n')
   self.assertEqual(getattr(m['read_config']()[2],key),value)
 def test_invalid(self):
  for section,key,maximum in [('agenda','days_back',366),('agenda','days_forward',366),('refresh','minutes',10080)]:
   for value in ['true','false','0','-1','1.5','"30"','[]',str(maximum+1)]:
    self.config.write_text(f'[{section}]\n{key}={value}\n')
    with self.assertRaisesRegex(ValueError,section+'.'+key):m['read_config']()
  self.config.write_text('agenda=5')
  with self.assertRaises(ValueError):m['read_config']()
 def test_window_and_overlap(self):
  today=date.today();begin,end=m['Settings'](2,3).window()
  self.assertEqual((begin,end),(today-timedelta(days=2),today+timedelta(days=4)))
  data=ics(event('overlap',(begin-timedelta(days=10)).strftime('%Y%m%d'),extra='RRULE:FREQ=DAILY;COUNT=12',end=(begin-timedelta(days=7)).strftime('%Y%m%d')),
           event('outside',(end+timedelta(days=2)).strftime('%Y%m%d'),uid='outside'))
  items=m['parse_appointments'](m['parse_feed'](data),begin,end)
  self.assertTrue(items)
  self.assertTrue(any(x.start.date()<begin and x.end.date()>begin for x in items))
  self.assertNotIn('outside',[x.title for x in items])
 def test_shared_cli_policy_and_fallback(self):
  self.configure(A,B)
  with self.config.open('a') as f:f.write('[refresh]\nminutes=60\n')
  self.store(A,ics(event('fresh')),age=1800)
  self.store(B,ics(event('stale')),age=4000)
  with patch.dict(g,{'download_ics':lambda url: (_ for _ in ()).throw(OSError('offline'))}):
   query=m['next_feed']()
  self.assertEqual(self.titles(query),['fresh','stale'])
 def test_ui_range_and_interval_reload(self):
  self.configure(A);self.store(A,m['demo_ics'](),age=1800)
  async def check():
   app=m['CalTUI']()
   with patch.dict(g,{'download_ics':lambda url: m['demo_ics']()}):
    async with app.run_test(size=(100,35)) as pilot:
     await pilot.pause()
     app.settings=m['Settings'](2,3,60)
     self.assertEqual(app.settings.window(),(date.today()-timedelta(days=2),date.today()+timedelta(days=4)))
     app.render_view()
     self.assertFalse(app.settings.stale(app.feed_modified[A]))
  run_ui(check())

 def test_cli_beyond_agenda_window(self):
  import contextlib, io, json
  from datetime import datetime, timezone
  self.configure(A)
  with self.config.open('a') as f:f.write('[agenda]\ndays_forward=1\n')
  self.store(A,ics(event('Far future','20310101T100000Z')))
  with patch.dict(g,{'datetime':fixtures.FrozenDatetime}):
   for mode in ['--next','--waybar']:
    output=io.StringIO()
    with patch('sys.argv',['caltui',mode]),contextlib.redirect_stdout(output):g['main']()
    result=json.loads(output.getvalue())
    self.assertIn('Far future',str(result))
    output=io.StringIO()
    with patch('sys.argv',['caltui',mode,'--within','60']),contextlib.redirect_stdout(output):g['main']()
    self.assertNotIn('Far future',output.getvalue())

class LiveSettings(unittest.TestCase):
 from test_settings import SettingsUI as _Fixture
 setUp=_Fixture.setUp
 tearDown=_Fixture.tearDown
 editor=_Fixture.editor
 def test_reload_range_interval_invalid_and_unchanged(self):
  # Use the Settings fixture's module, whose globals its editor patches.
  from test_settings import m as sm, g as sg, A as url
  async def check():
   app=sm['CalTUI'](agenda=True)
   async with app.run_test(size=(100,24)) as pilot:
    await pilot.pause()
    state=(app.month,app.anchor)
    text='url="'+url+'"\n[agenda]\ndays_back=2\ndays_forward=3\n'
    with self.editor(app,text),patch.object(app,'load_feed') as refresh:
     await pilot.press('s');await pilot.pause();refresh.assert_not_called()
    self.assertEqual((app.settings.days_back,app.settings.days_forward),(2,3))
    self.assertEqual((app.month,app.anchor),state)
    old=app.feed_query;settings=app.settings
    with self.editor(app,text+'[refresh]\nminutes=true\n'),patch.object(app,'load_feed') as refresh,patch.object(app,'notify') as notify:
     await pilot.press('s');await pilot.pause();refresh.assert_not_called();notify.assert_called_once()
    self.assertEqual(app.settings,settings);self.assertIs(app.feed_query,old)
    app.feed_modified[url]=sg['clock'].time()-120
    calls=[]
    with self.editor(app,text+'[refresh]\nminutes=1\n'),patch.dict(sg,{'download_ics':lambda u:(calls.append(u),sm['demo_ics']())[1]}):
     await pilot.press('s');await app.workers.wait_for_complete();await pilot.pause()
    self.assertEqual(calls,[url]);self.assertEqual(app.settings.minutes,1)
    with self.editor(app),patch.object(app,'load_feed') as refresh:
     await pilot.press('s');await pilot.pause();refresh.assert_not_called()
  run_ui(check())
