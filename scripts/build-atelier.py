#!/usr/bin/env python3
"""Build the Paper exploration and isolated embedded-JIT plugin worker."""
from pathlib import Path
import os
import plistlib
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'build/Jim Atelier.app'

def run(args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)

def main():
    if not (ROOT.parent / 'paper-test/lib/paper/Coil.toml').is_file():
        raise SystemExit('The neighboring paper-test library is required (read-only dependency).')
    run(['python3', 'scripts/build-native.py'])
    run(['coil', 'build', '-o', '../../build/atelier-plugin-worker'], ROOT / 'tools/plugin-worker')
    run(['coil', 'build', 'src/atelier.coil', '-o', 'build/jim-atelier-next'])
    (APP / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
    (ROOT / 'build/jim-atelier-next').replace(APP / 'Contents/MacOS/jim-atelier')
    run(['coil', 'build', 'src/atelier_icon.coil', '-o', 'build/atelier-icon'])
    run(['build/atelier-icon', '--snapshot', 'build/atelier-icon.png'])
    iconset = ROOT / 'build/atelier.iconset'
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for density in (1, 2):
            suffix = '@2x' if density == 2 else ''
            run(['sips', '-z', str(size * density), str(size * density),
                 'build/atelier-icon.png', '--out', str(iconset / f'icon_{size}x{size}{suffix}.png')])
    resources = APP / 'Contents/Resources'
    resources.mkdir(exist_ok=True)
    run(['iconutil', '-c', 'icns', str(iconset), '-o', str(resources / 'Atelier.icns')])
    with (APP / 'Contents/Info.plist').open('wb') as file:
        plistlib.dump({'CFBundleIdentifier': 'dev.jim.atelier',
                      'CFBundleName': 'Jim Atelier', 'CFBundleExecutable': 'jim-atelier',
                      'CFBundlePackageType': 'APPL', 'NSHighResolutionCapable': True,
                      'CFBundleIconFile': 'Atelier.icns',
                      'NSPrincipalClass': 'NSApplication'}, file)
    identity = os.environ.get('JIM_SIGN_IDENTITY', 'TerminalBevy Local Signing')
    run(['codesign', '--force', '--sign', identity, '--identifier', 'dev.jim.atelier', str(APP)])
    run(['codesign', '--verify', '--strict', str(APP)])
    print(APP)

if __name__ == '__main__':
    main()
