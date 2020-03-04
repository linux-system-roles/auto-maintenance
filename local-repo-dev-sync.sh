#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

if [ "${DEBUG:-false}" = true ]; then
    set -x
fi

LSR_GH_ORG=${LSR_GH_ORG:-linux-system-roles}
LSR_BASE_DIR=${LSR_BASE_DIR:-~/linux-system-roles}

requiredcmds="hub jq"
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

if [ ! -d "$LSR_BASE_DIR" ]; then
    mkdir -p "$LSR_BASE_DIR"
fi

##
# GET (list) a given github url, using the page interface to get all
# of the pages, and using a given jq filter to extract fields
#
#    $1 - github url e.g. orgs/linux-system-roles/repos
#    $2 - jq filter e.g. '.[].name'
#
# echos to stdout the filtered results.
# NOTE: the -e argument to jq tells jq to exit with an error code
# if the input is empty - this breaks the loop
gh_get_all() {
    local uri="$1"
    local filter="$2"
    local page=1
    while hub api "${uri}?page=$page" | jq -e -r "$filter"; do
        page=$((page + 1))
    done
}

repos=${REPOS:-$(gh_get_all orgs/linux-system-roles/repos '.[].name')}
EXCLIST=${EXCLIST:-"test-harness linux-system-roles.github.io sap-base-settings \
                     sap-hana-preconfigure experimental-azure-firstboot sap-preconfigure \
                     auto-maintenance image_builder sap-netweaver-preconfigure ci-testing \
                     meta_test tox-lsr tuned postfix"}
declare -A EXARRAY
for repo in $EXCLIST; do
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
        HUB_PROTOCOL=https hub clone "$LSR_GH_ORG/$repo"
    fi
    pushd "$LSR_BASE_DIR/$repo" > /dev/null
    # should have a remote called origin that points to lsr/repo
    if ! git remote get-url origin | grep -q "$LSR_GH_ORG/$repo"; then
        echo Error: non-standard git remote config - origin does not point
        echo to "$LSR_GH_ORG/$repo"
        git remote get-url origin
        echo please use git remote to configure origin to point to "$LSR_GH_ORG/$repo"
        exit 1
    fi
    # make sure we have a fork of this under our personal space
    # this will also create a git remote in the local repo if there
    # is not already one
    forkerr=0
    forkoutput=$(hub fork 2>&1) || forkerr=$?
    if [ $forkerr -ne 0 ]; then
        if ! grep -q "already exists" <<< "$forkoutput"; then
            echo Error: could not create fork of "$LSR_GH_ORG/$repo": "$forkoutput"
            exit 1
        fi
    fi
    git fetch
    if [ -z "${EXARRAY[$repo]:-}" ]; then
        if [ -n "${stdincmds:-}" ] && ! eval "$stdincmds"; then
            echo ERROR: commands read from stdin failed in "$(pwd)"
        fi
        if [ -n "${1:-}" ] && ! eval "$@"; then
            echo ERROR: command in "$(pwd)" failed
        fi
    fi
    popd > /dev/null
done

popd > /dev/null
