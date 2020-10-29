# Automatic Maintenance

Set of scripts and configuration options to manage tedious tasks across
linux-system-roles repos.

<!--ts-->
  * [shellcheck](#shellcheck)
  * [sync-template.sh](#sync-templatesh)
  * [lsr_role2collection.py](#lsr_role2collectionpy)
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
                       [--replace-dot REPLACE_DOT] [--subrole-prefix SUBROLE_PREFIX]
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
--replace-dot REPLACE_DOT
                     If sub-role name contains dots, replace them with the specified
                     value; default to '_'
--subrole-prefix SUBROLE_PREFIX
                     If sub-role name does not start with the specified value, change
                     the name to start with the value; default to an empty string
```

### environment variables

Each option has corresponding environment variable to set.
```
  --namespace NAMESPACE            COLLECTION_NAMESPACE
  --collection COLLECTION          COLLECTION_NAME
  --src-path SRC_PATH              COLLECTION_SRC_PATH
  --dest-path DEST_PATH            COLLECTION_DEST_PATH
  --role ROLE                      COLLECTION_ROLE
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
python lsr_role2collection.py --role myrole --namespace community --collection test
```

## Example 3
Convert a role myrole located in a custom src-path to a custom dest-path and a custom tests-dest-path

Source role path is /path/to/role_group/myrole.
Destination collections path is /path/to/collections.
```
python lsr_role2collection.py --src-path /path/to/role_group --dest-path /path/to/collections --tests-dest-path /path/to/test_dir --role myrole
```

## Example 4
Convert a role myrole in a github owner "linux-system-roles" located in a custom src-path to a custom dest-path and a custom tests-dest-path

Source role path is /path/to/role_group/myrole.
Destination collections path is /path/to/collections.
```
python lsr_role2collection.py --src-path /path/to/role_group --dest-path /path/to/collections --tests-dest-path /path/to/test_dir --role myrole --src-owner linux-system-roles
```
