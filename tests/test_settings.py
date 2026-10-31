"""Settings shortcut checks, using temporary configuration and fake editors."""
import contextlib
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from test_multifeed import run_ui

m=runpy.run_path(str(Path(__file__).resolve().parents[1] / 'caltui'));g=m['main'].__globals__
A='https://example.test/a';B='https://example.test/b'

class EditorSelection(unittest.TestCase):
 def choose(self,visual='',editor='',available=()):
  with patch.dict(os.environ,{'VISUAL':visual,'EDITOR':editor}),patch.object(g['shutil'],'which',side_effect=lambda cmd:cmd if cmd in available else None):
   return m['settings_editor']()
 def test_visual_with_arguments(self):
  self.assertEqual(self.choose('micro -softwrap','vim',('micro','vim','nano','vi')),['micro','-softwrap'])
 def test_editor_fallback(self):
  self.assertEqual(self.choose('missing','vim -n',('vim','nano','vi')),['vim','-n'])
 def test_nano_fallback(self):
  self.assertEqual(self.choose('missing','missing',('nano','vi')),['nano'])
 def test_vi_fallback(self):
  self.assertEqual(self.choose('missing','missing',('vi',)),['vi'])
 def test_quoted_path_and_arguments(self):
  self.assertEqual(self.choose('"/tmp/editor space" --flag "x y"',available=('/tmp/editor space',)),['/tmp/editor space','--flag','x y'])
 def test_bad_quoting_and_missing_editors(self):
  self.assertEqual(self.choose('"broken','vi',('vi',)),['vi'])
  self.assertIsNone(self.choose('missing','missing'))

