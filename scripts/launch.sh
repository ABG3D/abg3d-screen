#!/bin/sh
# X client started by xinit from abg3d-screen.service
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$DIR/venv/bin/python3"
[ -x "$PY" ] || PY=/usr/bin/python3
# no X screensaver; DPMS enabled without timeouts so abg3d-screen alone decides when to blank
xset s off 2>/dev/null
xset s noblank 2>/dev/null
xset +dpms 2>/dev/null
xset dpms 0 0 0 2>/dev/null
[ -n "$ABG3D_XRANDR" ] && xrandr $ABG3D_XRANDR 2>/dev/null
cd "$DIR" || exit 1
exec "$PY" -m abg3d_screen
