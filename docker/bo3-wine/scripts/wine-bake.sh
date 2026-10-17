#!/usr/bin/env bash
# Run the lighting bake for one map under Wine, the way zmforge's WineRunner
# does it (zmforge.toolchain.wine), for hands-on runs and experiments:
#
#   scripts/wine-bake.sh zm_forge_gate            # +medium
#   scripts/wine-bake.sh zm_mymap final
#
# Three things make the bake work here, and all three are applied by default
# [measured]:
#   --gpus all + with-display   Radiant is a Qt program and needs an X
#                               connection; its probe pass renders through
#                               D3D11, which goes to an NVIDIA GPU through
#                               DXVK (d3d11,dxgi,d3d10core=n below; the image
#                               entrypoint puts DXVK in the prefix).
#   embree shim                 bin\avx\embree64r.dll with one import renamed
#                               (scripts/patch-embree.py). Without it embree
#                               has one worker thread and nothing finishes.
#   blank GdtDBTrayLauncher.exe the tray helper page-faults under Wine and
#                               its crash line reads as a loader failure.
#
# Extra docker arguments go in BAKE_DOCKER_ARGS. Radiant does not exit on its
# own after exporting, so cap the run: timeout -k 15 600 scripts/wine-bake.sh ...
# and read wineprefix/drive_c/users/root/Documents/Radiant.log for the phases.
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
map="$1"; quality="${2:-medium}"
shims="$PREFIX/shims/bin"
python3 "$HERE/scripts/patch-embree.py" "$TOOLS" "$PREFIX/shims" >/dev/null
mkdir -p "$shims" "$PREFIX/dxvk-logs"; : > "$shims/GdtDBTrayLauncher.exe"
shim_mounts=()
for rel in avx/embree64r.dll embree64r.dll GdtDBTrayLauncher.exe; do
    [ -f "$shims/$rel" ] && shim_mounts+=(-v "$shims/$rel:/tools/bin/$rel:ro")
done
# shellcheck disable=SC2206
extra=(${BAKE_DOCKER_ARGS:-})
exec docker run --rm --gpus all "${shim_mounts[@]}" "${extra[@]}" \
    -v "$TOOLS:/tools" \
    -v "$PREFIX:/wineprefix" \
    -v "$HERE/logs:/logs" \
    -e "TA_GAME_PATH=${WIN_ROOT}\\" \
    -e "TA_TOOLS_PATH=${WIN_ROOT}\\" \
    -e "TA_LOCAL_ASSET_CACHE=${WIN_ROOT}\\share\\assetconvert\\" \
    -e WINEDEBUG="${WINEDEBUG:--all}" \
    -e WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree=d;msvcr110,msvcp110=n;d3d11,dxgi,d3d10core=n}" \
    -e DXVK_LOG_PATH=/wineprefix/dxvk-logs \
    -w "/wineprefix/drive_c/Program Files (x86)/Steam/steamapps/common/Call of Duty Black Ops III 455130/bin" \
    "$IMAGE" with-display wine "${WIN_ROOT}\\bin\\radiant_modtools.exe" \
    -ledSilent "+${quality}" +localprobes +forceclean +recompute \
    "${WIN_ROOT}\\map_source\\zm\\${map}.map"
