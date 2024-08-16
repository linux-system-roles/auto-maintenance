#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

if [ "${DEBUG:-false}" = true ]; then
    set -x
fi

LSR_GH_ORG=${LSR_GH_ORG:-linux-system-roles}
# only needed if operating on local code

requiredcmds="gh jq"
missingcmds=""

for cmd in $requiredcmds; do
    if ! type -p "$cmd" > /dev/null 2>&1; then
        missingcmds="$missingcmds $cmd"
    fi
done

if [ -n "$missingcmds" ]; then
    echo ERROR: this script requires the following commands: "$missingcmds"
    echo e.g. on Fedora - dnf -y install "$missingcmds"
    exit 1
fi

if [ -n "${GITHUB_TOKEN:-}" ] || [ -f "$HOME/.config/hub" ] || [ -f "$HOME/.config/gh/hosts.yml" ]; then
    : # ok
else
    echo ERROR: no github credentials specified for the gh command.
    echo Please see "'man gh-auth-login'" for how to specify
    echo credentials in your \$HOME/.config/gh/hosts.yml config file.
    echo Alternately, you can use the GITHUB_TOKEN environment variable.
    exit 1
fi

if [ -n "${LSR_BASE_DIR:-}" ] && [ ! -d "$LSR_BASE_DIR" ]; then
    mkdir -p "$LSR_BASE_DIR"
fi

clone_repo() {
    local base_dir org repo def_repo prot_save forked newname origin_repo
    base_dir="$1"
    org="$2"
    repo="$3"
    # get a local clone of the repo
    if [ ! -d "$base_dir/$repo" ]; then
        gh repo clone "$org/$repo" "$repo" -- -o upstream
    fi
    pushd "$base_dir/$repo" > /dev/null
    # should have a remote called upstream that points to lsr/repo
    if ! git remote get-url upstream | grep -q "$org/$repo"; then
        echo Error: non-standard git remote config - upstream does not point
        echo to "$org/$repo"
        git remote get-url upstream
        echo please use git remote to configure upstream to point to "$org/$repo"
        exit 1
    fi
    def_repo="$(gh repo set-default xxx/xxx --view 2>&1)"
    if [ -z "$def_repo" ] || [[ "$def_repo" =~ "no default repository" ]]; then
        gh repo set-default "$org/$repo"
    fi
    # make sure we have a fork of this under our personal space
    # this will also create a git remote in the local repo if there
    # is not already one - adds a remote called "origin" that points
    # to our fork
    if [ "${MAKE_FORK:-true}" = true ]; then
        prot_save=$(gh config -h github.com get git_protocol)
        gh config -h github.com set git_protocol ssh
        forked=false
        if ! gh repo fork --remote; then
            echo cannot fork
        else
            forked=true
        fi
        gh config -h github.com set git_protocol "$prot_save"
        if [ "$forked" = true ]; then
            if [[ "$(git remote get-url origin)" =~ .*:([^/]+)/([^/]+)$ ]]; then
                origin_org="${BASH_REMATCH[1]}"
                origin_repo="${BASH_REMATCH[2]/.git/}"
            else
                echo Error: origin remote points to unknown url "$(git remote get-url origin)"
                exit 1
            fi
            if [ "${RENAME_FORK:-false}" = true ]; then
                newname="${org}"-"$repo"
                if [ "$origin_repo" = "$newname" ]; then
                    : # already renamed
                else
                    gh repo rename "$newname" -R "$origin_org/$origin_repo"
                fi
            fi
        fi
    fi
    git fetch --all --quiet
}

repos=${REPOS:-$(gh repo list "$LSR_GH_ORG" -L 100 --json name -q '.[].name')}
DEFAULT_EXCLIST=${DEFAULT_EXCLIST:-"tft-tests test-harness linux-system-roles.github.io sap-base-settings \
                    sap-hana-preconfigure experimental-azure-firstboot sap-preconfigure \
                    auto-maintenance image_builder sap-netweaver-preconfigure ci-testing \
                    meta_test tox-lsr tuned .github lsr-gh-action-py26 \
                    ee_linux_system_roles ee_linux_automation lsr-woke-action"}
declare -A EXARRAY
for repo in $DEFAULT_EXCLIST ${EXCLIST:-}; do
    # EXARRAY is a "set" of excluded repos
    EXARRAY["$repo"]="$repo"
done

if [ -n "${LSR_BASE_DIR:-}" ]; then
    pushd "$LSR_BASE_DIR" > /dev/null
fi
if ! tty -s; then
    stdincmds="$(cat)"
fi

for repo in $repos; do
    if [ -n "${EXARRAY[$repo]:-}" ]; then
        continue
    fi

    echo Repo: "$repo"
    if [ -n "${LSR_BASE_DIR:-}" ]; then
        clone_repo "$LSR_BASE_DIR" "$LSR_GH_ORG" "$repo"
    fi
    if [ -z "${upstream_org:-}" ]; then
        upstream_org="$LSR_GH_ORG"
    fi
    if [ -z "${origin_org:-}" ]; then
        origin_org="$upstream_org"
    fi
    if [ -z "${EXARRAY[$repo]:-}" ]; then
        if [ -n "${stdincmds:-}" ] && ! eval "$stdincmds"; then
            echo ERROR: commands read from stdin failed in "$(pwd)"
        fi
        if [ -n "${1:-}" ]; then
            if [ -f "$1" ]; then
                # shellcheck disable=SC1090
                if ! source "$@"; then
                    echo ERROR: command "$1" in "$(pwd)" failed
                fi
            elif ! eval "$*"; then
                echo ERROR: command in "$(pwd)" failed
            fi
        fi
    fi
    if [ -n "${LSR_BASE_DIR:-}" ]; then
        popd > /dev/null
    fi
done
