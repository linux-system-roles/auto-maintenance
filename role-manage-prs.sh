#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2023, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

repo=${repo:-$(git remote get-url origin | awk -F'/' '{print $NF}')}

AUTHOR="${AUTHOR:-"@me"}"
APP="${APP:-""}"
declare -a searchargs=("--search" "draft:false")
if [ -n "$APP" ]; then
    searchargs=("--app" "$APP")
elif [ "$AUTHOR" != "@all" ]; then
    searchargs=("--author" "$AUTHOR")
fi

declare -a mergeargs=()
DELETE_BRANCH="${DELETE_BRANCH:-true}"
if [ "$DELETE_BRANCH" = true ]; then
    mergeargs+=("-d")
fi
# gh pr merge arguments:
#  -m, --merge                   Merge the commits with the base branch
#  -r, --rebase                  Rebase the commits onto the base branch
#  -s, --squash                  Squash the commits into one commit and merge it into the base branch
# ask - prompt user for merge type
MERGE_TYPE="${MERGE_TYPE:-r}"
if [ "$MERGE_TYPE" != ask ]; then
    mergeargs+=("-$MERGE_TYPE")
fi

# Typically used in conjunction with manage-role-repos.sh
# This script is called from every role - it uses `gh` to display
# a list of open PRs, then prompts to merge one using `gh`, then
# repeats until the user moves to the next role

list_prs() {
    # set in manage-role-repos.sh
    # shellcheck disable=SC2154
    gh pr list -R "$upstream_org/$repo" "${searchargs[@]}" "$@"
}

get_checks() {
    local pr total success failure pending cancelled error conclusion state name status display_name
    pr="$1"
    gh pr view "$pr" -R "$upstream_org/$repo" --json statusCheckRollup \
      --template '{{range .statusCheckRollup}}{{print (or .conclusion "<nil>")}}#{{print (or .state "<nil>")}}#{{print .name}}#{{println .context}}{{end}}' | \
    while IFS="#" read -r conclusion state name context; do
        if [ "$conclusion" = '<nil>' ] && [ "$state" = '<nil>' ]; then
            status=PENDING
        elif [ "$conclusion" = '<nil>' ] && [ "$state" = PENDING ]; then
            status=PENDING
        elif [ "$conclusion" = FAILURE ] || [ "$state" = FAILURE ]; then
            status=FAILURE
        elif [ "$conclusion" = SUCCESS ] || [ "$state" = SUCCESS ]; then
            status=SUCCESS
        elif [ "$conclusion" = CANCELLED ] || [ "$state" = CANCELLED ]; then
            status=CANCELLED
        elif [ "$conclusion" = ERROR ] || [ "$state" = ERROR ]; then
            status=ERROR
        elif [ "$conclusion" = NEUTRAL ]; then  # usually a python check if python code did not change
            status=SUCCESS
        elif [ "$conclusion" = ACTION_REQUIRED ]; then  # DCO check failed
            status=FAILURE
        elif [ "$conclusion" = SKIPPED ]; then  # e.g. [citest_skip]
            status=SKIPPED
        else
            echo ERROR: check "$name" has unknown conclusion "$conclusion" state "$state" 1>&2
            exit 1
        fi
        if [ "$name" != '<nil>' ]; then
            display_name="$name"
        elif [ "$context" != '<nil>' ]; then
            display_name="$context"
        fi
        echo "${display_name}#${status}"
    done
}

get_check_detail() {
    local pr name status
    pr="$1"; shift
    get_checks "$pr" | while IFS="#" read -r name status; do
        # shellcheck disable=SC1009
        # shellcheck disable=SC1072
        # shellcheck disable=SC1073
        if [ "$status" "$@" ]; then
            echo name "$name" status "$status"
        fi
    done
}

get_check_summary() {
    local pr
    pr="$1"
    get_checks "$pr" | {
    local -A counts
    local total status name
    while IFS="#" read -r name status; do
        counts[$status]=$(("${counts[$status]:-0}" + 1))
        total=$(("${total:-0}" + 1))
    done
    echo "${total:-0} ${counts[SUCCESS]:-0} ${counts[FAILURE]:-0} ${counts[PENDING]:-0} ${counts[CANCELLED]:-0} ${counts[ERROR]:-0} ${counts[SKIPPED]:-0}"
    }
}

