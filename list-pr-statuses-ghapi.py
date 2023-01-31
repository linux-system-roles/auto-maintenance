#!/usr/bin/python3 -u
"""Check PR statuses for linux-system-roles github"""

import argparse
import datetime
import itertools
import os
import re
import sys
import logging
import yaml
from collections import OrderedDict
from ghapi.all import GhApi
from ghapi.page import paged as gh_paged
from ghapi.core import gh2date
from operator import attrgetter

DEFAULT_EXCLUDES = [
    ".github",
    "auto-maintenance",
    "ci-testing",
    "experimental-azure-firstboot",
    "image_builder",
    "linux-system-roles.github.io",
    "lsr-gh-action-py26",
    "meta_test",
    "sap-base-settings",
    "sap-hana-preconfigure",
    "sap-netweaver-preconfigure",
    "sap-preconfigure",
    "test-harness",
    "tox-lsr",
    "tuned",
]

DEFAULT_ANSIBLES = ["ansible-2.9", "ansible-2.12", "ansible-2.13", "ansible-2.14"]

DEFAULT_PLATFORMS = [
    "centos-6",
    "centos-7",
    "centos-8",
    "fedora-36",
    "fedora-37",
    "rhel-6",
    "rhel-7",
    "rhel-8-y",
    "rhel-8",
    "rhel-x",
]

DEFAULT_STATES = ["pending", "failure", "success", "abandoned", "error"]

DEFAULT_ENVIRONMENTS = ["el7", "staging", "production"]


def match_environment(env, status, args):
    if status.context.startswith("linux-system-roles-test/"):
        env = "production"
    elif status.context.startswith("linux-system-roles-test-staging/"):
        env = "staging"
    elif env.endswith(" (staging)"):
        env = "staging"
    elif env.endswith(" (el7)"):
        env = "el7"
    elif env == "/(citool)":
        env = "production"
    else:
        env = "production"
    return env in args.env


def match_ansible(ansible, args):
    return ansible in args.ansible


def match_platform(platform, args):
    return args.platform is None or platform in args.platform


def match_user(user, args):
    if not args.user:
        return True
    return user in args.user


def conv_to_aware(dt, tz="+00:00"):
    """Convert a naive dt object to an aware dt object using the given string offset timezone"""
    if isinstance(dt, datetime.datetime):
        if dt.microsecond:
            return datetime.datetime.strptime(str(dt) + tz, "%Y-%m-%d %H:%M:%S.%f%z")
        else:
            return datetime.datetime.strptime(str(dt) + tz, "%Y-%m-%d %H:%M:%S%z")
    else:
        return gh2date(dt.replace("Z", "+00:00"))


datetime_min = conv_to_aware(datetime.datetime.min)
datetime_max = conv_to_aware(datetime.datetime.max)


def gh_iter(op, subfield, *args, **kwargs):
    """Hide paging iterator details from callers."""
    for attr in ["page", "per_page"]:
        if attr not in op.params:
            op.params.append(attr)
    pages = gh_paged(op, *args, **kwargs)
    for page in pages:
        if subfield:
            items = getattr(page, subfield)
            if not items:
                pages.close()
            for subitem in items:
                yield subitem
        else:
            for item in page:
                yield item


class Summary(OrderedDict):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getattr__(self, key):
        self.__setattr__(key, 0)
        return 0


def get_statuses(gh, args, repo, pr, updated_since):
    excluded_statuses = set()
    statuses = Summary(oldest=datetime_max, newest=datetime_min)
    for status in gh_iter(
        gh.repos.get_combined_status_for_ref,
        "statuses",
        owner=args.org,
        repo=repo.name,
        ref=pr.head.sha,
        per_page=99,
    ):
        logging.debug(
            f"\t\t\t{status.state} {status.context} {status.updated_at} {status.description}"
        )
        updated_at_conv = conv_to_aware(status.updated_at)
        seen_status = statuses.get(status.context)
        if seen_status is None or seen_status.updated_at < updated_at_conv:
            statuses.count += 1
            # e.g. fedora-33/ansible-2.9 OR fedora-33/ansible-2.9 (staging)
            match = re.match(r"([^/]+)/([^ /]+)(.*)", status.context)
            if not match or not len(match.groups()) == 3:
                logging.debug(f"unknown context {status.context}")
                continue
            platform, ansible, environment = match.groups()
            if not ansible.startswith("ansible-"):
                logging.debug(f"unknown context {status.context}")
                continue
            if (
                status.state in args.state
                and match_environment(environment, status, args)
                and match_ansible(ansible, args)
                and match_platform(platform, args)
                and (not args.updated_since or updated_at_conv > updated_since)
            ):
                setattr(status, "updated_at_conv", updated_at_conv)
                setattr(status, "ansible", ansible)
                setattr(status, "platform", platform)
                setattr(status, "env", environment)
                statuses[status.context] = status
                if status.state == "pending":
                    statuses.pending += 1
                elif status.state != "success":
                    statuses.failed += 1
                if statuses.oldest > updated_at_conv:
                    statuses.oldest = updated_at_conv
                if statuses.newest < updated_at_conv:
                    statuses.newest = updated_at_conv
            else:
                excluded_statuses.add(status.context)
    return statuses, excluded_statuses


