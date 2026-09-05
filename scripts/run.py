#!/usr/bin/env python3
"""Build, gracefully close this development shell if running, then open it."""
from pathlib import Path
import subprocess
import time
ROOT = Path(__file__).resolve().parents[1]
EXE = str(ROOT / 'build/JimCoil.app/Contents/MacOS/jim-coil')
def running():
    rows = subprocess.check_output(['/bin/ps', '-axo', 'command='], text=True).splitlines()
    return EXE in rows
subprocess.run(['python3', str(ROOT / 'scripts/build.py')], check=True)
if running():
    (ROOT / 'build/quit-request').touch()
    deadline = time.monotonic() + 15
    while running() and time.monotonic() < deadline:
        time.sleep(0.1)
    if running():
        raise SystemExit('The existing shell did not close. It was left running; close it before retrying.')
(ROOT / 'build/quit-request').unlink(missing_ok=True)
subprocess.run(['open', str(ROOT / 'build/JimCoil.app')], check=True)
