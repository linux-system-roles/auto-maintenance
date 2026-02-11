#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

# By default, this script will skip doing a release of roles
# that do not appear to have any changes since the last release.
# If you really want to have a chance to view and perhaps release
# such roles, set AUTOSKIP=false
# also, if you want to prompt to release role, set AUTOSKIP=false.
# otherwise, the script will go directly to the role release
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

# By default the script only collection PR titles. Set this to true to collect
# PR descriptions too.
USE_PR_BODY="${USE_PR_BODY:-false}"

# By default, AUTOSKIP=true will also skip roles that have only ci
# changes.  If you want to release roles that have only ci changes,
# set AUTOSKIP_PR_TYPES=none
# If the role has only changes for PR types in this list, the role
# will be skipped.  Otherwise, a new role release will be proposed.
AUTOSKIP_PR_TYPES="${AUTOSKIP_PR_TYPES:-ci}"

repo_entries="$(gh repo view --json name,owner)"
repo=${repo:-$(echo "$repo_entries" | jq -r .name)}
owner=${owner:-$(echo "$repo_entries" | jq -r .owner.login)}

if [ -z "${origin_org:-}" ]; then
    origin_org="$owner"
fi
if [ -z "${upstream_org:-}" ]; then
    upstream_org="$owner"
fi

# These roles are usually not released
NO_RELEASE_ROLES="${NO_RELEASE_ROLES:-template}"

for no_release_role in $NO_RELEASE_ROLES; do
    if [ "$repo" = "$no_release_role" ]; then
        echo not releasing role "$repo" - skipping
        return 0
    fi
done

