# Automatic Maintenance

![CI Status](https://github.com/linux-system-roles/auto-maintenance/workflows/tox/badge.svg)

Set of scripts and configuration options to manage tedious tasks across
linux-system-roles repos.

<!--ts-->
  * [shellcheck](#shellcheck)
  * [sync-template.sh](#sync-templatesh)
  * [lsr_role2collection.py](#lsr_role2collectionpy)
  * [release_collection.py](#release_collectionpy)
  * [check_rpmspec_collection.sh](#check_rpmspec_collectionsh)
  * [roles-tag-and-release.sh](#roles-tag-and-releasesh)
  * [update_collection.py](#update_collectionpy)
  * [list-pr-statuses-ghapi.py](#list-pr-statuses-ghapipy)
<!--te-->


# shellcheck

When making edits, use `shellcheck *.sh` to check your scripts for common
shell script problems.  On Fedora, `dnf -y install ShellCheck`. There is
currently no way to disable a check by using a mnemonic string or keyword
value - you must use a code like `SC2034`. See
https://github.com/koalaman/shellcheck/issues/1948 - In the meantime, if you
need to disable a check, add a link to the ShellCheck wiki like this:
```
# https://github.com/koalaman/shellcheck/wiki/SC2064
# shellcheck disable=SC2064
trap "rm -f ${STDOUT} ${STDERR}; cd ${HERE}" ABRT EXIT HUP INT QUIT
```
So that someone can easily figure out what this code means.  NOTE that the
link must come first, followed by the comment with the shellcheck disable
directive.

# sync-template.sh

There are two main workflows - one that is completely automated, and one that
is mostly automated.

## completely automated

This use case is suitable when the changes to be synced are
* small - small changes and/or small number of files
* for a large number of repos
* guaranteed to have no conflicts, no need for manual intervention
* committed to upstream `template` repo

The intention is to create a small PR, that will have no conflicts (no need
for rebase), is easy to review, that will need no subsequent add-on commits or
fixes to the PR.  If you need something for larger changes, where review and
manual intervention is required, and multiple commits and PR resubmissions may
be required, or you want to work from your local working directory to test
changes locally with `tox`, see `mostly automated` below.

Use the script like this:
```
$ ./sync-template.sh --token xxx --repolist repo1[,repo2,repo3,...] [--branch lsr-template-sync] [--from-branch master]
```
This will pull `https://github.com/linux-system-roles/template` branch
`master` to a local cache directory, then for each repo in `repolist`, will
copy the template files into the repo, create a git commit, and create a pull
request directly in the `https://github.com/linux-system-roles/template` repo,
using a service account and token (which must be acquired separately and made
available to the script).

## mostly automated

This use case is suitable when the changes to be synced are
* large - large changes and/or large numbers of files
* for a small number of repos
* conflicts that need to be manually merged
* local only (not merged upstream), in your working directory
* needed to be tested locally with `tox` first

The intention is that you are making some changes to `template` that may
potentially break code in the other repos, and you need to do some iterative,
interactive testing locally before submitting a PR, and the PR may fail
`travis` CI (since that is difficult to test locally) requiring multiple
commits or PR iterations.  So there are options to work in your local working
directory, to work locally without pulling or pushing changes to github, and
to submit PRs using your own personal github account, with a fork, and the
standard PR workflow of pushing a change to your personal github fork and
submitting a PR from there.  This allows you to force push subsequent changes
to update existing PRs, or otherwise alter PRs with your account.

NOTE: This mode requires the use of the `hub` and `jq` command line tools.

Use the script like this:
```
./sync-template.sh --use-hub --workdir $HOME/linux-system-roles \
    --repolist repo1[,repo2,repo3,...] [--branch lsr-template-sync] \
    [--from-branch master] [--force-copy] [--local]
```
Where `--workdir` is the parent directory for your local clone of
`https://github.com/linux-system-roles/template`, and of the other repos in
`https://github.com/linux-system-roles`.
Use `--local` if you just want to work locally - no git push or pull (but it
will still git clone an upstream repo and fork it if you specify a
`--repolist REPO` that you do not have a local copy of.)
Use `--force-copy` if you want to copy files which the repo has customized
(e.g. `.travis/config.sh`), and you need to update it anyway, merging in the
changes from `template` manually.  If there are such changes, the script will
issue an error message with the files that require manual intervention.

Typical workflow:

```
cd ~/linux-system-roles/auto-maintenance
./sync-template.sh --use-hub --workdir $HOME/linux-system-roles --repolist somerepo --local ...other args...
cd ../somerepo
# if using --force-copy, manually merge files
tox # qemu tests, molecule tests, etc. - note errors
cd ../template
edit template files to fix test errors
cd ../auto-maintenance
# run sync-template again, etc.
```
Then, once everything looks fine locally:
```
cd ~/linux-system-roles/auto-maintenance
./sync-template.sh --use-hub --workdir $HOME/linux-system-roles --repolist somerepo ...other args...
```
to submit the PR.  If there are errors, then
```
cd ~/linux-system-roles/template
# fix template files
cd ../somerepo
# fix repo specific files/customizations
cd ../auto-maintenance
./sync-template.sh --use-hub --workdir $HOME/linux-system-roles --repolist somerepo ...other args...
```
to submit another commit for this PR.

# lsr_role2collection.py

This is a tool to convert a linux-system-role style role to the collections format.

## usage
```
lsr_role2collection.py [-h] [--namespace NAMESPACE] [--collection COLLECTION]
                       [--dest-path DEST_PATH] [--tests-dest-path TESTS_DEST_PATH]
                       [--src-path SRC_PATH] [--src-owner SRC_OWNER] [--role ROLE]
                       [--new-role NEW_ROLE] [--replace-dot REPLACE_DOT]
                       [--subrole-prefix SUBROLE_PREFIX] [--readme README]
                       [--extra-mapping EXTRA_MAPPING]
```

### optional arguments
```
-h, --help           show this help message and exit
--namespace NAMESPACE
                     Collection namespace; default to fedora
--collection COLLECTION
                     Collection name; default to system_roles
--dest-path DEST_PATH
                     Path to parent of collection where role should be migrated;
                     default to ${HOME}/.ansible/collections
--tests-dest-path TESTS_DEST_PATH
                     Path to parent of tests directory in which rolename directory is
                     created and test scripts are copied to the directory; default to
                     DEST_PATH/NAMESPACE/COLLECTION
--src-path SRC_PATH  Path to the parent directory of the source role;
                     default to ${HOME}/linux-system-roles
--src-owner SRC_OWNER
                     Owner of the role in github. If the parent directory name in SRC_PATH is
                     not the github owner, may need to set to it, e.g., "linux-system-roles";
                     default to the parent directory of SRC_PATH
--role ROLE          Role to convert to collection
--new-role NEW_ROLE  The new role name to convert to
--replace-dot REPLACE_DOT
                     If sub-role name contains dots, replace them with the specified
                     value; default to '_'
--subrole-prefix SUBROLE_PREFIX
                     If sub-role name does not start with the specified value, change
                     the name to start with the value; default to an empty string
--readme README      Path to the readme file used in top README.md
--extra-mapping EXTRA_MAPPING
                     This is a comma delimited list of extra mappings to apply when converting the
                     files - this converts the given name to collection format with the optional given
                     namespace and collection.
                     The format is
                       "src_name:[[dest_namespace.]dest_collection.]dest_name,\
                        src_name:[[dest_namespace.]dest_collection.]dest_name,...."
                     The default for `dest_namespace` is the `--namespace` value,
                     and the default for `dest_collection` is the `--collection` value.
                     `src_name` is the name of a role, preferably in `namespace.rolename` format.
                     If just using `rolename` for `src_name`, and `rolename` is used in places
                     in the README that you do not want to change, you may have to change the
                     README in another way, not using this script, by using sed with a custom
                     regex.
```

### environment variables

Each option has corresponding environment variable to set.
```
  --namespace NAMESPACE            COLLECTION_NAMESPACE
  --collection COLLECTION          COLLECTION_NAME
  --src-path SRC_PATH              COLLECTION_SRC_PATH
  --dest-path DEST_PATH            COLLECTION_DEST_PATH
  --role ROLE                      COLLECTION_ROLE
  --new-role NEW_ROLE              COLLECTION_NEW_ROLE
  --replace-dot REPLACE_DOT        COLLECTION_REPLACE_DOT
  --subrole-prefix SUBROLE_PREFIX  COLLECTION_SUBROLE_PREFIX
```
The default logging level is ERROR.
To increase the level to INFO, set `LSR_INFO` to `true`.
To increase the level to DEBUG, set `LSR_DEBUG` to `true`.

## Table of original and new locations

In this table, DEST_PATH/ansible_collections/NAMESPACE/COLLECTION is represented as COLLECTION_PATH. Assume the role name to be converted is myrole.

| Items | Original roles path | New collections path |
|-------|---------------------|----------------------|
| README.md | SRC_PATH/myrole/README.md | COLLECTION_PATH/roles/myrole/README.md [[0]](#0) |
| role | SRC_PATH/myrole/{defaults,files,handlers,meta,tasks,templates,vars} | COLLECTION_PATH/roles/myrole/* |
| subrole | SRC_PATH/myrole/roles/mysubrole | COLLECTION_PATH/roles/mysubrole [[1]](#1) |
| modules | SRC_PATH/myrole/library/*.py | COLLECTION_PATH/plugins/modules/*.py |
| module_utils | SRC_PATH/myrole/module_utils/*.py | COLLECTION_PATH/plugins/module_utils/myrole/*.py [[2]](#2) |
| tests | SRC_PATH/myrole/tests/*.yml | COLLECTION_PATH/tests/myrole/*.yml |
| docs | SRC_PATH/myrole/{docs,design_docs,examples,DCO}/*.{md,yml} | COLLECTION_PATH/docs/myrole/*.{md,yml} |
| license files | SRC_PATH/myrole/filename | COLLECTION_PATH/filename-myrole |

#### [0]
A top level README.md is created in COLLECTION_PATH and it lists the link to COLLECTION_PATH/myrole/README.md.
#### [1]
If a main role has sub-roles in the roles directory, the sub-roles are copied to the same level as the main role in COLLECTION_PATH/roles. To distinguish such sub-roles from the main roles, the sub-roles are listed in the Private Roles section in the top level README.md.
#### [2]
In the current implementation, if a module_utils program is a direct child of SRC_PATH/module_utils, a directory named "myrole" is created in COLLECTIONS_PATH and the module_utils program is copied to COLLECTIONS_PATH/plugins/module_utils/myrole. If a module_utils program is already in a sub-directory of SRC_PATH/module_utils, the program is copied to COLLECTIONS_PATH/plugins/module_utils/sub-directory.

# Examples

## Example 1
Convert a role myrole located in the default src-path to the default dest-path with default namespace fedora and default collection name system_roles.

Source role path is /home/user/linux-system-roles/myrole.
Destination collections path is /home/user/.ansible/collections.
```
python lsr_role2collection.py --role myrole
```

## Example 2
Convert a role myrole located in the default src-path to the default dest-path with namespace community and collection name test.

Source role path is /home/user/linux-system-roles/myrole.
Destination collections path is /home/user/.ansible/collections.
```
python lsr_role2collection.py --role myrole \
                              --namespace community \
                              --collection test
```

## Example 3
Convert a role myrole located in a custom src-path to a custom dest-path and a custom tests-dest-path with a custom role name.

Source role path is /path/to/role_group/myrole.
Destination collections path is /path/to/collections.
```
python lsr_role2collection.py --role myrole \
                              --src-path /path/to/role_group \
                              --dest-path /path/to/collections \
                              --tests-dest-path /path/to/test_dir \
                              --new-role mynewrole
```

## Example 4
Convert a role myrole in a github owner "linux-system-roles" located in a custom src-path to a custom dest-path and a custom tests-dest-path

Source role path is /path/to/role_group/myrole.
Destination collections path is /path/to/collections.
```
python lsr_role2collection.py --role myrole \
                              --src-owner linux-system-roles \
                              --src-path /path/to/role_group \
                              --dest-path /path/to/collections \
                              --tests-dest-path /path/to/test_dir
```

# release_collection.py

This script is used to convert the roles to collection format using
[lsr_role2collection.py](#lsr_role2collectionpy) and build the collection file
for publishing.  It doesn't do the publishing, that must be done separately.

The list of roles is specified by default in the file `collection_release.yml`.
The format of this file is a `dict` of role names.  Each role name is a dict
which must specify the `ref` which is the git tag, branch, or commit hash
specifying the commit in the role repo to use to build the collection from.
You can optionally specify the `org` (default: `linux-system-roles`) and the
`repo` (default: role name).

The other collection metadata comes from `galaxy.yml` - namespace, collection
name, version, etc.  The script reads this metadata.

The script reads the list of roles from `collection_release.yml`.  For each
role, it will clone the repo from github to a local working directory (if there
is no local clone) and update the local clone to the commit specified by `ref`.
The script calls [lsr_role2collection.py](#lsr_role2collectionpy) to convert
each role to collection format using the galaxy namespace name and collection
name.  After all of the roles have been converted, the script uses
`ansible-galaxy collection build` to build the collection package file suitable
for publishing.

The script will then run `galaxy-importer` against the collection package file
to check if it will import into galaxy cleanly.  If you get errors, you will
probably need to go back and fix the role or add some suppressions to the
`.sanity-ansible-ignore-2.9.txt` in the role.  Or, you can add them to
`lsr_role2collection/extra-ignore-2.9.txt` if necessary.

To publish, use something like
```
ansible-galaxy collection publish /path/to/NAMESPACE-COLLECTION_NAME-VERSION.tar.gz
```

## Pre-requisites

`git clone https://github.com/linux-system-roles/auto-maintenance [-b STABLE_TAG]`

`STABLE_TAG` can be omitted to use `master`.

Or, figure out some way to download the correct versions of
[lsr_role2collection.py](#lsr_role2collectionpy), `galaxy.yml`,
`collection_release.yml`, and `release_collection.py` from this repo.

You will need to ensure that the information in `galaxy.yml` (particularly the
`version:` field), and the information in `collection_release.yml`
(particularly the `ref:` fields), are correct and up-to-date for the collection
you want to build and publish.  You are strongly encouraged to use
[roles-tag-and-release.sh](#roles-tag-and-releasesh) to tag, release, and
publish the individual roles first, then use
[update_collection.py](#update_collectionpy) to update
`collection_release.yml`.  You will have to manually update the version in
`galaxy.yml` after visually inspecting the version changes in the individual
roles.

You will need the `galaxy-importer` package - `pip install galaxy-importer --user`.
You will need `docker` in order to use `galaxy-importer`.

## collection_release.yml format
```yaml
ROLENAME:
  ref: TAG_OR_HASH_OR_BRANCH
  org: github-organization
  repo: github-repo
```
Where `ROLENAME` is the name of the role as it will appear in the collection
(under `NAMESPACE/COLLECTION_NAME/roles/`).  `ref` is the git tag (preferred),
commit hash, or branch to use (in the format used as the argument to `git clone
-b` or `git checkout`).  `org` is the github organization (default
`linux-system-roles`).  The `repo` is the name of the repo under the github
organization, and the default is the `ROLENAME`, so only use this if you need to
specify a different name for the role in the collection.

Example:
```yaml
certificate:
  ref: "1.0.0"
kdump:
  ref: "1.0.1"
kernel_settings:
  ref: "1.0.0"
```
This will use e.g. `git clone https://github.com/linux-system-roles/certificate
-b 1.0.0`, etc.

Use `roles-tag-and-release.sh` to create new tags/versions in each role.

Use `update_collection.py` to update the refs in `collection_release.yml` to the
latest tags.

## Usage
Basic usage:
```
cd auto-maintenance
python release_collection.py
ansible-galaxy collection publish -v $DEST_PATH/fedora-linux_system_roles-$VERSION.tar.gz 
```
This will use the `galaxy.yml` and `collection_release.yml` files in the current
directory, will create a temporary working directory to clone the roles into,
will create a collection under
`$HOME/.ansible/collections/ansible_collections/NAMESPACE/COLLECTION_NAME`, and
will create the collection package file
`$HOME/.ansible/collections/NAMESPACE-COLLECTION_NAME-VERSION.tar.gz`, where
`NAMESPACE`, `COLLECTION_NAME`, and `VERSION` are specified in `galaxy.yml`.

## Options

* `--galaxy-yml` - env: `GALAXY_YML` - default `galaxy.yml` in current directory
  - full path and filename of `galaxy.yml` to use to build the collection
* `--collection-release-yml` - env: `COLLECTION_RELEASE_YML` - default
  `collection_release.yml` in current directory - full path and filename of
  `collection_release.yml` to use to build the collection
* `--src-path` - env: `COLLECTION_SRC_PATH` - no default - Path to the directory
  containing the local clone of the role repos - if nothing is specified, the
  script will create a temporary directory
* `--dest-path` - env: `COLLECTION_DEST_PATH` - default
  `$HOME/.ansible/collections` - collection directory structure will be created
  in `DIR/ansible_collection/NAMESPACE/COLLECTION_NAME`  - collection package
  file will be created in `DIR`
* `--force` - boolean - default `False` - if specified, the collection directory
  will be removed first if it exists, and the package file, if any, will be
  overwritten

## Version

For the `version:` field in `galaxy.yml`, we have to use `X.Y.Z` where `X`, `Y`,
and `Z` are non-negative integers.  We will start at `0.0.1` until the
collection stabilizes, then we should start at `1.0.0`.  During this
stabilization period, we should just increase the `Z` number when we do a new
release.

After stabilization, when we want to do a new release, we assume that each role
will be doing regular tagged releases where the tag is the semantic version.  If
not, then it will be difficult to determine what sort of change the role has
made, and how it should affect the collection version.

The collection version will be derived from all of the role versions, and will
be semantic versioned.

Notation: `Xr` is the `X` number from the version of a given role `r`.  `Xc` is
the `X` number for the collection `c`.  Similarly for `Yr`, `Yc`, `Zr`, and
`Zc`.

Examine the versions in the updated roles and compare them to the roles in the
`collection_release.yml`.

If any of the `Xr` has changed, set the new `Xc` to `Xc + 1` - bump major
release number to indicate there is a role which has introduced an api breaking
change, and set `Yc` and `Zc` to `0`.

If none of the `Xr` has changed, and if any of the `Yr` has changed, set the new
`Yc` to `Yc + 1` - bump minor release number to indicate there is a role which
has introduced a non-breaking api change, and set `Zc` to `0`.

If none of the `Xr` or `Yr` has changed, and if any of the `Zr` has changed, set
`Zc` `Zc + 1` - some role has changed.

If the role does not use a semantic version for the tag, or it is otherwise
unclear how to determine what sort of changes have occurred in the role, it is
up to the collection maintainer to investigate the role to determine how to
change `Xc`, `Yc`, or `Zc`.

# local-repo-dev-sync.sh

This script is useful for the linux-system-roles team to make changes to
multiple roles.  For example, as a LSR admin you need to update the version of
tox-lsr used in each repo.

## Prerequisites

This script uses `hub` for cli/api interactions with github, and `jq` for
parsing and formatting the output of `hub`.  You can install these on Fedora
like `dnf -y install jq hub`.  The `hub` command also requires the use of your
github api token.  See `man hub` for instructions.

## Usage

Basic usage, with no arguments:
```
./local-repo-dev-sync.sh
```
This will clone all of the repos under https://github.com/linux-system-roles
(except those listed in `$EXCLIST` - see the script for the default list e.g. it
excludes repos such as `test-harness`, `auto-maintenance`, etc.).  These will be
cloned to `$HOME/linux-system-roles` using the `hub clone` command (if the
directory does not already exist).  Each repo will be forked under your github
user using the `hub fork` command (if you do not already have a fork).  Each
local clone will have a git remote named `origin` for the source repo, and a git
remote named after your github user id for your fork.  It will also do a `git
fetch` to pull the latest code from the remotes (but it will not merge that code
with your local branches - you must do that if desired).

## Options

Options are passed as environment variables.

`LSR_BASE_DIR` - local directory holding clones of repos - default is
`$HOME/linux-system-roles`

`LSR_GH_ORG` - the github org to use as the origin of the clones/forks e.g. the
ORG used in `https://github.com/ORG` - default is `linux-system-roles`

`DEBUG` - turns on `set -x`

## Commands

You can pass commands to perform in each repo in these ways:

### command line arguments

For each repo, checkout the main branch and make sure it is up-to-date:

```
LSR_BASE_DIR=~/working-lsr ./local-repo-dev-sync.sh "git checkout main || git checkout master; git pull"
```

The arguments will be passed to `eval` to be evaluated in the context of each
repo.  This is useful if you need to just refresh your local copy of the repo,
or perform a very simple task in each repo.

### stdin/here document

You can do the same as above like this:

```
LSR_BASE_DIR=~/working-lsr ./local-repo-dev-sync.sh <<EOF
git checkout main || git checkout master
git pull
EOF
```

That is, you can pass in the commands to use in a `bash` `here` document.  This
is useful when you have more complicated tasks to perform that takes multiple
commands and/or involves shell logic/looping.  Whatever you specify in the here
document will be passed to `eval` in each repo directory.

### shell script

For really complex repo administration, you may want to write a shell script to be
executed in each repo:

```
./local-repo-dev-sync.sh /path/to/myscript.sh
```

### update tox-lsr version in each repo

I need to update the version of tox-lsr in each repo, and submit a PR for that
change.

First, create a git commit file in the format expected by the `git commit -F`
argument e.g.

```
update tox-lsr version to 2.2.1

Update the version of tox-lsr used in CI to 2.2.1
```

This will be used for the git commit message and the hub pull-request message.
Then

```
./local-repo-dev-sync.sh <<EOF
set -euxo pipefail
if git checkout main; then
  mainbr=main
elif git checkout master; then
  mainbr=master
else
  echo ERROR: could not find branch main or master
  exit 1
fi
git pull
git checkout -b tox-lsr-2.2.1
sed -i -e 's|TOX_LSR: "git+https://github.com/linux-system-roles/tox-lsr@2.2.0"|TOX_LSR: "git+https://github.com/linux-system-roles/tox-lsr@2.2.1"|' .github/workflows/tox.yml
git commit -s -a -F /path/to/commit.txt
git push $USER tox-lsr-2.2.1
hub pull-request -F /path/to/commit.txt -b "\$mainbr"
EOF
```
If your `$USER` is not the same as your github username, use your github
username instead of `$USER`.

# check_rpmspec_collection.sh

This script is to be executed in the dist-git directory.
It locally builds rpm packages with various combination of `ansible` and `collection_artifact` options,
and checks whether the built rpm count is correct or not.
Then, it verifies that `README.html` files are only in /usr/share/doc/ area.

Usage: ./check_rpmspec_collection.sh [ -h | --help ] | [ fedpkg | rhpkg [ branch_name ] ]

# roles-tag-and-release.sh

This script is used in conjunction with `local-repo-dev-sync.sh` to examine the
changes, tag, release to github, and import each role to Galaxy.  Use it like
this:

```
LSR_BASE_DIR=~/working-lsr ./local-repo-dev-sync.sh `pwd`/roles-tag-and-release.sh
```

This script is highly interactive.  Since we are using semantic versioning,
there must be some sort of human interaction to decide which X, Y, or Z version
number to update.  The script will show you the commits since the last tag, and
will optionally show you the detailed changes.  It will then prompt for the new
tag.  If you hit Enter/Return here, it will skip tagging, so hit Enter/Return if
you do not want to make a new tag/release.  If you do want to make a new
release, enter a tag/version in the form of `X.Y.Z`, based on the semantic
changes to the role.  You will then be prompted to edit the release notes for
the release.  You will need to create some sort of meaningful title for the
release.  The body of the release will be filled in by the commit messages from
the commits since the last tag - you will almost certainly need to edit these.
When you are done, it will ask if you want to create a new GitHub release.  If
you do, it will create the release, then ask if you want to publish the role to
Galaxy.  If you do, it will perform a role import into Galaxy.

Use this script before `update_collection.py` and `release_collection.py`.

# update_collection.py

This script should be used after you have tagged the roles e.g. by using
`roles-tag-and-release.sh` as described above.  It will update the
`collection_release.yml` file with the latest tags.  Use `--src-path
~/working-lsr` if you already have a local git clone of the role repos,
otherwise, it will create a tempdir.  By default it will use the latest tag, but
you can use `--use-commit-hash` if you want to use the latest commit that is not
tagged.  You will need to update `galaxy.yml` with a new version number if any
of the roles have been updated (and remember - it is a semantic version).  Once
you do this, you are ready to use `release_collection.py`.

# list-pr-statuses-ghapi.py

Allows you to query the set of all PRs open across all repos.  By default, it
will print out all open PRs, along with their statuses and checks, along with
some other metadata.  There are a number of command line options to look for
specific repos, platform status, ansible version status, staging vs.
production, and many more.  See the help for the command for more information.
