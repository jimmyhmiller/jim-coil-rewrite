#!/usr/bin/env python3
"""Build every widget ahead of time, so Jim never waits on the JIT at launch.

Each widgets/NAME.coil, followed by src/widget_shim.txt, is compiled with
coil.safety into build/widget-cache/NAME.dylib. Beside it NAME.key hashes the
inputs, and Jim loads the library only while the sources on disk still hash to it
(see "widgets built ahead of time" in src/widgets.coil, which computes the same
key). A widget whose key already matches is left alone.

Usage: widget_cache.py [--sign IDENTITY]
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'build/widget-cache'
FNV_OFFSET = 0xcbf29ce484222325
FNV_PRIME = 0x100000001b3
MASK = (1 << 64) - 1


def hash_bytes(h, data):
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & MASK
    return h


def hash_part(h, label, data):
    h = hash_bytes(h, label.encode())
    h = hash_bytes(h, b'\0')
    h = hash_bytes(h, data)
    return hash_bytes(h, b'\0')


def key(source):
    h = FNV_OFFSET
    h = hash_part(h, 'src/widget_shim.txt', (ROOT / 'src/widget_shim.txt').read_bytes())
    h = hash_part(h, 'widget', source)
    h = hash_part(h, 'src/widget_api.coil', (ROOT / 'src/widget_api.coil').read_bytes())
    kit = sorted(p.name.encode() for p in (ROOT / 'src/widget_kit').iterdir() if p.name.endswith('.coil'))
    for name in kit:
        path = 'src/widget_kit/' + name.decode()
        h = hash_part(h, path, (ROOT / path).read_bytes())
    return '%016x' % h


def build(widget, sign):
    name = widget.stem
    source = widget.read_bytes()
    wanted = key(source)
    key_file = CACHE / (name + '.key')
    library = CACHE / (name + '.dylib')
    if library.exists() and key_file.exists() and key_file.read_text().strip() == wanted:
        return name, 'current'
    entry = CACHE / 'src' / (name + '.coil')
    entry.write_bytes(source + b'\n' + (ROOT / 'src/widget_shim.txt').read_bytes())
    obj = CACHE / 'obj' / (name + '.o')
    subprocess.run(['coil', 'emit-obj', str(entry), '-o', str(obj), '--use', 'coil.safety'],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    # Undefined symbols are libc's and the system's, found in Jim when it loads it.
    staged = CACHE / (name + '.dylib.next')
    subprocess.run(['cc', '-dynamiclib', '-undefined', 'dynamic_lookup', str(obj), '-o', str(staged)],
                   check=True)
    if sign:
        subprocess.run(['codesign', '--force', '--sign', sign, '--timestamp=none', str(staged)], check=True)
    # A stale key never names a new library: drop it first, write it last.
    key_file.unlink(missing_ok=True)
    staged.replace(library)
    key_file.write_text(wanted + '\n')
    return name, 'built'


def main():
    sign = None
    if len(sys.argv) == 3 and sys.argv[1] == '--sign':
        sign = sys.argv[2]
    elif len(sys.argv) != 1:
        raise SystemExit(__doc__)
    for sub in ['src', 'obj']:
        (CACHE / sub).mkdir(parents=True, exist_ok=True)
    widgets = sorted((ROOT / 'widgets').glob('*.coil'))
    names = {w.stem for w in widgets}
    for stale in CACHE.iterdir():
        if stale.is_file() and stale.name.split('.')[0] not in names:
            stale.unlink()
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for name, what in pool.map(lambda w: build(w, sign), widgets):
            if what == 'built':
                print('[widget-cache] built ' + name)


if __name__ == '__main__':
    main()
