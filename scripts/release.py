#!/usr/bin/env python3
"""Build a self-contained macOS release: build/dist/JimCoil.app and a zip of it.

A development build runs inside this checkout and uses the `coil` on PATH. The
release carries everything Jim reads at run time instead, so it runs on a Mac
with neither (see src/runtime.coil):

  Contents/MacOS/jim-coil      the app
  Contents/Frameworks/         libLLVM and the libraries it needs, which the app
                               (for its widget JIT) and the toolchain link
  Contents/Resources/root/     Coil.toml, src/, widgets/, config/, build/jim-session
                               and Ghostty's resources: copied to Application
                               Support on first launch, where Jim works
  Contents/Resources/coil/     the Coil toolchain that built Jim: bin/coil and
                               lib/coil, where widget sessions find the standard
                               library and theme reloads find the compiler

The toolchain is copied byte for byte. Coil keys its compile-time units to the
exact compiler binary, so rewriting the compiler's library paths or signing it
again would leave it unable to load them. It links LLVM at Homebrew's path
instead, and Jim runs it with DYLD_FALLBACK_LIBRARY_PATH set to the bundle's
Frameworks, which dyld searches only when that path is missing.

usage: scripts/release.py [--version VERSION] [--dirty]

The tree must be clean, so the release is exactly a commit. VERSION defaults to
the commit's short hash. Sign with JIM_RELEASE_SIGN_IDENTITY (default: ad hoc).
"""
from pathlib import Path
import argparse
import os
import plistlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'build/dist'
APP = DIST / 'JimCoil.app'

# What a widget session needs to resolve its imports: Jim's sources, without
# the native dependencies the app was linked with.
RUNTIME_MANIFEST = '''[package]
name = "jim"
entry = "src/main.coil"
source-roots = ["src"]
exclude = ["src/session/server.coil"]
'''

# The parts of an installed toolchain a running Jim uses. lint-profile is
# only for `coil lint`.
TOOLCHAIN_LIB = ['prelude.coil', 'stdlib', 'compiler', 'sealed', 'units', 'ct-units']


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def output(*cmd):
    return subprocess.check_output(cmd, text=True, cwd=ROOT).strip()


def code(path):
    """Whether PATH is an executable, a library or a bundle: code to sign,
    unlike an object file."""
    with open(path, 'rb') as f:
        header = f.read(16)
    return (len(header) == 16 and header[:4] == b'\xcf\xfa\xed\xfe'
            and int.from_bytes(header[12:16], 'little') in (2, 6, 8))


def dependencies(path):
    """The libraries PATH links that are not part of macOS. A library's own
    install name is not one of them."""
    own = output('otool', '-D', str(path)).splitlines()[1:]
    lines = output('otool', '-L', str(path)).splitlines()[1:]
    deps = [line.strip().split(' (')[0] for line in lines]
    return [d for d in deps
            if d not in own and not d.startswith(('/System/', '/usr/lib/', '@'))]


def add_rpath(path, rpath):
    if rpath not in output('otool', '-l', str(path)):
        run('install_name_tool', '-add_rpath', rpath, str(path), stderr=subprocess.DEVNULL)


def bundle_libraries(binaries, frameworks):
    """Copy every non-system library BINARIES need into FRAMEWORKS, and point
    every reference at @rpath."""
    frameworks.mkdir(parents=True, exist_ok=True)
    pending = [d for b in binaries for d in dependencies(b)]
    copied = {}
    while pending:
        dep = pending.pop()
        if dep in copied:
            continue
        target = frameworks / Path(dep).name
        shutil.copy2(os.path.realpath(dep), target)
        target.chmod(0o755)
        copied[dep] = target
        pending.extend(dependencies(target))
    for path in list(binaries) + list(copied.values()):
        for dep in dependencies(path):
            run('install_name_tool', '-change', dep, '@rpath/' + Path(dep).name, str(path),
                stderr=subprocess.DEVNULL)
    for target in copied.values():
        run('install_name_tool', '-id', '@rpath/' + target.name, str(target),
            stderr=subprocess.DEVNULL)
        add_rpath(target, '@loader_path')
    return list(copied.values())


