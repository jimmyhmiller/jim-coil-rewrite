#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
coil build  # the package build also produces build/jim-session
coil test

python3 tests/session_test.py
