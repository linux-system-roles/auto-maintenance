#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT
"""This script is used to manage Bugzilla and Jira issues
List and perform various lifecycle tasks
"""

import datetime
import click
import json
import logging
import os
import requests
import signal
import sys

from jira import JIRA
from operator import attrgetter

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

cfg = yaml.safe_load(open(os.path.join(os.environ["HOME"], ".config", "jira.yml")))
url = cfg[cfg["current"]]["url"]
token = cfg[cfg["current"]]["token"]

# jira = JIRA(url, token_auth=token, get_server_info=False, options={"rest_api_version": "3"})
jira = JIRA(url, token_auth=token)

# key is project
# value is dict
#   key is name or id - value is id or name corresponding
ISSUE_TYPES_TO_ID = {}  # key is name or id - value is id
ISSUE_TYPES_TO_NAME = {}  # key is name or id - value is name
# key is project
# value is dict
#   key is issue type name or id
#   value is dict
#     key is field name or field id
#     value data about field
ISSUE_TYPE_FIELDS = {}


def __ensure_project_issue_types(project):
    if project in ISSUE_TYPES_TO_NAME:
        return
    for issue_type in jira.project_issue_types(project, maxResults=999):
        ISSUE_TYPES_TO_ID.setdefault(project, {})[issue_type.name] = issue_type.id
        ISSUE_TYPES_TO_ID.setdefault(project, {})[issue_type.id] = issue_type.id
        ISSUE_TYPES_TO_NAME.setdefault(project, {})[issue_type.id] = issue_type.name
        ISSUE_TYPES_TO_NAME.setdefault(project, {})[issue_type.name] = issue_type.name


def __ensure_project_issue_fields(project, issue_type):
    __ensure_project_issue_types(project)
    if project in ISSUE_TYPE_FIELDS and issue_type in ISSUE_TYPE_FIELDS[project]:
        return
    issue_type_id = ISSUE_TYPES_TO_ID[project][issue_type]
    for field in jira.project_issue_fields(project, issue_type_id, maxResults=999):
        rec = field.raw
        for name in ("items", "custom", "system"):
            if not rec["schema"].get(name):
                rec["schema"][name] = None
        rec["project"] = project
        rec["issue_type"] = ISSUE_TYPES_TO_NAME[project][issue_type]
        rec["is_create_field"] = True
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(rec["issue_type"], {})[
            field.name
        ] = rec
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(rec["issue_type"], {})[
            field.fieldId
        ] = rec
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(issue_type_id, {})[
            field.name
        ] = rec
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(issue_type_id, {})[
            field.fieldId
        ] = rec


def __update_issue_type_fields(issue):
    project = issue.get_field("project").key
    issue_type = issue.get_field("issuetype").name
    __ensure_project_issue_fields(project, issue_type)
    issue_type_id = ISSUE_TYPES_TO_ID[project][issue_type]
    for field_id, rec in jira.editmeta(issue.key)["fields"].items():
        field_data = (
            ISSUE_TYPE_FIELDS.get(project, {}).get(issue_type, {}).get(field_id)
        )
        if field_data:
            logging.debug(
                "field [%s] already exists for project [%s] type [%s]",
                field_id,
                project,
                issue_type,
            )
            continue  # do not replace/overwrite existing fields
        for name in ("items", "custom", "system"):
            if not rec["schema"].get(name):
                rec["schema"][name] = None
        rec["project"] = project
        rec["issue_type"] = ISSUE_TYPES_TO_NAME[project][issue_type]
        rec["is_create_field"] = False
        field_name = rec["name"]
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(issue_type, {})[
            field_name
        ] = rec
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(issue_type, {})[
            field_id
        ] = rec
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(issue_type_id, {})[
            field_name
        ] = rec
        ISSUE_TYPE_FIELDS.setdefault(project, {}).setdefault(issue_type_id, {})[
            field_id
        ] = rec


def get_github_issue_pr(ctx):
    response = requests.get(ctx["github_url_api"])
    rv = response.json()
    rv["is_pull"] = "pull_request" in rv
    if rv["is_pull"]:
        response = requests.get(ctx["github_url_api_pr_merge"])
        rv["is_merged"] = response.status_code == 204
    else:
        rv["is_merged"] = False
    return rv


