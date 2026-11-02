#!/bin/sh
# Build, quit the running app, relaunch. Terminal sessions belong to their own
# services, so they survive and the new app reattaches to them.
#
# A failed build leaves the running app alone.

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd -P)"
APP="$ROOT/build/JimCoil.app"
BIN="$APP/Contents/MacOS/jim-coil"
QUIT_REQUEST="$ROOT/build/quit-request"
LOG="${TMPDIR:-/tmp}/jim-coil.log"

# The running app, bundled or from `coil run` in this checkout. A zombie is
# already dead and cannot be asked to quit.
gui_pids() {
    ps -Ao pid=,stat=,comm= | while read -r pid stat comm; do
        case "$stat" in Z*) continue ;; esac
        case "$comm" in
            "$BIN") echo "$pid" ;;
            */coil-*/*/1-main)
                if [ "$(lsof -a -d cwd -p "$pid" -Fn 2>/dev/null | sed -n 's/^n//p')" = "$ROOT" ]; then
                    echo "$pid"
                fi
                ;;
        esac
    done
}

# Opening both apps at once lost terminals on 2026-11-01, cause still unknown.
# See the jim-coil-rewrite pad. The daemons and bus of original Jim do not count.
if ps -Ao command= | grep -Eq '/Jim\.app/Contents/MacOS/jim *$'; then
    echo "[dev-restart] original Jim is open; refusing to launch alongside it." >&2
    exit 1
fi

echo "[dev-restart] building..."
python3 scripts/build.py

RUNNING="$(gui_pids)"
if [ -n "$RUNNING" ]; then
    echo "[dev-restart] asking the running app to quit:" $RUNNING
    touch "$QUIT_REQUEST"
    i=0
    while [ $i -lt 150 ] && [ -n "$(gui_pids)" ]; do
        sleep 0.1
        i=$((i + 1))
    done
    RUNNING="$(gui_pids)"
    if [ -n "$RUNNING" ]; then
        echo "[dev-restart] no quit after 15s, sending SIGTERM:" $RUNNING >&2
        kill $RUNNING 2>/dev/null || true
        sleep 2
        RUNNING="$(gui_pids)"
    fi
    if [ -n "$RUNNING" ]; then
        echo "[dev-restart] still alive, sending SIGKILL:" $RUNNING >&2
        kill -9 $RUNNING 2>/dev/null || true
        sleep 0.5
        RUNNING="$(gui_pids)"
    fi
    if [ -n "$RUNNING" ]; then
        echo "[dev-restart] ERROR: still running:" $RUNNING "; refusing to launch a second app." >&2
        exit 1
    fi
fi
# Left behind, it would quit the app being launched.
rm -f "$QUIT_REQUEST"

# `open` forwards the caller's environment to the app, and from there to every new
# terminal. Start from a login shell's environment instead, so nothing exported by
# whatever ran this script (an agent's GIT_EDITOR=true, say) reaches your shells.
echo "[dev-restart] launching, log at $LOG"
env -i \
    HOME="$HOME" USER="$USER" LOGNAME="$LOGNAME" \
    TERM="${TERM:-xterm-256color}" SHELL="$SHELL" TMPDIR="$TMPDIR" LANG="$LANG" \
    /bin/zsh -lc "exec open -n '$APP' --stdout '$LOG' --stderr '$LOG'"

# Prove exactly one app came up and stayed up.
i=0
while [ $i -lt 100 ] && [ -z "$(gui_pids)" ]; do
    sleep 0.1
    i=$((i + 1))
done
sleep 1
RUNNING="$(gui_pids | tr '\n' ' ' | sed 's/ *$//')"
COUNT="$(printf '%s' "$RUNNING" | wc -w | tr -d ' ')"
if [ "$COUNT" != "1" ]; then
    echo "[dev-restart] ERROR: expected 1 app, found $COUNT: $RUNNING. See $LOG" >&2
    exit 1
fi
echo "[dev-restart] verified: 1 app running (pid $RUNNING), launched through LaunchServices"
