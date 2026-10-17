#!/usr/bin/env bash
# Say whether this machine can build a Black Ops III map, before anything tries.
#
#     ./check.sh              # read bo3-wine.env, check everything
#     ./check.sh --quiet      # only print failures
#
# WHY this exists: every one of these failures, left unchecked, surfaces deep
# inside Wine as something unrelated. A tools copy missing xanim_export fails
# as an ERROR: line in the linker 30 seconds in. A missing vcrun2012 fails as
# "unimplemented function msvcr110.dll.??0_TaskCollection@..., aborting" with
# no line of the linker's own output. No GPU fails as a bake that runs for
# nine minutes and never ends. Each check below is one of those, moved to the
# front and given a sentence in English.
#
# Exit 0 when a build can run, 1 when something required is missing, 2 when
# only optional things are missing (compile and link will work, the bake will
# not).
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib-tools.sh
. "$HERE/scripts/lib-tools.sh"
load_env_file "$HERE/bo3-wine.env"

TOOLS=${ZMFORGE_WINE_TOOLS:-}
PREFIX=${ZMFORGE_WINE_PREFIX:-$HERE/wineprefix}
IMAGE=${BO3_WINE_IMAGE:-bo3-wine:local}
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

fail=0
warn=0


ok()   { [ "$QUIET" = 1 ] || printf '  ok    %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; fail=$((fail + 1)); }
soft() { printf '  warn  %s\n' "$1"; [ $# -gt 1 ] && printf '        %s\n' "$2"; warn=$((warn + 1)); }
head_() { [ "$QUIET" = 1 ] || printf '\n%s\n' "$1"; }

# ---------------------------------------------------------------- the host --
head_ "host"

if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        ok "docker runs"
    else
        bad "docker is installed but this user cannot talk to it" \
            "try: sudo usermod -aG docker \$USER, then log out and back in"
    fi
else
    bad "docker is not installed" "the mod tools run in a container; there is no host-Wine path here"
fi

if command -v python3 >/dev/null 2>&1; then
    ok "python3 is on PATH (setup.sh patches the ray tracer with it)"
else
    bad "python3 is not on PATH" "setup.sh needs it to write the embree shim"
fi

free_gb=$(df -PBG "$HERE" 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}')
if [ -n "${free_gb:-}" ] && [ "$free_gb" -lt 12 ]; then
    soft "${free_gb} GB free on $HERE" \
         "the Wine prefix plus Radiant's converted-asset cache comes to about 1.5 GB; a link writes fastfiles of 25 GB-scale maps into the tools copy"
else
    ok "${free_gb:-?} GB free on $HERE"
fi

# ----------------------------------------------------------------- the GPU --
head_ "gpu (the lighting bake only; compile and link do not need one)"

gpu_ok=1
if [ -e /dev/nvidia0 ]; then
    ok "/dev/nvidia0 exists"
else
    soft "no /dev/nvidia0" "compile and link will work; the bake will not"
    gpu_ok=0
fi

# Asked with --format rather than by grepping `docker info`: grep -q closes
# the pipe on its first match, docker info takes the SIGPIPE, and pipefail
# turns that into a failed check on a machine that is fine.
runtimes=$(docker info --format '{{range $name, $_ := .Runtimes}}{{$name}} {{end}}' 2>/dev/null)
if [ "${runtimes#*nvidia}" != "$runtimes" ]; then
    ok "docker reports the nvidia runtime"
else
    soft "docker does not list the nvidia runtime" \
         "install nvidia-container-toolkit, or build with --stages compile_full,link"
    gpu_ok=0
fi

if [ "$gpu_ok" = 1 ] && docker info >/dev/null 2>&1; then
    probe=$(docker run --rm --gpus all \
        -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display \
        -e BO3_TOOLS_OPTIONAL=1 \
        "$IMAGE" sh -c 'ls /usr/lib/xorg/modules/drivers/nvidia_drv.so' 2>&1)
    case "$probe" in
        */nvidia_drv.so)
            ok "the runtime injects nvidia_drv.so, so Xorg can run on the card"
            ;;
        *)
            soft "the container gets a GPU but no nvidia_drv.so" \
                 "NVIDIA_DRIVER_CAPABILITIES must include 'graphics'; without it the bake falls back to Xvfb on llvmpipe, where its probe pass does not finish [measured: 246 GLSL link failures]"
            ;;
    esac
fi

# --------------------------------------------------------------- the image --
head_ "image"

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    ok "docker image $IMAGE is built"
else
    bad "docker image $IMAGE is not built" "run ./setup.sh"
fi

# --------------------------------------------------------------- the tools --
head_ "mod tools"

if [ -z "$TOOLS" ]; then
    bad "ZMFORGE_WINE_TOOLS is not set" \
        "copy bo3-wine.env.example to bo3-wine.env and point it at your own mod-tools install (Steam app 455130)"
elif [ ! -d "$TOOLS" ]; then
    bad "ZMFORGE_WINE_TOOLS=$TOOLS is not a directory" \
        "this must be the folder that contains bin/, share/ and map_source/"
else
    ok "tools root $TOOLS"

    # The three executables. Named one at a time, because "an incomplete copy"
    # tells nobody which file to go and fetch.
    for exe in cod2map64.exe linker_modtools.exe radiant_modtools.exe; do
        if have_file "$TOOLS" "bin/$exe"; then
            ok "bin/$exe"
        else
            bad "bin/$exe is missing" "this is not a mod-tools install root, or the copy is partial"
        fi
    done

    # Directories a stage reads. Each one has a stage that dies without it.
    for dir in share/raw map_source/zm usermaps deffiles source_data; do
        if have_dir "$TOOLS" "$dir"; then
            ok "$dir/"
        else
            bad "$dir/ is missing" "the tools copy is partial"
        fi
    done
    for dir in xanim_export share/assetconvert; do
        if have_dir "$TOOLS" "$dir"; then
            ok "$dir/"
        else
            soft "$dir/ is missing" \
                 "the link loads animations by name from xanim_export and caches converted assets in share/assetconvert; a map that needs one fails with the asset named"
        fi
    done

    if [ -w "$TOOLS" ]; then
        ok "the tools root is writable (every stage writes its output inside it)"
    else
        bad "the tools root is not writable" \
            "cod2map64 writes share/raw, the linker writes usermaps/<map>/zone"
    fi

    # The ray tracer, and whether the patch will apply to it.
    embree_found=0
    for rel in bin/avx/embree64r.dll bin/embree64r.dll; do
        dll=$(find_ci "$TOOLS" "$rel") || continue
        embree_found=1
        n=$(python3 - "$dll" <<'PY' 2>/dev/null
import sys
print(open(sys.argv[1], "rb").read().count(b"SetThreadIdealProcessorEx\0"))
PY
)
        case "${n:-x}" in
            1) ok "$rel imports SetThreadIdealProcessorEx once (the patch applies)" ;;
            0) soft "$rel does not import SetThreadIdealProcessorEx" \
                    "either a different embree build, or already patched; if the bake spins at 400% CPU with no output, this is why" ;;
            *) soft "$rel names SetThreadIdealProcessorEx $n times" \
                    "the patch only rewrites a single occurrence and will leave this file alone" ;;
        esac
    done
    [ "$embree_found" = 0 ] && soft "no embree64r.dll under bin/" "the bake needs it; compile and link do not"
