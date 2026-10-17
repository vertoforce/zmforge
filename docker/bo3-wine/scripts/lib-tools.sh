# Look a path up inside a mod-tools install the way Wine does: one component
# at a time, case insensitively. Sourced by ../setup.sh and ../check.sh.
#
# WHY: the install is a Windows tree sitting on a case-sensitive filesystem,
# and its case is not the case anybody writes. The lighting baker really is
# "Radiant_modtools.exe" with a capital R, while the tools' own launcher, the
# published Treyarch documentation and zmforge all spell it lower case. It
# works because Wine does not care. A plain [ -f ] test does, and reports a
# complete install as broken [measured on the mod tools install].

find_ci() {
    local base=$1 rest=$2 part hit
    while [ -n "$rest" ]; do
        part=${rest%%/*}
        [ "$part" = "$rest" ] && rest= || rest=${rest#*/}
        hit=$(find "$base" -maxdepth 1 -iname "$part" -print -quit 2>/dev/null)
        [ -n "$hit" ] || return 1
        base=$hit
    done
    printf '%s\n' "$base"
}

have_file() { local p; p=$(find_ci "$1" "$2") && [ -f "$p" ]; }
have_dir()  { local p; p=$(find_ci "$1" "$2") && [ -d "$p" ]; }

# Read bo3-wine.env without overriding anything already in the environment.
#
# WHY not just `. bo3-wine.env`: a plain source makes the file win over an
# explicit `ZMFORGE_WINE_TOOLS=... ./check.sh`, which is backwards and hides
# the very thing someone is trying to test. The rule is simple:
# the file fills gaps, the
# environment decides.
load_env_file() {
    local file=$1 line name value
    [ -f "$file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; esac
        case "$line" in *=*) ;; *) continue ;; esac
        name=${line%%=*}
        value=${line#*=}
        name=$(printf '%s' "$name" | tr -d '[:space:]')
        # Strip one layer of surrounding quotes, the way an env file is written.
        case "$value" in
            \"*\") value=${value#\"}; value=${value%\"} ;;
            \'*\') value=${value#\'}; value=${value%\'} ;;
        esac
        [ -n "$name" ] || continue
        if [ -z "$(eval "printf '%s' \"\${$name:-}\"")" ]; then
            export "$name=$value"
        fi
    done < "$file"
}
