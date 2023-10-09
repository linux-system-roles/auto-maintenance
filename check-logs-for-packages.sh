#!/bin/bash
# -*- coding: utf-8 -*-
# Copyright: (c) 2023, Red Hat, Inc.
# SPDX-License-Identifier: MIT

set -euo pipefail

declare -A LOG_LEVELS=( [DEBUG]=0 [INFO]=1 [NOTICE]=2 [WARNING]=3 [ERROR]=4 [CRITICAL]=5 [FATAL]=6 )
LOG_LEVEL="${LOG_LEVEL:-NOTICE}"

logmsg() {
    if [ "${LOG_LEVELS[$1]}" -ge "${LOG_LEVELS[$LOG_LEVEL]}" ]; then
        local level
        level="$1"; shift
        echo "$level": "$@"
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

# Download the given log_link and optionally store it to log_dir if log_dir is given
# If log_link is a file, just return it.
get_log() {
    local role pr distro ver ansible_ver log_link file_name
    role="$1"
    pr="$2"
    distro="$3"
    major_ver="$4"
    ver="$5"
    ansible_ver="$6"
    log_link="$7"
    if [ -f "$log_link" ]; then
        cat "$log_link"
    else
        if [ -n "${log_dir:-}" ]; then
            if [ ! -d "$log_dir" ]; then
                mkdir -p "$log_dir"
            fi
            file_name="$log_dir/${role}@${pr}@${distro}@${major_ver}@${ver}@${ansible_ver}@$(basename "$log_link")"
            if [ ! -f "$file_name" ]; then
                curl -L -s -o "$file_name" "$log_link"
            fi
            cat "$file_name"
        else
            curl -L -s "$log_link"
        fi
    fi
}

# return value
# runtime - package is runtime and in given role
# testing - package is testing and in given role
# skip - package is from included role
parse_path() {
    local role path
    role="$1"
    path="$2"
    if [[ "$path" =~ /tests/roles/linux-system-roles.${role}/tasks/ ]]; then
        echo runtime
        debug runtime role path "$path"
    elif [[ "$path" =~ /ansible_collections/fedora/linux_system_roles/([a-z]+)/([a-z_]+)/tasks/ ]]; then
        local role_match type
        type="${BASH_REMATCH[1]}"
        role_match="${BASH_REMATCH[2]}"
        if [ "$role_match" = "$role" ] || [[ "$role_match" =~ ^private_${role}_ ]]; then
            if [ "$type" = tests ]; then
                echo testing
                debug testing role path "$path"
            else
                echo runtime
                debug runtime role path "$path"
            fi
        else
            echo skip
            debug not role path "$path"
        fi
    else
        echo testing
        debug assume testing "$path"
    fi
}

# we want to exclude packages managed by system roles called by this
# role - the package lists for this role should contain only packages
# managed by this role
# TASK [fedora.linux_system_roles.selinux : Install SELinux python3 tools] *******
# task path: /WORKDIR/git-weekly-ciq44gwyx3/.collection/ansible_collections/fedora/linux_system_roles/roles/selinux/tasks/set_facts_packages.yml:15
# Saturday 07 October 2023  10:42:51 +0000 (0:00:00.072)       0:00:13.103 ******
# ok: [sut] => {
#     "changed": false,
#     "rc": 0,
#     "results": []
# }

# Scan the given log file/url for packages.  Write the packages
# to $log_dir/${role}-packages-${pkg_type}-${distro}-${ver}.txt
# where pkg_type is runtime or testing
check_log_for_packages() {
    local role pr distro major_ver ver ansible_ver log_link ansible_distro
    role="$1"
    pr="$2"
    distro="$3"
    major_ver="$4"
    ver="$5"
    ansible_ver="$6"
    log_link="$7"
    if [[ "$log_link" =~ [.]log$ ]]; then
        :  # is a log
    else
        return 0
    fi
    ansible_distro="$distro"
    if [ "$ansible_distro" = RHEL ]; then
        ansible_distro=RedHat
    fi
    info "### test $log_link"
    get_log "$role" "$pr" "$distro" "$major_ver" "$ver" "$ansible_ver" "$log_link" | \
    { local pkg_type line output_file path
    pkg_type=""
    while read -r line; do
        if [[ "$line" =~ ^task\ path:\ (.+): ]]; then
            path="${BASH_REMATCH[1]}"
            pkg_type="$(parse_path "$role" "$path")"
        fi
        output_file="$log_dir/${role}-packages-${pkg_type}-${ansible_distro}-${ver}.txt"
        if [[ "$line" =~ ^lsrpackages:\ (.+) ]]; then
            if [ "$pkg_type" = skip ]; then
                # shellcheck disable=SC2001
                echo "${BASH_REMATCH[1]}" | sed 's/ /\n/g' >> "$log_dir/skip.txt"
            else
                # could not figure out how to use variable//search/replace for this
                # shellcheck disable=SC2001
                echo "${BASH_REMATCH[1]}" | sed 's/ /\n/g' >> "$output_file"
            fi
        fi
    done
    }
}

# Download and scan all of the logs from the given PR
get_logs_from_pr() {
    local role pr context summary_url distro ver major_ver rest ansible_ver log_link
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
        # split context into distro ver ansible ver
        if [[ "$context" =~ ^([[:alpha:]]+)(-Stream)?-([[:digit:].]+)(-latest)?/(.+) ]]; then
            distro="${BASH_REMATCH[1]}"
            ver="${BASH_REMATCH[3]}"
            ansible_ver="${BASH_REMATCH[5]}"
            IFS=. read -r major_ver rest <<< "$ver"
        else
            error Cannot parse context "$context"
            exit 1
        fi
        curl -s "$summary_url" | xmllint --html --xpath '//@href' - 2> /dev/null | \
        cut -d '"' -f 2 | \
        while read -r log_link; do
            check_log_for_packages "$role" "$pr" "$distro" "$major_ver" "$ver" "$ansible_ver" "$log_link"
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
                check_log_for_packages "${BASH_REMATCH[1]}" NOPR CONTEXT "$log_link"
            fi
        fi
    done
}

# See if the given version number is a major version or a full version with .
is_major_ver() {
    if [[ "$1" =~ ^[[:digit:]]+$ ]]; then
        return 0
    fi
    return 1
}

# input: the common file and N other files
# return: the common file will contain only lines
#         common to the other input files
#         each input file will contain only lines
#         not in the common file
roll_up_to_common() {
    local common tmp
    common="$1"; shift
    if [ -z "${1:-}" ] || [ ! -f "$1" ]; then
        debug roll_up_to_common: no files to process for "$common"
        return 0
    fi
    tmp="$(mktemp)"
    # init common file if it does not exist
    if [ ! -f "$common" ]; then
        if [ -n "${2:-}" ] && [ -f "$2" ]; then
            comm -12 "$1" "$2" > "$common"
        else
            cp "$1" "$common"
            rm "$1"
            debug roll_up_to_common: only 1 file to process for "$common" - "$1"
            return 0
        fi
    fi
    # $common will contain only lines in common to all files
    for file in "$@"; do
        if [ -f "$file" ]; then
            comm -12 "$file" "$common" > "$tmp"
            mv "$tmp" "$common"
            # shellcheck disable=SC2046
            debug roll_up_to_common: common packages between "$common" and "$file" are $(cat "$common")
        else
            debug roll_up_to_common: file "$file" does not exist
        fi
    done
    # each file will contain lines not in $common
    debug roll_up_to_common: here "$@"
    for file in "$@"; do
        debug roll_up_to_common: processing file "$file"
        if [ -f "$file" ]; then
            comm -23 "$file" "$common" > "$tmp"
            mv "$tmp" "$file"
            if [ ! -s "$file" ]; then
                # just remove empty files
                rm -f "$file"
                debug roll_up_to_common: file "$file" contains only common packages - removing
            else
                # shellcheck disable=SC2046
                debug roll_up_to_common: file "$file" has the packages not in common $(cat "$file")
            fi
            # shellcheck disable=SC2046
            debug roll_up_to_common: common packages in "$common" are now $(cat "$common")
        else
            debug roll_up_to_common: file "$file" does not exist
        fi
    done
    if [ -s "$common" ]; then
        # shellcheck disable=SC2046
        debug roll_up_to_common: common packages in "$common" - $(cat "$common")
    else
        debug roll_up_to_common no packages in common for "$@"
    fi
    rm -f "$tmp"
}

if [ -d "$1" ]; then
    log_dir="$1"
    find "$log_dir" -name \*.log | while read -r log_file; do
        # shellcheck disable=SC2034
        IFS=@ read -r role pr distro major_ver ver ansible_ver test <<< "$(basename "$log_file")"
        check_log_for_packages "$role" "$pr" "$distro" "$major_ver" "$ver" "$ansible_ver" "$log_file"
    done
elif [ -f "$1" ]; then
    log_dir="$(dirname "$1")"
    if [[ "$1" =~ [.]xml$ ]]; then
        get_logs_from_bkr_xml "$1" "${2:-}"
    elif [[ "$1" =~ [.]log$ ]]; then
        check_log_for_packages "" "" "$2" "$1"
    fi
elif [[ "$1" =~ ^http ]]; then
    # assume a link
    get_logs_from_bkr_xml "$1"
elif [ -n "${2:-}" ]; then
    while [ -n "${1:-}" ]; do
        role="$1"; shift
        pr="$1"; shift
        get_logs_from_pr "$role" "$pr"
    done
fi

# normalize and pre-digest the package files
declare -A roles pkg_types distros major_vers distro_major_ver
for file in "$log_dir"/*.txt; do
    sort -u "$file" > "$log_dir/tmp"
    mv -f "$log_dir/tmp" "$file"
    # shellcheck disable=SC2034
    IFS=- read -r role packages pkg_type distro ver <<< "$(basename "$file")"
    IFS=. read -r major_ver rest <<< "$ver"
    if [ -z "$pkg_type" ]; then continue; fi
    roles["$role"]="$role"
    pkg_types["$pkg_type"]="$pkg_type"
    distros["$distro"]="$distro"
    major_vers["$major_ver"]="$major_ver"
    distro_major_ver["${distro}-${major_ver}"]="${distro}-${major_ver}"
done

# We need data from at least these releases to have enough package
# coverage.
required_distro_major_ver=(Fedora-37 Fedora-38 CentOS-8 RedHat-8 RedHat-9)
for distro_ver in "${required_distro_major_ver[@]}"; do
    if [ -z "${distro_major_ver["$distro_ver"]:-}" ]; then
        error Do not have results from "$distro_ver" - cannot continue
        exit 1
    fi
done

debug roles "${roles[@]}"
debug pkg_types "${pkg_types[@]}"
debug distros "${distros[@]}"
debug major_vers "${major_vers[@]}"

for role in "${roles[@]}"; do
    for pkg_type in "${pkg_types[@]}"; do
        role_pkg_type="$log_dir/${role}-packages-${pkg_type}.txt"
        distro_files=()
        for distro in "${distros[@]}"; do
            role_pkg_type_distro="$log_dir/${role}-packages-${pkg_type}-${distro}.txt"
            major_vers_files=()
            for major_ver in "${major_vers[@]}"; do
                # roll up all full version files, if any, into the major version file
                role_pkg_type_distro_major="$log_dir/${role}-packages-${pkg_type}-${distro}-${major_ver}.txt"
                if [ -f "$role_pkg_type_distro_major" ]; then
                    debug "$role_pkg_type_distro_major" already exists - no full versions - skipping
                    major_vers_files+=("$role_pkg_type_distro_major")
                    continue
                fi
                full_vers_files=()
                for file in "$log_dir/${role}-packages-${pkg_type}-${distro}-${major_ver}".*.txt; do
                    if [ -f "$file" ]; then
                        full_vers_files+=("$file")
                    fi
                done
                roll_up_to_common "$role_pkg_type_distro_major" "${full_vers_files[@]}"
                if [ -f "$role_pkg_type_distro_major" ]; then
                    debug rolled up to "$role_pkg_type_distro_major" from "${full_vers_files[@]}"
                    major_vers_files+=("$role_pkg_type_distro_major")
                fi
            done
            # roll up major version files to distro
            roll_up_to_common "$role_pkg_type_distro" "${major_vers_files[@]}"
            if [ -f "$role_pkg_type_distro" ]; then
                debug rolled up to "$role_pkg_type_distro" from "${major_vers_files[@]}"
                distro_files+=("$role_pkg_type_distro")
            fi
        done
        # roll up all distro files to all runtime or testing files
        roll_up_to_common "$role_pkg_type" "${distro_files[@]}"
        if [ -f "$role_pkg_type" ]; then
            debug rolled up to "$role_pkg_type" from "${distro_files[@]}"
        fi
    done
done

if [ -n "${ROLE_PARENT_DIR:-}" ] && [ -d "$ROLE_PARENT_DIR" ]; then
    for role in "${roles[@]}"; do
        role_dir="$ROLE_PARENT_DIR/linux-system-roles.$role"
        if [ ! -d "$role_dir" ]; then
            role_dir="$ROLE_PARENT_DIR/$role"
        fi
        if [ ! -d "$role_dir" ]; then
            error Could not find directory for "$role" under "$ROLE_PARENT_DIR"
            exit 1
        fi
        firsttime=1
        for file in "$log_dir/${role}-packages-"*.txt; do
            if [ -f "$file" ]; then
                if [ ! -d "$role_dir/.ostree" ]; then
                    mkdir -p "$role_dir/.ostree"
                fi
                if [ "$firsttime" = 1 ]; then
                    rm -f "$role_dir/.ostree/packages-"*.txt
                    firsttime=0
                fi
                destfile="$role_dir/.ostree/$(basename "${file/${role}-/}")"
                cp "$file" "$destfile"
            fi
        done
    done
fi
