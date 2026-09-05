#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
cc -Wall -Wextra -Werror -c src/callbacks.c -o build/callbacks.o
cc -Wall -Wextra -Werror -c src/session/transport.c -o build/session-transport.o
cc -Wall -Wextra -Werror tests/abi.c -o build/abi-test
cc -Wall -Wextra -Werror tests/callbacks.c -o build/callback-test
build/callback-test
build/abi-test
(cd config && coil build shell.coil --shared -o ../build/shell-test.dylib)
coil test

cc -Wall -Wextra -Werror -I build/ghostty/include src/session/server.c build/session-transport.o build/ghostty/lib/libghostty-vt.a -o build/jim-session-next
mv build/jim-session-next build/jim-session
python3 tests/session_test.py