def get_update_value(project, issue_type, field_name_or_id, value, is_create):
    """Given a project, a field name or id, and a value, and a flag to indicate
    if this is for a create operation or an edit operation, return the value in
    the correct format for a create or edit operation."""
    __ensure_project_issue_fields(project, issue_type)
    field_data = ISSUE_TYPE_FIELDS[project][issue_type].get(field_name_or_id)
    if not field_data:
        return None  # possibly an edit only field?
    if field_data["is_create_field"] != is_create:
        return None  # field is not for this operation
    schema = field_data["schema"]
    if schema["type"] == "int":
        rv = int(value)
    elif schema["type"] == "number":
        rv = float(value)
    elif schema["type"] == "string" or schema["type"] == "any":
        rv = str(value)
    elif schema["type"] == "option":
        rv = {"value": str(value)}
    elif schema["type"] == "array":
        if isinstance(value, list):
            rv = value
        elif isinstance(value, tuple):
            rv = list(value)  # convert to list
        elif schema["items"] == "int":
            rv = [int(value)]
        elif schema["items"] == "number":
            rv = [float(value)]
        elif schema["items"] == "string" or schema["type"] == "any":
            rv = [str(value)]
        elif schema["items"] == "option":
            rv = [{"value": str(value)}]
        elif schema["system"]:
            rv = [{"name": str(value)}]
    elif schema["system"]:
        rv = {"name": str(value)}
    return {field_data["fieldId"]: rv}


# NOTE: Some fields specified here may not be available
# for the specified project and issue_type - we don't know
# that for sure until we call __update_issue_type_fields to
# get the editmeta - in that case, don't assume an error, but
# log to info
def __update_jira_issue(issue, fields):
    __update_issue_type_fields(issue)
    project = issue.get_field("project").key
    issue_type = issue.get_field("issuetype").name
    update_fields = {}
    for field_name, field_value in fields.items():
        # look for an update-only field first
        update_item = get_update_value(
            project, issue_type, field_name, field_value, False
        )
        if not update_item:
            # create fields can also be updated
            update_item = get_update_value(
                project, issue_type, field_name, field_value, True
            )
        if not update_item:
            logging.info("Field [%s] could not be found for project [%s] type [%s]", field_name, project, issue_type)
        else:
            update_fields.update(update_item)
    if update_fields:
        issue.update(fields=update_fields)
    return issue


def __create_jira_issue(fields):
    issue_type = fields.pop("issuetype")
    project = fields.pop("project")
    __ensure_project_issue_fields(project, issue_type)
    create_fields = {"project": project, "issuetype": issue_type}
    # update fields cannot be passed in the create op, so update after create
    update_fields = {}
    for field_name, field_value in fields.items():
        update_value = get_update_value(
            project, issue_type, field_name, field_value, True
        )
        if update_value:
            create_fields.update(update_value)
        else:
            update_fields[field_name] = field_value  # candidate for update
    issue = jira.create_issue(fields=create_fields)
    if update_fields:
        issue = __update_jira_issue(issue, update_fields)
    return issue


def __github_to_args(ctx):
    """Update fields in args with given github_url."""
    ary = ctx["github_url"].split("/")
    ctx["github_url_api"] = (
        "https://api.github.com/repos/" + ary[3] + "/" + ary[4] + "/issues/" + ary[-1]
    )
    ctx["github_url_api_pr_merge"] = (
        "https://api.github.com/repos/"
        + ary[3]
        + "/"
        + ary[4]
        + "/pulls/"
        + ary[-1]
        + "/merge"
    )
    gh_issue = get_github_issue_pr(ctx)
    if not ctx["summary"]:
        ctx["summary"] = gh_issue["title"]
    if not ctx["description"]:
        ctx["description"] = gh_issue["body"].replace("\r", "")
    if not ctx["issue_type"]:
        if ctx["summary"].startswith("feat: "):
            ctx["issue_type"] = "Story"
        elif ctx["summary"].startswith("fix: "):
            ctx["issue_type"] = "Bug"
        else:
            ctx["issue_type"] = "Bug"  # user should give ctx["issue_type"] in this case
    if not ctx["role"]:
        ary = ctx["github_url"].split("/")
        if ary[3] == "linux-system-roles":
            ctx["role"] = [ary[4]]
        elif ary[3] == "willshersystems" and ary[4] == "ansible-sshd":
            ctx["role"] = ["sshd"]
        elif ary[3] == "performancecopilot" and ary[4] == "ansible-pcp":
            ctx["role"] = ["metrics"]
        else:
            raise Exception("unknown url " + ctx["github_url"])
    if not ctx["status"]:
        if gh_issue["is_merged"]:
            ctx["status"] = "In Progress"
        else:
            ctx["status"] = "Planning"
    if not ctx["dev_ack"]:
        if gh_issue["is_pull"]:
            ctx["dev_ack"] = "Dev ack"
    if not ctx["doc_text_type"]:
        if ctx["issue_type"] == "Story":
            ctx["doc_text_type"] = "Enhancement"
        elif ctx["issue_type"] == "Bug":
            ctx["doc_text_type"] = "Bug Fix"
    if not ctx["doc_text"]:
        if gh_issue["is_pull"]:
            ctx["doc_text"] = ctx["description"]
    if not ctx["docs_impact"]:
        if ctx["doc_text_type"]:
            ctx["docs_impact"] = "Yes"
        else:
            ctx["docs_impact"] = "No"


