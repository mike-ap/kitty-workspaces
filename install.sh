#!/bin/sh
# Install or remove project-owned files; Kitty configuration is managed manually.
set -eu

project=kitty-workspaces
package_name=kitty_workspaces
endpoints='kitten.py worker.py watcher.py'
previous_endpoints='kitty_workspaces.py kitty_workspaces_collector.py kitty_workspaces_watcher.py'
configs='kitty-workspaces.conf tab_bar.py.example'
uninstall=false
usage() {
    echo "Usage: $0 [--config-dir PATH] [--source-dir PATH] [--uninstall]" >&2
    exit 2
}
fail() {
    echo "Cannot change installation: $*" >&2
    exit 1
}
config_dir=${KITTY_CONFIG_DIRECTORY:-${XDG_CONFIG_HOME:-$HOME/.config}/kitty}
source_dir=$(CDPATH='' cd -P "$(dirname "$0")" && pwd -P) || exit 1
while [ "$#" -gt 0 ]; do
    case $1 in
        --config-dir)
            [ "$#" -ge 2 ] || usage
            config_dir=$2
            shift 2
            ;;
        --source-dir)
            [ "$#" -ge 2 ] || usage
            source_dir=$2
            shift 2
            ;;
        --uninstall)
            uninstall=true
            shift
            ;;
        *) usage ;;
    esac
done
case $config_dir in
    '~') config_dir=$HOME ;;
    \~/*) config_dir=$HOME/${config_dir#\~/} ;;
esac
package=$config_dir/$package_name
marker=$package/.$project

# Validate the entire managed namespace before copying or removing anything.
[ ! -L "$package" ] || fail "$package must not be a symlink"
if [ -e "$package" ]; then
    if [ ! -d "$package" ] || [ ! -f "$marker" ] || [ -L "$marker" ]; then
        fail "$package is not owned by this installer"
    fi
    [ "$(head -n 1 "$marker")" = "Installed by $project" ] || fail "invalid ownership marker"
    for member in "$package"/*.py; do
        [ -e "$member" ] || [ -L "$member" ] || continue
        if [ ! -f "$member" ] || [ -L "$member" ]; then
            fail "$member must be a regular file"
        fi
    done
fi
for cache in "$package/__pycache__" "$config_dir/__pycache__"; do
    if [ -L "$cache" ] || { [ -e "$cache" ] && [ ! -d "$cache" ]; }; then
        fail "$cache must be a directory, not a symlink"
    fi
done
# Former root entry points may be removed only with a valid package ownership marker.
if [ -f "$marker" ]; then
    for name in $previous_endpoints; do
        endpoint=$config_dir/$name
        if [ -L "$endpoint" ] || { [ -e "$endpoint" ] && [ ! -f "$endpoint" ]; }; then
            fail "$endpoint must be a regular file"
        fi
    done
fi

clear_caches() {
    rm -rf -- "$package/__pycache__"
    if [ -d "$config_dir/__pycache__" ]; then
        for name in $previous_endpoints; do
            for cached in "$config_dir"/__pycache__/"${name%.py}".*.pyc; do
                [ -f "$cached" ] || [ -L "$cached" ] || continue
                rm -f -- "$cached"
            done
        done
    fi
}

if [ "$uninstall" = true ]; then
    clear_caches
    if [ -f "$marker" ]; then
        for name in $previous_endpoints; do
            rm -f -- "$config_dir/$name"
        done
    fi
    if [ -d "$package" ]; then
        rm -f -- "$package"/*.py
        # Keep configuration and the ownership record so reinstall remains safe.
    fi
    echo "Removed $project files. Remove its configuration entries manually and restart Kitty."
    exit 0
fi

if [ ! -f "$source_dir/src/$package_name/__init__.py" ] || [ ! -f "$source_dir/pyproject.toml" ]; then
    fail "incomplete source directory"
fi
for name in $endpoints; do
    [ -f "$source_dir/src/$package_name/$name" ] || fail "incomplete source directory"
done
for name in $configs; do
    [ -f "$source_dir/config/$name" ] || fail "missing configuration file $name"
done
# Release metadata uses a literal version in the project table; no Python needed.
version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$source_dir/pyproject.toml")
case $version in
    '' | *[!0-9A-Za-z.+_-]*) fail "missing or invalid project version" ;;
esac
mkdir -p "$package"
# The package's Python files are installer-owned, including obsolete modules.
for member in "$package"/*.py; do
    [ -f "$member" ] || continue
    name=${member##*/}
    [ -f "$source_dir/src/$package_name/$name" ] || rm -f -- "$member"
done
clear_caches
cp "$source_dir"/src/"$package_name"/*.py "$package/"
if [ -f "$marker" ]; then
    for name in $previous_endpoints; do
        rm -f -- "$config_dir/$name"
    done
fi
# Configuration belongs to the user once copied; preserve edits and links.
for name in $configs; do
    destination=$package/$name
    if [ "$name" = tab_bar.py.example ]; then
        destination=$config_dir/$name
    elif [ -f "$marker" ] && [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
        # Preserve configuration from earlier layouts, including edited examples.
        for previous in "$config_dir/$name" "$package/$name.example" "$config_dir/$name.example"; do
            if [ -e "$previous" ] || [ -L "$previous" ]; then
                mv -- "$previous" "$destination"
                break
            fi
        done
    fi
    if [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
        cp "$source_dir/config/$name" "$destination"
    fi
done
# Write the version only after all copies succeed.
printf '%s\n' "Installed by $project" "version=$version" >"$marker"
echo "Installed $project $version in $config_dir."
echo "Follow the configuration file comments to enable $project, then restart Kitty."
