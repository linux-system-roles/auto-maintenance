#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

AUTOSKIP="${AUTOSKIP:-true}"
# Find the last tag in each role
# Look at the merged PRs since that tag
# Automatically figure out what version to use for the new tag
# Automatically figure out what to put in the release notes for the release

# By default, if there are PR titles that do not follow the conventional
# commits format, the script will exit with an error.  You can set
# ALLOW_BAD_PRS=true to continue to edit the CHANGELOG to deal with
# the bad PR titles.
ALLOW_BAD_PRS="${ALLOW_BAD_PRS:-false}"

repo_entries="$(gh repo view --json name,owner)"
repo=${repo:-$(echo "$repo_entries" | jq -r .name)}
owner=${owner:-$(echo "$repo_entries" | jq -r .owner.login)}

# To be used in conjunction with local-repo-dev-sync.sh
# This script is called from every role

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

if ! type -p npm > /dev/null 2>&1; then
    echo npm command not found
    echo On Fedora, try 'sudo dnf install npm -y'
    exit 1
fi

export npm_config_prefix="$HOME/.local"
export npm_config_global=True

if ! npm list @commitlint/cli > /dev/null 2>&1; then
    npm install @commitlint/cli
fi
# There is a bug with config-conventional
# https://github.com/conventional-changelog/commitlint/issues/613
# workaround by setting NODE_PATH below
if ! npm list @commitlint/config-conventional > /dev/null 2>&1; then
    npm install @commitlint/config-conventional
fi
export NODE_PATH="$npm_config_prefix/lib/node_modules/@commitlint/config-conventional/node_modules"

git fetch --all --force
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

# get latest release
releases_latest=$(gh api repos/"$owner"/"$repo"/releases/latest -q '.tag_name,.published_at' 2> /dev/null || :)
skip=false
pr_titles_file=".pr_titles.txt"
prs_file=".prs.json"
commitlint_errors_file=".commitlint_errors.txt"
if [[ "$releases_latest" == *"Not Found"* ]]; then
    # repo and LSR_GH_ORG are referenced but not assigned.
    # shellcheck disable=SC2154
    echo Repo for "${LSR_GH_ORG:-linux-system-roles}" "$repo" has no tags - create one below or skip
    latest_tag=""
    tag_range=""
else
    latest_tag="$(echo "$releases_latest" | sed -n 1p)"
    tag_range="closed:>$(echo "$releases_latest" | sed -n 2p)"
fi
# Note that first: 100 is a maximum, it would work only if there are <100 PRs since last tag
prs_query="$(cat <<EOF
query {
  search(query: "repo:$owner/$repo is:pr is:merged $tag_range", type: ISSUE, first: 100) {
    issueCount
    edges {
      node {
        ... on PullRequest {
          number
          title
          body
          mergedAt
        }
      }
    }
  }
}
EOF
)"
gh api graphql -f query="$prs_query" -q '.data.search' > $prs_file
count=$(jq '.issueCount' "$prs_file")
if [ "${count:-0}" = 0 ]; then
    echo There are no merged PRs since latest tag "$latest_tag"
    echo ""
    if [ "$AUTOSKIP" = true ]; then
        echo Autoskip enabled - skipping tag/release for role "$repo"
        skip=true
    fi
else
    echo Pull requests since latest tag "$latest_tag":
    echo ""
    : > $pr_titles_file
    pr_descriptions=()
    # loop through pr_list in reverse to populate changelog in chronological order
    for ((i="$count"-1; i>=0; i--)); do
        pr_entry="$(jq '.edges['$i'].node' $prs_file)"
        pr_title="$(echo "$pr_entry" | jq -r '.title')"
        pr_num="$(echo "$pr_entry" | jq -r '.number')"
        pr_body="$(echo "$pr_entry" | jq -r '.body')"
        echo "$pr_title" >> "$pr_titles_file"
        if [ -n "$pr_body" ]; then
            # Indent pr_body 2 spaces to act as a bullet content for pr_title
            pr_body_ind="$(echo "$pr_body"  | awk '{ print "  " $0 }')"
            printf -v pr_description -- "- %s (#%s)\n\n%s\n" "$pr_title" "$pr_num" "$pr_body_ind"
        else
            printf -v pr_description -- "- %s (#%s)\n" "$pr_title" "$pr_num"
        fi
        pr_descriptions+=("$pr_description")
    done
    cat $pr_titles_file
    echo ""
    # see the changes?
    read -r -p 'Skip this role? (y/n)? (default: n) ' skip_role
    if [ "${skip_role:-n}" = y ]; then
        skip=true
    fi
