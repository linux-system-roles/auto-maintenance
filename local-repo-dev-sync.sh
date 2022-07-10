#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

if [ "${DEBUG:-false}" = true ]; then
    set -x
fi

LSR_GH_ORG=${LSR_GH_ORG:-linux-system-roles}
LSR_BASE_DIR=${LSR_BASE_DIR:-~/linux-system-roles}

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

if [ ! -d "$LSR_BASE_DIR" ]; then
    mkdir -p "$LSR_BASE_DIR"
fi

repos=${REPOS:-$(gh repo list "$LSR_GH_ORG" -L 100 --json name -q '.[].name')}
DEFAULT_EXCLIST=${DEFAULT_EXCLIST:-"test-harness linux-system-roles.github.io sap-base-settings \
                    sap-hana-preconfigure experimental-azure-firstboot sap-preconfigure \
                    auto-maintenance image_builder sap-netweaver-preconfigure ci-testing \
                    meta_test tox-lsr tuned .github lsr-gh-action-py26 \
                    ee_linux_system_roles ee_linux_automation .github"}
declare -A EXARRAY
for repo in $DEFAULT_EXCLIST ${EXCLIST:-}; do
    # EXARRAY is a "set" of excluded repos
    EXARRAY[$repo]=$repo
done

pushd "$LSR_BASE_DIR" > /dev/null
if ! tty -s; then
    stdincmds="$(cat)"
fi

for repo in $repos; do
    if [ -n "${EXARRAY[$repo]:-}" ]; then
        continue
    fi

    echo Repo: "$repo"
    # get a local clone of the repo
    if [ ! -d "$LSR_BASE_DIR/$repo" ]; then
        gh repo clone "$LSR_GH_ORG/$repo" -- -o upstream
    fi
    pushd "$LSR_BASE_DIR/$repo" > /dev/null
    # should have a remote called upstream that points to lsr/repo
    if ! git remote get-url upstream | grep -q "$LSR_GH_ORG/$repo"; then
        echo Error: non-standard git remote config - upstream does not point
        echo to "$LSR_GH_ORG/$repo"
        git remote get-url upstream
        echo please use git remote to configure upstream to point to "$LSR_GH_ORG/$repo"
        exit 1
    fi
    # make sure we have a fork of this under our personal space
    # this will also create a git remote in the local repo if there
    # is not already one - adds a remote called "origin" that points
    # to our fork
    if [ "${MAKE_FORK:-true}" = true ]; then
        prot_save=$(gh config -h github.com get git_protocol)
        gh config -h github.com set git_protocol ssh
        gh repo fork --remote
        gh config -h github.com set git_protocol "$prot_save"
        if [[ "$(git remote get-url origin)" =~ .*:([^/]+)/([^/]+)$ ]]; then
            origin_org="${BASH_REMATCH[1]}"
            origin_repo="${BASH_REMATCH[2]/.git/}"
        else
            echo Error: origin remote points to unknown url "$(git remote get-url origin)"
            exit 1
        fi
        if [ "${RENAME_FORK:-false}" = true ]; then
            newname="${LSR_GH_ORG}"-"$repo"
            if [ "$origin_repo" = "$newname" ]; then
                : # already renamed
            else
                gh repo rename "$newname" -R "$origin_org/$origin_repo"
                origin_repo="$newname"
            fi
        fi
    fi
    git fetch
    if [ -z "${EXARRAY[$repo]:-}" ]; then
        if [ -n "${stdincmds:-}" ] && ! eval "$stdincmds"; then
            echo ERROR: commands read from stdin failed in "$(pwd)"
        fi
        if [ -n "${1:-}" ]; then
            if [ -f "$1" ]; then
                if ! source "$@"; then
                    echo ERROR: command "$1" in "$(pwd)" failed
                fi
            elif ! eval "$@"; then
                echo ERROR: command in "$(pwd)" failed
            fi
        fi
    fi
    popd > /dev/null
done

popd > /dev/null
