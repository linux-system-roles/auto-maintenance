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

create_and_clone_issue() {
  local cmdline
  cmdline=(-vvvv -e version="$1" -e clone_version="$2")
  shift; shift
  # You must give a version for the new issue, and a version
  # for the clone issue.
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
  ansible-playbook "${cmdline[@]}" jira_playbooks/create_and_clone_issue_pb.yml
}

add_external_link() {
  ansible-playbook -vv -e issue_key="$1" -e external_link_url="$2" -e external_link_title="$3" jira_playbooks/add_external_link_pb.yml
}

clone_and_link_issue() {
  ansible-playbook -vv -e clone_issue_key="$1" -e clone_version="$2" jira_playbooks/clone_and_link_issue_pb.yml
}

rpm_release() {
  ansible-playbook -vv -e rpm_version="$1" jira_playbooks/rpm_release_pb.yml
}

get_createmeta() {
  # shellcheck disable=SC2034
  local projectid bug story issuetype
  projectid=12332745
  # shellcheck disable=SC2034
  bug=1
  story=17
  issuetype="$story"
  # shellcheck disable=SC2154
  curl -s -H "Authorization: Bearer $token" https://issues.redhat.com/rest/api/2/issue/createmeta/"$projectid"/issuetypes/"$issuetype"
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

dump_issue() {
  ansible-playbook -vv -e issue_key="$1" -e issue_file="${2:-"$1.json"}" jira_playbooks/dump_issue.yml
}

"$@"
