"""Real suspend/editor/resume round trip over a PTY, without a compositor."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shlex
import struct
import subprocess
import tempfile
import termios
import time
import sys

SCRIPT=str(Path(__file__).resolve().parents[1] / 'caltui')
with tempfile.TemporaryDirectory(prefix='caltui settings ') as directory:
 root=Path(directory);config=root/'config.toml';config.write_text('url="https://example.test/a"\n')
 log=root/'app.jsonl';marker=root/'editor.json';unwanted=root/'not-created';bad=root/'unlaunchable'
 bad.write_text('#!/nonexistent/caltui-editor-interpreter\n');bad.chmod(0o700)
 editor=root/'editor stub.py'
 editor.write_text('''import json,os,sys,termios
from pathlib import Path
Path(os.environ['EDITOR_MARKER']).write_text(json.dumps({'argv':sys.argv[1:],'tty':os.isatty(0),'echo':bool(termios.tcgetattr(0)[3]&termios.ECHO)}))
assert sys.stdin.readline().strip()=='done'
''')
 probe=root/'probe.py'
 probe.write_text('''import json,os,runpy
from pathlib import Path
m=runpy.run_path(os.environ['CALTUI_SCRIPT']);m['main'].__globals__['CONFIG']=Path(os.environ['TEST_CONFIG'])
class Probe(m['CalTUI']):
 def __init__(self):super().__init__(demo=True);self.settings_count=0
 def on_mount(self):
  super().on_mount();self.set_interval(.1,self.record);self.set_timer(12,self.exit)
 def record(self):
  with Path(os.environ['APP_LOG']).open('a') as f:f.write(json.dumps({'month':str(self.month),'anchor':str(self.anchor),'view':self.view,'layout':self.layout_mode,'settings':self.settings_count})+'\\n')
 def action_settings(self):
  super().action_settings();self.settings_count+=1
  os.environ['VISUAL']=os.environ['BAD_EDITOR']
Probe().run()
''')
 master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
 initial=termios.tcgetattr(slave)
 env={**os.environ,'TERM':'foot','VISUAL':shlex.join(['python',str(editor),'--literal',f'$(touch {unwanted})']),
      'EDITOR_MARKER':str(marker),'CALTUI_SCRIPT':SCRIPT,'TEST_CONFIG':str(config),'APP_LOG':str(log),'BAD_EDITOR':str(bad)}
 proc=subprocess.Popen([sys.executable,str(probe)],stdin=slave,stdout=slave,stderr=slave,env=env)
 output=bytearray();start=time.monotonic();stage=0;saved=None;sent_done=False
 try:
  while proc.poll() is None and time.monotonic()-start<10:
   ready,_,_=select.select([master],[],[],.03)
   if ready:output.extend(os.read(master,65536))
   rows=[]
   if log.exists():
    for line in log.read_text().splitlines():
     try:rows.append(json.loads(line))
     except json.JSONDecodeError:pass
   if stage==0 and rows:
    first=rows[-1];os.write(master,b'\x1b[C');stage=1
   elif stage==1 and rows[-1]['month']!=first['month']:
    saved=rows[-1];os.write(master,b's');stage=2
   elif stage==2 and marker.exists() and marker.stat().st_size:
    info=json.loads(marker.read_text())
    assert info['tty'] and info['echo'],info
    assert info['argv']==['--literal',f'$(touch {unwanted})',str(config)],info
    assert not unwanted.exists(),'editor argument was interpreted by a shell'
    os.write(master,b'done\n');stage=3
   elif stage==3 and rows[-1]['settings']==1:
    assert all(rows[-1][key]==saved[key] for key in ['month','anchor','view','layout'])
    os.write(master,b's');stage=4
   elif stage==4 and rows[-1]['settings']==2:
    os.write(master,b'\x1b[C');stage=5
   elif stage==5 and rows[-1]['month']!=saved['month']:
    os.write(master,b'q');stage=6
  proc.wait(timeout=3)
  assert proc.returncode==0,bytes(output[-3000:])
  assert stage==6,(stage,bytes(output[-3000:]))
  assert termios.tcgetattr(slave)[3]==initial[3], 'terminal modes not restored'
  assert config.read_text()=='url="https://example.test/a"\n'
  print('Real PTY editor, terminal modes, literal arguments, launch failure, resumed navigation and quit passed')
 finally:
  if proc.poll() is None:proc.kill();proc.wait()
  os.close(master);os.close(slave)
