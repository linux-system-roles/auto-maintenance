#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

ME=$(basename $0)
HERE=${PWD}
WORKDIR="${HOME}/.cache/${ME%.*}"
STDOUT=$(mktemp /tmp/${ME%.*}-XXXXXX.stdout)
STDERR=$(mktemp /tmp/${ME%.*}-XXXXXX.stderr)

COLOR_RESET='\e[0m'
COLOR_RED='\e[31m'
COLOR_GREEN='\e[32m'
COLOR_BLUE='\e[34m'

GIT_USER_DEFAULT='systemroller'
GIT_EMAIL_DEFAULT='39708361+systemroller@users.noreply.github.com'
declare -A USER2EMAIL_MAP=( [${GIT_USER_DEFAULT}]="${GIT_EMAIL_DEFAULT}" )
FROM_BRANCH_DEFAULT='master'
SYNC_BRANCH_DEFAULT='lsr-template-sync'
CONTACTS_DEFAULT='i386x,pcahyna,richm'

GITHUB="https://github.com"
LSR_GROUP="linux-system-roles"
LSR_TEMPLATE="template"
LSR_TEMPLATE_NS="${LSR_GROUP}/${LSR_TEMPLATE}"
LSR_TEMPLATE_REPO="${GITHUB}/${LSR_TEMPLATE_NS}.git"

FILES=(
  '--copy-if-missing=.gitignore'
  '--copy-if-missing=.lgtm.yml'
  '--ensure-directory=.travis'
  '--copy-if-missing=.travis/config.sh'
  '--copy=.travis/custom_pylint.py'
  '--copy-if-missing=.travis/custom.sh'
  '--copy=.travis/preinstall'
  '--copy=.travis/runblack.sh'
  '--copy=.travis/runcoveralls.sh'
  '--copy=.travis/runflake8.sh'
  '--copy=.travis/runpylint.sh'
  '--copy=.travis/runpytest.sh'
  '--copy=.travis/runsyspycmd.sh'
  '--copy=.travis/runtox'
  '--copy=.travis/utils.sh'
  '--copy=.travis.yml'
  '--copy-if-missing=custom_requirements.txt'
  '--copy-if-missing=LICENSE'
  '--copy-recursively=molecule'
  '--copy-if-missing=molecule_extra_requirements.txt'
  '--copy-if-missing=pylint_extra_requirements.txt'
  '--copy=pylintrc'
  '--copy=tox.ini'
)
declare -A IGNORE_IF_MISSING_MAP

INDENT=""
INHELP=""

trap "rm -f ${STDOUT} ${STDERR}; cd ${HERE}" ABRT EXIT HUP INT QUIT

if type -p hub > /dev/null 2>&1 ; then
  if [[ -z "${USE_HUB:-}" ]]; then
    USE_HUB=true
  fi
elif [[ "${USE_HUB:-false}" = true ]]; then
  echo ERROR: there is no \"hub\" command line tool
  echo see https://github.com/github/hub
  echo e.g. on Fedora - dnf -y install hub
  exit 1
else
  USE_HUB=false
fi

##
# inform ARGS
#
# Print ARGS to standard output (in blue).
function inform() {
  echo -e "${COLOR_BLUE}$*${COLOR_RESET}"
}

##
# report_success ARGS
#
# Print ARGS to standard output (in green).
function report_success() {
  echo -e "${COLOR_GREEN}$*${COLOR_RESET}"
}

##
# report_failure ARGS
#
# Print ARGS to standard error output (in red).
function report_failure() {
  echo -e "${COLOR_RED}$*${COLOR_RESET}" >&2
}

##
# error $1 [$2]
#
#   $1 - error message
#   $2 - exit code (optional, default: 1)
#
# Print $1 (in red) to standard error output and exit with $2.
function error() {
  report_failure "$1"
  exit ${2:-1}
}

