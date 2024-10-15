# manage_issues.py

## What is it?

Management of Jira issues - create issues, list issues, other issue management


## Requirements

Python based

Uses the (https://jira.readthedocs.io/)[python jira] library for the Jira REST
API.  This is available in Fedora as the `python3-jira` package.

Uses (https://click.palletsprojects.com/en/8.1.x/)[python click] library for CLI
option/argument management, instead of the built-in python `argparse` library,
which allows more complex option/arguments.  This is available in Fedora as the
`python3-click` package.

### Token

You must have a valid Jira API token.

Log in to your Jira instance.  Go to `Profile -> Personal Access Tokens`.  If
you do not already have a token that you want to use here, go to `Create token`.
Copy the token value to `~/.config/jira.yml` which looks like this:

```yaml
production:
  token: xxxxTheTokenxxxx
  url: https://issues.example.com
current: production
```

Each item is a context e.g. you can use different contexts for production,
staging, test, etc. each with a different url and token.  The `current` item is
the name of the current context you want to use.

## Commands

### create-issue

Create a Jira issue.  There are 3 main ways to create an issue:

* `--github-url` - use the data from a github PR or issue - summary, description, role,
  status, and doc fields will be set, and the new issue will have a remote link
  to the github issue
* `--base-issue` - use the summary, labels, and github remote link from the given issue
* specify all fields individually

#### project

Required - name of Jira project

#### component

Value for Jira component field

#### issue-type

Required if not using `--github-url` - Jira issue type ("Task", "Bug", etc.) - if using `--github-url` then the issue type will be determined by the Conventional Commit
format of the PR title (e.g. `feat:` is `Story`, `fix:` is `Bug`)

#### version

Fix version e.g. `rhel-9.6`

#### itm

Internal target milestone e.g. `19`

#### dtm

Dev target milestone e.g. `15`

#### dev_ack

Set the Dev ack e.g. `Dev ack`

#### status

"In Progress", "Planning", etc. - if using `--github-url`, then will default to
"In Progress" for merged PRs, "Planning" otherwise

#### severity

"Critical", "Moderate", etc.

#### summary

The title of the issue - if using `--github-url`, will use the PR/issue title -
if using `--base-issue`, then you can specify `--summary` with `{issue_summary}`
in the string e.g. `--summary 'packaging work for {issue_summary}'` - this also
works when using `--github-url` for subsequent `create-issue`

#### description

The description of the issue - if using `--github-url`, will use the PR/issue
body - if using `--base-issue`, then you can specify `--description` with
`{issue_summary}` in the string e.g. `--description 'packaging work for
{issue_summary}'` - this also works when using `--github-url` for subsequent
`create-issue`

#### epic-name

This is the name of the epic when creating a `--issue-type Epic` - if using
`--github-url` or `--base-issue` you can use `{issue_summary}` in the string
e.g. `--epic-name '[Epic] for {issue_summary}`


#### role

One or more role names to associate with the issue.  If more than one, specify
the argument multiple times on the command line e.g. `--role kdump --role ssh`

#### doc-text-type

Sets the field `Release Note Type` in the issue - see help for option values -
if using `--github-url` this will be derived like `issue-type`

#### doc-text

The text to use for the `Release Note`.  If using `--github-url`, this will
use the PR body.

#### docs-impact

`Yes` if this will impact documentation, otherwise `No`

#### story-points

Number of story points to assign to issue

#### sprint

Not supported yet

#### label

One or more labels.  To specify more than one, use `--label foo --label bar`

#### product

product

#### epic-issue-link

One or more other issues to assign to the epic when creating an epic.  This is
useful if there are already Jira issues created that you want to link into
the epic `--epic-issue-link PROJECT-123 --epic-issue-link ANOTHER-456`

### dump-issue

Print one or more issues in JSON format.

```bash
manage_issues.py dump-issues PROJECT-123 PROJECT-456 ....
```

### rpm-release

Doing an RPM release requires several types of text - spec file `%changelog`, CHANGELOG.md,
git commit message, and a list of issues.  `rpm-release` will create those for you in
several files - `cl-spec`, `cl-md`, `git-commit-msg`, and `issue-list`.

```bash
manage_issues.py --project PROJECT --component my-package --rpm-version 1.90.0-0.1 \
  --status "In Progress" --version rhel-9.6
```

#### project

Required - name of Jira project

#### component

Value for Jira component field

#### issue-type

Jira issue type ("Task", "Bug", etc.) - default is `("Bug", "Story")`

#### version

Fix version e.g. `rhel-9.6`

#### status

Issue status - default is `"In Progress"`

#### role

One or more role names to associate with the issue.  If more than one, specify
the argument multiple times on the command line e.g. `--role kdump --role ssh`

#### label

One or more labels.  To specify more than one, use `--label foo --label bar`

#### fields

One or more fields to return in the search.  The default is `("summary", "labels", "issuetype")`
The code right now is more or less hard coded to expect and output these fields.

#### jql

A Jira JQL query to use in the search rather than a search string constructed from
the options above.

#### rpm-version

This is the version number to use for the RPM update e.g. `1.88.9-0.1`.  This will
be used in `cl-spec`, `cl-md`, and `git-commit-msg`.

## Examples

Create a product bug/story in the product project from a github PR, an upstream
tracking task, a downstream packaging task, and an epic to contain them:

```bash
manage_issues.py create-issue --project PRODPROJ --component my-component \
    --github-url https://github.com/linux-system-roles/ROLE/pull/999 --version rhel-9.6 --itm 26 --dtm 22 --story-points 5 --status New --severity Low \
  create-issue --project TEAM --summary 'upstream work for {issue_summary}' \
    --description 'upstream work for {issue_summary}' --issue-type Task --story-points 1 \
    --label upstream --status "In Progress" \
  create-issue --project TEAM --summary 'packaging work for {issue_summary}' \
    --description 'packaging work for {issue_summary}' --issue-type Task --story-points 1 \
    --label packaging \
  create-issue --project TEAM --issue-type Epic --epic-name '[Epic]: {issue_summary}' \
    --summary '[Epic]: {issue_summary}' \
    --description 'tracker for all tasks related to {issue_summary}'
```

There is already a `PRODPROJ` issue, and we just want to create the other tracking
tasks/epics in our TEAM project, plus add a link to another issue to the epic -
this assumes `PRODPROJ-999` already has a label like `system_role_ROLENAME`, and
has a remote link to the github PR/issue:

```bash
manage_issues.py create-issue --base-issue PRODPROJ-999 --project TEAM \
    --summary 'upstream work for {issue_summary}' \
    --description 'upstream work for {issue_summary}' --issue-type Task --story-points 1 \
    --label upstream --status "In Progress" \
  create-issue --base-issue PRODPROJ-999 --project TEAM \
    --summary 'packaging work for {issue_summary}' \
    --description 'packaging work for {issue_summary}' --issue-type Task --story-points 1 \
    --label packaging \
  create-issue  --base-issue PRODPROJ-999 --project TEAM --issue-type Epic \
    --epic-name '[Epic]: {issue_summary}' --summary '[Epic]: {issue_summary}' \
    --description 'tracker for all tasks related to {issue_summary}' \
    --epic-issue-link ANOTHER-555
```
