#!/usr/bin/env bash
# Make the container's Wine prefix address the tools by the SAME absolute
# Windows path the Steam install uses on Windows.
#
# WHY: the mod tools' own data refers to itself by absolute path in places
# (GDTs, the converted-asset cache, .map prefab references), and the three
# TA_* variables are absolute Windows paths too. Reproducing
# C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130
# inside the prefix means every one of those strings is valid here without
# rewriting a single file.
set -euo pipefail

TOOLS_DIR=${TOOLS_DIR:-/tools}
# Wine prints "error: XDG_RUNTIME_DIR is invalid or not set in the
# environment." on every start when this is unset. That line begins with
# "error:", and zmforge's stage parser treats any ERROR: line (case
# insensitive) as a failed stage - so an unset variable would fail every
# build here. Give it a real directory instead of filtering the log.
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
WINEPREFIX=${WINEPREFIX:-/wineprefix}
STEAM_REL="Program Files (x86)/Steam/steamapps/common"
TOOLS_LEAF=${TOOLS_LEAF:-Call of Duty Black Ops III 455130}

export WINEPREFIX

if [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "== creating wine prefix in $WINEPREFIX" >&2
    wineboot --init >/dev/null 2>&1 || true
    wineserver -w
fi

# The linker needs Microsoft's own VC++ 2012 runtime, not Wine's builtin.
# Measured: with the builtin, linker_modtools.exe dies at
#   wine: Call from ... to unimplemented function
#   msvcr110.dll.??0_TaskCollection@details@Concurrency@@QEAA@XZ, aborting
# i.e. the Concurrency Runtime task scheduler, which Wine's msvcr110 does
# not implement. vcrun2012 installs the real DLLs into the prefix and the
# link then runs. cod2map64.exe does not need this and compiles either way.
if [ ! -f "$WINEPREFIX/.zmforge-vcrun2012" ]; then
    echo "== installing vcrun2012 into $WINEPREFIX" >&2
    export USER=${USER:-root}
    if xvfb-run -a winetricks -q vcrun2012 >"${WINEPREFIX}/.zmforge-vcrun2012.log" 2>&1; then
        touch "$WINEPREFIX/.zmforge-vcrun2012"
    else
        echo "!! vcrun2012 install failed; see $WINEPREFIX/.zmforge-vcrun2012.log" >&2
    fi
    wineserver -w
fi

# DXVK's D3D11 for the bake (see the Dockerfile). Copied, not mounted: a
# native DLL is only picked over Wine's builtin when WINEDLLOVERRIDES asks,
# so the file sitting in system32 changes nothing for the compile or link.
if [ -d /opt/dxvk/x64 ] && [ -d "$WINEPREFIX/drive_c/windows/system32" ]; then
    for dll in d3d11 dxgi d3d10core; do
        if ! cmp -s "/opt/dxvk/x64/$dll.dll" "$WINEPREFIX/drive_c/windows/system32/$dll.dll"; then
            cp "/opt/dxvk/x64/$dll.dll" "$WINEPREFIX/drive_c/windows/system32/$dll.dll"
        fi
    done
fi

# Fail here, in English, rather than eight layers down. Without a real tools
# copy on /tools the symlink below still succeeds and every failure that
# follows names something else: wine reports "Application could not be
# started", or the linker reads an empty search path and prints ERROR: lines
# about assets. BO3_TOOLS_OPTIONAL=1 is for the container probes that do not
# mount the tools at all (check.sh asks the image about its GPU libraries).
if [ "${BO3_TOOLS_OPTIONAL:-0}" != "1" ] && [ ! -f "$TOOLS_DIR/bin/cod2map64.exe" ]; then
    cat >&2 <<EOF
!! $TOOLS_DIR holds no mod-tools install: bin/cod2map64.exe is not there.
   This container expects your own Black Ops III mod tools (Steam app 455130)
   bind-mounted at $TOOLS_DIR. Nothing of Activision's ships in this image.
   Set ZMFORGE_WINE_TOOLS in bo3-wine.env and run ./check.sh.
EOF
    exit 78
fi

target="$WINEPREFIX/drive_c/$STEAM_REL/$TOOLS_LEAF"
mkdir -p "$WINEPREFIX/drive_c/$STEAM_REL"
if [ ! -e "$target" ]; then
    ln -s "$TOOLS_DIR" "$target"
fi

exec "$@"
