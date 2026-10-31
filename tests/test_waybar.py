"""Focused CLI checks: python -m unittest discover -s . -p test_waybar.py"""
import contextlib
from datetime import date, datetime, timedelta
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from icalendar import Calendar, Event

SCRIPT=str(Path(__file__).resolve().parents[1] / 'caltui')
m=runpy.run_path(SCRIPT)
g=m['main'].__globals__
NOW=datetime(2026,10,31,9,0,tzinfo=m['LOCAL_TZ'])
class DatetimeMeta(type):
 def __instancecheck__(cls, instance): return isinstance(instance,datetime)
class FrozenDatetime(datetime,metaclass=DatetimeMeta):
 @classmethod
 def now(cls,tz=None): return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

def feed(offset=60, title='Planning', location='Office', events=True):
 cal=Calendar();cal.add('version','2.0');cal.add('prodid','-//CLI test//EN')
 if events:
  for uid,at,summary,loc in [('past',NOW-timedelta(hours=1),'Past',''),
                            ('next',NOW+timedelta(minutes=offset),title,location)]:
   e=Event();e.add('uid',uid);e.add('dtstart',at);e.add('dtend',at+timedelta(minutes=30))
   e.add('summary',summary)
   if loc:e.add('location',loc)
   cal.add_component(e)
 # All-day events should never become the next timed appointment.
 e=Event();e.add('uid','all-day');e.add('dtstart',NOW.date()+timedelta(days=1))
 e.add('summary','All-day');cal.add_component(e)
 return m['parse_feed'](cal.to_ical())

class WaybarCLI(unittest.TestCase):
 def invoke(self,*args,query=None,error=None):
  loader=Mock(return_value=query if query is not None else feed(),side_effect=error)
  ui=Mock(side_effect=AssertionError('CLI initialized the TUI'))
  stdout,stderr=io.StringIO(),io.StringIO();code=0
  with patch.object(sys,'argv',[SCRIPT,*args]),patch.dict(g,{'next_feed':loader,'CalTUI':ui,'datetime':FrozenDatetime}),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
   try:g['main']()
   except SystemExit as exc:code=exc.code
  ui.assert_not_called()
  return code,stdout.getvalue(),stderr.getvalue(),loader
 def payload(self,*args,**kwargs):
  code,out,err,loader=self.invoke(*args,**kwargs)
  self.assertEqual(code,0,err);self.assertEqual(len(out.splitlines()),1)
  value=json.loads(out);self.assertEqual(set(value),{'text','tooltip','class'})
  loader.assert_called_once_with(demo='--demo' in args)
  return value
 def test_today(self):
  p=self.payload('--waybar','--demo')
  self.assertEqual(p['class'],'upcoming');self.assertEqual(p['text'],'10:00 AM · Planning')
  self.assertEqual(p['tooltip'],'Saturday, October 31, 2026\n10:00 AM\nPlanning\nOffice')
 def test_future_day(self):
  p=self.payload('--waybar',query=feed(offset=1500))
  self.assertEqual(p['text'],'Sun Nov 1 · 10:00 AM · Planning')
  self.assertIn('Sunday, November 1, 2026',p['tooltip'])
 def test_no_events(self):
  p=self.payload('--waybar',query=feed(events=False))
  self.assertEqual(p['class'],'empty');self.assertEqual(p['text'],'')
 def test_unavailable(self):
  p=self.payload('--waybar',error=OSError('private URL must not leak'))
  self.assertEqual(p['class'],'error');self.assertEqual(p['text'],'')
  self.assertIn('Calendar unavailable',p['tooltip']);self.assertNotIn('private',p['tooltip'])
 def test_within(self):
  self.assertEqual(self.payload('--waybar','--within','59')['class'],'empty')
  self.assertEqual(self.payload('--waybar','--within','60')['class'],'upcoming')
  self.assertEqual(self.payload('--waybar','--within','61')['class'],'upcoming')
 def test_sanitized_and_escaped(self):
  title='Team\n\x1b7\x1b(B\x1b[31mreview\x1b[0m \x1b]8;;https://example.test\x1b\\<b>&\x1b]8;;\x1b\\\x07\x00\x7f\u202e'
  p=self.payload('--waybar',query=feed(title=title,location='Room\tA\n\x9b31mWest\x9b0m'))
  self.assertEqual(p['text'],'10:00 AM · Team review &lt;b&gt;&amp;')
  self.assertTrue(p['tooltip'].endswith('Room A West'))
  for char in '\x1b\x07\x00\x7f\u202e\x9b':self.assertNotIn(char,json.dumps(p,ensure_ascii=False))
 def test_concise_pill_complete_tooltip(self):
  title='A'*100
  p=self.payload('--waybar',query=feed(title=title,location=''))
  self.assertEqual(p['text'],'10:00 AM · '+'A'*47+'…')
  self.assertTrue(p['tooltip'].endswith(title))
  self.assertEqual(len(p['tooltip'].splitlines()),3)
 def test_next_contract(self):
  title='Raw\nsummary <b>&'
  code,out,err,_=self.invoke('--next',query=feed(title=title))
  self.assertEqual(code,0,err)
  self.assertEqual(json.loads(out),{'date':'2026-10-31','time':'10:00 AM','description':title,'location':'Office'})
 def test_next_within(self):
  code,out,_,_=self.invoke('--next','--within','59')
  self.assertEqual(code,0);self.assertEqual(json.loads(out),dict.fromkeys(['date','time','description','location'],''))
 def test_next_error_contract(self):
  code,out,err,_=self.invoke('--next',error=OSError('Unavailable'))
  self.assertEqual(code,1);self.assertIn('Calendar unavailable',err)
  self.assertEqual(json.loads(out),dict.fromkeys(['date','time','description','location'],''))
 def test_invalid_arguments(self):
  for args in [('--next','--waybar'),('--within','60'),('--waybar','--within','0'),('--waybar','--within','nan'),('--waybar','--within','-1')]:
   with self.subTest(args=args):
    code,out,err,loader=self.invoke(*args)
    self.assertEqual(code,2);self.assertEqual(out,'');loader.assert_not_called()
 def test_executable_demo_without_terminal(self):
  result=subprocess.run([SCRIPT,'--demo','--waybar'],capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(len(result.stdout.splitlines()),1)
  self.assertIn(json.loads(result.stdout)['class'],('upcoming','empty'))

if __name__=='__main__':unittest.main()
