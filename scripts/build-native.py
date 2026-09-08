#!/usr/bin/env python3
"""Build Jim-owned Coil transport and session-service artifacts."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

(ROOT / 'build').mkdir(exist_ok=True)
subprocess.run(['coil', 'build'], cwd=ROOT / 'src/session', check=True)
(ROOT / 'build/jim-session-next').replace(ROOT / 'build/jim-session')