# these are all fields that can use the string format method
# to construct the final value from variables derived from
# previous issues
TEMPLATE_FIELDS = ["description", "epic_name", "summary"]


# this handles creating the jira issue, updating it,
# doing the status transition, adding links, etc.
def __create_issue(kwargs):
    remote_link_data = kwargs.get("remote_link_data", {})
    if kwargs["github_url"]:
        # update missing args with fields from given github issue/pr
        __github_to_args(kwargs)
        remote_link_data = {
            "url": kwargs["github_url"],
            "title": "link to github issue",
        }
    if kwargs["project"] == "RHEL" and not kwargs["component"]:
        kwargs["component"] = "rhel-system-roles"
    if kwargs["issue_type"] == "Epic":
        if not kwargs["epic_name"]:
            kwargs["epic_name"] = kwargs["summary"]
        elif not kwargs["summary"]:
            kwargs["summary"] = kwargs["epic_name"]
    if not kwargs.get("issue_summary"):
        kwargs["issue_summary"] = kwargs["summary"]
    else:
        for field in TEMPLATE_FIELDS:
            if kwargs[field]:
                kwargs[field] = kwargs[field].format(
                    issue_summary=kwargs["issue_summary"]
                )
    # convert args to jira create/update fields
    fields = {}
    for arg_field, jira_field in ARGS_TO_JIRA_FIELDS.items():
        val = kwargs[arg_field]
        if val:
            fields[jira_field] = val
    if kwargs["label"]:
        fields["labels"] = list(kwargs["label"])  # is a list
    if kwargs["role"]:
        val = ["system_role_" + ii for ii in kwargs["role"]]
        if "labels" in fields:
            fields["labels"].extend(val)
        else:
            fields["labels"] = val

    issue = __create_jira_issue(fields)
    if kwargs["status"]:
        jira.transition_issue(issue, kwargs["status"])
    if remote_link_data:
        jira.add_simple_link(issue.key, remote_link_data)
    if kwargs["github_url"]:
        if not kwargs.get("base_issue"):
            kwargs["base_issue"] = issue.key
        if not kwargs.get("remote_link_data"):
            kwargs["remote_link_data"] = remote_link_data
    return issue


# does not work
def createmeta(args):
    print(jira.createmeta(projectKeys=args.project, issuetypeNames=args.issue_type))


def editmeta(args):
    json.dump(jira.editmeta(args.params[0])["fields"], sys.stdout, indent=2)


def project_issue_types(args):
    __ensure_project_issue_types(args.project)
    json.dump(ISSUE_TYPES_TO_NAME[args.project], sys.stdout, indent=2)
    print("")


def project_issue_fields(args):
    __ensure_project_issue_types(args.project)
    for issue_type in ISSUE_TYPES_TO_ID[args.project].keys():
        try:
            if int(issue_type):
                __ensure_project_issue_fields(args.project, issue_type)
                print(
                    "Project",
                    args.project,
                    "issue_type",
                    ISSUE_TYPES_TO_NAME[args.project][issue_type],
                )
                json.dump(
                    ISSUE_TYPE_FIELDS[args.project][issue_type], sys.stdout, indent=2
                )
                print("")
        except ValueError:
            pass

@click.command()
@click.argument("keys", nargs=-1)
def dump_issue(keys):
    """Dump an issue."""
    for key in keys:
        issue = jira.issue(key)
        json.dump(issue.raw, sys.stdout, indent=2)
        print("\n")


def __list_issues(jql, fields):
    return jira.search_issues(jql, fields=fields)


KEY_TO_JQL = {
    "version": "fixVersion",
    "issue_type": "type",
}


def __key_to_jql(key):
    return KEY_TO_JQL.get(key, key)


def __format_as_jql_clause(key, val, op="="):
    clause = ""
    jql_key = __key_to_jql(key)
    if isinstance(val, (list, tuple)):
        if len(val) == 1:
            clause = f'"{jql_key}" {op} "{val[0]}"'
        else:
            clause = f'"{jql_key}" in {val}'
    else:
        clause = f'"{jql_key}" {op} "{val}"'
    return clause


