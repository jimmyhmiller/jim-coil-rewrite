#!/usr/bin/env python3
"""Build the pinned Ghostty embedding library without building the Ghostty app."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REV = '7aa9591746ffa4d2eee458960c76554352832595'
DEST = ROOT / 'build/ghostty'
source_override = os.environ.get('GHOSTTY_SOURCE')
SOURCE = Path(source_override).resolve() if source_override else ROOT / 'build/deps' / ('ghostty-' + REV)
if not SOURCE.exists():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    archive = SOURCE.parent / ('ghostty-' + REV + '.tar.gz')
    urllib.request.urlretrieve('https://codeload.github.com/ghostty-org/ghostty/tar.gz/' + REV, archive)
    with tarfile.open(archive) as tar:
        tar.extractall(SOURCE.parent, filter='data')
    archive.unlink()
# Keep the transport extension local even when reusing another checkout.
if source_override and not SOURCE.is_relative_to(ROOT / 'build'):
    local = ROOT / 'build/deps' / ('ghostty-' + REV)
    if not local.exists():
        shutil.copytree(SOURCE, local, ignore=shutil.ignore_patterns('.git', '.zig-cache', 'zig-out'))
    SOURCE = local
expected = hashlib.sha256((ROOT / 'vendor/ghostty.h').read_bytes()).digest()
actual = hashlib.sha256((SOURCE / 'include/ghostty.h').read_bytes()).digest()
if actual != expected:
    raise SystemExit('Ghostty header differs from the pinned, ABI-tested header. Refusing to build.')
if subprocess.check_output(['zig', 'version'], text=True).strip() != '0.16.0':
    raise SystemExit('This Ghostty revision requires Zig 0.16.0.')
subprocess.run(['xcrun', '-sdk', 'macosx', 'metal', '--version'], check=True)
subprocess.run(['python3', str(ROOT / 'scripts/ghostty/session-backend.py'), str(SOURCE)], check=True)
subprocess.run(['zig', 'build', '-Dapp-runtime=none', '-Demit-xcframework=true',
    '-Dxcframework-target=native', '-Doptimize=ReleaseFast', '-Demit-docs=false',
    '-Demit-webdata=false', '-Demit-macos-app=false', '--prefix', str(DEST)], cwd=SOURCE, check=True)
artifacts = list((SOURCE / 'macos/GhosttyKit.xcframework').glob('macos-*/libghostty-internal.a'))
if len(artifacts) != 1:
    raise SystemExit('Expected exactly one native GhosttyKit library.')
(DEST / 'lib').mkdir(parents=True, exist_ok=True)
shutil.copy2(artifacts[0], DEST / 'lib/libghostty-internal.a')
subprocess.run(['zig', 'build', '-Demit-lib-vt=true', '-Doptimize=ReleaseFast',
    '-Demit-docs=false', '--prefix', str(DEST)], cwd=SOURCE, check=True)
(DEST / 'revision').write_text(REV + '\n')
print('Ghostty embedding library is ready:', DEST)
