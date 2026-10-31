"""Local multi-source fixtures, private cache migration and TUI integration."""
import asyncio
import contextlib
from datetime import date, datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import threading
import unittest
from unittest.mock import patch

m=runpy.run_path(str(Path(__file__).resolve().parents[1] / 'caltui'));g=m['main'].__globals__
A='https://example.test/work.ics?token=secret-a'
B='https://example.test/personal.ics?token=secret-b'
C='https://example.test/other.ics?token=secret-c'
NOW=datetime(2030,1,1,9,tzinfo=timezone.utc)
class DatetimeMeta(type):
 def __instancecheck__(cls,obj):return isinstance(obj,datetime)
class FrozenDatetime(datetime,metaclass=DatetimeMeta):
 @classmethod
 def now(cls,tz=None):return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

def ics(*components):
 return ('\r\n'.join(['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//multi test//EN',*components,'END:VCALENDAR'])+'\r\n').encode()
def event(title,start='20300101T100000Z',uid='same',extra='',end=''):
 return '\r\n'.join(['BEGIN:VEVENT','UID:'+uid,'DTSTART:'+start,
                      *(['DTEND:'+end] if end else []),'SUMMARY:'+title,extra,'END:VEVENT'])
def snapshot(title,hour=10):return ics(event(title,f'20300101T{hour:02d}0000Z'))

def run_ui(coro):
 # This host's Python 3.14 can leave executor shutdown asleep after its future
 # completes (also with plain to_thread). A timer wakes the test loop only.
 def loop_factory():
  loop=asyncio.new_event_loop()
  def tick():loop.call_later(.05,tick)
  loop.call_soon(tick)
  return loop
 with asyncio.Runner(loop_factory=loop_factory) as runner:runner.run(coro)


