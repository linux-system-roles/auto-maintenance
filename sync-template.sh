#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

ME=$(basename "$0")
HERE=${PWD}
WORKDIR="${WORKDIR:-${HOME}/.cache/${ME%.*}}"
STDOUT=$(mktemp "/tmp/${ME%.*}-XXXXXX.stdout")
STDERR=$(mktemp "/tmp/${ME%.*}-XXXXXX.stderr")

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
LSR_FORK_PREFIX=${LSR_FORK_PREFIX:-"${LSR_GROUP}-"}
# this is the name of the git remote to use for the user's
# fork of the lsr repo
LSR_FORK_REMOTE=${LSR_FORK_REMOTE:-"lsr-user-remote"}

FILES=(
  '--copy=.ansible-lint'
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
  '--copy-recursively=molecule'
  '--copy-if-missing=molecule_extra_requirements.txt'
  '--copy-if-missing=pylint_extra_requirements.txt'
  '--copy-if-missing=pytest_extra_requirements.txt'
  '--copy-if-missing=ansible_pytest_extra_requirements.txt'
  '--copy=pylintrc'
  '--copy=tox.ini'
  '--copy-if-missing=.yamllint.yml'
  '--copy=.yamllint_defaults.yml'
  '--copy=tests/setup_module_utils.sh'
  '--remove-file=molecule/default/yamllint.yml'
  '--remove-file=pytest26_extra_requirements.txt'
  '--remove-file=ansible26_requirements.txt'
)
declare -A IGNORE_IF_MISSING_MAP

INDENT=""
INHELP=""

# https://github.com/koalaman/shellcheck/wiki/SC2064
# shellcheck disable=SC2064
trap "rm -f ${STDOUT} ${STDERR}; cd ${HERE}" ABRT EXIT HUP INT QUIT

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
  exit "${2:-1}"
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
  eval "$1" 1> "${STDOUT}" 2> "${STDERR}" || E=$?
  if [[ "${2:-}" ]]; then
    eval "$2=\"$(cat "${STDOUT}")\""
  else
    cat "${STDOUT}"
  fi
  if [[ $E -eq 0 ]]; then
    report_success "Command '$1' has completed successfully."
  else
    report_failure "Command '$1' has failed with exit code $E and error message:"
    cat "${STDERR}" >&2
  fi
  return $E
}

