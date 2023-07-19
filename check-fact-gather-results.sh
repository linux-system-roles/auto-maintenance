#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2023, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

# these are role which has a tests_default.yml which gathers facts
declare -A ROLE_DEFAULT_GATHERS_FACTS=( [ssh]=ssh [journald]=journald [ha_cluster]=ha_cluster )

check_log_for_fact_gather_result() {
    local role log_link
    role="$1"
    log_link="$2"
    if [[ "$log_link" =~ tests_default_wrapper ]]; then
        return 0  # too difficult
    elif [ "$role" = selinux ]; then
        # this role does some weird stuff with unsetting facts
        if [[ "$log_link" =~ tests_all_purge ]] || [[ "$log_link" =~ tests_boolean ]] || \
            [[ "$log_link" =~ tests_fcontext ]] || [[ "$log_link" =~ tests_login ]] || \
            [[ "$log_link" =~ tests_port ]] || [[ "$log_link" =~ tests_selinux_modules ]]; then
            return 0
        fi
    fi
    if [[ "$log_link" =~ [.]log$ ]]; then
        :  # is a log
    else
        return 0
    fi
    if [ "${ANSIBLE_GATHERING:-}" = explicit ]; then
        default_match="ok:"
    else
        default_match="skipping:"
    fi
    echo "###" test "$(basename "$log_link")"
    if [[ "$log_link" =~ tests_default_.*_generated ]]; then
        match="$default_match"
    elif [[ "$log_link" =~ tests_defaults_vars ]]; then
        match="$default_match"
    elif [[ "$log_link" =~ tests_default_vars ]]; then
        match="$default_match"
    elif [[ "$log_link" =~ tests_default_initscripts ]]; then
        match="$default_match"
    elif [[ "$log_link" =~ tests_default_nm ]]; then
        match="$default_match"
    elif [[ "$log_link" =~ tests_default_reboot ]]; then
        match="$default_match"
    elif [[ "$log_link" =~ tests_default ]]; then
        if [ -n "${ROLE_DEFAULT_GATHERS_FACTS[$role]:-}" ]; then
            match="$default_match"
        else
            match="ok:"
        fi
    elif [ "$role" = rhc ]; then  # runs some tests with gather_facts: false
        if [[ "$log_link" =~ tests_register_unregister ]]; then
            match="ok:"
        elif [[ "$log_link" =~ tests_repositories ]]; then
            match="ok:"
        else
            match="$default_match"
        fi
    elif [ "$role" = postgresql ]; then
        # requires an unusual fact - will almost always have to gather
        match="ok:"
    elif [ "$role" = ad_integration ]; then  # runs a test with gather_facts: false
        if [[ "$log_link" =~ tests_basic_join ]]; then
            match="ok:"
        else
            match="$default_match"
        fi
    elif [ "$role" = kdump ]; then
        if [ "${ANSIBLE_GATHERING:-no}" = explicit ] && [[ "$log_link" =~ tests_ssh.yml ]]; then
            match="skipping:"
        else
            match="$default_match"
        fi
    else
        match="$default_match"
    fi
    if [ "$role" = network ]; then
        task_match="TASK .*network : Ensure ansible_facts used by role are present"
    else
        task_match="TASK .*$role : Ensure ansible_facts used by role"
    fi
    curl -s -L "$log_link" | \
    while read -r line; do
        # use role to avoid issues with nested roles
        if [ "${in_task:-false}" = true ]; then
            if [[ "$line" =~ ^included: ]]; then
                # this is not the right task
                in_task=false
                task_lines=()
                continue
            elif [ -z "$line" ]; then
                echo ERROR - match not found in task
                printf '%s\n' "${task_lines[@]}"
                return 1
            elif [[ "$line" =~ ^${match} ]]; then
                # success
                in_task=false
                task_lines=()
                # if we already gathered facts in this test, we don't
                # need to gather again, so subsequent tasks should
                # report skipping
                match="skipping:"
                continue
            fi
            task_lines+=("$line")
        elif [[ "$line" =~ ^${task_match} ]]; then
            in_task=true
            task_lines=("$line")
        elif [[ "$line" =~ ^TASK\ \[Gathering\ Facts\] ]]; then
            if [ "$role" != postgresql ]; then
                match="skipping:"
            fi
        elif [[ "$line" =~ ^TASK\ \[.*Gather\ the\ minimum\ subset\ of\ ansible_facts ]]; then
            match="skipping:"
        elif [[ "$line" =~ ^TASK\ \[.*Ensure\ facts\ used\ by\ test ]]; then
            match="skipping:"
        elif [[ "$line" =~ ^TASK\ \[.*Ensure\ Ansible\ facts\ required\ by\ tests ]]; then
            match="skipping:"
        fi
    done
}

get_logs_from_pr() {
    local role pr
    role="$1"
    pr="$2"
    gh pr view "$pr" -R "linux-system-roles/$role" --json statusCheckRollup \
    --template '{{range .statusCheckRollup}}{{print .context}}#{{println .targetUrl}}{{end}}' | \
    while IFS="#" read -r context summary_url; do
        if [ "$context" = '<nil>' ] || [ "$summary_url" = '<nil>' ] || [ -z "$summary_url" ]; then
            continue
        elif [ "$context" = "codecov/project" ]; then
            continue
        fi
        echo "##" context "$context"
        curl -s "$summary_url" | xmllint --html --xpath '//@href' - 2> /dev/null | \
        cut -d '"' -f 2 | \
        while read -r log_link; do
            check_log_for_fact_gather_result "$role" "$log_link"
        done
    done
}

get_logs_from_bkr_xml() {
    local xml_url log_link
    xml_url="$1"  # this is the Beaker results XML URL
    curl -s "$xml_url" | xmllint --xpath '//@href' - | cut -d '"' -f 2 | \
    while read -r log_link; do
        if [[ "$log_link" =~ SYSTEM-ROLE-([a-z_]+)_tests_ ]]; then
            check_log_for_fact_gather_result "${BASH_REMATCH[1]}" "$log_link"
        fi
    done
}

if [[ "$1" =~ ^http ]]; then
    # assume a link
    get_logs_from_bkr_xml "$1"
elif [ -n "${2:-}" ]; then
    get_logs_from_pr "$1" "$2"
fi
