#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

AUTOSKIP=${AUTOSKIP:-true}
# Find the last tag in each role
# Look at the git commits since that tag
# Look at the actual changes since that tag
# Figure out what to use for the new tag
# Figure out what to put in the release notes for the release

repo=${repo:-$(git remote get-url origin | awk -F'/' '{print $NF}')}

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

get_main_branch() {
    local br
    br=$(git branch --list main)
    if [ -n "$br" ]; then
        echo main
        return 0
    fi
    br=$(git branch --list master)
    if [ -n "$br" ]; then
        echo master
        return 0
    fi
    echo UNKNOWN
    return 1
}

git fetch --all
# get the main branch
mainbr=$(get_main_branch)
currbr=$(git branch --show-current)
# see if BRANCH already exists - editing an existing PR
if [ -n "${BRANCH:-}" ]; then
    BRANCH_EXISTS=$(git branch --list "$BRANCH")
else # assume user wants to use the currently checked out branch
    BRANCH="$currbr"
fi
if [ "$BRANCH" = "$mainbr" ]; then
    echo ERROR: need a branch to use for the commit/PR
    echo please set BRANCH to the branch you want to use for the PR
    echo or git checkout the branch
    exit 1
fi
if [ "$BRANCH" = "$currbr" ]; then
    : # using current branch "$currbr"
elif [ -n "${BRANCH_EXISTS:-}" ]; then
    git checkout "$BRANCH"
else
    git checkout "$mainbr"
    git checkout -b "$BRANCH"
fi
echo Using branch "$BRANCH" for the changelog commit/PR

# get latest tag
latest_tag=$(git describe --tags --abbrev=0 2> /dev/null || :)
# special case for network and sshd
allow_v=""
case "$latest_tag" in
v*)
    if [ "$repo" = ansible-sshd ] || [ "$repo" = sshd ]; then
        # sshd uses a leading v
        allow_v=v
    else
        # network had a case where there where two tags for the
        # latest - one with leading v and one without - git describe
        # would return the one with the leading v - so had to strip
        # it off
        latest_tag="${latest_tag//v}"
    fi
    ;;
esac
skip=false
if [ -z "$latest_tag" ]; then
    # repo and LSR_GH_ORG are referenced but not assigned.
    # shellcheck disable=SC2154
    echo Repo for "${LSR_GH_ORG:-linux-system-roles}" "$repo" has no tags - create one below or skip
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
        read -r -p 'View changes (n/y/s)? (default: n) ' view_changes
        if [ "${view_changes:-n}" = y ]; then
            view_diffs "${latest_tag}"
        elif [ "${view_changes:-n}" = s ]; then
            skip=true
        fi
    fi
fi
if [ "$skip" = false ]; then
    echo "If you want to continue, enter the new tag in the form ${allow_v}X.Y.Z"
    echo "where X, Y, and Z are integers corresponding to the semantic"
    echo "version based on the changes above."
    echo "Or, just press Enter to skip this role and go to the next role."
    while true; do
        read -r -p "Old tag is ${latest_tag:-EMPTY} - new tag? (or Enter to skip) " new_tag
        if [ -z "$new_tag" ]; then
            break
        elif [[ "$new_tag" =~ ^"$allow_v"[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
            break
        else
            echo ERROR: invalid tag "$new_tag"
            echo Tag must be in format "$allow_v"X.Y.Z
            echo ""
        fi
    done
    if [ -n "${new_tag}" ]; then
        read -r -p "Edit CHANGELOG.md - press Enter to continue"
        rel_notes_file=".release-notes-${new_tag}"
        if [ ! -f "$rel_notes_file" ]; then
            { echo "[$new_tag] - $( date +%Y-%m-%d )"
              echo "--------------------"
              echo ""
              echo "REMOVE_ME: Recommend to itemize the change log entries in one of the following sections."
              echo "REMOVE_ME: If a section has no entries, it should be removed."
              echo "REMOVE_ME: Use 'Other Changes' for non-feature/non-bug changes such as:"
              echo "REMOVE_ME: - updates to documentation"
              echo "REMOVE_ME: - updates to examples"
              echo "REMOVE_ME: - deprecations (for example related to conscious language)"
              echo "REMOVE_ME: Do not mention changes that not visible for users such as changes to tests or github actions."
              echo "REMOVE_ME: If you need to cut a release without any user-visible changes, simply state as only item '- no user-visible changes' instead of adding more details."

              echo "### New Features"
              echo ""
              echo "### Bug Fixes"
              echo ""
              echo "### Other Changes"; } > "$rel_notes_file"
            if [ -n "$latest_tag" ]; then
                git_range="${latest_tag}.."
            else
                git_range=HEAD
            fi
            git log --oneline --no-merges --reverse --pretty=format:"- %B" "$git_range" | \
                tr -d '\r' >> "$rel_notes_file"
        fi
        ${EDITOR:-vi} "$rel_notes_file"
        myheader="Changelog
========="
        if [ -f CHANGELOG.md ]; then
            clheader=$(head -2 CHANGELOG.md)
        else
            clheader="$myheader"
        fi
        if [ "$myheader" = "$clheader" ]; then
            { echo "$clheader"; echo ""; } > .tmp-changelog
            cat "$rel_notes_file" >> .tmp-changelog
            if [ -f CHANGELOG.md ]; then
                tail -n +3 CHANGELOG.md >> .tmp-changelog
            fi
        else
            echo WARNING: Changelog header "$clheader"
            echo not in expected format "$myheader"
            cat "$rel_notes_file" CHANGELOG.md > .tmp-changelog
        fi
        mv .tmp-changelog CHANGELOG.md
        git add CHANGELOG.md
        { echo "docs(changelog): version $new_tag [citest skip]"; echo "";
          echo "Create changelog update and release for version $new_tag"; } > .gitcommitmsg
        git commit -s -F .gitcommitmsg
        rm -f .gitcommitmsg "$rel_notes_file"
        if [ -n "${origin_org:-}" ]; then
            git push -u origin "$BRANCH"
            gh pr create --fill --base "$mainbr" --head "$origin_org":"$BRANCH"
        fi
    fi
fi