##
# ensure_directory $1 [$2]
#
#   $1 - path to directory
#   $2 - optional - directory under $1 to create
#
# If both $1 and $2 are given, then $1 is the repo directory which should
# should already exist, and $2 is the sub-directory under it to create if
# it does not exist. If INHELP is non-empty, only print what will
# be done to standard output, indented with ${INDENT}.
function ensure_directory() {
  local newdir=$1
  if [[ -n "${2:-}" ]]; then
    newdir="$newdir/$2"
  fi
  if [[ "${INHELP}" ]]; then
    echo "${INDENT}create $newdir if it does not exist"
  else
    runcmd "(test -d $newdir || mkdir -vp $newdir)"
    if [[ -n "${2:-}" ]]; then
      runcmd "git add '$2'"
    fi
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
      runcmd "git add '$3'"
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
      if [[ "${FORCE_COPY:-false}" == true && -e $2/$3 ]]; then
        FORCE_COPY_FILES+=("$3")
        runcmd "${COMMAND}"
      else
        runcmd "(test -e $2/$3 || ${COMMAND})"
      fi
      runcmd "git add '$3'"
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
    ensure_directory "$2" "$3"
    local src
    local dest
    # https://github.com/koalaman/shellcheck/wiki/SC2044
    # shellcheck disable=SC2044
    for src in $(find "$1/$3"); do
      dest=${src#$1/}
      if [[ -d $src ]]; then
        ensure_directory "$2" "$dest"
      else
        copy_file "$1" "$2" "$dest"
      fi
    done
  fi
}

##
# remove_file $1
#
#   $1 - file to remove
#
# Removes the given file from the repo and from git (git rm)
function remove_file() {
  if [[ "${INHELP}" ]]; then
    echo "${INDENT}remove_file $1"
  else
    runcmd "git rm -f --ignore-unmatch $1"
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
        ensure_directory "$2" "${F#*=}"
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
      --remove-file=*)
        remove_file "${F#*=}"
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
      comma separated list of repositories for which the synchronization is
      applicable;

  --token, -t
      GitHub token;

  --user, -u
      set git user name and email, example

          --user "John Doe <jdoe@github.com>"

      (default: "${GIT_USER_DEFAULT} <${GIT_EMAIL_DEFAULT}>").

  --local, -l
      work locally only - assumes \$WORKDIR is your local working
      copy of linux-system-roles e.g. $HOME/linux-system-roles -
      assumes you just want to copy files locally from
      $HOME/linux-system-roles/template to
      $HOME/linux-system-roles/REPO in order to test "tox" and
      other commands

  --preserve, -p
      preserve the repos in \$WORKDIR - otherwise, assumes the
      repos in \$WORKDIR are temporary and will remove them -
      if you use \$WORKDIR as your $HOME/workingdir,
      USE --preserve to avoid wiping out your work.  Using
      --workdir will automatically set PRESERVE=true.

  --use-hub
      Use the "hub" command line tool to interact with github.
      This also means you will be using your personal github
      account instead of the $GIT_USER_DEFAULT service account.
      This also means you will have a fork of the repos in your
      personal github, prefixed with the string "$LSR_FORK_PREFIX",
      and the pull requests will be created from your personal forks;

  --workdir
      Name of your local working directory where the template and
      repo directories will be cloned, instead of a temporary
      directory.  Use this when you have a local clone of the repos
      e.g. $HOME/linux-system-roles and you want to interactively
      work on those changes locally.  This will set PRESERVE=true
      so you will not lose any local work.

The synchronization is done in the following way:

  1. cd to ${WORKDIR}
  2. clone or pull the latest template from ${LSR_TEMPLATE_REPO}
  3. for every \$REPO from --repolist:

       3.1 clone the \$REPO from ${GITHUB}/${LSR_GROUP}/\${REPO}.git
       3.2 cd to \$REPO
       3.3. if not --use-hub, configure git user.name and user.email for --user locally
       3.4. create a --branch and checkout to it
       3.5. then

$(INDENT="              " INHELP=yes copy_template_files ../template .)

       3.6. add files and push the --branch to upstream
       3.7. create a pull request

EXAMPLES

  Open a pull request against <${GITHUB}/${LSR_GROUP}/myrole> with recent files
  from <${LSR_TEMPLATE_REPO}> as a user John Doe:

    ./$ME -u "John Doe <jd123@company.com>" -r myrole -t fa1afe1caffebeef1ee7facadedecade7001f001

  Using "hub", create a fork of the repo in your personal github, push the changes to that,
  open a pull request against <${GITHUB}/${LSR_GROUP}/myrole> with recent files
  from <${LSR_TEMPLATE_REPO}> as your github user ID:

    ./$ME --use-hub --workdir $HOME/linux-system-roles -r myrole

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
      --local | -l)
        LOCAL=true
        ;;
      --preserve | -p)
        PRESERVE=true
        ;;
      --force-copy)
        FORCE_COPY=true
        ;;
      --use-hub)
        USE_HUB=true
        ;;
      --workdir)
        shift
        WORKDIR="$1"
        PRESERVE=true
        ;;
      --help | -h)
        usage
        exit 0
        ;;
      --clean)
        if [[ -z "${PRESERVE:-}" ]]; then
          rm -rfd "${WORKDIR}"
          exit 0
        fi
        ;;
      *)
        error "${ME}: Unknown option '$1'. Type '$0 --help' for help."
        ;;
    esac
    shift
  done || :
}

process_options "$@"

if [[ "${USE_HUB:-false}" == "true" ]]; then
  # commands needed in order to use hub (USE_HUB=true)
  hub_required_cmds="hub jq"
  hub_missing_cmds=""

  for cmd in $hub_required_cmds; do
    if ! type -p "$cmd" > /dev/null 2>&1; then
      hub_missing_cmds="$hub_missing_cmds $cmd"
    fi
  done

  if [[ -n "$hub_missing_cmds" ]]; then
    error "Missing commands required to use hub: $hub_missing_cmds - e.g. on Fedora - sudo dnf -y install $hub_missing_cmds"
  fi