@click.command()
@click.option("--component", type=str, help="component")
@click.option(
    "--rpm-version",
    type=str,
    required=True,
    help="RPM version",
)
@click.option(
    "--version",
    type=str,
    required=True,
    help="Internal Target Release e.g. rhel-9.6",
)
@click.option(
    "--status",
    type=str,
    default="In Progress",
    help="issue status",
)
@click.option(
    "--project",
    type=str,
    required=True,
    help="Project for issues",
)
@click.option(
    "--issue-type",
    type=click.Choice(["Bug", "Story", "Task", "Epic"], case_sensitive=False),
    multiple=True,
    default=("Bug", "Story"),
    help="Type of issue",
)
@click.option(
    "--role",
    multiple=True,
    help="One or more role names",
)
@click.option(
    "--label",
    multiple=True,
    help="labels",
)
@click.option(
    "--jql",
    default="",
    help="JQL string to use",
)
@click.option(
    "--fields",
    multiple=True,
    default=("summary", "labels", "issuetype"),
    help="labels",
)
def rpm_release(**kwargs):
    """Create files used for rpm release data."""
    rpm_version = kwargs.pop("rpm_version")
    fields = list(kwargs.pop("fields"))
    jql = kwargs.pop("jql")
    roles = list(kwargs.pop("role"))
    issue_type = kwargs.pop("issue_type")
    if not jql:
        for key, val in kwargs.items():
            if val:
                clause = __format_as_jql_clause(key, val)
                if jql:
                    jql = jql + " AND " + clause
                else:
                    jql = clause
    issues = __list_issues(jql, fields)
    if not issues:
        logging.error("Error: no issues match %s", jql)
        sys.exit(1)
    # add a role attr to each issue for later sorting by role in alpha order
    for issue in issues:
        roles = []
        for label in issue.get_field("labels"):
            if not label.startswith("system_role_"):
                continue
            role = label.replace("system_role_", "")
            roles.append(role)
        role_str = ",".join(sorted(roles))
        setattr(issue, "role", role_str)
    spec_lines = []
    cl_story_lines = []
    cl_bug_lines = []
    git_commit_lines = []
    list_lines = []
    for issue in sorted(issues, key=attrgetter("role")):
        key = issue.key
        role = f"{issue.role} - " if issue.role else ""
        summary = issue.get_field("summary")
        issue_type = issue.get_field("issuetype").name
        line = f"Resolves: {key} : {role}{summary}\n"
        git_commit_lines.append(line)
        spec_lines.append("- " + line)
        line = f"- [{role}{summary}]({issue.permalink()})\n"
        if issue_type == "Story":
            cl_story_lines.append(line)
        else:
            cl_bug_lines.append(line)
        list_lines.append(key)
    now = datetime.datetime.now()
    dt_spec = now.strftime("%a %b %d %Y")
    dt_cl = now.strftime("%Y-%m-%d")
    with open("cl-spec", "w") as out:
        out.write(f"* {dt_spec} Your Name <email@redhat.com> - {rpm_version}\n")
        out.writelines(spec_lines)
    with open("cl-md", "w") as out:
        out.write(f"[{rpm_version}] - {dt_cl}\n")
        out.write("----------------------------\n\n")
        out.write("### New Features\n\n")
        if cl_story_lines:
            out.writelines(cl_story_lines)
        else:
            out.write("- none\n")
        out.write("\n### Bug Fixes\n\n")
        if cl_bug_lines:
            out.writelines(cl_bug_lines)
        else:
            out.write("- none\n")
    with open("git-commit-msg", "w") as out:
        out.write(f"System Roles update for {rpm_version}\n\n")
        out.writelines(git_commit_lines)
    with open("issue-list", "w") as out:
        out.write(" ".join(list_lines) + "\n")


# for simple fields, map the name used when giving
# an argument to the name used with the Jira api
# fields not listed here require special handling
# or a different api (e.g. status is a transition)
ARGS_TO_JIRA_FIELDS = {
    "project": "project",
    "issue_type": "issuetype",
    "summary": "summary",
    "epic_name": "Epic Name",
    "description": "description",
    "component": "components",
    "version": "fixVersions",
    "itm": "Internal Target Milestone",
    "dtm": "Dev Target Milestone",
    "dev_ack": "ACKs Check",
    "story_points": "Story Points",
    "sprint": "Sprint",
    "doc_text_type": "Release Note Type",
    "doc_text": "Release Note Text",
    "docs_impact": "Product Documentation Required",
    "product": "Products",
    "severity": "Severity",
}

