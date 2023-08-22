#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2023, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

# these are roles which have a tests_default.yml which gathers facts
declare -A ROLE_DEFAULT_GATHERS_FACTS=( [ssh]=ssh [journald]=journald [ha_cluster]=ha_cluster )

declare -A LOG_LEVELS=( [DEBUG]=0 [INFO]=1 [NOTICE]=2 [WARNING]=3 [ERROR]=4 [CRITICAL]=5 [FATAL]=6 )
LOG_LEVEL="${LOG_LEVEL:-NOTICE}"

logmsg() {
    if [ "${LOG_LEVELS[$1]}" -ge "${LOG_LEVELS[$LOG_LEVEL]}" ]; then
        echo "$1": "$@"
    fi
}

debug() {
    logmsg DEBUG "$@"
}

info() {
    logmsg INFO "$@"
}

notice() {
    logmsg NOTICE "$@"
}

warning() {
    logmsg WARNING "$@"
}

error() {
    logmsg ERROR "$@"
}

critical() {
    logmsg CRITICAL "$@"
}

fatal() {
    logmsg FATAL "$@"
    exit 1
}

get_log() {
    local file_name
    if [ -f "$1" ]; then
        cat "$1"
    else
        if [ -n "${log_dir:-}" ]; then
            if [ ! -d "$log_dir" ]; then
                mkdir -p "$log_dir"
            fi
            file_name="$log_dir/$(basename "$1")"
            if [ ! -f "$file_name" ]; then
                curl -L -s -o "$file_name" "$1"
            fi
            cat "$file_name"
        else
            curl -L -s "$1"
        fi
    fi
}

check_log_for_fact_gather_result() {
    local role log_link default_match match task_match
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
    info "###" test "$(basename "$log_link")"
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
    get_log "$log_link" | \
    { local line in_task task_lines
    in_task=false
    while read -r line; do
        # use role to avoid issues with nested roles
        if [ "${in_task:-false}" = true ]; then
            if [[ "$line" =~ ^included: ]]; then
                # this is not the right task
                in_task=false
                task_lines=()
                continue
            elif [ -z "$line" ]; then
                error match not found in task
                printf '%s\n' "${task_lines[@]}"
                in_task=false
                task_lines=()
                match="skipping:"
                continue
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
        elif [[ "$line" =~ ^TASK\ \[.*Get\ facts\ for\ external\ test\ data ]]; then
            match="skipping:"
        fi
    done
    }
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
        info "##" context "$context"
        curl -s "$summary_url" | xmllint --html --xpath '//@href' - 2> /dev/null | \
        cut -d '"' -f 2 | \
        while read -r log_link; do
            check_log_for_fact_gather_result "$role" "$log_link"
        done
    done
}

get_bkr_xml() {
    if [ -f "$1" ]; then
        cat "$1"
    else
        curl -L -s "$1"
    fi
}

get_logs_from_bkr_xml() {
    local xml_url log_link role
    xml_url="$1"  # this is the Beaker results XML URL
    role="${2:-}"
    get_bkr_xml "$xml_url" | xmllint --xpath '//@href' - | cut -d '"' -f 2 | \
    while read -r log_link; do
        if [[ "$log_link" =~ SYSTEM-ROLE-([a-z_]+)_tests_ ]]; then
            if [ -z "$role" ] || [ "$role" = "${BASH_REMATCH[1]}" ]; then
                check_log_for_fact_gather_result "${BASH_REMATCH[1]}" "$log_link"
            fi
        fi
    done
}

if [ -f "$1" ]; then
    log_dir="$(dirname "$1")"
    if [[ "$1" =~ [.]xml$ ]]; then
        get_logs_from_bkr_xml "$1" "${2:-}"
    elif [[ "$1" =~ [.]log$ ]]; then
        check_log_for_fact_gather_result "$2" "$1"
    fi
elif [[ "$1" =~ ^http ]]; then
    # assume a link
    get_logs_from_bkr_xml "$1"
elif [ -n "${2:-}" ]; then
    get_logs_from_pr "$1" "$2"
fi