fi

# -------------------------------------------------------------- the prefix --
head_ "wine prefix"

if [ -f "$PREFIX/system.reg" ]; then
    ok "prefix at $PREFIX"
else
    bad "no wine prefix at $PREFIX" "run ./setup.sh"
fi

if [ -f "$PREFIX/.zmforge-vcrun2012" ]; then
    ok "Microsoft's VC++ 2012 runtime is installed"
else
    bad "VC++ 2012 is not installed in the prefix" \
        "without it linker_modtools.exe aborts on msvcr110.dll.??0_TaskCollection@details@Concurrency@@QEAA@XZ and prints nothing of its own; run ./setup.sh"
fi

sys32="$PREFIX/drive_c/windows/system32"
for dll in msvcr110.dll msvcp110.dll; do
    if [ -f "$sys32/$dll" ]; then ok "system32/$dll"; else bad "system32/$dll is missing" "run ./setup.sh"; fi
done
for dll in d3d11.dll dxgi.dll d3d10core.dll; do
    if [ -f "$sys32/$dll" ]; then
        ok "system32/$dll (DXVK, for the bake)"
    else
        soft "system32/$dll is missing" "the entrypoint installs DXVK on first run; without it the bake takes 88 s instead of 17 s and logs 335 D3D errors"
    fi
done

if [ -d "$PREFIX/shims" ]; then
    ok "shim directory $PREFIX/shims"
else
    soft "no shims yet at $PREFIX/shims" "setup.sh and the first bake both create them"
fi

# --------------------------------------------------------------- the verdict --
printf '\n'
if [ "$fail" -gt 0 ]; then
    printf '%s required check(s) failed. A build will not run.\n' "$fail"
    exit 1
fi
if [ "$warn" -gt 0 ]; then
    printf 'Ready for compile and link. %s optional check(s) failed, so the lighting bake may not work.\n' "$warn"
    printf 'Build without it: zmforge build <map> --stages compile_full,link\n'
    exit 2
fi
printf 'Ready. Everything the compile, the bake and the link need is here.\n'
exit 0
