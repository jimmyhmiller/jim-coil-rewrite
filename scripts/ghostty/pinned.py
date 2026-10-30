"""Build the pinned Ghostty embedding libraries when their inputs change.

Coil runs `link-flags.py` as a native-dependency `flags-command` before every
build and again while linking, so an up-to-date check must be cheap and all
build output must stay off stdout, which Coil reads as linker arguments.
"""
from pathlib import Path
import contextlib
import fcntl
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
# Ghostty v1.4.0.
REV = '83fb95624b0439ee660c2679b43b38c8b63769cd'
DEST = ROOT / 'build/ghostty'
LOCAL_SOURCE = ROOT / 'build/deps' / ('ghostty-' + REV)
# The Zig this Ghostty requires, kept beside it so the Zig on PATH, which
# other projects use, can stay at its own version.
ZIG_VERSION = '0.17.0'
ZIG_NAME = 'zig-aarch64-macos-' + ZIG_VERSION
ZIG_SHA256 = 'b607e9b9234790a008116ae5bdb71c6243b84b9fb42a53a9e70fde41c06c536a'
ZIG_MIRRORS = ['https://ziglang.freetls.fastly.net/',
               'https://ziglang.org/download/' + ZIG_VERSION + '/']
ZIG = ROOT / 'build/deps' / ZIG_NAME / 'zig'
LIBRARIES = {
    'internal': DEST / 'lib/libghostty-internal.a',
    'vt': DEST / 'lib/libghostty-vt.a',
}
STAMP = DEST / 'inputs.sha256'
INPUTS = [
    ROOT / 'vendor/ghostty.h',
    ROOT / 'scripts/ghostty/session.patch',
    ROOT / 'scripts/ghostty/session-backend.py',
    ROOT / 'src/session/GhosttySession.zig',
    Path(__file__).resolve(),
]


def run(args, **kwargs):
    # Keep tool output visible on stderr; stdout belongs to the linker flags.
    subprocess.run(args, check=True, stdout=sys.stderr, **kwargs)


def zig():
    """The pinned Zig, downloaded and checked against its digest on first use."""
    if not ZIG.is_file():
        ZIG.parent.parent.mkdir(parents=True, exist_ok=True)
        archive = ZIG.parent.parent / (ZIG_NAME + '.tar.xz')
        for mirror in ZIG_MIRRORS:
            print('Downloading Zig', ZIG_VERSION, 'from', mirror, file=sys.stderr)
            try:
                urllib.request.urlretrieve(mirror + ZIG_NAME + '.tar.xz', archive)
            except OSError as error:
                print('  failed:', error, file=sys.stderr)
                continue
            if hashlib.sha256(archive.read_bytes()).hexdigest() == ZIG_SHA256:
                break
            print('  digest mismatch', file=sys.stderr)
        else:
            raise SystemExit('Could not download Zig ' + ZIG_VERSION + ' with the pinned digest.')
        with tarfile.open(archive) as tar:
            tar.extractall(ZIG.parent.parent, filter='data')
        archive.unlink()
    version = subprocess.check_output([str(ZIG), 'version'], text=True).strip()
    if version != ZIG_VERSION:
        raise SystemExit(str(ZIG) + ' is Zig ' + version + ', not ' + ZIG_VERSION + '.')
    return str(ZIG)


def fingerprint():
    digest = hashlib.sha256()
    digest.update(REV.encode() + b'\0' + ZIG_VERSION.encode() + b'\0')
    for path in INPUTS:
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()


def up_to_date(expected):
    return (STAMP.is_file() and STAMP.read_text().strip() == expected
            and all(path.is_file() for path in LIBRARIES.values()))


def source():
    override = os.environ.get('GHOSTTY_SOURCE')
    if override:
        # Keep the transport extension local even when reusing another checkout.
        checkout = Path(override).resolve()
        if not LOCAL_SOURCE.exists():
            shutil.copytree(checkout, LOCAL_SOURCE,
                            ignore=shutil.ignore_patterns('.git', '.zig-cache', 'zig-out'))
    elif not LOCAL_SOURCE.exists():
        archive = LOCAL_SOURCE.parent / ('ghostty-' + REV + '.tar.gz')
        print('Downloading pinned Ghostty', REV, file=sys.stderr)
        urllib.request.urlretrieve('https://codeload.github.com/ghostty-org/ghostty/tar.gz/' + REV, archive)
        with tarfile.open(archive) as tar:
            tar.extractall(LOCAL_SOURCE.parent, filter='data')
        archive.unlink()
    return LOCAL_SOURCE


def version(src):
    """Ghostty's own version, marked with the pinned revision. Without it
    Ghostty's build asks git, which answers for this repository instead:
    our branch and commit, and a release tag on our HEAD stops the build."""
    match = re.search(r'\.version = "([^"]+)"', (src / 'build.zig.zon').read_text())
    if not match:
        raise SystemExit('No version in the pinned Ghostty build.zig.zon.')
    return match.group(1) + '+' + REV[:7]


def build():
    LOCAL_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    src = source()
    expected = hashlib.sha256((ROOT / 'vendor/ghostty.h').read_bytes()).digest()
    actual = hashlib.sha256((src / 'include/ghostty.h').read_bytes()).digest()
    if actual != expected:
        raise SystemExit('Ghostty header differs from the pinned, ABI-tested header. Refusing to build.')
    run(['xcrun', '-sdk', 'macosx', 'metal', '--version'])
    run(['python3', str(ROOT / 'scripts/ghostty/session-backend.py'), str(src)])
    # Without Sentry: Ghostty's crash reporter would install its handlers in
    # Jim and file Jim's crashes as Ghostty's.
    run([zig(), 'build', '-Dversion-string=' + version(src), '-Dsentry=false',
         '-Dapp-runtime=none', '-Demit-xcframework=true',
         '-Dxcframework-target=native', '-Doptimize=ReleaseFast', '-Demit-docs=false',
         '-Demit-webdata=false', '-Demit-macos-app=false', '--prefix', str(DEST)], cwd=src)
    artifacts = list((src / 'macos/GhosttyKit.xcframework').glob('macos-*/libghostty-internal.a'))
    if len(artifacts) != 1:
        raise SystemExit('Expected exactly one native GhosttyKit library.')
    (DEST / 'lib').mkdir(parents=True, exist_ok=True)
    shutil.copy2(artifacts[0], LIBRARIES['internal'])
    run([zig(), 'build', '-Dversion-string=' + version(src),
         '-Demit-lib-vt=true', '-Doptimize=ReleaseFast',
         '-Demit-docs=false', '--prefix', str(DEST)], cwd=src)
    (DEST / 'revision').write_text(REV + '\n')


def ensure():
    """Return once both libraries match the current inputs, building if needed."""
    DEST.mkdir(parents=True, exist_ok=True)
    with open(DEST / '.lock', 'w') as lock:
        # Concurrent Coil builds wait here instead of building over each other.
        fcntl.flock(lock, fcntl.LOCK_EX)
        expected = fingerprint()
        if up_to_date(expected):
            return
        with contextlib.suppress(FileNotFoundError):
            STAMP.unlink()
        print('Building pinned Ghostty libraries (inputs changed or missing)', file=sys.stderr)
        build()
        STAMP.write_text(expected + '\n')
