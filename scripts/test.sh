#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
coil build  # the package build also produces build/jim-session
(cd config && coil build shell.coil --shared -o ../build/shell-test.dylib)
coil test

python3 tests/session_test.py