##
# runcmd $1 [$2 [$3]]
#
#   $1 - command with arguments
#   $2 - variable name to store $1's standard output
#   $3 - default value of $2 if $1 cannot be run (i.e. if dry run is active)
#
# Run $1. If DRY_RUN has non-empty value, only print "[dry run] $1" to standard
# output (in blue) and return exit code 0. If $2 is given, save standard output
# to it.
function runcmd() {
  local E=0

  if [[ "${DRY_RUN}" ]]; then
    inform "[dry run] $1"
    if [[ "${2:-}" ]]; then
      eval "$2='${3:-}'"
    fi
    return $E
  fi
  eval "$1" 1> ${STDOUT} 2> ${STDERR} || E=$?
  if [[ "${2:-}" ]]; then
    eval "$2=\"$(cat ${STDOUT})\""
  else
    cat ${STDOUT}
  fi
  if [[ $E -eq 0 ]]; then
    report_success "Command '$1' has completed successfully."
  else
    report_failure "Command '$1' has failed with exit code $E and error message:"
    cat ${STDERR} >&2
  fi
  return $E
}

##
# ensure_directory $1
#
#   $1 - path to directory
#
# Create $1 if it does not exist. If INHELP is non-empty, only print what will
# be done to standard output, indented with ${INDENT}.
function ensure_directory() {
  if [[ "${INHELP}" ]]; then
    echo "${INDENT}create $1 if it does not exist"
  else
    runcmd "(test -d $1 || mkdir -vp $1)"
  fi
}

##
# copy_file $1 $2 $3
#
#   $1 - path to source
#   $2 - path to destination
#   $3 - file name
#
# Copy $1/$3 to $2/$3. If INHELP is non-empty, only print what will be done to
# standard output, indented with ${INDENT}. Do not fail if $3 is on
# ignore-missing-files list.
function copy_file() {
  if [[ "${INHELP}" ]]; then
    echo "${INDENT}copy $1/$3 to $2/$3"
  else
    COMMAND="cp -vf $1/$3 $2/$3"
    if [[ ! -e "$1/$3" && "${IGNORE_IF_MISSING_MAP[$3]:-}" ]]; then
      inform "[\`$COMMAND\` ignored with note: '$1/$3' does not exist]"
    else
      runcmd "${COMMAND}"
    fi
  fi
}

##
# copy_missing $1 $2 $3
#
#   $1 - path to source
#   $2 - path to destination
#   $3 - file name
#
# Copy $1/$3 to $2/$3 if $2/$3 does not exist yet. If INHELP is non-empty, only
# print what will be done to standard output, indented with ${INDENT}. Do not
# fail if $3 is on ignore-missing-files list.
function copy_missing() {
  if [[ "${INHELP}" ]]; then
    echo "${INDENT}copy $1/$3 to $2/$3 if $2/$3 is missing"
  else
    COMMAND="cp -vf $1/$3 $2/$3"
    if [[ ! -e "$1/$3" && "${IGNORE_IF_MISSING_MAP[$3]:-}" ]]; then
      inform "[\`$COMMAND\` ignored with note: '$1/$3' does not exist]"
    else
      runcmd "(test -e $2/$3 || ${COMMAND})"
    fi
  fi
}

##
# copy_recursive $1 $2 $3
#
#   $1 - path to source
#   $2 - path to destination
#   $3 - directory name
#
# Recursively copy $1/$3 to $2. If INHELP is non-empty, only print what will
# be done to standard output, indented with ${INDENT}. Do not fail if $3 is on
# ignore-missing-files list.
function copy_recursive() {
  if [[ "${INHELP}" ]]; then
    echo "${INDENT}copy $1/$3 to $2 recursively"
  else
    COMMAND="cp -vrf $1/$3 $2"
    if [[ ! -d "$1/$3" && "${IGNORE_IF_MISSING_MAP[$3]:-}" ]]; then
      inform "[\`$COMMAND\` ignored with note: '$1/$3' does not exist]"
    else
      runcmd "${COMMAND}"
    fi
  fi
}

##
# copy_template_files $1 $2
#
#   $1 - source directory
#   $2 - destination directory
#
# Iterate over actions in FILES list and perform every action. Supported
# actions are:
#
#   --ensure-directory=DIR
#     * create $2/DIR if it does not exist
#   --copy=FILE
#     * copy $1/FILE to $2/FILE
#   --copy-if-missing=FILE
#     * copy $1/FILE to $2/FILE if $2/FILE does not exist yet
#   --copy-recursively=DIR
#     * recursively copy $1/DIR to $2
#
function copy_template_files() {
  for F in "${FILES[@]}"; do
    case "$F" in
      --ensure-directory=*)
        ensure_directory "$2/${F#*=}"
        ;;
      --copy=*)
        copy_file "$1" "$2" "${F#*=}"
        ;;
      --copy-if-missing=*)
        copy_missing "$1" "$2" "${F#*=}"
        ;;
      --copy-recursively=*)
        copy_recursive "$1" "$2" "${F#*=}"
        ;;
      *)
        error "${ME}: In ${FUNCNAME[0]}: Unknown option '$F'."
        ;;
    esac
  done
}

