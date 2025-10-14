#!/bin/bash

# collect stats about PRs and issues in the given time frame
# by default, look for "external contributors" not role maintainers

set -euo pipefail

# "cache" of user lookups
# assumes that if someone is a collaborator on any system roles repo,
# that person is a collaborator on all system roles repos
# this is generally the case for PRs
declare -A USERS
# how many PRs were created for the given role
declare -A PRS_CREATED
# how many PRs were merged
declare -A PRS_MERGED
# how many PRs are open
declare -A PRS_OPEN
# how many PRs were created by non-maintainers
declare -A PRS_CREATED_NON_MAINT
# how many PRs were merged from non-maintainers
declare -A PRS_MERGED_NON_MAINT
# how many PRs are open from non-maintainers
declare -A PRS_OPEN_NON_MAINT
# how many issues were created for the given role
declare -A ISSUES_CREATED
# how many issues were closed
declare -A ISSUES_CLOSED
# how many issues were created by non-maintainers
declare -A ISSUES_CREATED_NON_MAINT
# how many issues were closed from non-maintainers
declare -A ISSUES_CLOSED_NON_MAINT

# silence shellcheck about unset vars
upstream_org="${upstream_org:?upstream_org is unset}"
repo="${repo:?repo is unset}"
if [ -z "${DATE_RANGE:-}" ]; then
    echo ERROR: Please specify DATE_RANGE like this
    echo DATE_RANGE=2024-01-01..2024-06-30
    exit 1
fi

# is the given user a role repo maintainer
user_is_maintainer() {
    local username
    username="$1"
    if [ -z "${USERS[$username]:-}" ]; then
        if gh api --silent \
          "/repos/$upstream_org/$repo/collaborators/$username" 2> /dev/null; then
            USERS["$username"]=0
        else
            USERS["$username"]=1
        fi
    fi
    return "${USERS[$username]}"
}

# get PRs
get_prs() {
    gh pr list -R "$upstream_org/$repo" \
      -S "created:$DATE_RANGE" \
      --state all \
      --json number,author,state,title \
      --jq '.[] | "\(.number) \(.author.login) \(.state) \(.title)"'
}

get_issues() {
    gh issue list -R "$upstream_org/$repo" \
      -S "created:$DATE_RANGE" \
      --state all \
      --json number,author,state \
      --jq '.[] | "\(.number) \(.author.login) \(.state)"'
}

get_prs > prs.txt
while read -r number author state title; do
    # exclude changelog and ci related prs
    if [[ "$title" =~ ^ci: ]]; then
        continue
    fi
    if [[ "$title" =~ ^docs\(changelog\) ]]; then
        continue
    fi
    PRS_CREATED["$repo"]=$(("${PRS_CREATED[$repo]:-0}" + 1))
    # see if author is a maintainer
    if ! user_is_maintainer "$author"; then
        PRS_CREATED_NON_MAINT["$repo"]=$(("${PRS_CREATED_NON_MAINT[$repo]:-0}" + 1))
    fi
    case "$state" in
    MERGED) PRS_MERGED["$repo"]=$(("${PRS_MERGED[$repo]:-0}" + 1))
            if ! user_is_maintainer "$author"; then
                PRS_MERGED_NON_MAINT["$repo"]=$(("${PRS_MERGED_NON_MAINT[$repo]:-0}" + 1))
            fi ;;
    CLOSED) echo closed without merging ;;
    OPEN) PRS_OPEN["$repo"]=$(("${PRS_OPEN[$repo]:-0}" + 1))
            if ! user_is_maintainer "$author"; then
                PRS_OPEN_NON_MAINT["$repo"]=$(("${PRS_OPEN_NON_MAINT[$repo]:-0}" + 1))
            fi ;;
    *) echo unknown state "$state" ;;
    esac
done < prs.txt
rm -f prs.txt

get_issues > issues.txt
# shellcheck disable=SC2034
while read -r number author state; do
    ISSUES_CREATED["$repo"]=$(("${ISSUES_CREATED[$repo]:-0}" + 1))
    # see if author is a maintainer
    if ! user_is_maintainer "$author"; then
        ISSUES_CREATED_NON_MAINT["$repo"]=$(("${ISSUES_CREATED_NON_MAINT[$repo]:-0}" + 1))
    fi
    if [ "$state" = CLOSED ]; then
        ISSUES_CLOSED["$repo"]=$(("${ISSUES_CLOSED[$repo]:-0}" + 1))
        if ! user_is_maintainer "$author"; then
            ISSUES_CLOSED_NON_MAINT["$repo"]=$(("${ISSUES_CLOSED_NON_MAINT[$repo]:-0}" + 1))
        fi
    fi
done < issues.txt
rm -f issues.txt

if [ -n "${PRS_CSVFILE:-}" ]; then
    if [ ! -s "${PRS_CSVFILE}" ]; then
        echo Role,PRs Created,PRs Merged,PRs open,Created non-maint,Merged non-maint,Open non-maint > "$PRS_CSVFILE"
    fi
    echo "$repo,${PRS_CREATED[$repo]:-0},${PRS_MERGED[$repo]:-0},${PRS_OPEN[$repo]:-0},${PRS_CREATED_NON_MAINT[$repo]:-0},${PRS_MERGED_NON_MAINT[$repo]:-0},${PRS_OPEN_NON_MAINT[$repo]:-0}" >> "$PRS_CSVFILE"
else
    echo In the range "$DATE_RANGE" in "$upstream_org/$repo":
    echo PRs created: "${PRS_CREATED[$repo]:-0}"
    echo PRs merged: "${PRS_MERGED[$repo]:-0}"
    echo PRs open: "${PRS_OPEN[$repo]:-0}"
    echo PRs created by non-maintainers: "${PRS_CREATED_NON_MAINT[$repo]:-0}"
    echo PRs merged from non-maintainers: "${PRS_MERGED_NON_MAINT[$repo]:-0}"
    echo PRs open from non-maintainers: "${PRS_OPEN_NON_MAINT[$repo]:-0}"
fi
if [ -n "${ISSUES_CSVFILE:-}" ]; then
    if [ ! -s "${ISSUES_CSVFILE}" ]; then
        echo Role,Issues Created,Issues Closed,Created non-maint,Closed non-maint > "$ISSUES_CSVFILE"
    fi
    echo "$repo,${ISSUES_CREATED[$repo]:-0},${ISSUES_CLOSED[$repo]:-0},${ISSUES_CREATED_NON_MAINT[$repo]:-0},${ISSUES_CLOSED_NON_MAINT[$repo]:-0}" >> "$ISSUES_CSVFILE"
else
    echo In the range "$DATE_RANGE" in "$upstream_org/$repo":
    echo Issues created: "${ISSUES_CREATED[$repo]:-0}"
    echo Issues closed: "${ISSUES_CLOSED[$repo]:-0}"
    echo Issues created by non-maintainers: "${ISSUES_CREATED_NON_MAINT[$repo]:-0}"
    echo Issues closed from non-maintainers: "${ISSUES_CLOSED_NON_MAINT[$repo]:-0}"
fi

cat <<EOF
curl -H 'accept: application/json' -H "Authorization: Token \$galaxy_token" -L \
 -s https://galaxy.ansible.com/api/v1/roles\?namespace=linux-system-roles\&page_size=50 \
 | jq -r '.results[] | select(.name | IN("template", "mssql") | not) | "\(.name),\(.download_count)"' \
 | sort -k1 -t, > galaxy.csv
get https://galaxy.ansible.com/ui/standalone/roles/willshersystems/sshd
EOF
