# Automatic Maintenance

Set of scripts and configuration options to manage tedious tasks across
linux-system-roles repos.

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
