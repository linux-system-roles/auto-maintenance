#!/bin/bash

set -euo pipefail
if [ -n "${DEBUG:-}" ]; then
  set -x
fi

get_bzs() {
  # shellcheck disable=SC2086
  # jq arguments $3 are unquoted to allow full expansion
  bugzilla query --from-url "$1" --json | jq ${3:-} "${2:-.bugs[].id}"
}

COMPONENT=${COMPONENT:-rhel-system-roles}
ITR_FIELD=${ITR_FIELD:-cf_internal_target_release}
ITR=${ITR:-8.7.0}
ITM_FIELD=${ITM_FIELD:-cf_internal_target_milestone}
ITM=${ITM:-16}
DTM_FIELD=${DTM_FIELD:-cf_dev_target_milestone}
DTM=${DTM:-13}
STATUS=${STATUS:-POST}
BZ_URL=${URL:-https://bugzilla.redhat.com/buglist.cgi}
LIMIT=${LIMIT:-100}
BASE_URL="${BZ_URL}?limit=${LIMIT}&component=${COMPONENT}&${ITR_FIELD}=${ITR}"

setitmdtm() {
  local field val bzlist baseurl
  if [ "$1" == itm ]; then
    field="$ITM_FIELD"
    val="$ITM"
  else
    field="$DTM_FIELD"
    val="$DTM"
  fi
  baseurl="${BASE_URL}&bug_status=${STATUS}&f1=${field}"
  # find and set bugs with no value set
  bzlist=$(get_bzs "${baseurl}&o1=isempty")
  if [ -n "$bzlist" ]; then
    # shellcheck disable=SC2086
    bugzilla modify --field "$field"="$val" $bzlist
  fi
  # find and set bugs with wrong value
  bzlist=$(get_bzs "${baseurl}&o1=lessthan&v1=${val}")
  if [ -n "$bzlist" ]; then
    # shellcheck disable=SC2086
    bugzilla modify --field "$field"="$val" $bzlist
  fi
}

reset_dev_wb() {
  local queryurl jq bz dev_wb newval
  queryurl="${BASE_URL}&f1=flagtypes.name&o1=substring&v1=qa_ack%2B&f2=cf_devel_whiteboard&o2=substring&v2=qa_ack%3F"
  jq='.bugs[] | ((.id|tostring) + " " + .devel_whiteboard)'
  get_bzs "${queryurl}" "$jq" -r | while read -r bz dev_wb; do
    # shellcheck disable=SC2001
    newval=$(echo "$dev_wb" | sed 's/[ ]*qa_ack?[ ]*//')
    set -x
    bugzilla modify --field cf_devel_whiteboard="$newval" "$bz"
    set +x
  done
  queryurl="${BASE_URL}&f1=cf_verified&o1=equals&v1=Tested&f2=cf_devel_whiteboard&o2=substring&v2=pre-verify%3F"
  get_bzs "${queryurl}" "$jq" -r | while read -r bz dev_wb; do
    # shellcheck disable=SC2001
    newval=$(echo "$dev_wb" | sed 's/[ ]*pre-verify?[ ]*//')
    set -x
    bugzilla modify --field cf_devel_whiteboard="$newval" "$bz"
    set +x
  done
}

# get a list of BZ formatted for dist git BZ checking
get_commit_msg() {
  local queryurl jq
  queryurl="${BASE_URL}&bug_status=${STATUS}&f1=flagtypes.name&o1=substring&v1=release%2B"
  jq='.bugs[] | ((.id|tostring) + " " + .summary)'
  get_bzs "${queryurl}" "$jq" -r | while read -r bz summary; do
    echo "$summary"
    echo "Resolves: rhbz#$bz"
    echo ""
  done
}

# get a list of BZ formatted for spec changelog or commit msg
get_cl() {
  local queryurl jq bz summary clone_bz clone_itr itr sum_prefix bz_prefix
  queryurl="${BASE_URL}&bug_status=${STATUS}"
  jq='.bugs[] | ((.id|tostring) + " " + .summary)'
  get_bzs "${queryurl}" "$jq" -r | while read -r bz summary; do
    if [ "${INCLUDE_CLONE:-false}" = true ]; then
      clone_bz=$(get_bz_clone "$bz")
      clone_itr=$(bugzilla query -b "$clone_bz" --json | jq -r '.bugs[].cf_internal_target_release')
      clone_itr=" ($clone_itr)"
      itr=" ($ITR)"
    else
      clone_bz=""
      clone_itr=""
      itr=""
    fi
    if [ "${RPM_CL:-false}" = true ]; then
      sum_prefix="- "
      bz_prefix="  "
    else
      sum_prefix=""
      bz_prefix=""
    fi
    echo "${sum_prefix}$summary"
    echo "${bz_prefix}Resolves: rhbz#${bz}${itr}"
    if [ -n "$clone_itr" ]; then
      echo "${bz_prefix}Resolves: rhbz#${clone_bz}${clone_itr}"
    fi
    echo ""
  done
}

new_bz() {
  local itr prod ver
  ver="$1"; shift  # X.Y
  summary="$1"; shift
  comment="$1"; shift
  role="$1"; shift
  case "$ver" in
  8*) prod="Red Hat Enterprise Linux 8";;
  9*) prod="Red Hat Enterprise Linux 9";;
  esac
  itr="${ver}.0"
  bugzilla new -p "$prod" -v "$ver" -c rhel-system-roles -t "$summary" \
    -l "$comment" --field status_whiteboard="$role" \
    --field cf_internal_target_release="$itr"
}