# if all reviews are approved, then return APPROVED
# if there any CHANGES_REQUESTED return CHANGES_REQUESTED
# otherwise if there are any comments return COMMENTED
# otherwise, return NO_REVIEWS
get_reviews() {
    local pr review rev found_cr found_c found_ap
    pr="$1"
    for rev in $(gh pr view "$pr" -R "$upstream_org/$repo" --json reviews \
        --template '{{range .reviews}}{{println .state}}{{end}}'); do
        if [ "$rev" == CHANGES_REQUESTED ]; then
            found_cr=true
            break
        elif [ "$rev" == COMMENTED ]; then
            found_c=true
        elif [ "$rev" == APPROVED ]; then
            found_ap=true
        fi
    done
    if [ "${found_cr:-false}" = true ]; then
        echo CHANGES_REQUESTED
    elif [ "${found_c:-false}" = true ]; then
        echo COMMENTED
    elif [ "${found_ap:-false}" = true ]; then
        echo APPROVED
    else
        echo NO_REVIEWS
    fi
}

show_pr() {
    local pr total success failure pending state review
    pr="$1"
    read -r total success failure pending cancelled error skipped <<< "$(get_check_summary "$pr")"
    if [ "$total" -eq 0 ]; then
        state=UNKNOWN
    elif [ "$total" = "$success" ]; then
        state=SUCCESS
    elif [ "$failure" -gt 0 ]; then
        state=FAILED
    elif [ "$pending" -gt 0 ]; then
        state=PENDING
    elif [ "$cancelled" -gt 0 ]; then
        state=CANCELLED
    elif [ "$error" -gt 0 ]; then
        state=ERROR
    elif [ "$skipped" -gt 0 ]; then
        state=SKIPPED
    else
        state=UNKNOWN
    fi
    review="$(get_reviews "$pr")"
    gh pr view "$pr" -R "$upstream_org/$repo" --json number,title,updatedAt \
      --template '#{{tablerow .number .updatedAt "'"$state"'" "'"$review"'" .title}}'
    echo "checks: total $total successful $success failed $failure pending $pending cancelled $cancelled error $error skipped $skipped"
}

merge_pr() {
    local pr
    pr="$1"; shift
    gh pr merge "$pr" -R "$upstream_org/$repo" "${mergeargs[@]}" "$@"
}

approve_pr() {
    local pr
    pr="$1"
    gh pr review --approve "$pr" -R "$upstream_org/$repo"
}

get_pr_list() {
    local pr prs
    unset PR_LIST
    prs="$(list_prs --json number -q .[].number)"
    # shellcheck disable=SC2086
    if [ -z "$prs" ]; then
        return 1
    fi
    for pr in $prs; do
        PR_LIST["$pr"]=$(show_pr "$pr")
    done
    return 0
}

show_pr_list() {
    local data
    for data in "${PR_LIST[@]}"; do
        echo "$data"
    done
}

if [ "${PR_LIST_DECLARED:-false}" = false ]; then
    declare -A PR_LIST
    PR_LIST_DECLARED=true
fi

done=false
if ! get_pr_list; then
    echo INFO: role "$repo" has no PRs matching search/author criteria - skipping
    done=true
fi
while [ "$done" = false ]; do
    echo ""
    show_pr_list
    cat <<EOF
