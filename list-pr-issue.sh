#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

if [ -n "${DEBUG:-}" ] ; then
    set -x
fi

if ! type -p hub > /dev/null 2>&1 ; then
    echo ERROR: you must use the \"hub\" command line tool
    echo for interacting with github
    echo see https://github.com/github/hub
    echo e.g. on Fedora - dnf -y install hub
    exit 1
fi

if ! type -p jq > /dev/null 2>&1 ; then
    echo ERROR: you must use the \"jq\" command line tool
    echo for parsing json output
    echo see https://stedolan.github.io/jq/
    echo e.g. on Fedora - dnf -y install jq
    exit 1
fi

# if you think you are getting errors for no reason, you
# may be hitting github rate limiting:
# https://developer.github.com/guides/best-practices-for-integrators/
# use `hub api /rate_limit | jq .` to see your
# current usage - https://developer.github.com/v3/rate_limit/

# in jq format - see https://stedolan.github.io/jq/manual/
PR_FORMAT=${PR_FORMAT:-'"\(.created_at|fromdateiso8601)" + " " + .user.login + " " + .created_at + " " + .html_url + " \(.title|gsub($eliputf; $elip))"'}
# see https://developer.github.com/v3/pulls/
PR_STATE=${PR_STATE:-open}
PR_SORT_FIELD=${PR_SORT_FIELD:-created}
PR_SORT_DIR=${PR_SORT_DIR:-desc}
# max number of PRs that can be returned at once
# if we need more than this, we'll have to implement
# support for pagination
# https://developer.github.com/v3/guides/traversing-with-pagination/
PR_PAGE_SIZE=${PR_PAGE_SIZE:-99}

ISSUE_FORMAT=${ISSUE_FORMAT:-"$PR_FORMAT"}
ISSUE_STATE=${ISSUE_STATE:-$PR_STATE}
ISSUE_SORT_FIELD=${ISSUE_SORT_FIELD:-$PR_SORT_FIELD}
ISSUE_SORT_DIR=${ISSUE_SORT_DIR:-$PR_SORT_DIR}
ISSUE_PAGE_SIZE=${ISSUE_PAGE_SIZE:-$PR_PAGE_SIZE}

prline() {
    # repo title created_at user url
    printf "%-20.20s %-80.80s %-20.20s %-10.10s %s\n" "$@"
}

header() {
    prline REPO TITLE DATE_CREATED USER URL
}

list_prs() {
    local org=$1
    local repo=$2
    hub api /repos/$org/$repo/pulls?state=$PR_STATE\&sort=$PR_SORT_FIELD\&direction=$PR_SORT_DIR\&per_page=$PR_PAGE_SIZE | \
        jq --arg repo "$repo" --arg eliputf '…' --arg elip '...' -r '.[] | $repo + " " + '"$PR_FORMAT"
}

list_issues() {
    local org=$1
    local repo=$2
    hub api /repos/$org/$repo/issues?state=$ISSUE_STATE\&sort=$ISSUE_SORT_FIELD\&direction=$ISSUE_SORT_DIR\&per_page=$ISSUE_PAGE_SIZE | \
        jq --arg repo "$repo" --arg eliputf '…' --arg elip '...' -r '.[] | select(has("pull_request")|not) | $repo + " " + '"$ISSUE_FORMAT"
}

LSR_ORG=${LSR_ORG:-linux-system-roles}

# get list of repos
REPOS=${REPOS:-$( hub api orgs/$LSR_ORG/repos | jq -r '.[].name' )}
LISTTYPE=${LISTTYPE:-both}

if [ "$LISTTYPE" = prs -o "$LISTTYPE" = both ] ; then
    echo PRS
    header
    for repo in $REPOS ; do
        list_prs $LSR_ORG $repo
    done | sort -n -k2 | \
        while read repo created_at_s user created_at url title ; do
            prline "$repo" "$title" "$created_at" "$user" "$url"
        done
fi

if [ "$LISTTYPE" = both ] ; then
    echo ""
fi

if [ "$LISTTYPE" = issues -o "$LISTTYPE" = both ] ; then
    echo ISSUES
    header
    for repo in $REPOS ; do
        list_issues $LSR_ORG $repo
    done | sort -n -k2 | \
        while read repo created_at_s user created_at url title ; do
            prline "$repo" "$title" "$created_at" "$user" "$url"
        done
fi