def minimum_macos(binary):
    lines = output('otool', '-l', str(binary)).splitlines()
    for i, line in enumerate(lines):
        if line.strip() == 'cmd LC_BUILD_VERSION':
            for follow in lines[i:i + 6]:
                if follow.strip().startswith('minos'):
                    return follow.split()[1]
    raise SystemExit('No LC_BUILD_VERSION in ' + str(binary))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version')
    parser.add_argument('--dirty', action='store_true',
                        help='build from uncommitted changes, to try the bundle out')
    args = parser.parse_args()
    if output('git', 'status', '--porcelain') and not args.dirty:
        raise SystemExit('The tree has uncommitted changes; a release is built from a commit.')
    version = args.version or output('git', 'rev-parse', '--short', 'HEAD')
    if args.dirty:
        version += '-dirty'


    run('python3', str(ROOT / 'scripts/build.py'), cwd=ROOT)

    coil = Path(os.path.realpath(shutil.which('coil') or ''))
    if not coil.is_file():
        raise SystemExit('coil must be on PATH: the release carries the toolchain that built Jim.')
    toolchain_lib = coil.parent.parent / 'lib/coil'
    if not toolchain_lib.is_dir():
        raise SystemExit('No standard library beside ' + str(coil) + ' at ' + str(toolchain_lib))

    if APP.exists():
        shutil.rmtree(APP)
    contents = APP / 'Contents'
    (contents / 'MacOS').mkdir(parents=True)
    app_binary = contents / 'MacOS/jim-coil'
    shutil.copy2(ROOT / 'build/JimCoil.app/Contents/MacOS/jim-coil', app_binary)

    root = contents / 'Resources/root'
    root.mkdir(parents=True)
    (root / 'Coil.toml').write_text(RUNTIME_MANIFEST)
    (root / '.release').write_text(version)
    for name in ['src', 'widgets', 'config']:
        shutil.copytree(ROOT / name, root / name)
    (root / 'build/ghostty').mkdir(parents=True)
    shutil.copy2(ROOT / 'build/jim-session', root / 'build/jim-session')
    shutil.copytree(ROOT / 'build/ghostty/share', root / 'build/ghostty/share', symlinks=True)

    bundled = contents / 'Resources/coil'
    (bundled / 'bin').mkdir(parents=True)
    bundled_coil = bundled / 'bin/coil'
    shutil.copy2(coil, bundled_coil)
    if Path(str(coil) + '.toolchain').is_file():
        shutil.copy2(str(coil) + '.toolchain', str(bundled_coil) + '.toolchain')
    for name in TOOLCHAIN_LIB:
        source = toolchain_lib / name
        if source.is_dir():
            shutil.copytree(source, bundled / 'lib/coil' / name, symlinks=True)
        elif source.is_file():
            (bundled / 'lib/coil').mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, bundled / 'lib/coil' / name)
        else:
            raise SystemExit('The toolchain has no ' + str(source))

    libraries = bundle_libraries([app_binary], contents / 'Frameworks')
    add_rpath(app_binary, '@executable_path/../Frameworks')

    with (contents / 'Info.plist').open('wb') as f:
        # Its own identifier: macOS keys privacy permissions to the identifier
        # and signature, and a release sharing the development build's would
        # unsettle the permissions that build was given.
        plistlib.dump({'CFBundleIdentifier': 'dev.jim.coil.release', 'CFBundleName': 'Jim Coil',
            'CFBundleExecutable': 'jim-coil', 'CFBundlePackageType': 'APPL',
            'CFBundleShortVersionString': version, 'CFBundleVersion': version,
            'LSMinimumSystemVersion': minimum_macos(app_binary),
            'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication'}, f)

    # The app and its libraries may reach only into the bundle and macOS; what
    # the toolchain links must be in Frameworks for dyld's fallback to find.
    for path in [app_binary] + libraries:
        stray = dependencies(path)
        if stray:
            raise SystemExit(str(path) + ' still links ' + ', '.join(stray))
    bundled_names = {p.name for p in libraries}
    for path in (contents / 'Resources').rglob('*'):
        if path.is_file() and not path.is_symlink() and code(path):
            missing = [d for d in dependencies(path) if Path(d).name not in bundled_names]
            if missing:
                raise SystemExit(str(path) + ' links ' + ', '.join(missing) + ', not in Frameworks')

    # Only what this script changed is signed again; the toolchain and
    # jim-session keep the signatures they were built with.
    identity = os.environ.get('JIM_RELEASE_SIGN_IDENTITY', '-')
    for path in libraries:
        run('codesign', '--force', '--sign', identity, '--timestamp=none', str(path))
    run('codesign', '--force', '--sign', identity, '--timestamp=none',
        '--identifier', 'dev.jim.coil.release', str(APP))
    run('codesign', '--verify', '--strict', '--deep', str(APP))

    archive = DIST / ('JimCoil-' + version + '-macos-arm64.zip')
    if archive.exists():
        archive.unlink()
    run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(APP), str(archive))
    print(APP)
    print(archive)


if __name__ == '__main__':
    main()
