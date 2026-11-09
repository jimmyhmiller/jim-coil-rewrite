#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
coil build  # the package build also produces build/jim-session and build/jimc
coil test

python3 tests/session_test.py
python3 tests/jimc_test.py