def get_checks(gh, args, repo, pr):
    checks = Summary(
        oldest_start=datetime_max,
        newest_start=datetime_min,
        oldest_finish=datetime_max,
        newest_finish=datetime_min,
    )
    for check_run in gh_iter(
        gh.checks.list_for_ref,
        "check_runs",
        owner=args.org,
        repo=repo.name,
        ref=pr.head.sha,
        per_page=99,
    ):
        checks.count += 1
        setattr(check_run, "started_at_conv", conv_to_aware(check_run.started_at))
        if checks.oldest_start > check_run.started_at_conv:
            checks.oldest_start = check_run.started_at_conv
        if checks.newest_start < check_run.started_at_conv:
            checks.newest_start = check_run.started_at_conv
        if check_run.status != "completed":
            checks.pending += 1
        else:
            setattr(
                check_run, "completed_at_conv", conv_to_aware(check_run.completed_at)
            )
            if checks.oldest_finish > check_run.completed_at_conv:
                checks.oldest_finish = check_run.completed_at_conv
            if checks.newest_finish < check_run.completed_at_conv:
                checks.newest_finish = check_run.completed_at_conv
            if check_run.conclusion not in ["success", "neutral"]:
                checks.failed += 1
        checks[check_run.name] = check_run
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        help="github oauth token",
    )
    parser.add_argument(
        "--exclude",
        default=DEFAULT_EXCLUDES,
        action="append",
        help="repos to exclude",
    )
    parser.add_argument(
        "--include",
        default=[],
        action="append",
        help="repos to include",
    )
    parser.add_argument(
        "--org",
        default="linux-system-roles",
        help="github organization",
    )
    parser.add_argument(
        "--state",
        action="append",
        help="only show statuses that have these states",
    )
    parser.add_argument(
        "--env",
        action="append",
        help="only show statuses from these environments",
    )
    parser.add_argument(
        "--ansible",
        action="append",
        help="only show statuses from tests with these versions of ansible",
    )
    parser.add_argument(
        "--platform",
        action="append",
        help="only show statuses from tests with these platforms",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v -v to increase verbosity",
    )
    parser.add_argument(
        "--user",
        action="append",
        help="only show statuses from PRs submitted by these users",
    )
    parser.add_argument(
        "--updated-since",
        action="store",
        default=0,
        type=int,
        help="only show statuses updated since this many hours ago",
    )
    parser.add_argument(
        "--sort-spec",
        action="append",
        default=[],
        help="sort PRs by these criteria",
    )
    parser.add_argument(
        "--stat-type",
        choices=["status", "check", "both"],
        default="both",
        help="Return only statuses or checks",
    )

    args = parser.parse_args()
    if not args.state:
        args.state = DEFAULT_STATES
    if not args.env:
        args.env = DEFAULT_ENVIRONMENTS
    if not args.ansible:
        args.ansible = DEFAULT_ANSIBLES
    if not args.token:
        with open(f"{os.environ['HOME']}/.config/gh/hosts.yml") as gh_conf:
            hsh = yaml.safe_load(gh_conf)
            args.token = hsh["github.com"]["oauth_token"]
    no_status_error_time = datetime.timedelta(hours=8)
    pending_error_time = datetime.timedelta(hours=8)
    status_env = ["" if xx == "production" else " (staging)" for xx in args.env]
    if args.platform:
        required_statuses = set(
            [
                f"{platform}/{ansible}{env}"
                for platform, ansible, env in itertools.product(
                    args.platform, args.ansible, status_env
                )
                if not (platform.startswith("fedora-") and ansible.endswith("-2.9"))
            ]
        )
    else:
        required_statuses = []

    prs = []
    gh = GhApi(token=args.token)
    rate_limit = gh.rate_limit.get()
    print(f"github limit remaining is {rate_limit.rate.remaining}")
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    logging.debug(f"time now is {now}")

    # gather the data
    for repo in gh_iter(gh.repos.list_for_org, "", args.org, per_page=100):
        if repo.name in args.exclude:
            logging.debug(f"Excluding repo {repo.name}")
            continue
        if args.include and repo.name not in args.include:
            logging.debug(f"repo not included {repo.name}")
            continue
        for pr in gh_iter(
            gh.pulls.list,
            "",
            owner=args.org,
            repo=repo.name,
            state="open",
            sort="created",
            per_page=100,
        ):
            if not match_user(pr.user.login, args):
                continue
            pr_updated_at = conv_to_aware(pr.updated_at)
            if args.updated_since:
                updated_since = now - datetime.timedelta(hours=args.updated_since)
            else:
                updated_since = None
            if args.stat_type in ["both", "status"]:
                statuses, excluded_statuses = get_statuses(
                    gh, args, repo, pr, updated_since
                )
                setattr(pr, "statuses", statuses)
                setattr(pr, "excluded_statuses", excluded_statuses)
                if args.stat_type == "status":
                    setattr(pr, "checks", [])
            if args.stat_type in ["both", "check"]:
                checks = get_checks(gh, args, repo, pr)
                setattr(pr, "checks", checks)
                if args.stat_type == "check":
                    setattr(pr, "statuses", [])
                    setattr(pr, "excluded_statuses", [])
            setattr(pr, "updated_at_conv", pr_updated_at)
            prs.append(pr)

    # sort the list by the field of pr
    # updated_at_conv
    # statuses.oldest
    # statuses.newest
    # checks.oldest_start
    # checks.newest_start
    # checks.oldest_finish
    # checks.newest_finish
    # statuses.failed
    # checks.failed
    # statuses.pending
    # checks.pending
    for raw_key in args.sort_spec:
        match = re.match(r"^(.+?)([-+])?$", raw_key)
        key = match.group(1)
        rev = match.group(2) == "-"
        prs.sort(key=attrgetter(key), reverse=rev)

    # report the data
    for pr in prs:
        indent = ""
        print(f"{indent}PR {pr.base.repo.name}#{pr.number} {pr.title}")
        indent += "  "
        print(f"{indent}{pr.user.login} Updated:{pr.updated_at} {pr.html_url}")
        checks = pr.checks
        statuses = pr.statuses
        excluded_statuses = pr.excluded_statuses
        if not checks:
            print(f"{indent}no checks for PR")
        elif checks.pending or checks.failed:
            print(
                f"{indent}checks: {checks.count} total - {checks.pending} pending - {checks.failed} failed"
            )
            if args.verbose:
                for name, check_run in checks.items():
                    print(
                        f"{indent}  {name} status {check_run.status} conclusion {check_run.conclusion} "
                        f"started_at {check_run.started_at} completed_at {check_run.completed_at}"
                    )
        else:
            print(f"{indent}checks: {checks.count} total all passed")

        if not statuses and now - pr_updated_at > no_status_error_time:
            print(f"{indent}problem - PR has no status after {no_status_error_time}")
        elif not statuses:
            print(f"{indent}no status for PR")
        else:
            for context in required_statuses:
                if context not in statuses and context not in excluded_statuses:
                    statuses.missing += 1
                    status = argparse.Namespace()
                    setattr(status, "state", "missing")
                    statuses[context] = status
            if statuses.pending or statuses.failed or statuses.missing:
                print(
                    f"{indent}statuses: matched {len(statuses)} out of {statuses.count} total "
                    f"- {statuses.pending} pending "
                    f"- {statuses.failed} failed - {statuses.missing} missing"
                )
                oldest_pending_status = None
                oldest_pending_status_dt = None
                for context, status in statuses.items():
                    if args.verbose:
                        if status.state == "missing":
                            print(f"{indent}  {context} is missing")
                            continue
                        print(
                            f"{indent}  {context} status {status.state} updated {status.updated_at}"
                        )
                    if status.state == "pending" and (
                        not oldest_pending_status_dt
                        or status.updated_at_conv < oldest_pending_status_dt
                    ):
                        oldest_pending_status_dt = status.updated_at_conv
                        oldest_pending_status = status
                if oldest_pending_status:
                    status_age = now - oldest_pending_status_dt
                    print(
                        f"{indent}oldest pending status is {oldest_pending_status_dt} for "
                        f"status {oldest_pending_status.context} diff {status_age}"
                    )
                    if status_age > pending_error_time:
                        print(
                            f"{indent}possible hang - age of {oldest_pending_status_dt} for "
                            f"status {oldest_pending_status.context}"
                        )
            else:
                print(
                    f"{indent}statuses: matched {len(statuses)} out of {statuses.count} total - all passed"
                )
    rate_limit = gh.rate_limit.get()
    print(f"github limit remaining is {rate_limit.rate.remaining}")


if __name__ == "__main__":
    sys.exit(main())