else
  USE_HUB=false
fi
# at this point, USE_HUB is set to true or false and is safe to use without quotes/braces

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
if [[ $USE_HUB == true ]]; then
  case $FROM_REPO in
      http://github.com/*) error "http URLs are not supported: $FROM_REPO" ;;
      https://github.com/*) FROM_REPO_HUB=${FROM_REPO#https://github.com/} ;;
      *github.com:*) FROM_REPO_HUB=${FROM_REPO#*github.com:} ;;
      *) info "${ME}: FROM_REPO $FROM_REPO not a recognized github repo - cannot use hub";
         USE_HUB=false ;;
  esac
  if [[ "${FROM_REPO_HUB:-}" ]]; then
    FROM_REPO=${FROM_REPO_HUB%.git}
  fi
fi
declare -a FORCE_COPY_FILES=()

function get_hub_user() {
  awk '/user:/ {print $NF}' "$HOME/.config/hub"
}

if [[ $USE_HUB == true ]]; then
  GIT_USER=$(get_hub_user)
fi

##
# check_required_options
#
# Check if required options are provided.
function check_required_options() {
  if [[ -z "${REPOLIST}" ]]; then
    error "${ME}: No repos (REPOLIST) were specified. Terminating."
  fi
  if [[ -n "${LOCAL:-}" ]]; then
    return
  fi
  if [[ $USE_HUB == true ]]; then
    # if using hub, git options not required
    return
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
  # looks like a false positive
  # https://github.com/koalaman/shellcheck/wiki/SC2016
  # shellcheck disable=SC2016
  printf '\nRevision: [`%s`](%s)' "$1" "${GITHUB}/${LSR_TEMPLATE_NS}/tree/$1"
}

##
# expand_contacts
#
# If CONTACTS has a form "C1 C2 C3 ... Cn", return "\nCC: @C1, @C2, ..., @Cn.".
function expand_contacts() {
  if [[ "${CONTACTS}" ]]; then
    printf '\nCC: @%s' "${CONTACTS//,/, @}"
  fi
}

