"""Exercise the real Textual Linux input thread with a terminal emulator PTY."""
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import struct
import subprocess
import termios
import time
import sys
import tempfile

_temporary = tempfile.TemporaryDirectory(prefix='caltui-colors-')
PROBE = Path(_temporary.name) / 'pty-probe.py'
SCRIPT = str(Path(__file__).resolve().parents[1] / 'caltui')
PROBE.write_text('''import runpy,json,os
from pathlib import Path
m=runpy.run_path(os.environ['CALTUI_SCRIPT'])
class Probe(m['CalTUI']):
 def on_mount(self):
  super().on_mount()
  self.set_interval(.15,self.record)
  self.set_timer(12,self.exit)
 def record(self):
  with Path(os.environ['PROBE_LOG']).open('a') as f:
   f.write(json.dumps({'palette':self.palette,'colors':self._text_colors,'view':self.view,'month':str(self.month),'page':self.page})+'\\n')
Probe(demo=True).run()
''')
DARK={'10':(238,238,238),'11':(17,17,17),'4;4':(34,68,136),'4;6':(85,187,204),'4;15':(255,255,255)}
LIGHT={'10':(34,34,34),'11':(238,238,238),'4;4':(170,187,221),'4;6':(0,102,119),'4;15':(255,255,255)}
QUERY=re.compile(rb'\x1b](10|11|4;(?:4|6|15));\?\x1b\\')

def run(initial, switch=False, supported=True):
 log=(PROBE.parent / ('pty-'+('light' if initial==LIGHT else 'dark')+('-unsupported' if not supported else '')+'.jsonl'))
 log.unlink(missing_ok=True)
 master,slave=pty.openpty()
 fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
 proc=subprocess.Popen([sys.executable,str(PROBE)],stdin=slave,stdout=slave,stderr=slave,
                       env={**os.environ,'TERM':'foot','PROBE_LOG':str(log),'CALTUI_SCRIPT':SCRIPT})
 os.close(slave)
 begin=time.monotonic();current=initial;buf=b'';output=bytearray();pressed=False;quit_sent=False
 try:
  while proc.poll() is None and time.monotonic()-begin<11:
   elapsed=time.monotonic()-begin
   if switch and elapsed>3: current=LIGHT
   if elapsed>1 and not pressed:
    os.write(master,b'\x1b[C'); pressed=True
   if elapsed>7 and not quit_sent:
    os.write(master,b'q');quit_sent=True
   readable,_,_=select.select([master],[],[],.05)
   if not readable: continue
   try: data=os.read(master,65536)
   except OSError as e:
    if e.errno==errno.EIO: break
    raise
   output.extend(data);buf+=data
   for match in QUERY.finditer(buf):
    if supported:
     key=match[1].decode();color=current[key]
     # Foot reports 16-bit rgb components. Split the reply across reads.
     reply=('\x1b]'+key+';rgb:'+'/'.join(f'{v*257:04x}' for v in color)+'\x1b\\').encode()
     os.write(master,reply[:4]);os.write(master,reply[4:])
   # Keep only a possible incomplete OSC query suffix.
   last=buf.rfind(b'\x1b]')
   buf=buf[last:] if last>=0 and not buf.endswith(b'\x1b\\') and b'\x1b\\' not in buf[last:] else b''
  proc.wait(timeout=2)
  assert proc.returncode==0,bytes(output[-3000:])
  rows=[json.loads(line) for line in log.read_text().splitlines()]
  assert rows and rows[-1]['palette']==({k:list(v) for k,v in current.items()} if supported else {})
  if switch:
   assert any(r['palette']=={k:list(v) for k,v in DARK.items()} for r in rows)
   assert any(r['palette']=={k:list(v) for k,v in LIGHT.items()} for r in rows)
  assert len({r['month'] for r in rows})==2, 'right key lost or color reply triggered keys'
  assert all(r['view']=='calendar' for r in rows), 'reply became an agenda key'
  print(log.name,'passed')
 finally:
  if proc.poll() is None: proc.kill();proc.wait()
  os.close(master)
run(DARK,switch=True)
run(LIGHT)
run(DARK,supported=False)