##
# usage
#
# Print script usage to standard output.
function usage() {
  cat <<EOF
Synchronize linux-system-roles repositories with the recent version of
template.

Usage: $ME [options]
where [options] are

  --branch, -b
      a name of branch from which to make the pull request
      (default: "${SYNC_BRANCH_DEFAULT}");

  --clean
      remove ${WORKDIR} and exit;

  --contacts, -c
      comma separated list of contacts to be appeared in pull request message
      under CC section; a contact is a GitHub user (default: "${CONTACTS_DEFAULT}");

  --dry-run, -d
      only write what will be done, do not touch anything;

  --from-branch
      a name of branch from which to take template files
      (default: "${FROM_BRANCH_DEFAULT}");

  --from-repo
      specify the template repo (default: "${LSR_TEMPLATE_REPO}");

  --help, -h
      print this help and exit;

  --ignore, -i
      add file or directory to ignore list; if such a file or directory will be
      missing then a file system operation will be skipped;

  --repolist, -r
      comma separeted list of repositories for which the synchronization is
      applicable;

  --token, -t
      GitHub token;

  --user, -u
      set git user name and email, example

          --user "John Doe <jdoe@github.com>"

      (default: "${GIT_USER_DEFAULT} <${GIT_EMAIL_DEFAULT}>").

The synchronization is done in the following way:

  1. cd to ${WORKDIR}
  2. clone or pull the latest template from ${LSR_TEMPLATE_REPO}
  3. for every \$REPO from --repolist:

       3.1 clone the \$REPO from ${GITHUB}/${LSR_GROUP}/\${REPO}.git
       3.2 cd to \$REPO
       3.3. configure git user.name and user.email for --user locally
       3.4. create a --branch and checkout to it
       3.5. then

$(INDENT="              " INHELP=yes copy_template_files ../template .)

       3.6. add files and push the --branch to upstream
       3.7. create a pull request

EXAMPLES

  Open a pull request against <${GITHUB}/${LSR_GROUP}/myrole> with recent files
  from <${LSR_TEMPLATE_REPO}> as a user John Doe:

    ./$ME -u "John Doe <jd123@company.com>" -r myrole -t fa1afe1caffebeef1ee7facadedecade7001f001

EOF
}

##
# process_options ARGS
#
# Process ARGS. ARGS reflects script options.
function process_options() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run | -d)
        DRY_RUN=yes
        ;;
      --user | -u)
        shift
        if [[ "$1" =~ ^(.*)[\ ]+\<(.*)\>$ ]]; then
          GIT_USER="${BASH_REMATCH[1]}"
          GIT_EMAIL="${BASH_REMATCH[2]}"
        else
          GIT_USER="$1"
        fi
        ;;
      --from-repo)
        shift
        FROM_REPO="$1"
        ;;
      --from-branch)
        shift
        FROM_BRANCH="$1"
        ;;
      --branch | -b)
        shift
        SYNC_BRANCH="$1"
        ;;
      --ignore | -i)
        shift
        IGNORE_IF_MISSING_MAP["$1"]="yes"
        ;;
      --contacts | -c)
        shift
        CONTACTS="$1"
        ;;
      --token | -t)
        shift
        GITHUB_TOKEN="$1"
        ;;
      --repolist | -r)
        shift
        REPOLIST="$1"
        ;;
      --help | -h)
        usage
        exit 0
        ;;
      --clean)
        rm -rfd ${WORKDIR}
        exit 0
        ;;
      *)
        error "${ME}: Unknown option '$1'. Type '$0 --help' for help."
        ;;
    esac
    shift
  done || :
}

process_options "$@"

