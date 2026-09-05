#!/usr/bin/env python3
"""Apply Jim's reviewed transport patch to the project-local pinned Ghostty.

The complete patch is checked before any mutation. Accept an already applied
patch, but reject a partially patched or incompatible source tree.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(sys.argv[1]).resolve()
PATCH = ROOT / 'scripts/ghostty/session.patch'
if not SOURCE.is_relative_to(ROOT / 'build'):
    raise SystemExit('Refusing to patch a Ghostty checkout outside this project’s build directory.')
command = ['git', 'apply', '--unsafe-paths', '--directory', str(SOURCE)]

def matches(reverse=False):
    args = command + ['--check'] + (['--reverse'] if reverse else []) + [str(PATCH)]
    return subprocess.run(args, cwd=ROOT, capture_output=True).returncode == 0

if matches():
    subprocess.run(command + [str(PATCH)], cwd=ROOT, check=True)
elif not matches(reverse=True):
    raise SystemExit('Ghostty integration differs from the complete pinned patch. Restore the dependency source before rebuilding.')
shutil.copy2(ROOT / 'src/session/GhosttySession.zig', SOURCE / 'src/termio/Session.zig')
