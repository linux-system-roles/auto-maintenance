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

if ! type -p python3 > /dev/null 2>&1; then
    echo python3 command not found
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PR_TITLE_LINT="${PR_TITLE_LINT:-$SCRIPT_DIR/pr_title_lint.py}"
if [ ! -f "$PR_TITLE_LINT" ]; then
    echo ERROR: pr_title_lint.py not found at "$PR_TITLE_LINT"
    exit 1
fi

# get latest release
releases_latest=$(gh api repos/"$owner"/"$repo"/releases/latest -q '.tag_name,.published_at' 2> /dev/null || :)
skip=false
workdir="$(mktemp -d --suffix=_lsr)"
pushd "$workdir" > /dev/null 2>&1
# shellcheck disable=SC2064
trap "popd > /dev/null 2>&1; rm -rf $workdir" EXIT
pr_titles_file="$workdir/.pr_titles.txt"
prs_file="$workdir/.prs.json"
pr_title_lint_errors_file="$workdir/.pr_title_lint_errors.txt"
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
          url
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
    echo Found "$count" merged PRs since latest tag "$latest_tag"
    echo ""
    : > "$pr_titles_file"
    pr_descriptions=()
    skip=true
    # loop through pr_list in reverse to populate changelog in chronological order
    for ((i="$count"-1; i>=0; i--)); do
        pr_entry="$(jq '.edges['$i'].node' "$prs_file")"
        pr_title="$(echo "$pr_entry" | jq -r '.title')"
        pr_num="$(echo "$pr_entry" | jq -r '.number')"
        pr_url="$(echo "$pr_entry" | jq -r '.url')"
        pr_body="$(echo "$pr_entry" | jq -r '.body')"
        printf '%s\t%s\n' "$pr_url" "$pr_title" >> "$pr_titles_file"
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
    if [ "$AUTOSKIP" = false ]; then
        skip=false
    elif [ "$skip" = true ]; then
        echo Autoskip enabled - the role has only PRs of type "$AUTOSKIP_PR_TYPES"
        echo If you want to this role, set AUTOSKIP_PR_TYPES=none and re-run this command
        echo ""
    fi
