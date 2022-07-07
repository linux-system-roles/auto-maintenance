#!/bin/bash -eux
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT
set -o pipefail

AUTOSKIP=${AUTOSKIP:-true}
# Find the last tag in each role
# Look at the git commits since that tag
# Look at the actual changes since that tag
# Figure out what to use for the new tag
# Figure out what to put in the release notes for the release

CHANGELOG_ONLY=${CHANGELOG_ONLY:-false}
repo=${repo:-$( git remote get-url origin | awk -F'/' '{print $NF}' )}

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
if [ "$CHANGELOG_ONLY" != true ]; then
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
else
    mainbr=$( git branch --show-current )
fi

# get latest tag
latest_tag=$(git describe --tags --abbrev=0 2> /dev/null)
# special case for network and sshd
case "$latest_tag" in
v*)
    if [ "$repo" != "ansible-sshd" ]; then
        latest_tag="${latest_tag//v}"
    fi
    ;;
esac
skip=false
if [ -z "$latest_tag" ]; then
    # repo and LSR_GH_ORG are referenced but not assigned.
    # shellcheck disable=SC2154
    echo Repo for "$LSR_GH_ORG" "$repo" has no tags - create one below or skip
else
    # get the number of commits since latest tag
    count=$(git log --oneline --no-merges --reverse "${latest_tag}".. | wc -l)
    if [ "${count:-0}" = 0 ]; then
        echo There are no commits since latest tag "$latest_tag"
        echo ""
        if [ "$AUTOSKIP" = true ]; then
            echo Autoskip enabled - skipping tag/release for role "$repo"
            skip=true
        fi
    else
        echo Commits since latest tag "$latest_tag"
        echo ""
        # get the commits since the tag
        git log --oneline --no-merges --reverse "${latest_tag}"..
        echo ""
        # see the changes?
        read -r -p 'View changes (y)? (default: n) ' view_changes
        if [ "${view_changes:-n}" = y ]; then
            view_diffs "${latest_tag}"
        fi
    fi
fi
if [ "$skip" = false ]; then
    echo "If you want to continue, enter the new tag in the form X.Y.Z"
    echo "where X, Y, and Z are integers corresponding to the semantic"
    echo "version based on the changes above."
    echo "Or, just press Enter to skip this role and go to the next role."
    read -r -p "Old tag is ${latest_tag:-EMPTY} - new tag? (or Enter to skip) " new_tag
    if [ -n "${new_tag}" ]; then
        read -r -p "Edit release notes - press Enter to continue"
        rel_notes_file=".release-notes-${new_tag}"
        if [ ! -f "$rel_notes_file" ]; then
            { echo "[$new_tag] - $( date +%Y-%m-%d )"; \
              echo "--------------------"; \
              echo ""; \
              echo "REMOVE_ME: Recommend to itemize the change logs in either of the following sections."; \
              echo "REMOVE_ME: Use Other Changes for the CI related items."; \
              echo "### New Features"; \
              echo "### Bug Fixes"; \
              echo "### Other Changes"; } > "$rel_notes_file"
            git log --oneline --no-merges --reverse --pretty=format:"- %B" "${latest_tag}".. | \
                tr -d '\r' >> "$rel_notes_file"
        fi
        ${EDITOR:-vi} "$rel_notes_file"
        if [ -f CHANGELOG.md ]; then
            read -r -p "Edit CHANGELOG.md - press Enter to continue"
            myheader="Changelog
========="
            clheader=$(head -2 CHANGELOG.md)
            if [ "$myheader" = "$clheader" ]; then
                { echo "$clheader"; echo ""; } > .tmp-changelog
                cat "$rel_notes_file" >> .tmp-changelog
                tail -n +3 CHANGELOG.md >> .tmp-changelog
            else
                echo WARNING: Changelog header "$clheader"
                echo not in expected format "$myheader"
                cat "$rel_notes_file" CHANGELOG.md > .tmp-changelog
            fi
            mv .tmp-changelog CHANGELOG.md
            ${EDITOR:-vi} CHANGELOG.md
            git add CHANGELOG.md
            git commit -s -F "$rel_notes_file"
            if [ "$CHANGELOG_ONLY" == true ]; then
                exit 0
            fi
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
