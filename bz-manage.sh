#!/bin/bash

set -euo pipefail
if [ -n "${DEBUG:-}" ]; then
  set -x
fi

get_bzs() {
  # shellcheck disable=SC2086
  # jq arguments $3 are unquoted to allow full expansion
  # echo "bugzilla query --from-url \"$1\" --json | jq ${3:-} \"${2:-.bugs[].id}\""
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
show_url="https://bugzilla.redhat.com/show_bug.cgi?id="

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

new_bz() {
  local itr prod ver summary comment role
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

# Format the summary text for the spec changelog - if the summary
# already begins with the role, remove it
fmt_summary() {
  local summary roles
  summary="$1"
  roles="$2"
  if [ -n "$roles" ]; then
    if [[ "$summary" =~ ^${roles}[\ -:]+(.+)$ ]]; then
      echo "$roles - ${BASH_REMATCH[1]}"
    elif [[ "$summary" =~ ^\[RFE\]\ ${roles}[\ -:]+(.+)$ ]]; then
      echo "$roles - [RFE] ${BASH_REMATCH[1]}"
    else
      echo "$roles - $summary"
    fi
  else
    echo "$summary"
  fi
}

# Format a section header like New Features or Bug Fixes for
# either md or rST
fmt_section() {
  if [ -n "${USE_RST:-}" ]; then
    echo "$@"
    echo "~~~~~~~~~~~~~~"
  else
    echo "### $*"
  fi
}

# Format a bz entry for the changelog md or rST
fmt_bz_for_cl_md_rst() {
  local summary bz
  summary="$1"
  bz="$2"
  if [ -n "${USE_RST:-}" ]; then
    # do some rst fixup
    # convert ` into ``
    # shellcheck disable=SC2001
    # shellcheck disable=SC2016
    summary="$(echo "$summary" | sed 's/\([^`]\)`\([^`]\)/\1``\2/g')"
    echo "- \`${summary} <${show_url}${bz}>\`_"
  else
    echo "- [${summary}](${show_url}$bz)"
  fi
}

rpm_release() {
  # look up BZ for given ITR and status (default status is POST)
  # input is new version - N-V-R format
  # generate 3 files
  # - cl-spec - the new %changelog entry for the spec file - user will
  #   need to edit for name, email
  # - git-commit-msg - in the format required by dist-git
  # - cl.$suf - the new entry for CHANGELOG - .md or .rst
  # USE_RST will use .rst for suffix and generate rST - otherwise, .md and markdown
  local version queryurl jq bz summary fix_summary roles doc_text datesec new_features fixes suf new_cl
  version="$1"; shift
  queryurl="${BASE_URL}&bug_status=${STATUS}"
  jq='.bugs[] | ((.id|tostring) + "|" + (.whiteboard|gsub("role:"; "")) + "|" + .cf_doc_type + "|" + .summary)'
  datesec=$(date +%s)
  get_bzs "$queryurl" "$jq" -r | sort -k 2 -t \| > bzs.raw
  if [ -n "${USE_RST:-}" ]; then
    suf="rst"
  else
    suf="md"
  fi
  new_cl="${NEW_CL:-new-cl.$suf}"
  cat > "$new_cl" <<EOF
[$version] - $(date -I --date=@"$datesec")
----------------------------

EOF
  fmt_section "New Features" >> "$new_cl"
  echo "" >> "$new_cl"
  echo "* $(LANG=en_US.utf8 date --date=@"$datesec" "+%a %b %d %Y") Your Name <email@redhat.com> - $version" > "${CL_SPEC:-cl-spec}"
  echo "Package update" > "${GIT_COMMIT_MSG:-git-commit-msg}"
  new_features=false
  while IFS=\| read -r bz roles doc_text summary; do
    if [ "$doc_text" = Enhancement ]; then
      fix_summary=$(fmt_summary "$summary" "$roles")
      fmt_bz_for_cl_md_rst "$fix_summary" "$bz" >> "$new_cl"
      echo "- Resolves:rhbz#${bz} : ${fix_summary}" >> "${CL_SPEC:-cl-spec}"
      { echo ""
        echo "$fix_summary"
        echo "Resolves:rhbz#${bz}"; } >> "${GIT_COMMIT_MSG:-git-commit-msg}"
      new_features=true
    fi
  done < bzs.raw
  if [ "$new_features" = false ]; then
    echo "- none" >> "$new_cl"
  fi
  { echo "" ; fmt_section "Bug Fixes"; echo ""; } >> "$new_cl"
  fixes=false
  while IFS=\| read -r bz roles doc_text summary; do
    if [ "$doc_text" = "Bug Fix" ]; then
      fix_summary=$(fmt_summary "$summary" "$roles")
      fmt_bz_for_cl_md_rst "$fix_summary" "$bz" >> "$new_cl"
      echo "- Resolves:rhbz#${bz} : ${fix_summary}" >> "${CL_SPEC:-cl-spec}"
      { echo ""
        echo "$fix_summary"
        echo "Resolves:rhbz#${bz}"; } >> "${GIT_COMMIT_MSG:-git-commit-msg}"
      fixes=true
    fi
  done < bzs.raw
  if [ "$fixes" = false ]; then
    { echo "- none"; echo ""; } >> "$new_cl"
  fi
  while IFS=\| read -r bz roles doc_text summary; do
    if [ "$doc_text" != Enhancement ] && [ "$doc_text" != "Bug Fix" ]; then
      fix_summary=$(fmt_summary "$summary" "$roles")
      echo "- Resolves:rhbz#${bz} : ${fix_summary}" >> "${CL_SPEC:-cl-spec}"
      { echo ""
        echo "$fix_summary"
        echo "Resolves:rhbz#${bz}"; } >> "${GIT_COMMIT_MSG:-git-commit-msg}"
    fi
  done < bzs.raw
  rm bzs.raw
}

format_bz_for_md_rst() {
  local bz roles doc_text summary nf_file bf_file jq output fix_summary
  bz="$1"
  nf_file="$2"
  bf_file="$3"
  jq='.bugs[] | ((.whiteboard|gsub("role:"; "")) + "|" + .cf_doc_type + "|" + .summary)'
  IFS=\| read -r roles doc_text summary <<< "$(bugzilla query -b "$bz" --json | jq -r "$jq")"
  if [ "${doc_text:-}" = Enhancement ]; then
    output="$nf_file"
  elif [ "${doc_text:-}" = "Bug Fix" ]; then
    output="$bf_file"
  else
    echo Skipping "$bz" "${doc_text:-no doc text}" "${summary:-no summary}"
    return 0
  fi
  if [ -n "$roles" ]; then
    if [[ "$summary" =~ ^${roles}[\ -]+(.+)$ ]]; then
      fix_summary="$roles - ${BASH_REMATCH[1]}"
    else
      fix_summary="$roles - $summary"
    fi
  else
    fix_summary="$summary"
  fi
  if [ -f "$output" ]; then
    if grep -F -q "$fix_summary" "$output" || grep -q "\<${bz}\>" "$output"; then
      # already in there - skip
      return 0
    fi
  fi
  fmt_bz_for_cl_md_rst "$fix_summary" "$bz" >> "$output"
}

make_cl_for_version() {
  local version datestr cl_file cl_nf_file cl_bf_file
  version="$1"
  datestr="$2"
  cl_file="$3"
  cl_nf_file="$4"
  cl_bf_file="$5"
  if [ ! -f "$cl_nf_file" ] && [ ! -f "$cl_bf_file" ]; then
    return 0  # no cl for this version
  fi
  { echo ""
    echo ["$version"] - "$datestr"
    echo ----------------------------
    echo ""
    fmt_summary "New Features"
    echo ""; } >> "$cl_file"
  if [ -f "$cl_nf_file" ]; then
    cat "$cl_nf_file" >> "$cl_file"
  else
    echo "- none" >> "$cl_file"
  fi
  { echo ""
    fmt_summary "Bug Fixes"
    echo ""; } >> "$cl_file"
  if [ -f "$cl_bf_file" ]; then
    cat "$cl_bf_file" >> "$cl_file"
  else
    echo "- none" >> "$cl_file"
  fi
  rm -f "$cl_nf_file" "$cl_bf_file"
}

spec_cl_to_cl_md_rst() {
  local spec print cur_ver mon day year version datestr cl_file cl_nf_file cl_bf_file suf
  spec="$1"
  print=false
  version=""
  cur_ver=""
  if [ -n "${USE_RST:-}" ]; then
    suf="rst"
  else
    suf="md"
  fi
  cl_file=".cl.$suf"
  cl_nf_file=".cl-nf.$suf"
  cl_bf_file=".cl-bf.$suf"
  { echo Changelog
    echo =========; } > "$cl_file"
  while read -r line ; do
    if [ "$line" = %changelog ]; then
      print=true
      continue
    fi
    if [ "$print" = false ]; then
      continue
    fi
    if [[ "$line" =~ ^\*\ +[a-zA-Z]+\ +([a-zA-Z]+)\ +([0-9]+)\ +([0-9]+)\ .*-\ +([0-9]+\.[0-9]+(\.[0-9]+)?)- ]]; then
      mon="${BASH_REMATCH[1]}"
      day="${BASH_REMATCH[2]}"
      year="${BASH_REMATCH[3]}"
      version="${BASH_REMATCH[4]}"
      need_new_datestr=false
      if [ -n "$cur_ver" ] && [ "$version" != "$cur_ver" ]; then
        make_cl_for_version "$cur_ver" "$datestr" "$cl_file" "$cl_nf_file" "$cl_bf_file"
        need_new_datestr=true
      fi
      if [ -z "${datestr:-}" ] || [ "$need_new_datestr" = true ]; then
        datestr=$(date --date="$mon $day $year" +%Y-%m-%d)
      fi
      cur_ver="$version"
    elif [[ "$line" =~ bz.?([0-9]{7}) ]]; then
      while [[ "$line" =~ bz.?([0-9]{7}) ]]; do
        bz="${BASH_REMATCH[1]}"
        format_bz_for_md_rst "$bz" "$cl_nf_file" "$cl_bf_file"
        line="${line/$bz}"
      done
    fi
  done < "$spec"
  make_cl_for_version "$cur_ver" "$datestr" "$cl_file" "$cl_nf_file" "$cl_bf_file"
}

# e.g.
# 1234567   This is the bz summary
get_bz_id_summary() {
  local queryurl jq bz summary
  queryurl="${BASE_URL}"
  jq='.bugs[] | ((.id|tostring) + " " + .summary)'
  get_bzs "${queryurl}" "$jq" -r | while read -r bz summary; do
    echo "$bz   $summary"
  done
}

get_pr_info() {
  local gh_pr gh_pr_info
  gh_pr=$1
  gh_pr_info=$(gh pr view "$gh_pr" --json title,body --jq .title,.body)
  gh_pr_desc=$(echo "$gh_pr_info" | sed 1d | sed -e 's/[[:space:]]*$//' -e '/^$/d')
  gh_pr_title=$(echo "$gh_pr_info" | sed -n 1p)
  if [[ "$gh_pr_title" =~ ^feat.* ]]; then
    gh_pr_type="Enhancement"
  elif [[ "$gh_pr_title" =~ ^fix.* ]]; then
    gh_pr_type="Bug Fix"
  else
    gh_pr_type="Enhancement"
  fi
}

bz_add_doc_text() {
  gh_pr=$1
  bz=$2
  get_pr_info "$gh_pr"
  comment="Updating Doc Type and Text with info from the attached PR $gh_pr"
  echo "BZ#$bz: $comment"
  bugzilla modify --private \
    --field cf_doc_type="$gh_pr_type" \
    --field cf_release_notes="$gh_pr_desc" \
    --comment "$comment" \
    "$bz"
}

print_doc_text() {
  doc_type=$1
  doc_text=$2
  echo "~~~"
  echo "Doc Type:
$doc_type"
  echo -e "Doc Text:
$doc_text"
  echo "~~~"
}

bz_mod_doc_text() {
  gh_pr=$1
  bz=$2
  query_file=$3
  get_pr_info "$gh_pr"
  doc_text="$(jq -r "select(.id == $bz) | .cf_release_notes" "$query_file" | sed -e 's/[[:space:]]*$//' -e '/^$/d')"
  if [ -z "$doc_text" ]; then
    comment="Updating Doc Type and Text with info from the attached PR $gh_pr"
    echo "BZ#$bz: $comment"
    bugzilla modify --private \
      --field cf_doc_type="$gh_pr_type" \
      --field cf_release_notes="$gh_pr_desc" \
      --comment "$comment" \
      "$bz"
  else
    if [ "$doc_text" != "$gh_pr_desc" ]; then
      echo "BZ#$bz has Doc Text that differs from GitHub PR description"
      echo "The current Doc Type and Text:"
      print_doc_text "$doc_type" "$doc_text"
      echo ""
      echo "Doc Type and Text suggested from the GH PR:"
      print_doc_text "$gh_pr_type" "$gh_pr_desc"
      read -r -p 'Do you want to update the BZ with the suggested Doc Text and Type (y/n)? (default: n) ' update_bz </dev/tty
      if [ "${update_bz:-n}" = n ]; then
        return
      elif [ "${update_bz:-n}" = y ]; then
        comment="Updating Doc Type and Text with info from the attached PR $gh_pr"
        echo "BZ#$bz: $comment"
        bugzilla modify --private \
          --field cf_doc_type="$gh_pr_type" \
          --field cf_release_notes="$gh_pr_desc" \
          --comment "$comment" \
          "$bz"
      fi
    else
      echo "BZ#$bz already has Doc Text that equals GitHub PR description"
    fi
  fi
}

process_count_prs() {
  bz=$1
  func=$2
  args=$3
  echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
  jq_count_prs="select(.id == $bz)\
| [.external_bugs[]\
| select((.type.type == \"GitHub\") and (.ext_bz_bug_id | contains(\"pull\")))]\
| length"
  gh_pr_count=$(jq -r "$jq_count_prs" "$query_file")
  if [ "$gh_pr_count" -eq 1 ]; then
    # shellcheck disable=SC2086
    $func $args
  elif [ "$gh_pr_count" -gt 1 ]; then
    echo "BZ#$bz has $gh_pr_count GH PRs attached, you may choose info from what PR to use"
    for ((i=0;i<gh_pr_count;i++)); do
      jq_gh_pr="\"https://github.com/\" + ([.external_bugs[]\
| select((.type.type == \"GitHub\") and (.ext_bz_bug_id | contains(\"pull\")))][$i] .ext_bz_bug_id | tostring)"
      gh_pr=$(jq -r "$jq_gh_pr" "$query_file")
      get_pr_info "$gh_pr"
      echo "($i) Doc Type and Text suggested from GH PR $gh_pr:"
      print_doc_text "$gh_pr_type" "$gh_pr_desc"
    done
    read -r -p "What PR do you want to use for Doc Text and Type? (type a number from 0 to $((gh_pr_count-1)), or s to skip)? (default: s) " update_gh </dev/tty
    if [ "${update_gh:-s}" = s ]; then
      return
    else
      jq_gh_pr="\"https://github.com/\" + ([.external_bugs[]\
| select((.type.type == \"GitHub\") and (.ext_bz_bug_id | contains(\"pull\")))][$update_gh] .ext_bz_bug_id | tostring)"
      gh_pr=$(jq -r "$jq_gh_pr" "$query_file")
      # shellcheck disable=SC2086
      $func $args
    fi
  fi
}

update_doc_text() {
  local queryurl jq bz bz_assignee doc_type doc_text gh_pr gh_pr_info gh_pr_title gh_pr_desc gh_pr_type update_bz
  query_file=.query_file.json

  # I. If a BZ has required_doc_text? set and GitHub PR set:
  # If the existing doc_text is empty, add doc text from PR description
  # else
  # Print BZ's doc text and type, print GH PR title and desc
  # Ask user if they want to update the doc text.

  # substring doesn't work with ext_bz_bug_map.ext_bz_bug_id, using anywordssubstr
  queryurl="${BASE_URL}\
&f1=flagtypes.name&f2=external_bugzilla.url&f3=ext_bz_bug_map.ext_bz_bug_id\
&o1=substring&o2=substring&o3=anywordssubstr\
&v1=requires_doc_text?&v2=github&v3=pull"
  jq='.bugs[]'
  echo Searching BZs that have required_doc_text? set and GitHub PR set
  get_bzs "${queryurl}" "$jq" -r > "$query_file"
  jq="(.id | tostring) + \"|https://github.com/\" + \
[(.external_bugs[] | select(.type.type == \"GitHub\") | select(.ext_bz_bug_id | contains(\"pull\")) | .ext_bz_bug_id | tostring)][0]\
+ \"|\" + .cf_doc_type"
  jq -r "$jq" "$query_file" | while IFS=\| read -r bz gh_pr doc_type; do
    process_count_prs "$bz" bz_mod_doc_text "$gh_pr $bz $query_file"
    done

  # II. If a BZ has required_doc_text unset and GH PR set:
  # Add doc text from PR description

  # substring doesn't work with ext_bz_bug_map.ext_bz_bug_id, using anywordssubstr
  queryurl="${BASE_URL}\
&f1=flagtypes.name&f2=external_bugzilla.url&f3=ext_bz_bug_map.ext_bz_bug_id\
&o1=notsubstring&o2=substring&o3=anywordssubstr\
&v1=requires_doc_text&v2=github&v3=pull"
  jq='.bugs[]'
  echo Searching BZs that have required_doc_text unset and GH PR set
  get_bzs "${queryurl}" "$jq" -r > "$query_file"
  jq="(.id | tostring) + \" https://github.com/\" + \
[(.external_bugs[] | select(.type.type == \"GitHub\") | .ext_bz_bug_id | tostring)][0]"
  jq -r "$jq" "$query_file" | while read -r bz gh_pr; do
    process_count_prs "$bz" bz_add_doc_text "$gh_pr $bz"
    done

  # III. If a BZ has required_doc_text not set to + or - and GitHub PR unset:
  # Print the current doc text and type,
  # Ask users if they want to post a comment asking to attach a GH PR or
  # enter the doc text.

  # substring doesn't work with ext_bz_bug_map.ext_bz_bug_id, using anywordssubstr
  # %n3=1 is required because nowordssubstr doesn't work
  queryurl="${BASE_URL}\
&f1=flagtypes.name&f2=flagtypes.name&f3=external_bugzilla.url\
&o1=notsubstring&o2=notsubstring&o3=anywordssubstr&n3=1\
&v1=requires_doc_text-&v2=requires_doc_text%2B&v3=github"
  jq='.bugs[]'
  echo Searching BZs that have required_doc_text not set to + or - and GitHub PR unset
  get_bzs "${queryurl}" "$jq" -r > "$query_file"
  jq='(.id | tostring)'
  jq -r "$jq" "$query_file" | while read -r bz; do
    echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
    doc_type="$(jq -r "select(.id == $bz) | .cf_doc_type" $query_file)"
    bz_assignee="$(jq -r "select(.id == $bz) | .assigned_to" $query_file)"
    if [[ "$doc_type" != "If docs needed, set a value" ]]; then
      doc_text="$(jq -r "select(.id == $bz) | .cf_release_notes" $query_file)"
      echo "BZ#$bz has required_doc_text set to ? and doesn't have GitHub PR provided"
      echo "The current Doc Type and Text:"
      print_doc_text "$doc_type" "$doc_text"
      echo ""
    else
      echo "BZ#$bz doesn't have required_doc_text set and doesn't have GitHub PR provided"
    fi
    read -r -p "Do you want to post a comment asking to attach a GH PR or enter a doc text (y/n)? (default: n) " update_bz </dev/tty
    if [ "${update_bz:-n}" = n ]; then
        continue
    elif [ "$update_bz" = y ]; then
      echo "BZ#$bz: Posting a comment asking to attach a GH PR or enter a doc text"
      bugzilla modify --private \
        --comment "Hello @$bz_assignee,
Please attach a related GitHub PR to this bug so that we can collect a Doc Text from it, or provide a Doc Text yourself.
Thank you" \
        "$bz"
    fi
    done
}

"$@"
