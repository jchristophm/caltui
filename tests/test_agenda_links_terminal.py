"""Raw SGR mouse input reaches the agenda link through the Linux driver."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time

SCRIPT = os.environ.get('CALTUI_SCRIPT', str(Path(__file__).resolve().parents[1] / 'caltui'))
with tempfile.TemporaryDirectory(prefix='caltui-links-') as directory:
    root = Path(directory)
    probe = root / 'probe.py'
    probe.write_text('''import json, os, runpy, webbrowser
from pathlib import Path
m = runpy.run_path(os.environ['CALTUI_SCRIPT'])
root = Path(os.environ['PROBE_ROOT'])
webbrowser.open = lambda url: (root / 'opened').write_text(url)
class Probe(m['CalTUI']):
    def on_mount(self):
        super().on_mount()
        self.set_timer(.5, self.ready)
        self.set_timer(8, self.exit)
    def ready(self):
        body = self.query_one('#agenda-body')
        body.update(m['location_text']('https://meet.example.invalid/join?token=complete%20encoded-1234567890', body.content_size.width, self.secondary))
        self.call_after_refresh(self.record)
    def record(self):
        body = self.query_one('#agenda-body')
        region = body.content_region
        (root / 'ready').write_text(json.dumps([region.x + 2, region.y + (region.height - 1) // 2]))
Probe(demo=True, agenda=True).run()
''')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 60, 0, 0))
    proc = subprocess.Popen([sys.executable, str(probe)], stdin=slave, stdout=slave, stderr=slave,
                            env={**os.environ, 'TERM': 'foot', 'CALTUI_SCRIPT': SCRIPT, 'PROBE_ROOT': str(root)})
    os.close(slave)
    clicked = False
    output = bytearray()
    begin = time.monotonic()
    try:
        while proc.poll() is None and time.monotonic() - begin < 7:
            if select.select([master], [], [], .03)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            if (root / 'ready').exists() and not clicked:
                assert not (root / 'opened').exists(), 'browser opened without a click'
                x, y = json.loads((root / 'ready').read_text())
                os.write(master, f'\x1b[<0;{x+1};{y+1}M\x1b[<0;{x+1};{y+1}m'.encode())
                clicked = True
            if (root / 'opened').exists():
                assert proc.poll() is None, 'application closed after click'
                os.write(master, b'q')
                break
        proc.wait(timeout=3)
        assert proc.returncode == 0, bytes(output[-1000:])
        assert (root / 'opened').read_text() == 'https://meet.example.invalid/join?token=complete%20encoded-1234567890'
        print('PTY mouse click opened complete truncated URL; application stayed open')
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)
