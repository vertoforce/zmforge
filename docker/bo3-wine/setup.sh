#!/usr/bin/env bash
# Get from a fresh checkout to a machine that can build a map.
#
#     cp bo3-wine.env.example bo3-wine.env     # then edit the one path in it
#     ./setup.sh
#
# Four steps, each of which says what it is doing and stops on the first one
# that fails:
#
#   1. read bo3-wine.env and check the mod-tools path really is a mod-tools
#      install, before docker is involved
#   2. build the Wine image (no mod-tools bytes go into it, see .dockerignore)
#   3. create the Wine prefix: Microsoft's VC++ 2012 runtime, DXVK, and the
#      symlink that makes the tools answer to their Windows path
#   4. write the embree shim from your own DLL, and run ./check.sh
#
# Steps 2 and 3 are slow the first time (an apt install and a winetricks run,
# a few minutes) and near-instant afterwards. Re-running this script is safe.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
IMAGE=${BO3_WINE_IMAGE:-bo3-wine:local}

# shellcheck source=scripts/lib-tools.sh
. "$HERE/scripts/lib-tools.sh"

die() { printf '\n!! %s\n' "$1" >&2; shift; for line in "$@"; do printf '   %s\n' "$line" >&2; done; exit 1; }
step() { printf '\n== %s\n' "$1"; }

# ------------------------------------------------------- 1. where the tools are --
step "1/4 reading bo3-wine.env"

if [ ! -f "$HERE/bo3-wine.env" ]; then
    die "no $HERE/bo3-wine.env" \
        "cp bo3-wine.env.example bo3-wine.env" \
        "then set ZMFORGE_WINE_TOOLS to your own Black Ops III mod tools install."
fi
# shellcheck source=/dev/null
load_env_file "$HERE/bo3-wine.env"

TOOLS=${ZMFORGE_WINE_TOOLS:-}
PREFIX=${ZMFORGE_WINE_PREFIX:-$HERE/wineprefix}

[ -n "$TOOLS" ] || die "bo3-wine.env does not set ZMFORGE_WINE_TOOLS" \
    "It is the folder Steam app 455130 installed, the one whose name ends in '455130'."
[ -d "$TOOLS" ] || die "ZMFORGE_WINE_TOOLS=$TOOLS is not a directory"

# The checks worth doing before docker starts, because each of them otherwise
# surfaces as a Wine error that names none of this.
missing=()
for want in bin/cod2map64.exe bin/linker_modtools.exe bin/radiant_modtools.exe; do
    have_file "$TOOLS" "$want" || missing+=("$want")
done
for want in share/raw map_source/zm deffiles source_data; do
    have_dir "$TOOLS" "$want" || missing+=("$want/")
done
if [ ${#missing[@]} -gt 0 ]; then
    die "$TOOLS does not look like a mod-tools install" \
        "missing: ${missing[*]}" \
        "The right folder is the one containing bin\\cod2map64.exe. On a Windows" \
        "install that is:" \
        "  ...\\Steam\\steamapps\\common\\Call of Duty Black Ops III 455130"
fi
[ -w "$TOOLS" ] || die "$TOOLS is not writable" \
    "Every stage writes inside the tools root: cod2map64 into share/raw, the linker into usermaps/<map>/zone."

printf '   tools  %s\n' "$TOOLS"
printf '   prefix %s\n' "$PREFIX"

# ------------------------------------------------------------ 2. the image --
step "2/4 building the Wine image ($IMAGE)"

command -v docker >/dev/null 2>&1 || die "docker is not installed" \
    "The mod tools run in a container. There is no host-Wine path here."
docker info >/dev/null 2>&1 || die "this user cannot talk to the docker daemon" \
    "try: sudo usermod -aG docker \$USER, then log out and back in"

docker build -t "$IMAGE" "$HERE"

# ----------------------------------------------------------- 3. the prefix --
step "3/4 creating the Wine prefix"
printf '   First run installs Microsoft VC++ 2012 through winetricks. Minutes, not seconds.\n'

mkdir -p "$PREFIX"
# The image's entrypoint is the whole of prefix creation: wineboot, vcrun2012,
# DXVK into system32, and the symlink that gives the tools their Windows path.
# Running `true` through it does all of that and then exits.
docker run --rm \
    -v "$TOOLS:/tools" \
    -v "$PREFIX:/wineprefix" \
    "$IMAGE" true

[ -f "$PREFIX/.zmforge-vcrun2012" ] || die "the VC++ 2012 install did not finish" \
    "see $PREFIX/.zmforge-vcrun2012.log" \
    "Without it linker_modtools.exe aborts on" \
    "  msvcr110.dll.??0_TaskCollection@details@Concurrency@@QEAA@XZ" \
    "and prints no line of its own."

# ------------------------------------------------------------- 4. the shim --
step "4/4 patching the ray tracer into the shim directory"
printf '   Your own bin/avx/embree64r.dll is read, one imported function name is\n'
printf '   rewritten, and the result is written under the prefix. Your copy of the\n'
printf '   file is not modified. See PATCHES.md.\n'

python3 "$HERE/scripts/patch-embree.py" "$TOOLS" "$PREFIX/shims"
mkdir -p "$PREFIX/shims/bin"
: > "$PREFIX/shims/bin/GdtDBTrayLauncher.exe"

step "checking"
set +e
"$HERE/check.sh"
verdict=$?
set -e

if [ "$verdict" = 0 ]; then
    cat <<EOF

Build a map:

    cd ../..   # the zmforge checkout
    ZMFORGE_WINE_TOOLS=$TOOLS \\
      .venv/bin/zmforge build <map>

Or run one stage by hand:

    ./scripts/wine-bake.sh <map>
EOF
fi
exit "$verdict"