fi
if [ "$skip" = false ]; then
    if [ -s "$pr_titles_file" ] && [ "${ALLOW_BAD_PRS}" = false ] && [ "${count:-0}" != 0 ]; then
        echo ""
        echo Verifying if all PR titles comply with the conventional commits format ...
        if ! python3 "$PR_TITLE_LINT" -f "$pr_titles_file" > "$pr_title_lint_errors_file" || [ -s "$pr_title_lint_errors_file" ]; then
            echo "ERROR: the following PR titles failed the pr_title_lint check."
            echo "Follow the URL links to fix the PR titles then re-run this command."
            echo ""
            cat "$pr_title_lint_errors_file"
            exit 1
        fi
        echo Success
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
    if cut -f2- "$pr_titles_file" | grep -q '^.*!:.*'; then
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
    elif cut -f2- "$pr_titles_file" | grep -q '^feat.*'; then
        ver_minor=$((ver_minor+=1))
        ver_patch=0
    else
        ver_patch=$((ver_patch+=1))
    fi
    new_tag="${allow_v}$ver_major.$ver_minor.$ver_patch"
    changelog_entry_file="$workdir/.changelog-entry.md"
    new_features_file="$workdir/.new_features.md"
    bug_fixes_file="$workdir/.bug_fixes.md"
    other_changes_file="$workdir/.other_changes.md"
    preview_changelog_file="$workdir/.preview-changelog.md"

    generate_changelog_entry() {
        local tag="$1"
        local output_file="$2"
        rm -f "$new_features_file" "$bug_fixes_file" "$other_changes_file"
        for pr_description in "${pr_descriptions[@]}"; do
            if echo "$pr_description" | sed -n 1p | grep -q '^- feat.*'; then
                echo "$pr_description" >> "$new_features_file"
            elif echo "$pr_description" | sed -n 1p | grep -q '^- fix.*'; then
                echo "$pr_description" >> "$bug_fixes_file"
            else
                echo "$pr_description" >> "$other_changes_file"
            fi
        done
        {   echo "[$tag] - $( date +%Y-%m-%d )"
            echo "--------------------"
            echo ""
        } > "$output_file"
        if [ -f "$new_features_file" ]; then
            {   echo "### New Features"
                echo ""
                cat --squeeze-blank "$new_features_file"
                echo ""
            } >> "$output_file"
        fi
        if [ -f "$bug_fixes_file" ]; then
            {   echo "### Bug Fixes"
                echo ""
                cat --squeeze-blank "$bug_fixes_file"
                echo ""
            } >> "$output_file"
        fi
        if [ -f "$other_changes_file" ]; then
            {   echo "### Other Changes"
                echo ""
                cat --squeeze-blank "$other_changes_file"
                echo ""
            } >> "$output_file"
        fi
    }

    build_full_changelog() {
        local changelog_source="$1"
        local output_file="$2"
        local myheader="Changelog
========="
        if [ -f "$changelog_source" ]; then
            clheader=$(head -2 "$changelog_source")
        else
            clheader="$myheader"
        fi
        if [ "$myheader" = "$clheader" ]; then
            { echo "$clheader"; echo ""; } > "$output_file"
            cat "$changelog_entry_file" >> "$output_file"
            if [ -f "$changelog_source" ]; then
                tail -n +3 "$changelog_source" >> "$output_file"
            fi
        else
            echo WARNING: Changelog header "$clheader" >&2
            echo not in expected format "$myheader" >&2
            if [ -f "$changelog_source" ]; then
                cat "$changelog_entry_file" "$changelog_source" > "$output_file"
            else
                cat "$changelog_entry_file" > "$output_file"
            fi
        fi
    }

    existing_changelog_file="$workdir/.existing-changelog.md"
    mainbr=$(get_main_branch)
    if ! gh api "/repos/$owner/$repo/contents/CHANGELOG.md?ref=$mainbr" -q .content 2> /dev/null | base64 --decode > "$existing_changelog_file"; then
        rm -f "$existing_changelog_file"
    fi

    accept_changelog_entry=false
    do_generate_changelog_entry=true
    while true; do
        if [ "$do_generate_changelog_entry" = true ]; then
            echo ""
            echo "New changelog entry:"
            echo ""
            generate_changelog_entry "$new_tag" "$changelog_entry_file"
            do_generate_changelog_entry=false
        fi
        cat --squeeze-blank "$changelog_entry_file"
        echo ""
        echo "Previous version: $latest_tag        New version: $new_tag"
        echo "Options:"
        echo "* y - accept changelog entry and create PR"
        echo "* n or Enter - skip"
        echo "* e - edit changelog"
        echo "* ${allow_v}X.Y.Z - new version"
        echo "* p - show PR titles"
        read -r -p "Enter your choice: " user_in
        if [ -z "$user_in" ] || [ "$user_in" = n ]; then
            break
        elif [ "$user_in" = y ]; then
            accept_changelog_entry=true
            break
        elif [ "$user_in" = e ]; then
            ${EDITOR:-vi} "$changelog_entry_file"
            do_generate_changelog_entry=false
            # grab the new_tag from the changelog_entry_file in case user edited it
            new_tag="$(sed -n '/^\[\([0-9][0-9]*[.][0-9][0-9]*[.][0-9][0-9]*\)\]/{s/^\[\([0-9][0-9]*[.][0-9][0-9]*[.][0-9][0-9]*\)\].*$/\1/;p}' "$changelog_entry_file")"
        elif [ "$user_in" = p ]; then
            echo ""
            echo Pull request titles since latest tag "$latest_tag":
            echo ""
            cat "$pr_titles_file"
            echo ""
            do_generate_changelog_entry=false
        elif [[ "$user_in" =~ ^"$allow_v"[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
            new_tag="$user_in"
            do_generate_changelog_entry=true
        else
            echo ""
            echo ERROR: invalid input "$user_in"
            echo Enter y, n, e, p, ${allow_v}X.Y.Z, or press Enter to skip.
            echo ""
            do_generate_changelog_entry=false
        fi
    done
    if [ "$accept_changelog_entry" = true ]; then
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
        build_full_changelog CHANGELOG.md "$preview_changelog_file"
        cat --squeeze-blank "$preview_changelog_file" > CHANGELOG.md
        gh api /repos/"$owner"/"$repo"/contents/latest/README.html?ref=docs -q .content | base64 --decode > .README.html
        git add CHANGELOG.md .README.html
        { echo "docs(changelog): version $new_tag [citest_skip]"; echo "";
          echo "Update changelog and .README.html for version $new_tag"; } > .gitcommitmsg
        git commit -s -F .gitcommitmsg
        rm -f .gitcommitmsg "$changelog_entry_file" "$new_features_file" \
            "$bug_fixes_file" "$other_changes_file" "$pr_titles_file" \
            "$pr_title_lint_errors_file" "$prs_file" \
            "$preview_changelog_file" "$existing_changelog_file"
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
if [[ "$workdir" =~ ^/tmp/ ]]; then
    rm -rf "$workdir"
fi
