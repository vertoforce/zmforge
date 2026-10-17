#!/usr/bin/env bash
# Run a command with DISPLAY pointing at a display server started here.
#
#   with-display wine radiant_modtools.exe -ledSilent ...
#
# Radiant is a Qt program even in -ledSilent mode and will not start without
# an X connection. Which server it gets is decided by what the container was
# given, and is printed on stderr so a log always says which one ran:
#
#   nvidia  /dev/nvidia0 is present and the runtime injected nvidia_drv.so:
#           Xorg on the GPU (xorg-headless.conf). Real GLX, real shaders.
#   xvfb    anything else. Mesa llvmpipe only. Enough for a program that
#           merely wants a display; not enough for the bake's D3D11 renderer
#           [measured: 246 GLSL link failures, probe pass never
#           finished].
#
# The child is exec'd so its exit code is this script's exit code, and the
# server dies with the container.
set -euo pipefail
DISPLAY_NUMBER=${DISPLAY_NUMBER:-99}
export DISPLAY=":${DISPLAY_NUMBER}"
socket="/tmp/.X11-unix/X${DISPLAY_NUMBER}"

if [ -e /dev/nvidia0 ] && [ -e /usr/lib/xorg/modules/drivers/nvidia_drv.so ] \
        && command -v Xorg >/dev/null; then
    kind=nvidia
    Xorg "$DISPLAY" -config /etc/X11/xorg-headless.conf -noreset -nolisten tcp \
        -novtswitch -sharevts -logfile /tmp/xorg.log >/tmp/xorg.out 2>&1 &
else
    kind=xvfb
    Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
fi
server=$!

for _ in $(seq 1 100); do
    [ -e "$socket" ] && break
    if ! kill -0 "$server" 2>/dev/null; then
        echo "with-display: $kind server exited before opening $DISPLAY" >&2
        cat /tmp/xorg.out /tmp/xvfb.log 2>/dev/null | tail -20 >&2
        exit 70
    fi
    sleep 0.1
done
if [ ! -e "$socket" ]; then
    echo "with-display: $kind server did not open $DISPLAY in 10s" >&2
    exit 70
fi

renderer=$(glxinfo -B 2>/dev/null | sed -n 's/^OpenGL renderer string: //p' | head -1)
echo "with-display: $kind on $DISPLAY, GL renderer: ${renderer:-unknown}" >&2

exec "$@"