fi
if [ "$skip" = false ]; then
    if [ -s "$pr_titles_file" ] && [ "${ALLOW_BAD_PRS}" = false ] && [ "${count:-0}" != 0 ]; then
        echo ""
        echo Verifying if all PR titles comply with the conventional commits format
        : > $commitlint_errors_file
        while read -r pr_title; do
            echo "$pr_title" | npx commitlint >> $commitlint_errors_file 2>&1 || :
        done < $pr_titles_file
        if [ -s "$commitlint_errors_file" ]; then
            echo ERROR: the following PR titles failed commitlint the check:
            cat "$commitlint_errors_file"
            exit 1
        else
            echo Success
        fi
    fi
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
    if [[ "$latest_tag" =~ ^"$allow_v"([0-9]+)[.]([0-9]+)[.]([0-9]+)$ ]]; then
        ver_major="${BASH_REMATCH[1]}"
        ver_minor="${BASH_REMATCH[2]}"
        ver_patch="${BASH_REMATCH[3]}"
    elif [ -z "$latest_tag" ]; then
        ver_major=0
        ver_minor=0
        ver_patch=0
    else
        echo ERROR: unexpected tag "$latest_tag"
        exit 1
    fi
    if grep -q '^.*!:.*' $pr_titles_file; then
        # Don't bump ver_major for prerelease versions (when ver_major=0)
        if [[ "$ver_major" != 0 ]]; then
            ver_major=$((ver_major+=1))
            ver_minor=0
            ver_patch=0
        else
            ver_major=0
            ver_minor=$((ver_minor+=1))
            ver_patch=0
        fi
    elif grep -q '^feat.*' $pr_titles_file; then
        ver_minor=$((ver_minor+=1))
        ver_patch=0
    else
        ver_patch=$((ver_patch+=1))
    fi
    new_tag="${allow_v}$ver_major.$ver_minor.$ver_patch"
    while true; do
        read -r -p "The script calculates the new tag based on PR titles types.
The previous tag is ${latest_tag:-EMPTY}.
The new tag is $new_tag.
You have three options:
1. To continue with the suggested new tag $new_tag and edit CHANGELOG.md, enter 'y',
2. To provide a different tag, and edit CHANGELOG.md enter the new tag in the following format:
   ${allow_v}X.Y.Z, where X, Y, and Z are integers,
3. To skip this role and go to the next role just press Enter. " new_tag_in
        if [ -z "$new_tag_in" ]; then
            break
        elif [[ "$new_tag_in" =~ ^"$allow_v"[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
            new_tag=$new_tag_in
            break
        elif [ "$new_tag_in" == y ]; then
            break
        else
            echo ERROR: invalid input "$new_tag_in"
            echo You must either input y or provide a new tag.
            echo Tag must be in format "$allow_v"X.Y.Z
            echo ""
        fi
    done
    if [ -n "${new_tag_in}" ]; then
        rel_notes_file=".release-notes-${new_tag}.md"
        new_features_file=.new_features.md
        bug_fixes_file=.bug_fixes.md
        other_changes_file=.other_changes.md
        rm -f "$new_features_file" "$bug_fixes_file" "$other_changes_file"
        for pr_description in "${pr_descriptions[@]}"; do
            if echo "$pr_description" | sed -n 1p | grep '^- feat.*'; then
                echo "$pr_description" >> "$new_features_file"
            elif echo "$pr_description" | sed -n 1p | grep '^- fix.*'; then
                echo "$pr_description" >> "$bug_fixes_file"
            else
                echo "$pr_description" >> "$other_changes_file"
            fi
        done
        if [ ! -f "$rel_notes_file" ]; then
            {   echo "[$new_tag] - $( date +%Y-%m-%d )"
                echo "--------------------"
                echo ""
            } > "$rel_notes_file"
            if [ -f "$new_features_file" ]; then
                {   echo "### New Features"
                    echo ""
                    cat $new_features_file
                } >> "$rel_notes_file"
            fi
            if [ -f "$bug_fixes_file" ]; then
                {   echo "### Bug Fixes"
                    echo ""
                    cat $bug_fixes_file
                } >> "$rel_notes_file"
            fi
            if [ -f "$other_changes_file" ]; then
                {   echo "### Other Changes"
                    echo ""
                    cat $other_changes_file
                } >> "$rel_notes_file"
            fi
        fi
        # When PR are edited using GH web UI, DOS carriage return ^M appears
        # in PR title and body
        sed -i "s/$(printf '\r')\$//" "$rel_notes_file"
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
        gh api /repos/"$owner"/"$repo"/contents/latest/README.html?ref=docs -q .content | base64 --decode > .README.html
        git add CHANGELOG.md .README.html
        { echo "docs(changelog): version $new_tag [citest skip]"; echo "";
          echo "Update changelog and .README.html for version $new_tag"; } > .gitcommitmsg
        git commit -s -F .gitcommitmsg
        rm -f .gitcommitmsg "$rel_notes_file" "$new_features_file" \
            "$bug_fixes_file" "$other_changes_file" "$pr_titles_file" \
            "$commitlint_errors_file" "$prs_file"
        if [ -n "${origin_org:-}" ]; then
            git push -u origin "$BRANCH"
            gh pr create --fill --base "$mainbr" --head "$origin_org":"$BRANCH"
        fi
    fi
fi
