#!/usr/bin/env bash
# Run one mod-tools executable under Wine in the container, exactly the way
# Windows runs it: working directory <root>\bin, the three TA_*
# variables set, arguments verbatim.
#
#   wine-tool.sh bin/cod2map64.exe -platform pc -navmesh ...
#
# Paths in the arguments must be the Windows paths under
# C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130
# which is what the prefix maps /tools to.
set -euo pipefail
# Where the tools and the prefix are comes from bo3-wine.env (see
# bo3-wine.env.example); the defaults below apply when that file is absent.
HERE=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=/dev/null
[ -f "$HERE/bo3-wine.env" ] && . "$HERE/bo3-wine.env"
TOOLS=${ZMFORGE_WINE_TOOLS:-$HERE/tools}
PREFIX=${ZMFORGE_WINE_PREFIX:-$HERE/wineprefix}
IMAGE=${BO3_WINE_IMAGE:-bo3-wine:local}
if [ ! -f "$TOOLS/bin/cod2map64.exe" ]; then
    echo "$(basename "$0"): $TOOLS is not a mod-tools install (no bin/cod2map64.exe)." >&2
    echo "Set ZMFORGE_WINE_TOOLS in $HERE/bo3-wine.env, then run $HERE/check.sh." >&2
    exit 2
fi
WIN_ROOT='C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130'
exe="$1"; shift
exec docker run --rm \
    -v "$TOOLS:/tools" \
    -v "$PREFIX:/wineprefix" \
    -v "$HERE/logs:/logs" \
    -e "TA_GAME_PATH=${WIN_ROOT}\\" \
    -e "TA_TOOLS_PATH=${WIN_ROOT}\\" \
    -e "TA_LOCAL_ASSET_CACHE=${WIN_ROOT}\\share\\assetconvert\\" \
    -e WINEDEBUG="${WINEDEBUG:--all}" \
    -e WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-msvcr110,msvcp110=n}" \
    -w "/wineprefix/drive_c/Program Files (x86)/Steam/steamapps/common/Call of Duty Black Ops III 455130/bin" \
    "$IMAGE" wine "${WIN_ROOT}\\${exe//\//\\}" "$@"