class SettingsUI(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.config=self.root/'config.toml';self.config.write_text('url="'+A+'"\n')
  self.cache=self.root/'cache'/'calendar.ics'
  self.patches=patch.dict(g,{'CONFIG':self.config,'CACHE':self.cache});self.patches.start()
  m['save_private_cache'](m['demo_ics'](),A)
 def tearDown(self):self.patches.stop();self.tmp.cleanup()
 @contextlib.contextmanager
 def editor(self,app,edit=None,exit_code=0,error=None):
  order=[]
  @contextlib.contextmanager
  def suspend():
   order.append('suspend')
   yield
   order.append('resume')
  def launch(argv,**kwargs):
   self.assertEqual(order[-1],'suspend')
   self.assertEqual(argv,['/test/editor','--literal','$(not-a-shell)',str(self.config)])
   self.assertEqual(kwargs,{'check':False})
   if error:raise error
   if edit is not None:self.config.write_text(edit)
   return subprocess.CompletedProcess(argv,exit_code)
  with patch.dict(g,{'settings_editor':lambda:['/test/editor','--literal','$(not-a-shell)']}),patch.object(app,'suspend',suspend),patch.object(g['subprocess'],'run',side_effect=launch) as runner:
   yield order,runner
 def test_binding_modes_and_navigation_after_return(self):
  async def check():
   app=m['CalTUI'](agenda=True)
   async with app.run_test(size=(120,35)) as pilot:
    for size in [(120,35),(60,35),(60,20),(45,18)]:
     await pilot.resize_terminal(*size);await pilot.pause()
     await pilot.press('down','right');await pilot.pause()
     state=(app.month,app.anchor,app.view,app.page,app.layout_mode)
     with self.editor(app) as (order,runner),patch.object(app,'load_feed') as refresh:
      await pilot.press('s');await pilot.pause()
      self.assertEqual(order,['suspend','resume']);runner.assert_called_once();refresh.assert_not_called()
     self.assertEqual((app.month,app.anchor,app.view,app.page,app.layout_mode),state)
     self.assertIn('S Settings',str(app.query_one('#keys').render()))
     await pilot.press('c');await pilot.pause()
     cell=next(c for c in app.query('.day') if c.day is not None)
     selected=cell.day;await pilot.click(cell);await pilot.pause()
     self.assertEqual(app.anchor,selected)
    await pilot.press('t');self.assertEqual(app.anchor,m['date'].today())
  run_ui(check())
 def test_changed_urls_load_only_new_subscription(self):
  async def check():
   app=m['CalTUI'](agenda=True)
   async with app.run_test(size=(60,35)) as pilot:
    await pilot.press('down','right');await pilot.pause()
    state=(app.month,app.anchor,app.view,app.page_starts[app.page])
    empty=b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n'
    download=Mock(return_value=empty)
    with self.editor(app,'url="'+A+'"\n[[calendars]]\nurl="'+B+'"\n'),patch.dict(g,{'download_ics':download}):
     await pilot.press('s');await app.workers.wait_for_complete();await pilot.pause()
    download.assert_called_once_with(B)
    self.assertEqual(set(app.feed_queries),{A,B})
    self.assertEqual((app.month,app.anchor,app.view,app.page_starts[app.page]),state)
  run_ui(check())
 def test_invalid_toml_keeps_loaded_schedule_and_can_be_fixed(self):
  async def check():
   app=m['CalTUI'](agenda=True)
   async with app.run_test(size=(100,24)) as pilot:
    await pilot.pause();old=app.feed_query
    with self.editor(app,'[[broken'),patch.object(app,'notify') as notify,patch.object(app,'load_feed') as refresh:
     await pilot.press('s');await pilot.pause()
     notify.assert_called_once();self.assertIn('Invalid',notify.call_args.args[0]);refresh.assert_not_called()
    self.assertIs(app.feed_query,old);self.assertEqual(set(app.feed_queries),{A})
    with self.editor(app,'url="'+A+'"\n'),patch.object(app,'load_feed') as refresh:
     await pilot.press('s');await pilot.pause();refresh.assert_not_called()
  run_ui(check())
 def test_comments_duplicates_and_reordering_do_not_refresh(self):
  async def check():
   app=m['CalTUI']()
   async with app.run_test(size=(100,24)) as pilot:
    with self.editor(app,'# edited comment\n[[calendars]]\nurl="'+A+'"\n[[calendars]]\nurl="'+A+'"\n'),patch.object(app,'load_feed') as refresh:
     await pilot.press('s');await pilot.pause();refresh.assert_not_called()
  run_ui(check())
 def test_editor_launch_failure_resumes(self):
  async def check():
   app=m['CalTUI']()
   async with app.run_test() as pilot:
    for error in [OSError('cannot launch'),ValueError('invalid argv'),KeyboardInterrupt()]:
     with self.subTest(error=type(error).__name__),self.editor(app,error=error) as (order,_),patch.object(app,'notify') as notify:
      await pilot.press('s');await pilot.pause()
      self.assertEqual(order,['suspend','resume']);notify.assert_called_once()
    await pilot.press('right');self.assertEqual(app.month,m['month_shift'](m['date'].today().replace(day=1),1))
  run_ui(check())
 def test_unsuccessful_exit_notifies_and_still_applies_valid_changes(self):
  async def check():
   app=m['CalTUI']()
   async with app.run_test() as pilot:
    with self.editor(app,'url="'+B+'"',exit_code=2),patch.object(app,'notify') as notify,patch.object(app,'load_feed') as refresh:
     await pilot.press('s');await pilot.pause()
     self.assertIn('status 2',notify.call_args.args[0]);refresh.assert_called_once_with(stale_only=True)
  run_ui(check())
 def test_missing_editor_and_unsupported_suspend(self):
  async def check():
   app=m['CalTUI']()
   async with app.run_test() as pilot:
    with patch.dict(g,{'settings_editor':lambda:None}),patch.object(app,'suspend') as suspend,patch.object(app,'notify') as notify:
     await pilot.press('s');notify.assert_called_once();suspend.assert_not_called()
    with patch.dict(g,{'settings_editor':lambda:['vi']}),patch.object(app,'suspend',side_effect=m['SuspendNotSupported']()),patch.object(g['subprocess'],'run') as runner,patch.object(app,'notify') as notify:
     await pilot.press('s');notify.assert_called_once();runner.assert_not_called()
  run_ui(check())
 def test_missing_config_is_not_created_and_demo_stays_independent(self):
  async def check():
   self.config.unlink()
   app=m['CalTUI'](demo=True)
   async with app.run_test() as pilot:
    old=app.feed_query
    with self.editor(app),patch.object(app,'load_feed') as refresh:
     await pilot.press('s');self.assertFalse(self.config.exists());refresh.assert_not_called()
    with self.editor(app,'url="'+B+'"'),patch.object(app,'load_feed') as refresh:
     await pilot.press('s');self.assertIs(app.feed_query,old);refresh.assert_not_called()
  run_ui(check())

if __name__=='__main__':unittest.main()