create_issues = []


@click.command()
@click.option("--component", type=str, help="component")
@click.option(
    "--github-url",
    type=str,
    help="https url of github issue or pr used to create or update jira issue",
)
@click.option(
    "--version",
    type=str,
    help="Internal Target Release e.g. rhel-9.6",
)
@click.option(
    "--itm",
    type=int,
    help="Internal Target Milestone",
)
@click.option(
    "--dtm",
    type=int,
    help="Dev Target Milestone",
)
@click.option(
    "--dev-ack",
    type=str,
    help="Give dev ack",
)
@click.option(
    "--status",
    type=str,
    help="issue status",
)
@click.option(
    "--project",
    type=str,
    required=True,
    help="Project for issues",
)
@click.option(
    "--issue-type",
    type=click.Choice(["Bug", "Story", "Task", "Epic"], case_sensitive=False),
    help="Type of issue",
)
@click.option(
    "--severity",
    type=click.Choice(["Critical", "Important", "Moderate", "Low"], case_sensitive=False),
    default="Low",
    help="Severity of issue",
)
@click.option(
    "--summary",
    type=str,
    help="Issue summary - short title for issue",
)
@click.option(
    "--epic-name",
    type=str,
    help="Epic name - required for epics",
)
@click.option(
    "--description",
    type=str,
    help="Issue description - long, multiline information about issue",
)
@click.option(
    "--role",
    multiple=True,
    help="One or more role names",
)
@click.option(
    "--doc-text-type",
    type=click.Choice(["Bug Fix", "CVE - Common Vulnerabilities and Exposures", "Enhancement", "Release Note Not Required"], case_sensitive=False),
    help="release note type",
)
@click.option(
    "--doc-text",
    type=str,
    help="release note text",
)
@click.option(
    "--docs-impact",
    type=str,
    help="will docs be impacted, yes or no",
)
@click.option(
    "--story-points",
    type=float,
    help="story points",
)
@click.option(
    "--sprint",
    type=str,
    help="sprint",
)
@click.option(
    "--label",
    multiple=True,
    help="labels",
)
@click.option(
    "--product",
    type=str,
    help="product",
)
@click.option(
    "--base-issue",
    type=str,
    help="Issue to use for summary and other fields and to link to epic",
)
def create_issue(**kwargs):
    """Create an issue."""
    # just append the arguments to the list, so we can process instances
    # where there are multiple issues and an epic
    create_issues.append(kwargs)


@click.group(chain=True)
@click.option("--debug", is_flag=True)
def cli(debug):
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


cli.add_command(create_issue)
cli.add_command(dump_issue)
cli.add_command(rpm_release)

def __update_data_from_base_issue(base_issue, data):
    data["issue_summary"] = base_issue.get_field("summary")
    for label in base_issue.get_field("labels"):
        if label.startswith("system_role_"):
            if not isinstance(data["label"], list):
                data["label"] = list(data["label"])
            if not label in data["label"]:
                data["label"].append(label)
    # update links to include github link, if any
    if not data.get("remote_link_data"):
        base_links = jira.remote_links(base_issue.key)
        for link in base_links:
            if link.raw["object"]["url"].startswith("https://github.com"):
                data["remote_link_data"] = link.raw
                break


def main():
    try:
        cli(auto_envvar_prefix="LSR")
    except SystemExit as se:
        if se.code != 0:
            raise se
    # this is where we do the actual processing for create_issue
    issue_keys = set()
    issues = []
    epic_issue = None
    issue_summary = None
    for data in create_issues:
        data["issue_summary"] = issue_summary
        base_issue_key = data.pop("base_issue", None)
        if base_issue_key:
            base_issue = jira.issue(base_issue_key)
            __update_data_from_base_issue(base_issue, data)
            if not base_issue_key in issue_keys:
                issue_keys.add(base_issue_key)
                issues.append(base_issue)
        issue = __create_issue(data)
        issue_summary = data["issue_summary"]
        if data.get("issue_type", "").lower() == "epic":
            epic_issue = issue
        else:
            issue_keys.add(issue.key)
            issues.append(issue)
    if epic_issue:
        jira.add_issues_to_epic(epic_issue.id, list(issue_keys))
        print(epic_issue.permalink(), epic_issue.get_field("summary"))
    for issue in issues:
        print(issue.permalink(), issue.get_field("summary"))


if __name__ == "__main__":
    sys.exit(main())
