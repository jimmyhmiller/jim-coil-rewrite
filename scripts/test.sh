#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
cc -Wall -Wextra -Werror tests/abi.c -o build/abi-test
build/abi-test
coil build config/shell.coil --shared -o build/shell-test.dylib
coil test
