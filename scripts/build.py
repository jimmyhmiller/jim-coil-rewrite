#!/usr/bin/env python3
"""Build the development app bundle, retaining all compiler/linker diagnostics."""
from pathlib import Path
import plistlib
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/JimCoil.app'
if not (ROOT / 'build/ghostty/lib/libghostty-internal.a').is_file():
    raise SystemExit('Run scripts/prepare-ghostty.py first.')
(APP / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-c', 'src/callbacks.c', '-o', 'build/callbacks.o'], cwd=ROOT, check=True)
subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-c', 'src/session/transport.c', '-o', 'build/session-transport.o'], cwd=ROOT, check=True)
subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-I', 'build/ghostty/include',
    'src/session/server.c', 'build/session-transport.o', 'build/ghostty/lib/libghostty-vt.a',
    '-o', 'build/jim-session-next'], cwd=ROOT, check=True)
(ROOT / 'build/jim-session-next').replace(ROOT / 'build/jim-session')
subprocess.run(['coil', 'build', '-o', 'build/jim-next'], cwd=ROOT, check=True)
# Rename a completed executable atomically; never truncate a running image.
(ROOT / 'build/jim-next').replace(APP / 'Contents/MacOS/jim-coil')
with (APP / 'Contents/Info.plist').open('wb') as f:
    plistlib.dump({'CFBundleIdentifier': 'dev.jim.coil', 'CFBundleName': 'Jim Coil',
        'CFBundleExecutable': 'jim-coil', 'CFBundlePackageType': 'APPL',
        'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication'}, f)
identity = os.environ.get('JIM_SIGN_IDENTITY', 'TerminalBevy Local Signing')
identities = subprocess.check_output(['security', 'find-identity', '-p', 'codesigning'], text=True)
if identity not in identities:
    raise SystemExit('Signing identity not installed: ' + identity + '. Set JIM_SIGN_IDENTITY to an installed code-signing identity.')
subprocess.run(['codesign', '--force', '--sign', identity, '--identifier', 'dev.jim.coil', str(APP)], check=True)
subprocess.run(['codesign', '--verify', '--strict', str(APP)], check=True)
print(APP)
