#!/usr/bin/env python

import argparse
import datetime
import logging
import os.path
import re
import pytz
import requests

# import requests_cache
import shutil
import signal
import sys
from ghapi.all import GhApi
from ghapi.page import paged as gh_paged
from bs4 import BeautifulSoup

signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

# don't use cache for now - it interferes with stream=True
# needed to download large files
# requests_cache.install_cache("web_cache", backend="filesystem")


def download_file(url, dest_file):
    """Download file from url and write to dest_file."""
    with requests.get(url, stream=True) as resp:
        with open(dest_file, "wb") as ff:
            shutil.copyfileobj(resp.raw, ff)


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


def get_statuses(gh, org, repo, pr_num):
    pr = gh.pulls.get(org, repo, pr_num)
    statuses = []
    for status in gh_iter(
        gh.repos.get_combined_status_for_ref,
        "statuses",
        owner=org,
        repo=repo,
        ref=pr.head.sha,
        per_page=99,
    ):
        logging.debug(
            "%s %s %s %s %s",
            status.state,
            status.context,
            status.updated_at,
            status.description,
            status.target_url,
        )
        # e.g. role|fedora-33|ansible-2.9
        ary = status.context.split("|")
        if len(ary) == 2:
            role = repo
            platform = ary[0]
            ansible = ary[1]
        else:
            role = ary[0]
            platform = ary[1]
            ansible = ary[2]
        setattr(status, "role", role)
        setattr(status, "platform", platform)
        setattr(status, "ansible", ansible)
        statuses.append(status)
    return statuses


def get_logs_from_artifacts_page(args, url):
    """The url is the directory of the artifacts from a pr CI tests run."""
    logging.info("Getting results from %s", url)
    response = requests.get(url)
    parsed_html = BeautifulSoup(response.text, "html.parser")
    if args.all_statuses:
        # grab all logs
        log_re = re.compile(r"[.]log$")
    else:
        # grab only something-FAIL.log
        log_re = re.compile(r"-FAIL[.]log$")
    # get directory name
    info_re = re.compile(r"/logs/([^/]+)/")
    match = info_re.search(url)
    directory = match.group(1)
    for item in parsed_html.find_all(href=log_re):
        log_url = url + "/" + item.attrs["href"]
        dest_dir = os.path.join(args.log_dir, directory)
        dest_file = os.path.join(dest_dir, item.attrs["href"])
        if os.path.exists(dest_file) and not args.force:
            continue
        os.makedirs(dest_dir, exist_ok=True)
        download_file(log_url, dest_file)


def get_logs_from_github(args):
    if args.token:
        gh = GhApi(token=args.token)
    else:
        gh = GhApi(authenticate=False)
    rate_limit = gh.rate_limit.get()
    logging.info("github limit remaining is %s", rate_limit.rate.remaining)

    if args.github_pr:
        prs = [(args.github_org, args.github_repo, args.github_pr)]
    else:
        if args.github_pr_search:
            qs = args.github_pr_search
        else:
            qs = "is:pr is:open"
        if args.github_repo:
            qs = qs + f" repo:{args.github_org}/{args.github_repo}"
        else:
            qs = qs + f" org:{args.github_org}"
        items = gh.search.issues_and_pull_requests(qs)
        prs = []
        for pr in items["items"]:
            ary = pr.url.split("/")
            prs.append((ary[4], ary[5], ary[7]))
    for org, repo, pr_num in prs:
        for status in get_statuses(gh, org, repo, pr_num):
            if status.target_url:
                get_logs_from_artifacts_page(args, status.target_url)
            else:
                logging.info(
                    f"No logs for [{org}/{repo}/{pr_num}/{status.context}]: {status.description}"
                )


def parse_date_range(date_range):
    ary = date_range.split("..")
    rv = []
    for dt_str in ary:
        dt = datetime.datetime.fromisoformat(dt_str)
        if not dt.tzinfo:
            # need timezone for comparison
            dt = dt.replace(tzinfo=pytz.timezone("UTC"))
        rv.append(dt)
    return rv[0], rv[1]


def get_logs_from_url(args):
    """Assumes args.log_url is HTML with a list of folders to logs from test runs."""
    matching_roles = None
    if args.role != ["ALL"]:
        matching_roles = set(args.role)
    if args.date_range == "latest":
        min_dt, max_dt = None, None
    else:
        min_dt, max_dt = parse_date_range(args.date_range)
    response = requests.get(args.log_url)
    parsed_html = BeautifulSoup(response.text, "html.parser")
    log_re = re.compile(r"^tf_([a-z0-9_]+)-([0-9]+)_([^_]+)_([^/]+)")
    data = {}
    for item in parsed_html.find_all(href=log_re):
        match = log_re.search(item.attrs["href"])
        if match:
            role = match.group(1)
            # pr_num = match.group(2)
            platform_ansible = match.group(3)
            dt = datetime.datetime.strptime(match.group(4), "%Y%m%d-%H%M%S")
            if matching_roles and role not in matching_roles:
                continue
            if min_dt and max_dt and (dt < min_dt or dt > max_dt):
                continue
            logs = data.setdefault(role, {}).setdefault(platform_ansible, [])
            if not logs or args.date_range != "latest":
                logs.append(item.attrs["href"])
            else:
                match = log_re.search(logs[0])
                last_dt = datetime.datetime.strptime(match.group(4), "%Y%m%d-%H%M%S")
                if dt > last_dt:
                    logs[0] = item.attrs["href"]
    # data[role][platform] = [log1, log2, ...]
    for platform in data.values():
        for log_dirs in platform.values():
            for log_dir in log_dirs:
                url = args.log_url + "/" + log_dir + "/artifacts"
                get_logs_from_artifacts_page(args, url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        help="github oauth token",
    )
    parser.add_argument(
        "--log-dir",
        help="log directory - will create if does not exist",
        required=True,
    )
    parser.add_argument(
        "--github-org",
        default="linux-system-roles",
        help="github org",
    )
    parser.add_argument(
        "--github-repo",
        help="github repo under github-org",
    )
    parser.add_argument(
        "--github-pr",
        help="github PR in github-org/github-repo/pulls",
    )
    parser.add_argument(
        "--github-pr-search",
        help="operate on all PRs that match this search criteria",
    )
    parser.add_argument(
        "--force",
        default=False,
        action="store_true",
        help="force download and overwrite of existing files",
    )
    parser.add_argument(
        "--all-statuses",
        default=False,
        action="store_true",
        help="by default, only download failed log runs - use this to download successful log runs also",
    )
    parser.add_argument(
        "--log-url",
        default="https://dl.fedoraproject.org/pub/alt/linuxsystemroles/logs",
        help="url of logs",
    )
    parser.add_argument(
        "--date-range",
        default="latest",
        help="latest, or a date range like fromISO..toISO",
    )
    parser.add_argument(
        "--role",
        default=["ALL"],
        action="append",
        help="roles to download",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v -v to increase verbosity",
    )

    args = parser.parse_args()

    if args.verbose > 1:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logging.getLogger().setLevel(logging.INFO)

    if any((args.github_repo, args.github_pr, args.github_pr_search)):
        get_logs_from_github(args)
    if args.log_url:
        get_logs_from_url(args)


if __name__ == "__main__":
    sys.exit(main())
