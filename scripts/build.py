#!/usr/bin/env python3
"""Build the development app bundle, retaining all compiler/linker diagnostics."""
from pathlib import Path
import plistlib
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/JimCoil.app'
(APP / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
subprocess.run(['coil', 'build', '-o', 'build/jim-next'], cwd=ROOT, check=True)  # also builds build/jim-session
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
