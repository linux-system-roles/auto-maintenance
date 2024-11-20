#!/usr/bin/env python

import argparse
import datetime
import logging
import os.path
import re
import subprocess
import pytz
import requests

# import requests_cache
import shutil
import signal
import sys
from ghapi.all import GhApi
from ghapi.page import paged as gh_paged
from bs4 import BeautifulSoup
from http.client import HTTPConnection

signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

# don't use cache for now - it interferes with stream=True
# needed to download large files
# requests_cache.install_cache("web_cache", backend="filesystem")

# there seems to be some problem on my system with IPV6 resolution
# downloads take forever - I guess it is trying to use IPV6 first,
# then it times out after a minute or so, then it falls back to IPV4
requests.packages.urllib3.util.connection.HAS_IPV6 = False


def debug_requests_on():
    """Switches on logging of the requests module."""
    HTTPConnection.debuglevel = 1
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


def debug_requests_off():
    """Switches off logging of the requests module, might be some side-effects"""
    HTTPConnection.debuglevel = 0
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    root_logger.handlers = []
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.WARNING)
    requests_log.propagate = False


def download_file(args, url, dest_file):
    """Download file from url and write to dest_file.  Create dest directory if needed."""
    if args.force or not os.path.exists(dest_file):
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
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
        dest_file = os.path.join(args.log_dir, directory, item.attrs["href"])
        download_file(args, log_url, dest_file)


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


def parse_beaker_job_log(log_file):
    result_re = re.compile(r"^::   OVERALL RESULT: ([A-Z]+)")
    fail_re = re.compile(r":: \[   FAIL   \] :: Test ([a-z0-9_]+)/([^\ ]+)")
    pass_re = re.compile(r":: \[   PASS   \] :: Test ([a-z0-9_]+)/([^\ ]+)")
    duration_re = re.compile(r"Duration: ([0-9a-zA-Z_]+)")
    failed = []
    passed = []
    duration = None
    last_test = None
    status = "RUNNING"
    with open(log_file) as df:
        for line in df:
            match = duration_re.search(line)
            if match:
                duration = match.group(1)
            match = result_re.search(line)
            if match:
                status = match.group(1)
                break
            match = fail_re.search(line)
            if match:
                last_test = match.group(1) + "/" + match.group(2)
                failed.append(last_test)
                continue
            match = pass_re.search(line)
            if match:
                last_test = match.group(1) + "/" + match.group(2)
                passed.append(last_test)
                continue
    return status, duration, failed, passed, last_test


def get_beaker_job_info(job):
    result = subprocess.run(
        ["bkr", "job-results", job], capture_output=True, text=True, check=True
    )
    bs = BeautifulSoup(result.stdout, "xml")
    data = {}
    data["job"] = job
    data["whiteboard"] = bs.find("whiteboard").text
    data["system"] = bs.find("recipe").get("system")
    data["distro"] = bs.find("recipe").get("distro")
    data["arch"] = bs.find("recipe").get("arch")
    data["install_start"] = bs.find("installation").get("install_started")
    data["post_install_end"] = bs.find("installation").get("postinstall_finished")
    data["tasks"] = []
    for task in bs.find_all("task"):
        task_data = {}
        for key in (
            "name",
            "result",
            "status",
            "start_time",
            "finish_time",
            "duration",
        ):
            task_data[key] = task.get(key)
        if task_data["name"].endswith("basic-smoke-test"):
            task_data["name"] = "basic-smoke-test"
            for log in task.find("logs"):
                link = log.get("href")
                name = log.get("name")
                log_urls = []
                if name == "taskout.log":
                    task_data["taskout_log"] = link
                elif name.startswith("SYSTEM-ROLE-"):
                    log_urls.append(link)
        data["tasks"].append(task_data)
    return data


def print_beaker_job_info(args, info):
    print(
        f"Distro [{info['distro']}] arch [{info['arch']}] whiteboard [{info['whiteboard']}] job [{info['job']}]"
    )
    print(f"  Install start [{info['install_start']}] end [{info['post_install_end']}]")
    for task in info["tasks"]:
        sys.stdout.write("  Task")
        for key in (
            "name",
            "result",
            "status",
            "start_time",
            "finish_time",
            "duration",
        ):
            val = task[key]
            if not val:
                val = "N/A"
            sys.stdout.write(" " + key + " [" + val + "]")
        print("")
        taskout_url = task.get("taskout_log")
        if not taskout_url:
            continue
        dest_file = args.log_dir + "/" + os.path.basename(taskout_url)
        download_file(args, taskout_url, dest_file)
        status, duration, failed, passed, last_test = parse_beaker_job_log(dest_file)
        os.unlink(dest_file)  # don't need it anymore
        print(
            f"  Status {status} - {len(passed)} passed - {len(failed)} failed - {last_test} last test"
        )
        if status != "RUNNING" and duration:
            print(f"  Duration {duration}")
        if args.failed_tests_to_show > 0:
            for failed_test in failed[-args.failed_tests_to_show:]:  # fmt: skip
                print(f"    failed {failed_test}")

    print("")


def get_logs_from_beaker(args):
    if args.beaker_job == ["ALL"]:
        result = subprocess.run(
            ["bkr", "job-list", "--mine", "--format=list"],
            capture_output=True,
            text=True,
            check=True,
        )
        args.beaker_job = result.stdout.split("\n")
    for job in args.beaker_job:
        if not job:
            continue
        info = get_beaker_job_info(job)
        print_beaker_job_info(args, info)


def parse_ansible_junit_log(log_file):
    rv = []
    name_re = re.compile(r"\[([^]]+)\] (.+)$")
    with open(log_file) as lf:
        bs = BeautifulSoup(lf, "xml")
        for failure in bs.find_all(["failure", "error"]):
            name = failure.parent.get("name")
            match = name_re.search(name)
            host = match.group(1)
            ary = match.group(2).split(":")
            if len(ary) > 2:
                play = ary[0].strip()
                role = ary[1].strip()
                task = ary[2].strip()
            else:
                play = ary[0].strip()
                task = ary[1].strip()
                role = ""
            data = {
                "context": failure.parent.get("classname"),
                "message": failure.get("message"),
                "play": play,
                "role": role,
                "task": task,
                "time": failure.parent.get("time"),
                "host": host,
            }
            rv.append(data)
        # last element in the return array is the summary
        summary = bs.find_all("testsuite")[-1]
        data = {}
        for attr in (
            "failures",
            "errors",
            "disabled",
            "name",
            "skipped",
            "tests",
            "time",
        ):
            if attr == "tests":
                data["tasks"] = summary.get("tests")
            else:
                data[attr] = summary.get(attr)
        rv.append(data)
    return rv


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
        "--beaker-job",
        default=[],
        action="append",
        help="beaker jobs to get logs for - use ALL to get logs from all jobs",
    )
    parser.add_argument(
        "--failed-tests-to-show",
        type=int,
        default=0,
        help="for beaker logs, show this many failed tests",
    )
    parser.add_argument(
        "--junit-log",
        default=[],
        action="append",
        help="junit log file",
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
        debug_requests_on()
    elif args.verbose > 0:
        logging.getLogger().setLevel(logging.INFO)

    if args.junit_log:
        import pprint

        for log_file in args.junit_log:
            failures = parse_ansible_junit_log(log_file)
            pprint.pprint(failures)
    elif args.beaker_job:
        get_logs_from_beaker(args)
    elif any((args.github_repo, args.github_pr, args.github_pr_search)):
        get_logs_from_github(args)
    elif args.log_url:
        get_logs_from_url(args)


if __name__ == "__main__":
    sys.exit(main())
