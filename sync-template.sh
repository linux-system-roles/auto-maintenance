#!/bin/bash

set -euo pipefail

GIT_MAIL="lsrbot@gmail.com"
GIT_USER="lsrbot"
GITHUB_USER="linux-system-roles"
LSR_TEMPLATE="template"
SYNC_BRANCH="lsr-template-sync"
DEVEL_LEAD="pcahyna"
PAYLOAD=$(echo \
'{"title":"Synchronize files from @<GITHUB_USER>@/@<LSR_TEMPLATE>@",
  "base":"master",
  "head":"@<SYNC_BRANCH>@",
  "body":"One or more files which should be in sync across @<GITHUB_USER>@ repos were changed either here or in [@<GITHUB_USER>@/@<LSR_TEMPLATE>@](https://github.com/@<GITHUB_USER>@/@<LSR_TEMPLATE>@).\nThis PR propagates files from [@<GITHUB_USER>@/@<LSR_TEMPLATE>@](https://github.com/@<GITHUB_USER>@/@<LSR_TEMPLATE>@). If something was changed here, please first modify @<LSR_TEMPLATE>@ repository.\n\nCC: @@<DEVEL_LEAD>@."}' \
| sed -e s,@<GITHUB_USER>@,${GITHUB_USER},g \
      -e s,@<LSR_TEMPLATE>@,${LSR_TEMPLATE},g \
      -e s,@<SYNC_BRANCH>@,${SYNC_BRANCH},g \
      -e s,@<DEVEL_LEAD>@,${DEVEL_LEAD},g \
)

if [ -z "${GITHUB_TOKEN}" ]; then
  echo -e "\e[31mGitHub token (GITHUB_TOKEN) not set. Terminating.\e[0m"
  exit 1
else
  export GITHUB_TOKEN=${GITHUB_TOKEN}
fi

git config --global user.email "${GIT_MAIL}"
git config --global user.name "${GIT_USER}"

git clone "https://github.com/${GITHUB_USER}/${LSR_TEMPLATE}.git" "${LSR_TEMPLATE}"

HERE=$(pwd)
curl --retry 5 --silent -u "${GIT_USER}:${GITHUB_TOKEN}" https://api.github.com/users/${GITHUB_USER}/repos 2>/dev/null | jq '.[].name' | grep '^"ansible' | sed 's/"//g' | while read -r; do
  REPO="${REPLY}"
  echo -e "\e[32m Anylyzing ${REPO}\e[0m"

  cd "${HERE}"
  git clone "https://github.com/${GITHUB_USER}/${REPO}.git" "${REPO}"
  cd "${REPO}"
  git checkout -b "${SYNC_BRANCH}"

  # Replace files in target repo by ones from ${GITHUB_USER}/${LSR_TEMPLATE}
  cp -f ../${LSR_TEMPLATE}/.gitignore ./
  cp -rf ../${LSR_TEMPLATE}/molecule ./
  if [ -n "$(git status --porcelain)" ]; then
    git add .
    git commit -m ":robot: synchronize files from ${GITHUB_USER}/${LSR_TEMPLATE}"
    if git push "https://${GITHUB_TOKEN}:@github.com/${GITHUB_USER}/${REPO}" --set-upstream ${LSR_TEMPLATE}; then
      curl -u "${GIT_USER}:${GITHUB_TOKEN}" -X POST -d "${PAYLOAD}" "https://api.github.com/repos/${GITHUB_USER}/${REPO}/pulls"
    fi
  fi
done