DRY_RUN="${DRY_RUN:-}"
GIT_USER="${GIT_USER:-${GIT_USER_DEFAULT}}"
GIT_EMAIL="${GIT_EMAIL:-${USER2EMAIL_MAP[${GIT_USER}]:-}}"
FROM_REPO="${FROM_REPO:-${LSR_TEMPLATE_REPO}}"
FROM_BRANCH="${FROM_BRANCH:-${FROM_BRANCH_DEFAULT}}"
SYNC_BRANCH="${SYNC_BRANCH:-${SYNC_BRANCH_DEFAULT}}"
CONTACTS="${CONTACTS:-${CONTACTS_DEFAULT}}"
export GITHUB_TOKEN="${GITHUB_TOKEN:-}"
REPOLIST="${REPOLIST:-}"
REPOLIST="${REPOLIST//,/ }"
if [[ $USE_HUB = true ]]; then
  case $FROM_REPO in
      http*://github.com/*) FROM_REPO_HUB=${FROM_REPO#http*://github.com/} ;;
      *github.com:*) FROM_REPO_HUB=${FROM_REPO#*github.com:} ;;
      *) info "${ME}: FROM_REPO $FROM_REPO not a recognized github repo - cannot use hub";
         USE_HUB=false ;;
  esac
  if [[ "${FROM_REPO_HUB:-}" ]]; then
    FROM_REPO=${FROM_REPO_HUB%.git}
  fi
fi

##
# check_required_options
#
# Check if required options are provided.
function check_required_options() {
  if [[ -z "${REPOLIST}" ]]; then
    error "${ME}: No repos (REPOLIST) were specified. Terminating."
  fi
  if [[ $USE_HUB = true ]]; then
    # if using hub, git options not required
    return 0
  fi
  if [[ -z "${GITHUB_TOKEN}" ]]; then
    error "${ME}: GitHub token (GITHUB_TOKEN) not set. Terminating."
  fi
  if [[ -z "${GIT_USER}" ]]; then
    error "${ME}: Git user name is missing. Terminating."
  fi
  if [[ -z "${GIT_EMAIL}" ]]; then
    error "${ME}: Git user's email is missing. Terminating."
  fi
}

##
# put_revision $1
#
#   $1 - revision id
#
# Put a link to the revision into the payload.
function put_revision() {
  echo -n '\nRevision: [`'"$1"'`]'"(${GITHUB}/${LSR_TEMPLATE_NS}/tree/$1)"
}

##
# expand_contacts
#
# If CONTACTS has a form "C1 C2 C3 ... Cn", return "\nCC: @C1, @C2, ..., @Cn.".
function expand_contacts() {
  if [[ "${CONTACTS}" ]]; then
    echo -n '\nCC:' "@${CONTACTS//,/, @}"
  fi
}

##
# get_repo
#
#    $1 - URL of repo to clone e.g. https://github.com/org/reponame.git
#         if using hub, then it can be just org/reponame
#    $2 - branch to checkout
#    $3 - new branch to create from $2 using checkout -b $3 (optional)
#    $4 - git user name (not used with hub)
#    $5 - git email (not used with hub)
#
# clone the given repo, checked out to the given
# branch, set it up for git commit/push
function get_repo() {
  local repo=$1
  local branch=$2
  local newbranch=${3:-}
  local gituser=${4:-}
  local gitemail=${5:-}
  local repodir=$( basename $repo )
  repodir=${repodir%.git}
    
  if [[ -d "$repodir" ]]; then
    runcmd "pushd '$repodir'"
    runcmd "git fetch"
    runcmd "git checkout '$branch'"
    runcmd "git pull"
    runcmd "popd"
  elif [[ $USE_HUB = true ]]; then
    runcmd "hub clone -b '$branch' '$repo' '$repodir'"
  else
    runcmd "git clone -b '$branch' '$repo' '$repodir'"
    if [[ -n "$gituser" && -n "$gitemail" ]]; then
      runcmd "pushd $repodir"
      runcmd "git config --local user.name '$gituser'"
      runcmd "git config --local user.email '$gitemail'"
      runcmd "popd"
    fi
  fi
  if [[ $USE_HUB = true ]]; then
    runcmd "pushd '$repodir'"
    runcmd "hub fork"
    runcmd "popd"
  fi
  if [[ -n "$newbranch" ]]; then
    runcmd "pushd '$repodir'"
    runcmd "git checkout -b '$newbranch'"
    runcmd "popd"
  fi
}