class MultiFeed(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.config=self.root/'config.toml';self.cache=self.root/'cache'/'calendar.ics'
  self.patch=patch.dict(g,{'CONFIG':self.config,'CACHE':self.cache});self.patch.start()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def configure(self,*urls,legacy=None):
  text=('url = '+json.dumps(legacy)+'\n' if legacy is not None else '')
  text+=''.join('[[calendars]]\nurl = '+json.dumps(url)+'\n' for url in urls)
  self.config.write_text(text)
 def store(self,url,data,age=0):
  m['save_private_cache'](data,url)
  os.utime(m['cache_path'](url),(g['clock'].time()-age,)*2)
 def titles(self,query):
  return [a.title for a in m['parse_appointments'](query,date(2030,1,1),date(2030,1,6))]
 def test_config_legacy_and_multiple(self):
  self.configure(B,'',A,C,'  ',B,legacy=A)
  self.assertEqual(m['subscription_urls'](),([A,B,C],A))
 def test_config_no_subscriptions(self):
  self.assertEqual(m['subscription_urls'](),([],''))
  self.configure('',' ')
  self.assertEqual(m['subscription_urls'](),([],''))
  with self.assertRaises(ValueError):m['next_feed']()
 def test_config_invalid(self):
  for value in ['url="http://bad"','[[calendars]]\nurl="ftp://bad"','calendars="bad"']:
   self.config.write_text(value)
   with self.assertRaises(ValueError):m['subscription_urls']()
 def test_legacy_download_and_migration(self):
  self.configure(legacy=A)
  m['save_private_cache'](snapshot('Legacy'))
  oldtime=self.cache.stat().st_mtime
  with patch.dict(g,{'download_ics':lambda _:self.fail('fresh legacy cache downloaded')}):
   query=m['next_feed']()
  self.assertEqual(self.titles(query),['Legacy'])
  self.assertFalse(self.cache.exists())
  path=m['cache_path'](A)
  self.assertEqual(path.stat().st_mtime,oldtime)
  self.assertEqual(path.stat().st_mode & 0o777,0o600)
  self.assertEqual(path.read_bytes(),snapshot('Legacy'))
 def test_migration_root_plus_array(self):
  self.configure(B,legacy=A);m['save_private_cache'](snapshot('Legacy',11))
  self.store(B,snapshot('Personal',10))
  with patch.dict(g,{'download_ics':lambda _:self.fail('fresh cache downloaded')}):
   self.assertEqual(self.titles(m['next_feed']()),['Personal','Legacy'])
 def test_migration_does_not_overwrite_new_snapshot(self):
  self.configure(legacy=A);m['save_private_cache'](snapshot('Old'));self.store(A,snapshot('New'))
  self.assertEqual(self.titles(m['next_feed']()),['New'])
 def test_three_interleaved_and_duplicate_uids(self):
  self.configure(A,B,A,C)
  fixtures={A:snapshot('Middle',11),B:snapshot('First',10),C:snapshot('Last',12)};calls=[]
  def download(url):calls.append(url);return fixtures[url]
  with patch.dict(g,{'download_ics':download}):query=m['next_feed']()
  self.assertEqual(calls,[A,B,C]);self.assertEqual(self.titles(query),['First','Middle','Last'])
  self.assertEqual(len({a.uid for a in m['parse_appointments'](query,date(2030,1,1),date(2030,1,6))}),1)
  for url in fixtures:
   path=m['cache_path'](url)
   self.assertRegex(path.name,r'^[a-f0-9]{64}\.ics$');self.assertNotIn('secret',str(path))
   self.assertEqual(path.stat().st_mode & 0o777,0o600)
  self.assertFalse(list(self.cache.parent.glob('*.tmp')))
 def test_overlaps_not_deduplicated(self):
  query=m['CombinedFeed']([m['parse_feed'](snapshot('Same')) for _ in range(2)])
  self.assertEqual(self.titles(query),['Same','Same'])
 def test_recurrence_exceptions_isolated_by_source(self):
  source=ics(event('A',extra='RRULE:FREQ=DAILY;COUNT=4\r\nEXDATE:20300102T100000Z'),
             event('Moved','20300103T120000Z',extra='RECURRENCE-ID:20300103T100000Z'),
             event('Cancelled','20300104T100000Z',extra='RECURRENCE-ID:20300104T100000Z\r\nSTATUS:CANCELLED'))
  other=ics(event('B','20300101T110000Z',extra='RRULE:FREQ=DAILY;COUNT=2'))
  query=m['CombinedFeed']([m['parse_feed'](source),m['parse_feed'](other)])
  self.assertEqual(self.titles(query),['A','B','B','Moved'])
  next_day=m['next_event'](query,datetime(2030,1,2,9,tzinfo=timezone.utc))
  self.assertEqual(next_day['description'],'B')
  changed=m['next_event'](query,datetime(2030,1,3,9,tzinfo=timezone.utc))
  self.assertEqual(changed['description'],'Moved')
  self.assertEqual(m['next_event'](query,datetime(2030,1,4,9,tzinfo=timezone.utc))['date'],'')
 def test_all_day_multiday_and_markers(self):
  raw=ics('BEGIN:VEVENT\r\nUID:same\r\nDTSTART;VALUE=DATE:20300101\r\nDTEND;VALUE=DATE:20300104\r\nSUMMARY:Trip\r\nEND:VEVENT')
  query=m['CombinedFeed']([m['parse_feed'](raw),m['parse_feed'](snapshot('Meeting'))])
  items=m['parse_appointments'](query,date(2030,1,1),date(2030,1,6))
  self.assertEqual([len(x[1]) for x in m['day_groups'](items,date(2030,1,1),date(2030,1,6))],[2,1,1])
 def test_failed_source_does_not_block_success(self):
  self.configure(A,B)
  def download(url):
   if url==A:raise OSError('private '+url)
   return snapshot('Available')
  with patch.dict(g,{'download_ics':download}),contextlib.redirect_stderr(io.StringIO()) as err:
   self.assertEqual(self.titles(m['next_feed']()),['Available'])
  self.assertNotIn('secret',err.getvalue())
  self.assertTrue(m['cache_path'](B).is_file())
 def test_failed_source_uses_cache_and_other_updates(self):
  self.configure(A,B);old=snapshot('Cached',10);self.store(A,old,age=1801)
  self.store(B,snapshot('Outdated',12),age=1801)
  def download(url):
   if url==A:raise OSError('offline')
   return snapshot('Updated',11)
  with patch.dict(g,{'download_ics':download}),contextlib.redirect_stderr(io.StringIO()):
   self.assertEqual(self.titles(m['next_feed']()),['Cached','Updated'])
  self.assertEqual(m['cache_path'](A).read_bytes(),old)
 def test_malformed_refresh_preserves_snapshot(self):
  self.configure(legacy=A);old=snapshot('Good');self.store(A,old,age=1801)
  with patch.dict(g,{'download_ics':lambda _:b'BEGIN:VCALENDAR\r\ninvalid\r\n'}),contextlib.redirect_stderr(io.StringIO()):
   self.assertEqual(self.titles(m['next_feed']()),['Good'])
  self.assertEqual(m['cache_path'](A).read_bytes(),old)
  malformed=event('Standalone event').encode()
  with patch.dict(g,{'download_ics':lambda _:malformed}),contextlib.redirect_stderr(io.StringIO()):
   self.assertEqual(self.titles(m['next_feed']()),['Good'])
  self.assertEqual(m['cache_path'](A).read_bytes(),old)
 def test_added_and_removed_sources(self):
  self.configure(A);self.store(A,snapshot('A'))
  self.assertEqual(self.titles(m['next_feed']()),['A'])
  self.configure(A,B)
  with patch.dict(g,{'download_ics':lambda _:snapshot('B',11)}):self.assertEqual(self.titles(m['next_feed']()),['A','B'])
  self.configure(B)
  self.assertEqual(self.titles(m['next_feed']()),['B'])
  self.configure()
  with self.assertRaises(ValueError):m['next_feed']()
 def test_cli_refresh_interval(self):
  self.configure(A);self.store(A,snapshot('Fresh'),age=1799)
  with patch.dict(g,{'download_ics':lambda _:self.fail('fresh cache downloaded')}):m['next_feed']()
  self.store(A,snapshot('Stale'),age=1801)
  with patch.dict(g,{'download_ics':lambda _:snapshot('Refreshed')}):self.assertEqual(self.titles(m['next_feed']()),['Refreshed'])
 def test_cli_next_waybar_within_timestamp_order(self):
  self.configure(A,B,C)
  self.store(A,ics(event('UTC later','20300101T103000Z')))
  eastern=event('Offset earlier','20300101T050000').replace('DTSTART:','DTSTART;TZID=America/New_York:')
  self.store(B,ics(eastern));self.store(C,snapshot('Last',12))
  for mode in ['--next','--waybar']:
   for limit,present in [(59,False),(60,True),(61,True)]:
    with self.subTest(mode=mode,limit=limit):
     out=io.StringIO()
     with patch.dict(g,{'datetime':FrozenDatetime,'CalTUI':lambda **_:self.fail('CLI started UI')}),patch('sys.argv',['caltui',mode,'--within',str(limit)]),contextlib.redirect_stdout(out):g['main']()
     self.assertEqual(len(out.getvalue().splitlines()),1)
     result=json.loads(out.getvalue())
     if mode=='--next':self.assertEqual(result['description'],'Offset earlier' if present else '')
     else:self.assertEqual(result['class'],'upcoming' if present else 'empty')
 def test_demo_ignores_configuration(self):
  self.config.write_text('broken config')
  with patch.dict(g,{'download_ics':lambda _:self.fail('demo downloaded')}):self.assertIsNotNone(m['next_feed'](demo=True))
 def test_all_failed_is_error(self):
  self.configure(A,B)
  with patch.dict(g,{'download_ics':lambda _:(_ for _ in ()).throw(OSError('offline'))}):
   with self.assertRaises(ValueError):m['next_feed']()

 def test_tui_cached_startup_and_independent_manual_refresh(self):
  async def check():
   today=date.today();raw=m['demo_ics']()
   self.configure(A,B);self.store(A,raw);self.store(B,raw)
   release=threading.Event();started=threading.Event()
   app=m['CalTUI'](agenda=True)
   def blocked(url):
    started.set()
    if url==A:
     if not release.wait(5):raise TimeoutError('test timeout')
     raise OSError('offline')
    return raw
   with patch.dict(g,{'download_ics':lambda _:self.fail('fresh TUI startup downloaded')}):
    async with app.run_test(size=(100,24)) as pilot:
     await pilot.pause()
     self.assertEqual(len(app.feed_queries),2)
     cells=[cell for cell in app.query('.day') if cell.day==today]
     self.assertTrue(cells and cells[0].has_class('has-event'))
     # Use a smaller viewport to ensure several agenda pages.
     await pilot.resize_terminal(60,35);await pilot.pause()
     await pilot.press('down','right');await pilot.pause()
     saved=(app.view,app.month,app.anchor,app.page_starts[app.page])
     with patch.dict(g,{'download_ics':blocked}):
      app.action_refresh_feed()
      for _ in range(100):
       await asyncio.sleep(.01)
       if app.feed_modified[B]>app.feed_modified[A]:break
      self.assertTrue(started.is_set());self.assertGreater(app.feed_modified[B],app.feed_modified[A])
      self.assertFalse(release.is_set(),'slow source blocked fast refresh')
      release.set();await app.workers.wait_for_complete();await pilot.pause()
     self.assertEqual(saved,(app.view,app.month,app.anchor,app.page_starts[app.page]))
     self.assertIn('1 calendars updated',app.data_status);self.assertIn('1 using cache',app.data_status)
     # Removing A and adding C on manual refresh changes only the data sources.
     self.configure(B,C)
     with patch.dict(g,{'download_ics':lambda _:raw}):
      await pilot.press('r');await app.workers.wait_for_complete();await pilot.pause()
     self.assertEqual(set(app.feed_queries),{B,C})
     self.assertEqual((app.view,app.month,app.anchor),saved[:3])
     self.configure()
     await pilot.press('r');await app.workers.wait_for_complete();await pilot.pause()
     self.assertIsNotNone(app.feed_query);self.assertFalse(app.feed_queries)
   release.set()
  run_ui(check())
 def test_tui_startup_refreshes_only_stale_feeds(self):
  async def check():
   self.configure(A,B,C);raw=m['demo_ics']()
   self.store(A,raw,age=1799);self.store(B,raw,age=1801)
   calls=[]
   def download(url):calls.append(url);return raw
   with patch.dict(g,{'download_ics':download}):
    app=m['CalTUI']()
    async with app.run_test(size=(120,35)) as pilot:
     await app.workers.wait_for_complete();await pilot.pause()
     self.assertCountEqual(calls,[B,C]);self.assertEqual(len(app.feed_queries),3)
  run_ui(check())

if __name__=='__main__':unittest.main()
