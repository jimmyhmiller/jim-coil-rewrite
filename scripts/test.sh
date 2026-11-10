#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
coil build  # the package build also produces build/jim-session and build/jimc
python3 scripts/widget_cache.py  # widgets built ahead of time, which the widget tests load
coil test

python3 tests/session_test.py
python3 tests/jimc_test.py