##
# get_revision_id $1
#
#   $1 - variable to store the result
#
# Store revision identifier as SHA-1 of common template's repository HEAD to $1.
function get_revision_id() {
  runcmd "pushd ${LSR_TEMPLATE}"
  runcmd "git rev-parse HEAD" "$1" "0000000000000000000000000000000000000000"
  runcmd "popd"
}

##
# submit_pr $1 $2 $3 $4
#
#   $1 - title of PR
#   $2 - base branch to submit PR against, usually master
#   $3 - head or commit of local change, usually HEAD
#   $4 - body of PR message
#
# Assumes you are inside the directory of a local clone of
# an LSR repo.  Assumes the LSR repo is the git remote "origin"
# and you are pus
function submit_pr() {
  local title="$1"
  local base="$2"
  local head="$3"
  local body="$4"
  local PAYLOAD
  if [[ $USE_HUB = true ]]; then
    local fixbody=$( printf "$body" )
    PAYLOAD=$(cat <<-EOFa
		$title
		
		$fixbody
		EOFa
    )
    runcmd "hub pull-request -m '$PAYLOAD' -b $base -h $head"
  else
    PAYLOAD=$(cat <<-EOFb
		{"title":"$title",
		"base":"$base",
		"head":"$head",
		"body":"$body"}
		EOFb
    )
    runcmd "curl -u '${GIT_USER}:${GITHUB_TOKEN}' -X POST -d '${PAYLOAD}' 'https://api.github.com/repos/${LSR_GROUP}/${REPO}/pulls'"
  fi
}

##
# github_push $1 $2 $3 $4
#
#   $1 - title of PR
#   $2 - base branch to submit PR against, usually master
#   $3 - head or commit of local change, usually HEAD
#   $4 - body of PR message
#
# Assumes you are inside the directory of a local clone of
# an LSR repo.  Pushes
function github_push() {
  local reponame=$1
  if [[ $USE_HUB = true ]]; then
    # use the first non-origin upstream to push to
    local remote
    local item
    for item in $( git remote ) ; do
      if [ $item != origin ] ; then
        remote="$item"
        break
      fi
    done
    if [[ -z "${remote:-}" ]] ; then
      error Cannot push to origin - set up remote for $( pwd ) - $( git remote -v )
    fi
    runcmd "git push '$remote' '${SYNC_BRANCH}'"
  else
    runcmd "git push 'https://${GITHUB_TOKEN}:@github.com/${LSR_GROUP}/$reponame' -u '${SYNC_BRANCH}'"
  fi
}

##
# do_sync
#
# Synchronize common template files across system roles repositories.
function do_sync() {
  check_required_options

  ensure_directory ${WORKDIR}

  runcmd "pushd ${WORKDIR}"

  get_repo $FROM_REPO $FROM_BRANCH
  get_revision_id GIT_HEAD

  for REPO in ${REPOLIST}; do
    inform "Synchronizing ${REPO} with ../${LSR_TEMPLATE}."
    runcmd "[[ -d \"${REPO}\" ]] && rm -rfd ${REPO} || :"
    if [[ $USE_HUB = true ]]; then
      url=${LSR_GROUP}/${REPO}
    else
      url=${GITHUB}/${LSR_GROUP}/${REPO}.git
    fi
    get_repo $url master ${SYNC_BRANCH} ${GIT_USER} ${GIT_EMAIL}
    runcmd "pushd ${REPO}"
    copy_template_files ../${LSR_TEMPLATE} .
    if [[ "${DRY_RUN}" || "$(git status --porcelain)" ]]; then
      runcmd "git commit -a -m 'Synchronize files from ${FROM_REPO}'"
      if github_push ${REPO}; then
        submit_pr "Synchronize files from ${LSR_TEMPLATE_NS}" master "${SYNC_BRANCH}" \
                  "This PR propagates files from [${LSR_TEMPLATE_NS}](${GITHUB}/${LSR_TEMPLATE_NS}) which should be in sync across [${LSR_GROUP}](${GITHUB}/${LSR_GROUP}) repos. In case of changing affected files via pushing to this PR, please do not forget also to push the changes to [${LSR_TEMPLATE_NS}](${GITHUB}/${LSR_TEMPLATE_NS}) repo.\n$(put_revision ${GIT_HEAD})\n$(expand_contacts)"
      fi
    fi
    runcmd "popd"
  done

  runcmd "popd"

  report_success "All repositories was synchronized with the template successfully."
}

do_sync
