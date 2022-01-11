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
            read -r -p 'View full diff (y)? Start over (s)? Quit viewing diffs (q)? Next commit (n)? (default: n) ' action
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

git fetch --all
if git checkout main 2> /dev/null; then
    mainbr=main
elif git checkout master; then
    mainbr=master
else
    echo ERROR: could not checkout either main or master
    git remote -vv
    exit 1
fi
git pull

read -r -p 'Examine role (y)? (default: n) ' examine_role
if [ "${examine_role:-n}" = y ]; then
    # get latest tag
    latest_tag=$(git describe --tags --abbrev=0)
    # special case for network
    case "$latest_tag" in
    v*) latest_tag="${latest_tag//v}" ;;
    esac
    # get the number of commits since latest tag
    count=$(git log --oneline --no-merges --reverse "${latest_tag}".. | wc -l)
    if [ "${count:-0}" = 0 ]; then
        echo There are no commits since latest tag "$latest_tag"
        echo ""
    else
        echo Commits since latest tag "$latest_tag"
        # get the commits since the tag
        git log --oneline --no-merges --reverse "${latest_tag}"..
        # see the changes?
        read -r -p 'View changes (y)? (default: n) ' view_changes
        if [ "${view_changes:-n}" = y ]; then
            view_diffs "${latest_tag}"
        fi
    fi
    echo "If you want to continue, enter the new tag in the form X.Y.Z"
    echo "where X, Y, and Z are integers corresponding to the semantic"
    echo "version based on the changes above."
    echo "Or, just press Enter to skip this role and go to the next role."
    read -r -p "Old tag is $latest_tag - new tag? (or Enter to skip) " new_tag
    if [ -n "${new_tag}" ]; then
        read -r -p "Edit release notes - press Enter to continue"
        rel_notes_file=".release-notes-${new_tag}"
        if [ ! -f "$rel_notes_file" ]; then
            echo title goes here > "$rel_notes_file"
            echo "" >> "$rel_notes_file"
            git log --oneline --no-merges --reverse --pretty=format:"# %B" "${latest_tag}".. | \
                tr -d '\r' >> "$rel_notes_file"
        fi
        ${EDITOR:-vi} "$rel_notes_file"
        if [ -f CHANGELOG.md ]; then
            read -r -p "Edit CHANGELOG.md - press Enter to continue"
            cat "$rel_notes_file" CHANGELOG.md > .tmp-changelog
            mv .tmp-changelog CHANGELOG.md
            ${EDITOR:-vi} CHANGELOG.md
            git add CHANGELOG.md
            git commit -F "$rel_notes_file"
            git push origin "$mainbr"
        fi
        read -r -p 'Create new github release - press Enter to continue'
        hub release create -t "$mainbr" -F "$rel_notes_file" "$new_tag"
        read -r -p 'Publish to Galaxy - press Enter to continue'
        # note - bug with --no-wait - KeyError: 'github_user'
        # repo and LSR_GH_ORG are referenced but not assigned.
        # shellcheck disable=SC2154
        ansible-galaxy role import --branch "$mainbr" "$LSR_GH_ORG" "$repo"
    fi
fi