# given a bz, return the clone of that bz, or nothing if the
# bz has no clone
get_bz_clone() {
  local bz clone_bz blocks block_bz
  bz="$1"
  clone_bz=$(bugzilla query -b "$bz" --json | jq -r '.bugs[].cf_clone_of')
  if [ "${clone_bz:-null}" != null ]; then
    echo "$clone_bz"
    return 0
  fi
  blocks=$(bugzilla query -b "$bz" --json | jq -r '.bugs[].blocks[]')
  for block_bz in $blocks; do
    clone_bz=$(bugzilla query -b "$block_bz" --json | jq -r '.bugs[].cf_clone_of')
    if [ "$bz" = "$clone_bz" ]; then
      echo "$block_bz"
      return 0
    fi
  done
  echo ""
  return 1
}

# we want to ensure that for each bz in itr1, there is a corresponding
# clone in itr2 - the problem is that there is no "cf_clones" field,
# only a "cf_clone_of" field - so to go back the other way, we have
# to look at the "blocks" to see if any of those refer to a bz that is
# a clone of the original bz
clone_check() {
  local bz bz_list blocks clone_bz rc bz_summary clone_summary clone_status
  rc=0
  bz_list=$(get_bzs "$BASE_URL&bug_status=${STATUS}")
  for bz in $bz_list; do
    if clone_bz=$(get_bz_clone "$bz") && [ -n "$clone_bz" ]; then
      bz_summary=$(bugzilla query -b "$bz" --json | jq -r '.bugs[].summary')
      read -r clone_status clone_summary <<< "$(bugzilla query -b "$clone_bz" --json | jq -r '.bugs[] | (.status + " " + .summary)')"
      if [ "$bz_summary" != "$clone_summary" ]; then
        echo ERROR: bz "$bz" summary ["$bz_summary"] does not match clone "$clone_bz" summary ["$clone_summary"]
        rc=1
      fi
      if [ "$STATUS" != "$clone_status" ]; then
        echo ERROR: bz "$bz" status ["$STATUS"] does not match clone "$clone_bz" status ["$clone_status"]
        rc=1
      fi
    else
      echo ERROR: bz "$bz" has no clone
      rc=1
    fi
  done
  return $rc
}

case "${1:-}" in
setitm) setitmdtm itm ;;
setdtm) setitmdtm dtm ;;
reset_dev_wb) reset_dev_wb ;;
get_commit_msg) get_commit_msg ;;
get_cl) get_cl ;;
new) shift; new_bz "$@" ;;
clone_check) clone_check ;;
*) echo Error - see documentation; exit 1 ;;
esac
