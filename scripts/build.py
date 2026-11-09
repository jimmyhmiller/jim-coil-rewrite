#!/usr/bin/env python3
"""Build the development app bundle, retaining all compiler/linker diagnostics."""
from pathlib import Path
import plistlib
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/JimCoil.app'
(APP / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
subprocess.run(['coil', 'build', '-o', 'build/jim-next'], cwd=ROOT, check=True)  # also builds build/jim-session and build/jimc
# Rename a completed executable atomically; never truncate a running image.
(ROOT / 'build/jim-next').replace(APP / 'Contents/MacOS/jim-coil')
with (APP / 'Contents/Info.plist').open('wb') as f:
    plistlib.dump({'CFBundleIdentifier': 'dev.jim.coil', 'CFBundleName': 'Jim Coil',
        'CFBundleExecutable': 'jim-coil', 'CFBundlePackageType': 'APPL',
        'NSHighResolutionCapable': True,
        'NSMicrophoneUsageDescription': 'Jim transcribes your speech into the focused terminal when you start dictation.', 'NSPrincipalClass': 'NSApplication'}, f)
identity = os.environ.get('JIM_SIGN_IDENTITY', 'TerminalBevy Local Signing')
identities = subprocess.check_output(['security', 'find-identity', '-p', 'codesigning'], text=True)
if identity not in identities:
    raise SystemExit('Signing identity not installed: ' + identity + '. Set JIM_SIGN_IDENTITY to an installed code-signing identity.')
# The service runs from the bundle, so macOS applies the app's privacy permissions to its
# shells. Signed before the rename: a running service keeps the file it started from.
service_next = APP / 'Contents/MacOS/jim-session.next'
shutil.copy2(ROOT / 'build/jim-session', service_next)
subprocess.run(['codesign', '--force', '--sign', identity, '--identifier', 'dev.jim.coil', str(service_next)], check=True)
service_next.replace(APP / 'Contents/MacOS/jim-session')
subprocess.run(['codesign', '--force', '--sign', identity, '--identifier', 'dev.jim.coil', str(APP)], check=True)
subprocess.run(['codesign', '--verify', '--strict', str(APP)], check=True)

# `jimc` on PATH follows this checkout's build. Something else already called jimc
# isn't ours to replace.
LINK = Path.home() / '.local/bin/jimc'
if LINK.is_symlink() or not LINK.exists():
    LINK.parent.mkdir(parents=True, exist_ok=True)
    LINK.unlink(missing_ok=True)
    LINK.symlink_to(ROOT / 'build/jimc')
else:
    print('Not linking jimc: ' + str(LINK) + ' already exists and is not a link')
print(APP)
