#!/bin/bash

set -euo pipefail
if [ -n "${DEBUG:-}" ]; then
  set -x
fi

type -p ansible-playbook > /dev/null 2>&1 || { echo ERROR: Requires ansible-playbook to run jira-playbooks; exit 1; }
type -p ansible-galaxy > /dev/null 2>&1 || { echo ERROR: Requires ansible-galaxy to run jira-playbooks; exit 1; }

if ansible-galaxy collection list community.general | grep -q 'unable to find community.general'; then
  echo ERROR: requires collection community.general for jira module
  exit 1
fi

if ansible-galaxy collection list ansible.posix | grep -q 'unable to find ansible.posix'; then
  echo ERROR: requires collection ansible.posix
  exit 1
fi

export ANSIBLE_STDOUT_CALLBACK=debug
# we need to be able to use
# set_fact:
#   var: "Yes"
# see https://github.com/ansible/ansible/pull/43425
export ANSIBLE_JINJA2_NATIVE=1

create_issue() {
  local cmdline
  cmdline=(-vv -e version="$1")
  shift
  # You must give a version for the new issue
  # If you give a URL to a github issue, most of the other fields
  # can be determined like summary and description.  If the link is
  # to a PR that is in Conventional Commits format, then the issuetype
  # can be discovered - otherwise, you will also have to specify the
  # issuetype.
  if [[ "$1" =~ ^https://github.com ]]; then
    # url - note that the playbook can construct all of the below fields
    # from the github issue - but you can override the github issue
    # fields by specifying them
    cmdline+=(-e github_issue="$1")
    shift
  fi
  if [ -n "${1:-}" ]; then
    # Bug or Story
    cmdline+=(-e issuetype="$1")
    shift
  fi
  if [ -n "${1:-}" ]; then
    # comma delimited list of role names
    cmdline+=(-e roles="$1")
    shift
  fi
  if [ -n "${1:-}" ]; then
    # e.g. "fix: this is a fix"
    cmdline+=(-e summary="'$1'")
    shift
  fi
  if [ -n "${1:-}" ]; then
    # description
    cmdline+=(-e description="'$1'")
    shift
  fi
  if [ -z "${new_issue_file:-}" ]; then
    new_issue_file="$(pwd)/new_issue"
  fi
  rm -f "$new_issue_file"
  ansible-playbook "${cmdline[@]}" -e new_issue_file="$new_issue_file" jira_playbooks/create_issue_pb.yml
  cat "$new_issue_file"
}

# first argument is the clone version - second argument is the original version
# I know this is backwards but we can do a shift to get the clone version, then
# pass the remaining args to create_issue
create_and_clone_issue() {
  local issue_to_clone clone_version
  new_issue_file="$(pwd)/new_issue"
  clone_version="$1"; shift
  create_issue "$@"
  issue_to_clone="$(cat "$new_issue_file")"
  clone_and_link_issue "$issue_to_clone" "$clone_version"
}

add_external_link() {
  ansible-playbook -vv -e issue_key="$1" -e external_link_url="$2" -e external_link_title="$3" jira_playbooks/add_external_link_pb.yml
}

clone_and_link_issue() {
  ansible-playbook -vv -e clone_issue_key="$1" -e clone_version="$2" jira_playbooks/clone_and_link_issue_pb.yml
}

request_clone_issue() {
  # version is something like e.g. "RHEL 10"
  # field to set in clone - must be listed in __field_map in update_issue.yml
  local cmdline
  cmdline=(-vv -e clone_issue_key="$1" -e request_clone_version="'$2'")
  shift; shift
  while [ -n "${1:-}" ] && [ -n "${2:-}" ]; do
    # shellcheck disable=SC2191
    cmdline+=(-e "$1"="$2"); shift; shift
  done
  ansible-playbook "${cmdline[@]}" jira_playbooks/request_clone_pb.yml
}


rpm_release() {
  ansible-playbook -vv -e rpm_version="$1" jira_playbooks/rpm_release_pb.yml
}

get_create_edit_meta() {
  # https://developer.atlassian.com/server/jira/platform/jira-rest-api-examples/
  # shellcheck disable=SC2034
  local projectid bug story issuetype bug_issue story_issue
  projectid=12332745
  # shellcheck disable=SC2034
  bug=1
  story=17
  # shellcheck disable=SC2154
  curl -s -H "Authorization: Bearer $token" https://issues.redhat.com/rest/api/2/issue/createmeta/"$projectid"/issuetypes/"$bug" | jq . > createmeta-bug.json
  curl -s -H "Authorization: Bearer $token" https://issues.redhat.com/rest/api/2/issue/createmeta/"$projectid"/issuetypes/"$story" | jq . > createmeta-story.json
  bug_issue=RHEL-25777
  story_issue=RHEL-30170
  curl -s -H "Authorization: Bearer $token" https://issues.redhat.com/rest/api/2/issue/"$bug_issue"/editmeta | jq . > editmeta-bug.json
  curl -s -H "Authorization: Bearer $token" https://issues.redhat.com/rest/api/2/issue/"$story_issue"/editmeta | jq . > editmeta-story.json
}

get_pr_info() {
  local gh_pr gh_pr_info
  gh_pr="$1"
  gh_pr_info=$(gh pr view "$gh_pr" --json title,body --jq .title,.body)
  gh_pr_desc=$(echo "$gh_pr_info" | sed 1d | sed -e 's/[[:space:]]*$//' -e '/^$/d')
  gh_pr_title=$(echo "$gh_pr_info" | sed -n 1p)
  if [[ "$gh_pr_title" =~ ^feat:.* ]]; then
    gh_pr_type="Enhancement"
  elif [[ "$gh_pr_title" =~ ^fix:.* ]]; then
    gh_pr_type="Bug Fix"
  else
    gh_pr_type="Enhancement"
  fi
}

print_doc_text() {
  local doc_type doc_text
  doc_type="$1"
  doc_text="$2"
  echo "~~~"
  echo "Doc Type:
$doc_type"
  echo -e "Doc Text:
$doc_text"
  echo "~~~"
}

issue_add_doc_text() {
  local gh_pr issue comment
  gh_pr="$1"
  issue="$2"
  get_pr_info "$gh_pr"
  comment="Updating Doc Type and Text with info from the attached PR $gh_pr"
  echo "Issue $issue: $comment"
  ansible-playbook -vv -e update_issue_key="$issue" -e doc_text_type="'$gh_pr_type'" -e doc_text="'$gh_pr_desc'" -e comment="'$comment'" jira_playbooks/update_issue_pb.yml
}

update_itm_dtm() {
  local cmd=(ansible-playbook -vv -e status="'$1'")
  if [ -n "$2" ]; then
    cmd+=(-e itm="$2")
  fi
  if [ -n "${3:-}" ]; then
    cmd+=(-e dtm="$3")
  fi
  "${cmd[@]}" jira_playbooks/update_itm_dtm.yml
}

dump_issue() {
  ansible-playbook -vv -e issue_key="$1" -e issue_file="${2:-"$1.json"}" jira_playbooks/dump_issue.yml
}

list_issues() {
  local output_file
  output_file="$(pwd)/issues"
  ansible-playbook -vv -e status="'$1'" -e output_file="$output_file" jira_playbooks/list_issues_pb.yml
  cat "$output_file"
}

"$@"
