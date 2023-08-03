#!/bin/bash

set -euxo pipefail

SPEC_FILE="${SPEC_FILE:-linux-system-roles.spec}"

usage() {
    cat <<EOF
$0 [-s branch|--src_branch branch] dest_remote dest_branch
If src_branch is not specified, it will use the current branch
EOF
}

src_branch="$(git rev-parse --abbrev-ref HEAD)"
case "$1" in
-s|--src_branch) shift; src_branch="$1"; shift;;
esac

dest_remote="$1"; shift
dest_branch="$1"; shift

if git checkout "$dest_branch"; then
    git merge "$src_branch"
else
    git checkout -b "$dest_branch" "$src_branch"
fi

spectool -g "$SPEC_FILE"
upload_flags=()
if [ "${dry_run:-true}" = true ]; then
    upload_flags+=("--offline")
fi
# shellcheck disable=SC2046
fedpkg upload "${upload_flags[@]}" $(awk -F'[ ()]' '{print $3}' sources)
git diff --cached
git reset --hard HEAD  # reset changed sources .gitignore
if [ "${dry_run:-true}" = false ]; then
    git push "$dest_remote" "$dest_branch"
fi