##
# fork_repo
#
#    $1 - name of repo
#
# Forks the current repo under the current user.  Names the forked repo to
# have a "linux-system-roles-" prefix if the fork was created by this command.
# If the user has already created a fork under a different name, just use that
# name for the repo.  Assumes the command is being run from a local clone of a
# github.com/linux-system-roles/REPO Creates a git remote named
# $LSR_FORK_REMOTE for the forked repo.  If there is already a git remote
# pointing to the forked repo, it will be untouched. For example, if in
# $HOME/linux-system-roles/timesync, calling `fork_repo` will create
# https://github.com/$GIT_USER/linux-system-roles-timesync, and the git remote
# $LSR_FORK_REMOTE will point to
# git@github.com:$GIT_USER/linux-system-roles-timesync
# If this seems a bit excessive, note that
# - it is much more difficult to use the api to determine if the user has
#   already forked a repo under a different repo name
# - the fork api gives no indication that a new fork was created - it will
#   always return success even if there is already a fork
# - the fork api does not have a way to specify the name of the forked repo
#   this is currently under development - at which point, all of the timestamp
#   and rename stuff can be replaced with
#   hub api -X POST /repos/$LSR_GROUP/$reponame/forks -F name=$newname
# - the name of the newly forked repo might not be $reponame - consider the case
#   where the user already has e.g. user/projectA which is completely unrelated
#   to linux-system-roles/projectA, and attempts to fork linux-system-roles/projectA
#   the github API will auto-generate a unique name e.g. user/projectA-1 - this is
#   why we have to get the forkname returned by the api
function fork_repo() {
  local reponame="$1"
  local newname="${LSR_FORK_PREFIX}$reponame"
  HUB_VERBOSE=true runcmd "hub api -X POST /repos/$LSR_GROUP/$reponame/forks" > /dev/null 2>&1
  local forkname
  forkname=$(grep -m 1 '^{' "$STDERR" | jq -r .name)
  local fullname
  fullname=$(grep -m 1 '^{' "$STDERR" | jq -r .full_name)
  if [[ "$forkname" == "null" || "$fullname" == "null" ]]; then
    # using the systemroller user - do not fork
    return 0
  fi
  # NOTE: There is apparently a bug in the jq fromdateiso8601/fromdate filter - it will report
  # the date 1 hour in the future - I have found experimentally that the `date` command
  # is able to accurately parse the timestamp string
  local create_ts
  create_ts=$(grep -m 1 '^{' "$STDERR" | jq -r '.created_at')
  local create_ts_sec
  create_ts_sec=$(date +%s --date="$create_ts")
  local diff_sec
  diff_sec=$(($(date +%s) - "$create_ts_sec")) || :
  # abs
  case "$diff_sec" in
  -*) diff_sec=$((0 - "$diff_sec")) || : ;;
  esac
  # assume if repo was created less than 30 seconds ago, we created it above with
  # the fork - if so, rename it
  if [ "$diff_sec" -lt 30 ] ; then
    # rename the newly created repo with the LSR prefix
    runcmd "hub api -X PATCH /repos/$GIT_USER/$forkname -F 'name=$newname'" > /dev/null
    fullname="$GIT_USER/$newname"
  fi
  # make sure there is a git remote for the new repo
  if git remote | grep -q -F -x "$LSR_FORK_REMOTE" ; then
    runcmd "git remote rm '$LSR_FORK_REMOTE'"
  fi
  runcmd "git remote add '$LSR_FORK_REMOTE' git@github.com:$fullname"
  runcmd "git fetch '$LSR_FORK_REMOTE'"
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
  local repodir
  repodir=$(basename "$repo" .git)

  if [[ -d "$repodir" ]]; then
    runcmd "pushd '$repodir'"
    runcmd "git fetch"
    if [[ -z "$newbranch" ]]; then
      runcmd "git checkout '$branch'"
    fi
    if [[ -z "${LOCAL:-}" ]] && git rev-parse '@{u}' > /dev/null 2>&1 ; then
      runcmd "git pull"
    fi
    runcmd "popd"
  elif [[ $USE_HUB == true ]]; then
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
  if [[ $USE_HUB == true && -z "${LOCAL:-}" && -n "${newbranch:-}" ]]; then
    # make sure we have a fork of the repo, and that we have
    # a git remote to push to, that we have fetched from the remote
    runcmd "pushd '$repodir'"
    fork_repo "$repodir"
    runcmd "popd"
  fi
  if [[ -n "$newbranch" ]]; then
    runcmd "pushd '$repodir'"
    if runcmd "git checkout '$newbranch'"; then
      if [[ -z "${LOCAL:-}" ]] && git rev-parse '@{u}' > /dev/null 2>&1 ; then
        runcmd "git pull"
      fi
    else
      runcmd "git checkout -b '$newbranch'"
    fi
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
# pr_exists $1
#
#   $1 - branch that was used for the PR
#
# Assumes $GIT_USER is set correctly.  Assumes this function is being
# run from the repo directory.
#
# Returns 0 if there is already a PR for this user + branch, 1 otherwise.
function pr_exists() {
  if [[ $USE_HUB == true ]]; then
    #runcmd "hub pr list -h $GIT_USER:$1 -f %I" pr_exists_prnum
    # seems to be a bug in hub pr list, which also affects the github api
    # not sure how I got into this situation, but I have a case where
    # hub pr list -h richm:my-branch does not return my PR, even though
    # if I do hub pr list -f '%H%n' it shows head richm:my-branch
    # so for now, just use the output piped through a filter :-(
    runcmd "hub pr list -f '%H%n' | grep -q -F -x '$GIT_USER:$1'" IGNOREME > /dev/null 2>&1
  else
    return 1
  fi
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
# an LSR repo.  Assumes the LSR repo is the git remote "origin".
function submit_pr() {
  local title="$1"
  local base="$2"
  local head="$3"
  local body="$4"
  local PAYLOAD
  if [[ $USE_HUB == true ]]; then
    # if there is already a PR for this branch, then the previous git push
    # will have updated that PR
    if pr_exists "$head" ; then
      inform There is already a PR for "$head" - existing PR will be updated
      return
    fi
    local fixbody
    fixbody=$( printf '%s' "$body" )
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
# github_push $1 $2
#
#   $1 - push to this remote branch
#   $2 - reponame - not needed for hub
#
# Assumes you are inside the directory of a local clone of
# an LSR repo.
function github_push() {
  local branch="$1"
  local reponame=$2
  if [[ $USE_HUB == true ]]; then
    # use the first non-origin upstream to push to
    local remote
    local item
    for item in $( git remote ) ; do
      if [[ "$item" == "$LSR_FORK_REMOTE" ]] ; then
        remote="$item"
        break
      elif [[ "$item" == "$GIT_USER" ]] ; then
        remote="$item"
        break
      fi
    done
    if [[ -z "${remote:-}" ]] ; then
      error "Cannot push to origin - no git remote for $GIT_USER - set up remote for $( pwd ) - $( git remote -v )"
    fi
    runcmd "git push '$remote' '${branch}'"
  else
    runcmd "git push 'https://${GITHUB_TOKEN}:@github.com/${LSR_GROUP}/$reponame' -u '${branch}'"
  fi
}

##
# do_sync
#
# Synchronize common template files across system roles repositories.
function do_sync() {
  check_required_options

  ensure_directory "${WORKDIR}"

  runcmd "pushd ${WORKDIR}"

  get_repo "$FROM_REPO" "$FROM_BRANCH"
  get_revision_id GIT_HEAD

  for REPO in ${REPOLIST}; do
    inform "Synchronizing ${REPO} with ../${LSR_TEMPLATE}."
    if [[ $USE_HUB == true ]]; then
      url="${LSR_GROUP}/${REPO}"
    else
      url="${GITHUB}/${LSR_GROUP}/${REPO}.git"
    fi
    if [[ -z "${PRESERVE:-}" ]]; then
      runcmd "[[ -d \"${REPO}\" ]] && rm -rfd ${REPO} || :"
    fi
    get_repo "$url" master "${SYNC_BRANCH}" "${GIT_USER}" "${GIT_EMAIL}"
    runcmd "pushd ${REPO}"
    copy_template_files "../${LSR_TEMPLATE}" .
    if [[ -n "${LOCAL:-}" ]]; then
      continue
    fi
    if [[ "${DRY_RUN}" || "$(git status -uno --porcelain)" ]]; then
      if [[ "${FORCE_COPY:-false}" == true && "${#FORCE_COPY_FILES[*]}" -gt 0 ]]; then
        report_failure "In $(pwd)"
        report_failure "Not committing - force-copy used and some files were force copied"
        error "you will need to manually merge, add, and commit the following files: ${FORCE_COPY_FILES[*]}"
      fi
      runcmd "git commit -a -m 'Synchronize files from ${FROM_REPO}'"
      if github_push "${SYNC_BRANCH}" "${REPO}"; then
        # https://github.com/koalaman/shellcheck/wiki/SC2086
        # shellcheck disable=SC2086
        submit_pr "Synchronize files from ${LSR_TEMPLATE_NS}" master "${SYNC_BRANCH}" \
                  "This PR propagates files from [${LSR_TEMPLATE_NS}](${GITHUB}/${LSR_TEMPLATE_NS}) which should be in sync across [${LSR_GROUP}](${GITHUB}/${LSR_GROUP}) repos. In case of changing affected files via pushing to this PR, please do not forget also to push the changes to [${LSR_TEMPLATE_NS}](${GITHUB}/${LSR_TEMPLATE_NS}) repo.\n$(put_revision ${GIT_HEAD})\n$(expand_contacts)"
      fi
    elif [[ "$(git status --porcelain)" ]]; then
      inform There are some untracked files in "${FROM_REPO}"
      git status --porcelain
    fi
    runcmd "popd"
  done

  runcmd "popd"

  report_success "All repositories were synchronized with the template successfully."
}

do_sync

# Local Variables:
# mode: Shell-script
# sh-basic-offset: 2
# End:
