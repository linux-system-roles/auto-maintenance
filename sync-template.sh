#!/bin/bash

set -euo pipefail

ME=$(basename $0)
HERE=${PWD}
WORKDIR="${HOME}/.cache/${ME%.*}"
STDERR=/tmp/${ME%.*}.stderr

COLOR_RESET='\e[0m'
COLOR_RED='\e[31m'
COLOR_GREEN='\e[32m'
COLOR_BLUE='\e[34m'
COLOR_YELLOW='\e[1;33m'

GIT_USER_DEFAULT='systemroller'
GIT_MAILSERVER_DEFAULT='localhost.localdomain'
SYNC_BRANCH_DEFAULT='lsr-template-sync'
CONTACTS_DEFAULT='i386x,pcahyna'
REPOLIST_DEFAULT='firewall,kdump,network,postfix,selinux,storage,timesync,tuned'

GITHUB="https://github.com"
LSR_GROUP="linux-system-roles"
LSR_TEMPLATE="template"
LSR_TEMPLATE_REPO="${GITHUB}/${LSR_GROUP}/${LSR_TEMPLATE}.git"

FILES=(
  '--copy-if-missing=.gitignore'
  '--ensure-directory=.travis'
  '--copy-if-missing=.travis/config.sh'
  '--copy-if-missing=.travis/custom.sh'
  '--copy=.travis/preinstall'
  '--copy=.travis/runcoveralls.sh'
  '--copy=.travis/runpytest.sh'
  '--copy=.travis/runsyspycmd.sh'
  '--copy=.travis/runtox'
  '--copy=.travis/utils.sh'
  '--copy=.travis.yml'
  '--copy-if-missing=custom_requirements.txt'
  '--copy=LICENSE'
  '--copy-recursively=molecule'
  '--copy-if-missing=molecule_extra_requirements.txt'
  '--copy=pylintrc'
  '--copy=run_pylint.py'
  '--copy=tox.ini'
)

INDENT=""

trap "rm -f ${STDERR}; cd ${HERE}" EXIT

function error() {
  failure "$1"
  exit ${2:-1}
}

function failure() {
  echo -e "${COLOR_RED}$*${COLOR_RESET}" >&2
}

function alert() {
  echo -e "${COLOR_YELLOW}$*${COLOR_RESET}" >&2
}

function inform() {
  echo -e "${COLOR_BLUE}$*${COLOR_RESET}"
}

function success() {
  echo -e "${COLOR_GREEN}$*${COLOR_RESET}"
}

function runcmd() {
  local E=0

  if [[ "${DRY_RUN}" ]]; then
    inform "[dry run] $1"
    return $E
  fi
  $1 2> ${STDERR} || E=$?
  if [[ $E -eq 0 ]]; then
    success "Command '$1' has completed successfully."
  else
    failure "Command '$1' has failed with exit code $E and error message:"
    cat ${STDERR} >&2
  fi
  return $E
}

function ensure_directory() {
  if [[ "${DRY_RUN}" ]]; then
    echo "${INDENT}create $1 if it does not exist"
  else
    runcmd "(test -d $1 || mkdir -vp $1)"
  fi
}

function copy_file() {
  if [[ "${DRY_RUN}" ]]; then
    echo "${INDENT}copy $1 to $2"
  else
    runcmd "cp -vf $1 $2"
  fi
}

function copy_missing() {
  if [[ "${DRY_RUN}" ]]; then
    echo "${INDENT}copy $1 to $2 if $2 is missing"
  else
    runcmd "(test -e $2 || cp -vf $1 $2)"
  fi
}

function copy_recursive() {
  if [[ "${DRY_RUN}" ]]; then
    echo "${INDENT}copy $1 to $2 recursively"
  else
    runcmd "cp -vrf $1 $2"
  fi
}

function copy_template_files() {
  for F in "${FILES[@]}"; do
    case "$F" in
      --ensure-directory=*)
        ensure_directory "$2/${F:19}"
        ;;
      --copy=*)
        copy_file "$1/${F:7}" "$2/${F:7}"
        ;;
      --copy-if-missing=*)
        copy_missing "$1/${F:18}" "$2/${F:18}"
        ;;
      --copy-recursively=*)
        copy_recursive "$1/${F:19}" "$2/${F:19}"
        ;;
      *)
        error "${ME}: In ${FUNCNAME[0]}: Unknown option '$F'."
        ;;
    esac
  done
}

function usage() {
  cat <<EOF
Synchronize linux-system-roles repositories with the recent version of
template.

Usage: $ME [options]
where [options] are

  --branch, -b
      set the name of a branch with content to be synchronized from which the
      pull request is made of (default: "${SYNC_BRANCH_DEFAULT}");

  --clean
      remove ${WORKDIR} and exit;

  --contacts, -c
      comma separated list of contacts to be appeared in pull request message
      under CC section; a contact is a GitHub user (default: "${CONTACTS_DEFAULT}");

  --dry-run, -d
      only write what will be done, do not touch anything;

  --help, -h
      print this help and exit;

  --repolist, -r
      comma separeted list of repositories for which the synchronization is
      applicable (default: "${REPOLIST_DEFAULT}");

  --token, -t
      GitHub token;

  --user, -u
      set git user name and email, example

          --user "John Doe <jdoe@github.com>"

      if email part is missing, it is crafted from user name (spaces are
      replaced with dots, letters are lowercased, and mail part becomes
      "${GIT_MAILSERVER_DEFAULT}"); if name is missing, "${GIT_USER_DEFAULT}"
      is used.

The synchronization is done in the following way:

  1. cd to ${WORKDIR}
  2. clone the template from ${LSR_TEMPLATE_REPO}
  3. for every \$REPO from --repolist:

       3.1 clone the \$REPO from ${GITHUB}/${LSR_GROUP}/\${REPO}.git
       3.2 cd to \$REPO
       3.3. configure git user.name and user.email for --user locally
       3.4. create a --branch and checkout to it
       3.5. then

$(INDENT="              " DRY_RUN=yes copy_template_files ../template .)

       3.6. add files and push the --branch to upstream
       3.7. create a pull request

EOF
}

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
          GIT_MAIL="${BASH_REMATCH[2]}"
        else
          GIT_USER="$1"
        fi
        ;;
      --branch | -b)
        shift
        SYNC_BRANCH="$1"
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

function gen_user_email() {
  local X="${1// /.}"

  echo -n "${X,,}@${GIT_MAILSERVER_DEFAULT}"
}

function expand_contacts() {
  if [[ "${CONTACTS}" ]]; then
    echo -n '\nCC:' "@${CONTACTS//,/, @}."
  fi
}

process_options "$@"

DRY_RUN="${DRY_RUN:-}"
GIT_USER="${GIT_USER:-${GIT_USER_DEFAULT}}"
GIT_MAIL="${GIT_MAIL:-$(gen_user_email "${GIT_USER}")}"
SYNC_BRANCH="${SYNC_BRANCH:-${SYNC_BRANCH_DEFAULT}}"
CONTACTS="${CONTACTS:-${CONTACTS_DEFAULT}}"
export GITHUB_TOKEN="${GITHUB_TOKEN:-}"
REPOLIST="${REPOLIST:-${REPOLIST_DEFAULT}}"
REPOLIST="${REPOLIST//,/ }"
PAYLOAD=$(cat <<EOF
{"title":"Synchronize files from ${LSR_GROUP}/${LSR_TEMPLATE}",
  "base":"master",
  "head":"${SYNC_BRANCH}",
  "body":"One or more files which should be in sync across ${LSR_GROUP} repos were changed either here or in [${LSR_GROUP}/${LSR_TEMPLATE}](https://github.com/${LSR_GROUP}/${LSR_TEMPLATE}).\nThis PR propagates files from [${LSR_GROUP}/${LSR_TEMPLATE}](https://github.com/${LSR_GROUP}/${LSR_TEMPLATE}). If something was changed here, please first modify ${LSR_GROUP} repository.\n$(expand_contacts)"}
EOF
)

if [[ -z "${GITHUB_TOKEN}" ]]; then
  error "${ME}: GitHub token (GITHUB_TOKEN) not set. Terminating."
fi

ensure_directory ${WORKDIR}

runcmd "pushd ${WORKDIR}"

runcmd "git clone '${LSR_TEMPLATE_REPO}' '${LSR_TEMPLATE}'"

for REPO in ${REPOLIST}; do
  inform "Synchronizing ${REPO} wiht ../${LSR_TEMPLATE}."
  runcmd "git clone '${GITHUB}/${LSR_GROUP}/${REPO}.git' '${REPO}'"
  runcmd "pushd ${REPO}"
  runcmd "git config --local user.name '${GIT_USER}'"
  runcmd "git config --local user.email '${GIT_MAIL}'"
  runcmd "git checkout -b '${SYNC_BRANCH}'"
  copy_template_files ../${LSR_TEMPLATE} .
  if [[ "${DRY_RUN}" || "$(git status --porcelain)" ]]; then
    runcmd "git add ."
    runcmd "git commit -m ':robot: synchronize files from ${LSR_GROUP}/${LSR_TEMPLATE}'"
    if runcmd "git push 'https://${GITHUB_TOKEN}:@github.com/${LSR_GROUP}/${REPO}' -u '${SYNC_BRANCH}'"; then
      runcmd "curl -u '${GIT_USER}:${GITHUB_TOKEN}' -X POST -d '${PAYLOAD}' 'https://api.github.com/repos/${LSR_GROUP}/${REPO}/pulls'"
    fi
  fi
  runcmd "popd"
done

runcmd "popd"

success "All repositories was synchronized with the template successfully."
