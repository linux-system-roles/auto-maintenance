#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2023, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

repo=${repo:-$(git remote get-url origin | awk -F'/' '{print $NF}')}

ALERTS=()

get_alerts() {
    IFS=$'\n' ALERTS=($(gh api -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "/repos/$origin_org/$repo/dependabot/alerts?state=open&direction=asc" \
        --template \
        '{{tablerow "NUM" "PACKAGE" "FILE" "SUMMARY"}}{{range .}}{{tablerow .number .dependency.package.name .dependency.manifest_path .security_advisory.summary}}{{end}}'))
    unset IFS
}

dismiss_alert() {
    local num reason comment
    num="$1"; shift
    reason="$1"; shift
    comment="$*"
    gh api --method PATCH -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "/repos/$origin_org/$repo/dependabot/alerts/$num" \
        -f "state=dismissed" -f "dismissed_reason=$reason" \
        -f "dismissed_comment=$comment"
}

dismiss_all_alerts() {
    local alert num reason comment rest
    reason="$1"; shift
    comment="$*"
    for alert in "${ALERTS[@]}"; do
        read -r num rest <<< "$alert"
        if [ "$num" != NUM ]; then
            dismiss_alert "$num" "$reason" "$comment"
        fi
    done
}

done=false

get_alerts

if [ -z "${ALERTS[1]:-}" ]; then
    echo INFO: role "$repo" has no alerts - skipping
    done=true
fi

while [ "$done" = false ]; do
    if [ -z "${ALERTS[1]:-}" ]; then
        get_alerts
    fi
    if [ -z "${ALERTS[1]:-}" ]; then
        echo INFO: role "$repo" has no more alerts - skipping
        done=true
    else
        for alert in "${ALERTS[@]}"; do
            echo "$alert"
        done
        echo ""
        cat <<EOF
Actions:
"d NUM reason comment" - dismiss the alert
reason is one of fix_started, inaccurate, no_bandwidth, not_used, tolerable_risk
comment is a comment to add to the dismissal
"a reason comment" - dismiss all alerts with the given reason and comment
"v NUM" - view the alert in the browser
Press Enter to skip to next role
EOF
        read -r -p "Action? " input
        if [ "$input" = l ]; then
            done=false
        elif [[ "$input" =~ ^v\ ([0-9]+)$ ]]; then
            xdg-open "https://github.com/$origin_org/$repo/security/dependabot/${BASH_REMATCH[1]}"
            ALERTS=()  # reset for next loop iter
        elif [[ "$input" =~ ^d\ ([0-9]+)\ ([a-z_]+)\ (.+)$ ]]; then
            dismiss_alert "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}"
            ALERTS=()  # reset for next loop iter
        elif [[ "$input" =~ ^a\ ([a-z_]+)\ (.+)$ ]]; then
            dismiss_all_alerts "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
            ALERTS=()  # reset for next loop iter
        elif [ -z "$input" ]; then
            done=true
        else
            echo ERROR: invalid input ["$input"]
        fi
    fi
done