get_main_branch() {
    gh api "/repos/$owner/$repo" -q .default_branch
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

# get latest release
releases_latest=$(gh api repos/"$owner"/"$repo"/releases/latest -q '.tag_name,.published_at' 2> /dev/null || :)
skip=false
workdir="$(mktemp -d --suffix=_lsr)"
pushd "$workdir" > /dev/null 2>&1
# shellcheck disable=SC2064
trap "popd > /dev/null 2>&1; rm -rf $workdir" EXIT
pr_titles_file="$workdir/.pr_titles.txt"
prs_file="$workdir/.prs.json"
commitlint_errors_file="$workdir/.commitlint_errors.txt"
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

cl_query="query { \
  search(query: \"repo:$owner/$repo is:pr is:open docs(changelog) in:title\", type: ISSUE, first: 1) { \
    issueCount \
    edges { \
      node { \
        ... on PullRequest { \
          number \
          title \
        } \
      } \
    } \
  } \
}"
cl_result="$(gh api graphql -f query="$cl_query" -q .data.search --jq '.data.search.edges[].node | "#\(.number) \(.title)"')"

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
gh api graphql -f query="$prs_query" -q .data.search > "$prs_file"
count=$(jq '.issueCount' "$prs_file")
if [ -n "$cl_result" ]; then
    echo There is already a PR for version changelog:
    echo "$cl_result"
    echo skipping tag/release for role "$repo"
    echo ""
    skip=true
elif [ "${count:-0}" = 0 ]; then
    echo There are no merged PRs since latest tag "$latest_tag"
    if [ "$AUTOSKIP" = true ]; then
        echo Autoskip enabled - skipping tag/release for role "$repo"
        echo ""
        skip=true
    else
        echo ""
    fi
else
    echo Pull requests since latest tag "$latest_tag":
    echo ""
    : > "$pr_titles_file"
    pr_descriptions=()
    skip=true
    # loop through pr_list in reverse to populate changelog in chronological order
    for ((i="$count"-1; i>=0; i--)); do
        pr_entry="$(jq '.edges['$i'].node' "$prs_file")"
        pr_title="$(echo "$pr_entry" | jq -r '.title')"
        pr_num="$(echo "$pr_entry" | jq -r '.number')"
        pr_body="$(echo "$pr_entry" | jq -r '.body')"
        echo "$pr_title" >> "$pr_titles_file"
        # Only append PR body to PRs of type feat and fix
        if
        [ "${USE_PR_BODY}" = true ] &&
        [ -n "$pr_body" ] &&
        echo "$pr_title" | grep -e '^feat.*' -e '^fix.*'; then
            # Indent pr_body 2 spaces to act as a bullet content for pr_title
            pr_body_ind="$(echo "$pr_body" | awk '{ print "  " $0 }')"
            # Remove DOS carriage return ^M from PR body
            # shellcheck disable=SC2001
            # DOS carriage return ^M appears when PRs are edited using GH web UI
            pr_body_rm_rt="$(echo "$pr_body_ind" | sed "s/$(printf '\r')\$//")"
            # Remove 2 spaces on empty lines so that "cat --squeeze-blank" works
            # shellcheck disable=SC2116
            pr_body_rm_sp="$(echo "${pr_body_rm_rt//  /}")"
            printf -v pr_description -- "- %s (#%s)\n\n%s\n" "$pr_title" "$pr_num" "$pr_body_rm_sp"
        else
            printf -v pr_description -- "- %s (#%s)" "$pr_title" "$pr_num"
        fi
        pr_descriptions+=("$pr_description")
        for pr_type in $AUTOSKIP_PR_TYPES; do
            if [ "$pr_type" = none ]; then
                skip=false  # user does not want to skip
            elif [[ "$pr_title" =~ ^"$pr_type": ]]; then
                : # do nothing - do not touch skip value
            else
                skip=false  # cannot skip - this is a "real" change
            fi
        done
    done
    cat "$pr_titles_file"
    echo ""
    # see the changes?
    if [ "$AUTOSKIP" = false ]; then
        read -r -p 'Release this role? (y/n)? (default: y) ' release_role
        if [ "${release_role:-y}" = n ]; then
            skip=true
        fi
    elif [ "$skip" = true ]; then
        echo Autoskip enabled - the role has only PRs of type "$AUTOSKIP_PR_TYPES"
        echo If you want to this role, set AUTOSKIP_PR_TYPES=none and re-run this command
        echo ""
    fi
fi
if [ "$skip" = false ]; then
    if [ -s "$pr_titles_file" ] && [ "${ALLOW_BAD_PRS}" = false ] && [ "${count:-0}" != 0 ]; then
        # get commitlint rc file
        gh api /repos/"$owner"/"$repo"/contents/.commitlintrc.js -q .content | \
            base64 --decode > "$workdir/.commitlintrc.js"
        echo ""
        echo Verifying if all PR titles comply with the conventional commits format ...
        : > "$commitlint_errors_file"
        while read -r pr_title; do
            echo "$pr_title" | npx commitlint >> "$commitlint_errors_file" 2>&1 || :
        done < "$pr_titles_file"
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
    if grep -q '^.*!:.*' "$pr_titles_file"; then
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
    elif grep -q '^feat.*' "$pr_titles_file"; then
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
Here are your options:
* To continue with the suggested new tag $new_tag and edit CHANGELOG.md, enter 'y',
* To provide a different tag, and edit CHANGELOG.md enter the new tag in the following format:
   ${allow_v}X.Y.Z, where X, Y, and Z are integers,
* To skip this role and go to the next role just press Enter. " new_tag_in
        if [ -z "$new_tag_in" ]; then
            break
        elif [[ "$new_tag_in" =~ ^"$allow_v"[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
            new_tag=$new_tag_in
            break
        elif [ "$new_tag_in" == y ]; then
            break
        else
            echo ""
            echo ERROR: invalid input "$new_tag_in"
            echo You must either input y or provide a new tag.
            echo Tag must be in format "$allow_v"X.Y.Z
            echo ""
        fi
    done
    if [ -n "${new_tag_in}" ]; then
        mainbr=$(get_main_branch)
        rel_notes_file="$workdir/.release-notes-${new_tag}.md"
        new_features_file="$workdir/.new_features.md"
        bug_fixes_file="$workdir/.bug_fixes.md"
        other_changes_file="$workdir/.other_changes.md"
        tmp_changelog_file="$workdir/.tmp-changelog"
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
                    cat --squeeze-blank "$new_features_file"
                    echo ""
                } >> "$rel_notes_file"
            fi
            if [ -f "$bug_fixes_file" ]; then
                {   echo "### Bug Fixes"
                    echo ""
                    cat --squeeze-blank "$bug_fixes_file"
                    echo ""
                } >> "$rel_notes_file"
            fi
            if [ -f "$other_changes_file" ]; then
                {   echo "### Other Changes"
                    echo ""
                    cat --squeeze-blank "$other_changes_file"
                    echo ""
                } >> "$rel_notes_file"
            fi
        fi
        ${EDITOR:-vi} "$rel_notes_file"
        # this also will do a pushd to the checkedout repo dir
        # shellcheck disable=SC2154
        if [ "${CALLED_FROM_MANAGE_ROLE_REPOS:-false}" = true ]; then
            clone_repo . "$upstream_org" "$repo"
        else
            # assume we are in the repo dir
            popd > /dev/null 2>&1
        fi
        current_branch="$(git branch --show-current)"
        if [ "$current_branch" != "$mainbr" ] && [ "${CALLED_FROM_MANAGE_ROLE_REPOS:-false}" = true ]; then
            git checkout "$mainbr"
        elif [ -z "${BRANCH:-}" ] && [ "$current_branch" != "$mainbr" ]; then
            BRANCH="$current_branch"
        fi
        if [ -z "${BRANCH:-}" ]; then
            BRANCH="changelog-$(date -I)"
            if [ -n "$(git branch --list "$BRANCH")" ]; then
                BRANCH="changelog-$(date -Isec)"
            fi
        fi
        if [ -n "$(git branch --list "$BRANCH")" ] && [ "$current_branch" != "$BRANCH" ]; then
            git checkout "$BRANCH"
            git rebase "$mainbr"
        elif [ -z "$(git branch --list "$BRANCH")" ]; then
            git checkout -b "$BRANCH"
        fi
        myheader="Changelog
========="
        if [ -f CHANGELOG.md ]; then
            clheader=$(head -2 CHANGELOG.md)
        else
            clheader="$myheader"
        fi
        if [ "$myheader" = "$clheader" ]; then
            { echo "$clheader"; echo ""; } > "$tmp_changelog_file"
            cat "$rel_notes_file" >> "$tmp_changelog_file"
            if [ -f CHANGELOG.md ]; then
                tail -n +3 CHANGELOG.md >> "$tmp_changelog_file"
            fi
        else
            echo WARNING: Changelog header "$clheader"
            echo not in expected format "$myheader"
            cat "$rel_notes_file" CHANGELOG.md > "$tmp_changelog_file"
        fi
        # Squeeze possible blank lines
        cat --squeeze-blank "$tmp_changelog_file" > CHANGELOG.md
        gh api /repos/"$owner"/"$repo"/contents/latest/README.html?ref=docs -q .content | base64 --decode > .README.html
        git add CHANGELOG.md .README.html
        { echo "docs(changelog): version $new_tag [citest_skip]"; echo "";
          echo "Update changelog and .README.html for version $new_tag"; } > .gitcommitmsg
        git commit -s -F .gitcommitmsg
        rm -f .gitcommitmsg "$rel_notes_file" "$new_features_file" \
            "$bug_fixes_file" "$other_changes_file" "$pr_titles_file" \
            "$commitlint_errors_file" "$prs_file" "$tmp_changelog_file"
        if [ -n "${origin_org:-}" ]; then
            git push -u origin "$BRANCH"
            gh pr create --fill --base "$mainbr" --head "$origin_org":"$BRANCH"
        fi
        if [ "${CALLED_FROM_MANAGE_ROLE_REPOS:-false}" = true ]; then
            popd > /dev/null 2>&1  # clone_repo does a pushd to repo dir
        fi
    fi
    echo ""
    echo ""
fi

trap - EXIT
popd > /dev/null 2>&1
if [[ "$workdir" =~ ^/tmp ]]; then
    rm -rf "$workdir"
fi
