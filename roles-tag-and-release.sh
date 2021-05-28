#!/bin/bash -eux
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT
set -o pipefail

# Find the last tag in each role
# Look at the git commits since that tag
# Look at the actual changes since that tag
# Figure out what to use for the new tag
# Figure out what to put in the release notes for the release

# To be used in conjunction with local-repo-dev-sync.sh
# This script is called from every role

view_diffs() {
    local tag="$1"
    local action
    action=""
    while [ "$action" != "q" ]; do
        action=""
        for hsh in $(git log --pretty=format:%h --no-merges --reverse "${tag}.."); do
            git show --stat "$hsh"
            read -r -p 'View full diff (y)? Start over (s)? Quit (q)? ' action
            if [ "$action" = y ]; then
                git show "$hsh"
            elif [ "$action" = s ] || [ "$action" = q ]; then
                break
            fi
            action=""
        done
        if [ -z "${action}" ]; then
            break
        fi
    done
}

mainbr=$(git branch -r | awk '/origin[/]HEAD/ {sub("origin/", "", $3); print $3}')
git checkout "$mainbr"
git pull

read -r -p 'Examine role? ' examine_role
if [ "${examine_role:-n}" = y ]; then
    # get latest tag
    latest_tag=$(git describe --tags --abbrev=0)
    # special case for network
    case "$latest_tag" in
    v*) latest_tag="${latest_tag//v}" ;;
    esac
    echo commits since latest tag "$latest_tag"

    # get the commits since the tag
    git log --oneline --no-merges --reverse "${latest_tag}"..

    # see the changes?
    read -r -p 'View changes? ' view_changes
    if [ "${view_changes:-n}" = y ]; then
        view_diffs "${latest_tag}"
    fi

    read -r -p "Old tag is $latest_tag - what is the new tag? " new_tag
    if [ -n "${new_tag}" ]; then
        read -r -p 'Edit release notes? ' rel_notes
        if [ "${rel_notes:-n}" = y ]; then
            rel_notes_file=".release-notes-${new_tag}"
            if [ ! -f "$rel_notes_file" ]; then
                echo title goes here > "$rel_notes_file"
                echo "" >> "$rel_notes_file"
                git log --oneline --no-merges --reverse --pretty=format:"# %B" "${latest_tag}".. >> "$rel_notes_file"
            fi
            ${EDITOR:-vi} "$rel_notes_file"
            read -r -p 'Create new github release? ' create_release
            if [ "${create_release:-n}" = y ]; then
                hub release create -t "$mainbr" -F "$rel_notes_file" "$new_tag"
                read -r -p 'Publish to Galaxy? ' publish_galaxy
                if [ "${publish_galaxy:-n}" = y ]; then
                    # note - bug with --no-wait - KeyError: 'github_user'
                    # repo and LSR_GH_ORG are referenced but not assigned.
                    # shellcheck disable=SC2154
                    ansible-galaxy role import --branch "$mainbr" "$LSR_GH_ORG" "$repo"
                fi
            fi
        fi
    fi
fi
