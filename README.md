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
  * [role-make-version-changelog.sh](#role-make-version-changelogsh)
  * [list-pr-statuses-ghapi.py](#list-pr-statuses-ghapipy)
  * [bz-manage.sh](#bz-managesh)
  * [check_jenkins.py](#check_jenkinspy)
  * [configure_squid](#configure_squid)
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
                       [--extra-mapping EXTRA_MAPPING] [--meta-runtime META_RUNTIME]
                       [--extra-script EXTRA_SCRIPT]

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
                     This is a comma delimited list of extra mappings to apply when converting
                     the files - this replaces the given role name with collection format with
                     the optional given namespace and collection as sell as the given FQCN with
                     other FQCN.
                     The format is
                       "src_name:[[dest_namespace.]dest_collection.]dest_name,\
                        ...,
                        src_FQCN:[[dest_namespace.]dest_collection.]dest_name,\
                        ..."
                     The default for `dest_namespace` is the `--namespace` value,
                     and the default for `dest_collection` is the `--collection` value.
                     `src_name` is the name of a role, preferably in `namespace.rolename` format.
                     If just using `rolename` for `src_name`, and `rolename` is used in places
                     in the README that you do not want to change, you may have to change the
                     README in another way, not using this script, by using sed with a custom
                     regex.
                     In addition, 'fedora.linux_system_roles:NAMESPACE.COLLECTION' is in the
                     mapping, 'fedora.linux_system_roles' is converted to 'NAMESPACE.COLLECTION'.
--meta-runtime /path/to/runtime.yml
                     This is the path to the collection meta/runtime.yml - the default is
                     $HOME/linux-system-roles/auto-maintenance/lsr_role2collection/runtime.yml.
--extra-script /path/to/executable
                     This is a script to use to do custom conversion of the role.  For example,
                     to convert uses of filter plugins to FQCN.  If you do not specify anything,
                     then it looks for an executable file named `lsr_role2coll_extra_script` in
                     the role root directory, and runs it.  The arguments such as dest dir,
                     namespace, etc. are passed in via environment variables.  See the code for
                     the list of environment variables available.
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

This script is used to:
* Check all of the roles for new versions, and update `collection_release.yml`
  with the updated `ref` fields.
* Convert the roles to collection using [lsr_role2collection.py](#lsr_role2collectionpy)
* Update the version in `galaxy.yml`
* Build the collection file using `ansible-galaxy collection build`
* Check the collection using `galaxy-importer`
* Publish the collection using `ansible-galaxy collection publish`
* Additionally, instead of the upstream sources, the rpm file could be used as
  an input. If the option is selected, it skips the first 3 items and builds the
  collection file using `ansible-galaxy collection build` with `galaxy.yml` or
  `MANIFEST.json` in the rpm file.

The list of roles is specified by default in the file `collection_release.yml`.
You can use the `--include` and `--exclude` options (described below) to control
which roles you want to update and release in the collection. The format of this
file is a `dict` of role names.  Each role name is a dict which must specify the
`ref` which is the git tag, branch, or commit hash specifying the commit in the
role repo to use to build the collection from. You can optionally specify the
`org` (default: `linux-system-roles`) and the `repo` (default: role name).  The
use of the tag in semantic version format is strongly encouraged, as the script
can automatically update the collection version in `galaxy.yml` if all of the
tags are semantically versioned (see `--no-auto-version`, `--new-version`).

The other collection metadata comes from `galaxy.yml` - namespace, collection
name, version, etc.  The script can update the `version` field automatically if
all updated roles are using semantic versioning (see `--no-auto-version`,
`--new-version`).

The script reads the list of roles from `collection_release.yml` and modifies
the list depending on `--include` and `--exclude`.  For each role, it will clone
the repo from github to a local working directory (if there is no local clone).
By default, the script will attempt to determine if there are any updates to the
role by comparing the `ref` in the file with the latest commit.  If both refs
are tags in the format of a semantic version, the script will attempt to
automatically determine what the new semantic version of the collection should
be.  See the `Version` section below for details.  If using the `--no-update`
flag, then the script will assume the user has already updated
`collection_release.yml` to the correct ref and will checkout that ref.  If you
have a local working copy of the roles, you can specify it with the `--src-path`
argument, or the script will use a tmp directory.

The script calls [lsr_role2collection.py](#lsr_role2collectionpy) to convert
each role to collection format using the galaxy namespace name and collection
name specified in `galaxy.yml`.  The script will use
`~/.ansible/collections/ansible_collections/$NAMESPACE/$NAME` to convert the
files into and assemble the other metadata (such as the ignore files).  If you
want to use a different directory, use `--dest-path`.  After all of the roles
have been converted, the script uses `ansible-galaxy collection build` to build
the collection package file suitable for publishing.  The file will be placed in
the `~/.ansible/collections` directory.  If the `--dest-path` exists, and you
want to replace it, use the `--force` argument.

The script will then run `galaxy-importer` against the collection package file
to check if it will import into galaxy cleanly.  If you get errors, you will
probably need to go back and fix the role or add some suppressions to the
`.sanity-ansible-ignore-x.y.txt` in the role, where `x.y` is the version of
ansible that `galaxy-importer` is using.

By default, the script will not publish the collection to Galaxy.  Specify the
`--publish` argument to publish the collection to Galaxy.  The script will then
do something like this:
```
ansible-galaxy collection publish -vv ~/.ansible/collections/NAMESPACE-COLLECTION_NAME-VERSION.tar.gz
```
and will wait until the publish is completed.  If you do not want to wait,
specify the `--no-wait` argument which will do something like this:
```
ansible-galaxy collection publish --no-wait ~/.ansible/collections/NAMESPACE-COLLECTION_NAME-VERSION.tar.gz
```
If the script is unable to calculate the new version for `galaxy.yml` you will
need to figure out what the new semantic version will be, and use the
`--new-version` argument.

## Pre-requisites

`git clone https://github.com/linux-system-roles/auto-maintenance [-b STABLE_TAG]`

`STABLE_TAG` can be omitted to use `master`.

Or, figure out some way to download the correct versions of
[lsr_role2collection.py](#lsr_role2collectionpy), `galaxy.yml`,
`collection_release.yml`, and `release_collection.py` from this repo.

You should ensure that the roles have been appropriately tagged with semantic
versions.  You are strongly encouraged to use
[role-make-version-changelog.sh](#role-make-version-changelogsh) to tag, release, and
publish the individual roles.  If you do this, then you can usually let the
script automatically update the versions in `collection_release.yml` and
`galaxy.yml`.  Otherwise, you will need to ensure that the information in
`galaxy.yml` (particularly the `version:` field), and the information in
`collection_release.yml` (particularly the `ref:` fields), are correct and
up-to-date for the collection you want to build and publish, then use the
`--no-update` argument.

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
(under `NAMESPACE/COLLECTION_NAME/roles/`).  `ref` is the git tag in semantic
version format (preferred), commit hash, or branch to use (in the format used as
the argument to `git clone -b` or `git checkout`).  `org` is the github
organization (default `linux-system-roles`).  The `repo` is the name of the repo
under the github organization, and the default is the `ROLENAME`, so only use
this if you need to specify a different name for the role in the collection.
The `sshd` role currently uses both `org` and `repo`.

Example:
```yaml
certificate:
  ref: 1.0.0
kdump:
  ref: 1.0.1
kernel_settings:
  ref: 1.0.0
```
This will use e.g.
`git clone https://github.com/linux-system-roles/certificate -b 1.0.0`, etc.

Use [role-make-version-changelog.sh](#role-make-version-changelogsh) to create new
tags/versions in each role.  If you use strict semantic versioning everywhere,
in your github tags and in the `collection_release.yml` file, you can use the
automatic versioning feature of the script to automatically update the version
in `galaxy.yml`.

## Usage
Basic usage:
```
cd auto-maintenance
python release_collection.py --publish
```
This will use the `galaxy.yml` and `collection_release.yml` files in the current
directory, will create a temporary working directory to clone the roles into,
will create a collection under
`$HOME/.ansible/collections/ansible_collections/NAMESPACE/COLLECTION_NAME`, and
will create the collection package file
`$HOME/.ansible/collections/NAMESPACE-COLLECTION_NAME-VERSION.tar.gz`, where
`NAMESPACE`, `COLLECTION_NAME`, and `VERSION` are specified in `galaxy.yml`, and
will publish the collection, waiting until it is completed.

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
* `--include` - list - default empty - by default, the script will operate on
  all roles in the `collection_release.yml`.  Use `--include` to specify only
  those roles you want to update in the new collection.  If you specify both
  `--exclude` and `--include` then `--exclude` takes precedence.
* `--exclude` - list - default empty - by default, the script will operate on
  all roles in the `collection_release.yml`.  Use `--exclude` to remove the
  specified roles from that list.  If you specify both `--exclude` and
  `--include` then `--exclude` takes precedence.
* `--new-version` - string - The new semantic version to use for the collection.
  The script will update this
* `--use-commit-hash` - boolean - By default, only tags in semantic version
  format will be used for the `ref` field in `collection_release.yml`. If
  instead you want to use the latest commit hash for a role that has not been
  tagged, use this flag. However, this means you will not be able to use
  automatic versioning, and you will need to use `--new-version`, or manually
  edit the `collection_release.yml` and `galaxy.yml` and use `--no-update`.
* `--use-commit-hash-role` - list - By default, use whatever is the value
  of `--use-commit-hash`.  There are some cases where you want to use the
  tag for all roles *except* one or a few.  In that case, you can use
  `--use-commit-hash-role role1 --use-commit-hash-role role2` to specify the
  roles for which you want to use the commit hash, and use the tag for all
  other roles.
* `--no-auto-version` - boolean - By default, the script will attempt to
  update the collection version in `galaxy.yml`.  Use this flag if you do
  not want to do that.
* `--no-update` - boolean - By default, the script will attempt to update the
  `ref` fields for each role in `collection_release.yml` and the version in
  `galaxy.yml`.  Use this flag if you do not want to do that.
* `--publish` - boolean - By default, the script will just create the collection
  tarball in `~/.ansible/collections`.  You must specify `--publish` if you want
  to publish the collection.
* `--no-wait` - boolean - By default, when publishing, the script will wait
  until the publishing is completed.  Use `--no-wait` if you do not want to
  wait, and instead will check the import status in Galaxy.
* `--skip-git` - boolean - If set to `true`, use local source. By default, `false`.
* `--skip-check` - boolean - If set to `true`, check using galaxy-importer is
  skipped. By default, `false`.
rue when skip check with galaxy-importer
* `--debug` - boolean - By default, the script will only output informational
  messages.  Use `--debug` to see the details.
* `--rpm` - string - Specifies the rpm file for the input collection. When --rpm
  is set, other input options such as `--galaxy-yml`, `--include`, `--exclude`,
  `--new-version`, `--use-commit-hash`, and `--no-auto-version` are ignored.
  Note: if the rpm file does not contain `galaxy.yml` or `MANIFEST.json` in
  `/path/to/ansible_collections/namespace/collection`, `release_collection.py`
  fails.  No default value.

## Version

For the `version:` field in `galaxy.yml`, we have to use `X.Y.Z` where `X`, `Y`,
and `Z` are non-negative integers.  We will start at `0.0.1` until the
collection stabilizes, then we should start at `1.0.0`.  During this
stabilization period, we should just increase the `Z` number when we do a new
release.

We assume that each role will be doing regular tagged releases where the tag is
the semantic version.  If not, then it will be difficult to determine what sort
of change the role has made, and how it should affect the collection version.
The [role-make-version-changelog.sh](#role-make-version-changelogsh) script is useful to
identify what sort of changes were made in each role, update the semantic
version tag, do github releases, and publish individual roles to Galaxy.  You
are strongly encouraged to use that script.

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

# role-make-version-changelog.sh

This script is used to create a new version, tag, and release for a role.  It
will guide you through the process.  It will show you the changes in the role
since the last tag, and ask you what will be the new semantic version to use for
the tag.  It will then put the changes in a file to use for the update to the
CHANGELOG.md file for the new version, and put you in your editor to edit the
file.  If you are using this in conjunction with `local-repo-dev-sync.sh`, it
will push the changes to your repo and create a pull request for CHANGELOG.md.
Once the CHANGELOG.md PR is merged, there is github action automation to tag the
repo with the version, create a github release, and import the new version into
Ansible Galaxy.  You must provide a branch for the PR, or if you are not using
the script with `local-repo-dev-sync.sh`, you can create a branch in your local
clone directory.
```
BRANCH=my_branch_name LSR_BASE_DIR=~/working-lsr ./local-repo-dev-sync.sh `pwd`/role-make-version-changelog.sh
```
NOTE: You must install and configure `gh` in order to create the pull request.
If you want to have more control over the commit, commit msg, and PR, then you
can clone the repo manually, create the branch, and run
`role-make-version-changelog.sh` in the local repo clone directory.  This will
not push or create a PR.

This script is highly interactive.  Since we are using semantic versioning,
there must be some sort of human interaction to decide which X, Y, or Z version
number to update.  The script will show you the commits since the last tag, and
will optionally show you the detailed changes.  It will then prompt for the new
tag.  If you hit Enter/Return here, it will skip tagging, so hit Enter/Return if
you do not want to make a new tag/release.  If you do want to make a new
release, enter a tag/version in the form of `X.Y.Z`, based on the semantic
changes to the role.  You will then be prompted to edit CHANGELOG.md for the
release.  The body will be filled in by the commit messages from the commits
since the last tag - you will need to edit these. When you are done, it will
make a commit in your local repo.  If you are using it with
`local-repo-dev-sync.sh`, and `gh` is installed and configured, it will push the
changes to your repo and create the PR.

Use this script, and ensure the CHANGELOG.md PR is merged, and the repo is
tagged and released, before you run
[release_collection.py](#release_collectionpy).

# list-pr-statuses-ghapi.py

Allows you to query the set of all PRs open across all repos.  By default, it
will print out all open PRs, along with their statuses and checks, along with
some other metadata.  There are a number of command line options to look for
specific repos, platform status, ansible version status, staging vs.
production, and many more.  See the help for the command for more information.

# bz-manage.sh

## Intro

This tool is primarily for downstream maintainers for various administrative
Bugzilla tasks such as creating new system roles BZs, checking if a BZ in a
specified release has a clone in other releases, setting the ITM and DTM fields
for BZs in a given ITR, managing the `devel_whiteboard` field, and printing git
commit and changelog entries.

See also
[RHEL Development Guide](https://one.redhat.com/rhel-development-guide/#assembly_rhel-9-development_rhel-dev-guide)
for more information about the Bugzilla workflow.

## Requirements

You must have the `bugzilla` cli tool (provided by the `python-bugzilla-cli`
package on Fedora).

You must have an authentication API key configured
[API Key](https://bugzilla.redhat.com/userprefs.cgi?tab=apikey) - see
[Authentication](https://bugzilla.redhat.com/docs/en/html/api/core/v1/general.html#authentication)
and `man bugzilla` - the section "AUTHENTICATION CACHE AND API KEYS" for more
information.

You must have the `jq` cli tool (provided by the `jq` package on Fedora).

## Commands

### setitm, setdtm
Use this to set the ITM or DTM for all BZ in a given ITR and given STATUS to a
given value, if the ITM/DTM is less than the given value.  For example, you have
several BZ in the POST status for ITR 8.7.0, and you need to ensure that all of
them have an ITM of at least 23 - if the ITM is not set, set it to 23 - if the
ITM is set to a value less than 23, set it to 23 - if the ITM is set to a value
of 23 or higher, do not touch it.
```
ITR=8.7.0 ITM=23 STATUS=POST ./bz-manage.sh setitm
```

### reset_dev_wb
Use this to remove `qa_ack?` from the `Devel Whiteboard` field if the BZ has
been given `qa_ack+`, and remove `pre-verify?` from the `Devel Whiteboard`
field if the BZ has been given `Verified:Tested`.
```
ITR=9.1.0 ./bz-manage.sh reset_dev_wb
```

### new
Create a new system roles BZ.  NOTE: Does not use any environment variables -
all parameters are passed in on the command line.  All parameters are required.
Usage:
```
./bz-manage.sh new X.Y "SUMMARY" "COMMENT" ROLENAME
```
* `X.Y` - the major.minor version (e.g. 8.7) - the ITR will be set to `X.Y.0`
* `SUMMARY` - the BZ summary/title
* `COMMENT` - the initial BZ comment
* `ROLENAME` - name of role - the whiteboard field will be updated with
`role:ROLENAME` - use `""` if you want to leave the field blank e.g. the BZ
corresponds to multiple roles

For example, to create a new 9.1
BZ:
```
./bz-manage.sh new 9.1 "kernel_settings mis-configures memory settings" \
  "I can reproduce on rhel-9 but not rhel-8" kernel_settings
```
NOTE: You will have to edit the BZ after creation.  And the RHEL Bugzilla
workflow tools automatically edit the BZ several times. It may take a few
minutes after you create a new BZ that you can actually edit it without having
your edits overwritten or discarded.

### clone_check
Check that the BZs of a given ITR and STATUS all have an appropriate clone.  It will
check that there is a clone, that the clone has the same SUMMARY, and that the clone
has the same STATUS.
```
ITR=8.7.0 STATUS=POST ./bz-manage clone_check
```
e.g.
```
ERROR: bz 2066876 status [POST] does not match clone 2072745 status [ON_QA]
```
The clone check is not perfect, so be sure to check manually.

### rpm_release
Use this to generate the following files:
* cl-md - The new text to add to the CHANGELOG.md
* cl-spec - The new text to add to the spec %changelog section
* git-commit-msg - The git commit message

For example - I have several BZ in POST that I am doing a new build for ITR 8.7.0.
The new version will be 1.20.0.  NOTE that the version in CHANGELOG.md
is different from the version in the spec file - so you will need to add
the `-N` for the RELEASE for the spec file version.
I want to update the CHANGELOG.md, the spec %changelog, and the git commit
message with the information from all of these BZ, formatted in the correct
manner for all of these.  You will need to edit all 3 files:
* Edit CHANGELOG.md and add the contents of cl-md in the right place
* Edit the spec file to add cl-spec in the right place, and ensure the name
  and email are correct.
* Edit the git-commit-msg with the correct git subject line.  You can then
  use this file with git commit -F

## Parameters

Almost all parameters are passed as environment variables.  However, the `new`
command takes all parameters on the command line - see above.

### ITR
default "8.7.0" - the Internal Target Release of the BZ to manage

### ITM
Internal Target Milestone - used with `setitm`

### DTM
Dev Target Milestone - used with `setdtm`

### STATUS
BZ status e.g. `NEW`, `ASSIGNED`, `POST`, etc.  Most commands only operate on BZs that
have the specified STATUS - the primary exception is `reset_dev_wb`.

### LIMIT
By default, the limit on the number of BZ returned by a query is 100.  Use LIMIT to
change that value.

There are other undocumented environment variables used, check the code for more details.

# check_jenkins.py

Check the test tasks in a jenkins server.

## Requirements

package `python3-jenkins-1.7.0-6.fc36.noarch`

You must have Kerberos authentication set up.

You have to create a file `~/.config/jenkins.yml` like this:
```yaml
somename:
  username: MY_USERNAME
  url: "https://my.jenkins.hostname.tld"
  job_name: MY_JENKINS_JOBNAME
current: somename
```

## Usage

By default, it will print the queued tasks, the running tasks, and the completed tasks.
```
> ./check_jenkins.py
Queued tasks:
QueueID  Queued Since        Role            PR  Platform               Queue Reason        
3915644  2022-09-14T19:27:23 timesync        119 RHEL-9.2/ansible-2.13  waiting on executor 
3915643  2022-09-14T19:27:23 timesync        119 RHEL-9.2/ansible-2.9   waiting on executor 
3915642  2022-09-14T19:27:23 timesync        119 RHEL-8.8/ansible-2.13  waiting on executor 
3915641  2022-09-14T19:27:23 timesync        119 RHEL-8.8/ansible-2.9   waiting on executor 
...

Running tasks:
TaskID   Started At          Role            PR  Platform               Queue Time
15994    2022-09-14T19:23:42 cockpit         73  RHEL-9.2/ansible-2.9   11        
15993    2022-09-14T19:23:41 cockpit         73  RHEL-8.8/ansible-2.13  10        
15992    2022-09-14T19:23:41 cockpit         73  RHEL-8.8/ansible-2.9   10        
...

Completed tasks:
TaskID   Started At          Role            PR  Platform               Duration Queue Time Status    
15966    2022-09-14T16:00:06 podman          14  RHEL-9.2/ansible-2.13  695      491        FAILED    
15965    2022-09-14T15:58:55 podman          14  RHEL-9.2/ansible-2.9   563      420        FAILED    
...
```
It takes a long time to run.  You can shorten the duration by using the environment variable
`MAX_TASK_AGE` (number of seconds of maximum task age) e.g.
```
> MAX_TASK_AGE=7200 ./check_jenkins.py
Queued tasks:
...

```
e.g. to skip tasks older than 2 hours.

You can also specify the argument `print_queued_tasks`, `print_running_tasks`, or `print_completed_tasks`
if you just want to look at those tasks.
```
> ./check_jenkins.py print_queued_tasks
Queued tasks:
QueueID  Queued Since        Role            PR  Platform               Queue Reason        
3915644  2022-09-14T19:27:23 timesync        119 RHEL-9.2/ansible-2.13  waiting on executor 
...
```
Use `print_task_info TASK_NUM` to show a YAML representation of a task:
```
> ./check_jenkins.py print_task_info 15967
_class: hudson.model.FreeStyleBuild
actions:
- _class: hudson.model.ParametersAction
  parameters:
  - _class: hudson.model.StringParameterValue
    name: priority
    value: '3'
...
```
which isn't very useful unless you are debugging the script and/or Jenkins itself.

### print_task_tests_info

Use this to see information about the task, including the individual tests
statuses.
```
> ./check_jenkins.py print_task_tests_info 12345
Role:nbde_client PR:80 Platform:RHEL-8.8.0-20220921.0 Arch:x86_64
Node:production-3 IP:10.0.0.3 Workspace:/var/lib/jenkins/workspace/ci-test-jobname@6
Stage                State      Result     GuestID                              Test Workdir
COMPLETE             OK         PASSED     c3767ea3-934c-408d-b42f-d7639e3e30ca tests_bind_high_availability.yml work-tests_bind_high_availability.ymlrHBR08
COMPLETE             OK         PASSED     06e43cbc-0090-41ad-8477-16fe0ff43447 tests_default.yml work-tests_default.yml16nMco
COMPLETE             OK         PASSED     d05aaf71-5075-47a1-b50a-9904cc33b699 tests_default_vars.yml work-tests_default_vars.ymlQdWTmI
GUEST_PROVISIONING   OK         UNDEFINED  unknown                              tests_include_vars_from_parent.yml unknown
GUEST_PROVISIONING   OK         UNDEFINED  unknown                              tests_key_rotation.yml unknown
GUEST_PROVISIONING   OK         UNDEFINED  unknown                              tests_passphrase_temporary.yml unknown
CREATED              OK         UNDEFINED  unknown                              tests_passphrase_temporary_keyfile.yml unknown
```
`Node` is the internal node name used by Jenkins.  `Workspace` is the path to
the directory on the node which is used to hold the test artifacts before they
are published.  For example, if you want to see the ansible results for the
completed tests_bind_high_availability.yml test:
```
ssh -i /path/to/key root@10.0.0.3
cd /var/lib/jenkins/workspace/ci-test-jobname@6
# from here you can see citool-debug.txt, etc.
cat work-tests_bind_high_availability.ymlrHBR08/ansible-output.txt
cat guest-setup-c3767ea3-934c-408d-b42f-d7639e3e30ca/pre-installation-artifact-workaround.txt
etc.
```

### print_task_console

If you just want to see the task output without having to use the web browser:
```
./check_jenkins.py print_task_console 12345 30
... bunch of text here ...
```
This will show the last 30 lines of the console.

# configure_squid

The `configure_squid` directory stores the playbook that you can use to
configure a Squid caching proxy server for caching RPM packages. The playbook
copies the `squid.conf` file to the managed node. The `squid.conf` file 
onfigures Squid to use SSL Bump to cache RPM packages over HTTPS and does some
further configurations required for RPM packages caching. You can compare
`squid.conf` with `squid.conf.default` to see what `squid.conf` adds.

After you configure a squid proxy using this playbook, you must point dnf or yum
to use this proxy. To do that, append the following strings to /etc/yum.conf on
EL 6 or to /etc/dnf/dnf.conf on EL > 6 and Fedora:

```
proxy=http://<squid_server_ip>:3128
sslverify=False
```