Actions:
"NUM" - merge PR                 | "w" - list PRs in browser
"l" - refresh the list           | "v NUM" - view PR in browser
"a NUM" - merge with admin priv. | "ci NUM" - add "[citest]" comment to PR
"t NUM" - view test/check detail | "s NUM /path/to/script" - run script
"c NUM [comment]" - close PR with optional comment
"d NUM [diff args]" - gh pr diff NUM [args]
"e NUM [edit args]" - gh pr edit NUM [args]
"p NUM" - approve PR - cannot approve your own PRs
"pm NUM" - approve and merge PR - cannot approve your own PRs
Press Enter to skip to next role
EOF
    read -r -p "Action? " input
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        if merge_pr "$input"; then
            unset PR_LIST["$input"]
        fi
    elif [ "$input" = w ]; then
        list_prs -w
    elif [ "$input" = l ]; then
        if get_pr_list; then
            done=false
        else
            done=true
            echo INFO: role "$repo" has no more PRs matching search/author criteria - skipping
        fi
    elif [[ "$input" =~ ^v\ ([0-9]+)$ ]]; then
        gh pr view "${BASH_REMATCH[1]}" --web -R "$upstream_org/$repo"
    elif [[ "$input" =~ ^a\ ([0-9]+)$ ]]; then
        if merge_pr "${BASH_REMATCH[1]}" --admin; then
            unset PR_LIST["${BASH_REMATCH[1]}"]
        fi
    elif [[ "$input" =~ ^ci\ ([0-9]+)$ ]]; then
        gh pr comment "${BASH_REMATCH[1]}" --body "[citest]" -R "$upstream_org/$repo"
    elif [[ "$input" =~ ^t\ ([0-9]+)$ ]]; then
        get_check_detail "${BASH_REMATCH[1]}" "!=" SUCCESS
    elif [[ "$input" =~ ^s\ ([0-9]+)\ (.+)$ ]]; then
        "${BASH_REMATCH[2]}" "$repo" "${BASH_REMATCH[1]}"
    elif [[ "$input" =~ ^c\ ([0-9]+)(\ (.+))?$ ]]; then
        args=("${BASH_REMATCH[1]}" -R "$upstream_org/$repo" -d)
        if [ -n "${BASH_REMATCH[2]}" ]; then
            args+=(-c "${BASH_REMATCH[2]}")
        fi
        if gh pr close "${args[@]}"; then
            unset PR_LIST["${BASH_REMATCH[1]}"]
        fi
    elif [[ "$input" =~ ^d\ ([0-9]+)(\ (.+))?$ ]]; then
        args=("${BASH_REMATCH[1]}" -R "$upstream_org/$repo")
        if [ -n "${BASH_REMATCH[2]}" ]; then
            args+=("${BASH_REMATCH[2]}")
        fi
        gh pr diff "${args[@]}"
    elif [[ "$input" =~ ^e\ ([0-9]+)(\ (.+))?$ ]]; then
        args=(gh pr edit "${BASH_REMATCH[1]}" -R "$upstream_org/$repo")
        if [ -n "${BASH_REMATCH[3]:-}" ]; then
            "${args[@]}" ${BASH_REMATCH[3]}
        else
            "${args[@]}"
        fi
    elif [[ "$input" =~ ^p\ ([0-9]+)$ ]]; then
        approve_pr "${BASH_REMATCH[1]}"
    elif [[ "$input" =~ ^pm\ ([0-9]+)$ ]]; then
        approve_pr "${BASH_REMATCH[1]}"
        sleep 1  # wait for approval to be applied
        if merge_pr "${BASH_REMATCH[1]}" --admin; then
            unset PR_LIST["${BASH_REMATCH[1]}"]
        fi
    elif [ -z "$input" ]; then
        done=true
    else
        echo ERROR: invalid input ["$input"]
    fi
    if [ "$done" = false ] && [ "${#PR_LIST[*]}" = 0 ]; then
        done=true
        echo INFO: role "$repo" has no more PRs matching search/author criteria - skipping
    fi
done

# PR fields
# Specify one or more comma-separated fields for `--json`:
#   additions
#   assignees
#   author
#   autoMergeRequest
#   baseRefName
#   body
#   changedFiles
#   closed
#   closedAt
#   comments
#   commits
#   createdAt
#   deletions
#   files
#   headRefName
#   headRefOid
#   headRepository
#   headRepositoryOwner
#   id
#   isCrossRepository
#   isDraft
#   labels
#   latestReviews
#   maintainerCanModify
#   mergeCommit
#   mergeStateStatus
#   mergeable
#   mergedAt
#   mergedBy
#   milestone
#   number
#   potentialMergeCommit
#   projectCards
#   projectItems
#   reactionGroups
#   reviewDecision
#   reviewRequests
#   reviews
#   state
#   statusCheckRollup
#   title
#   updatedAt
#   url
