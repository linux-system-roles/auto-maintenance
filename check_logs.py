#!/usr/bin/env python

import argparse
import copy
import csv
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
try:
    from ghapi.all import GhApi
    from ghapi.page import paged as gh_paged
except ModuleNotFoundError:
    logging.warning("no ghapi library")
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


TZ_UTC = datetime.UTC


def hr_min_sec_to_dt(ref_dt, hour, minute, second):
    dt = ref_dt.replace(hour=int(hour), minute=int(minute), second=int(second))
    if dt < ref_dt:
        # time has wrapped around to next day
        dt = dt + datetime.timedelta(hours=24)
    return dt.astimezone(TZ_UTC)


class AVC(object):
    avc_re = re.compile(
      r"type=AVC msg=audit\(([0-9.]+):\d+\): avc:\s+denied\s+{([^}]+)}"
      r"\s+for\s+pid=\d+ (.+)$"
    )

    # this is the dict as returned by csv.DictReader from the output of ausearch --format csv
    def __init__(self, avc_dict_or_str):
        if isinstance(avc_dict_or_str, dict):
            for key, val in avc_dict_or_str.items():
                setattr(self, key.lower(), val)
            self.dt_iso_str = f"{self.year:04d}-{self.month:02d}-{self.day:02d}T{self.time},{self.milli}{self.gmt_offset}"
            self.dt = datetime.datetime.fromisoformat(self.dt_iso_str)
            self.valid = True
        elif avc_dict_or_str.startswith("type=AVC "):
            match = AVC.avc_re.match(avc_dict_or_str)
            if not match:
                raise Exception(f"cannot parse as AVC: {avc_dict_or_str}")
            self.dt = datetime.datetime.fromtimestamp(float(match.group(1)), TZ_UTC)
            self.dt_iso_str = self.dt.isoformat()
            self.actions = match.group(2)
            self.text = match.group(3)
            self.valid = True
        else:
            self.valid = False

    def __str__(self):
        if hasattr(self, "event_kind"):
            return (
                f"{self.dt_iso_str} {self.event_kind} {self.subj_prime}:{self.subj_sec} {self.subj_label}"
                f" {self.action} {self.obj_kind} {self.how}"
            )
        else:
            return f"{self.dt_iso_str} denied {{{self.actions}}} {self.text}"

    def __eq__(self, other):
        if hasattr(self, "event_kind"):
            comp_fields = ["event_kind", "subj_prime", "subj_sec", "subj_label", "action", "obj_kind", "how"]
        else:
            comp_fields = ["actions", "text"]
        for field in comp_fields:
            if getattr(self, field, None) != getattr(other, field, None):
                return False
        return True


# This represents data from a beaker test log which looks like this:
# :: [ 22:37:43 ] :: [  BEGIN   ] :: Test ad_integration/tests_default.yml ...
# :: [ 22:37:49 ] :: [   PASS   ] :: Test ad_integration/tests_default.yml ...
# or
# :: [ 22:37:49 ] :: [   FAIL   ] :: Test ad_integration/tests_default.yml ...
# start_data is the data parsed from the BEGIN line
# end_data is the data parsed from the PASS or FAIL line
# ref_dt is the reference datetime with timezone information for converting
# the time from the line to a tz and date aware datetime
class BeakerTestRec(object):
    def __init__(self, ref_dt, start_data, end_data):
        self.start_dt = hr_min_sec_to_dt(ref_dt, start_data["hour"], start_data["min"], start_data["sec"])
        self.end_dt = hr_min_sec_to_dt(ref_dt, end_data["hour"], end_data["min"], end_data["sec"])
        self.status = end_data["status"]
        self.role = end_data["role"]
        self.test_name = end_data["test_name"]

    def __str__(self):
        return (
            f"{self.role}/{self.test_name} "
            f"{self.start_dt.isoformat()} "
            f"{self.end_dt.isoformat()}"
        )

    def dt_during_test(self, dt):
        return dt >= self.start_dt and dt <= self.end_dt


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


def get_file_data(args, url, dest_file=None):
    """Download file from url and write to dest_file.  Create dest directory if needed."""
    if dest_file and (args.force or not os.path.exists(dest_file)):
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
    with requests.get(url, stream=True) as resp:
        if dest_file:
            with open(dest_file, "wb") as ff:
                shutil.copyfileobj(resp.raw, ff)
        else:
            for line in resp.iter_lines():
                yield line.decode("utf-8")


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


# returns a list of dict
# each dict contains the following keys:
# * error - the error line from the log
# * url - link to ansible log file
# * context_lines - log lines to give some context for the error
def get_errors_from_ansible_log(args, log_url):
    errors = []
    context_lines = []
    logging.debug("Getting errors from ansible log [%s]", log_url)
    for line in get_file_data(args, log_url):
        context_lines.append(line)
        if len(context_lines) > 4:
            context_lines.pop(0)
        if line.startswith("fatal:"):
            error = {"url": log_url, "context_lines": copy.deepcopy(context_lines), "error": line}
            errors.append(error)
    logging.debug("Found [%d] errors", len(errors))
    return errors


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
    errors = []
    for item in parsed_html.find_all(href=log_re):
        log_url = url + "/" + item.attrs["href"]
        errors.extend(get_errors_from_ansible_log(args, log_url))
    return errors


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
            dt = dt.replace(tzinfo=TZ_UTC)
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
    errors = []
    for platform in data.values():
        for log_dirs in platform.values():
            for log_dir in log_dirs:
                url = args.log_url + "/" + log_dir + "/artifacts"
                errors.extend(get_logs_from_artifacts_page(args, url))
    return errors


def print_avcs_and_tasks(args, task_data):
    avcs = task_data["avcs"]
    if not avcs:
        return
    job_data_roles = task_data["job_data"]["roles"]
    for role, avc_list in avcs.items():
        avc_count = len(avc_list)
        if args.print_all_avcs:
            for avc in avc_list:
                for btr in job_data_roles[role]:
                    if btr.dt_during_test(avc.dt):
                        print(f"    AVC in {btr}: {avc}")
        elif avc_count > 0:
          print(f"    {avc_count} AVCs during tests for role {role}")


# Times printed in job log have no TZ information - figure out TZ based
# on offset from given start_dt
def parse_beaker_job_log(args, start_dt_utc, taskout_url):
    result_re = re.compile(r"^::   OVERALL RESULT: ([A-Z]+)")
    test_re_str = (
        r"^:: \[ (?P<hour>[0-9]{2}):(?P<min>[0-9]{2}):(?P<sec>[0-9]{2}) \] "
        r":: \[ +(?P<status>[A-Z]+) +\] :: Test (?P<role>[a-z0-9_]+)/(?P<test_name>[^ ]+)"
    )
    test_re = re.compile(test_re_str)
    duration_re = re.compile(r"Duration: ([0-9a-zA-Z_]+)")
    start_dt = None
    start_data = None
    job_data = {"roles": {}, "passed": [], "failed": [], "status": "RUNNING", "last_test": "N/A"}
    for line in get_file_data(args, taskout_url):
        match = duration_re.search(line)
        if match:
            job_data["duration"] = match.group(1)
        match = result_re.search(line)
        if match:
            job_data["status"] = match.group(1)
            break
        match = test_re.search(line)
        if match:
            data = match.groupdict()
            if not start_dt:
                # figure out TZ offset and set in start_dt
                start_dt = start_dt_utc.replace(hour=int(data["hour"]), minute=int(data["min"]), second=int(data["sec"]))
                hour_offset = round((start_dt - start_dt_utc).total_seconds()/3600.0)
                tz_str = f"{hour_offset:+03d}00"
                dt_with_tz = datetime.datetime.strptime(tz_str, "%z")
                start_dt = start_dt.replace(tzinfo=dt_with_tz.tzinfo)
            if data["status"] == "BEGIN":
                job_data["last_test"] = data["role"] + "/" + data["test_name"]
                start_data = data
            elif start_data:
                btr = BeakerTestRec(start_dt, start_data, data)
                job_data["roles"].setdefault(data["role"], []).append(btr)
                if data["status"] == "PASS":
                    job_data["passed"].append(btr)
                else:
                    job_data["failed"].append(btr)
                start_data = None
    return job_data


def parse_avc_log(args, log_url):
    avcs = []
    for line in get_file_data(args, log_url):
        avc = AVC(line)
        if avc.valid:
            avcs.append(avc)
    return avcs


def get_beaker_job_info(args, job):
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
            if key in ("start_time", "finish_time") and task_data[key]:
                dt = datetime.datetime.fromisoformat(task_data[key] + "+00:00")
                task_data[key] = dt
        if task_data["name"].endswith("basic-smoke-test"):
            task_data["name"] = "basic-smoke-test"
            log_urls = []
            for log in task.find("logs"):
                link = log.get("href")
                name = log.get("name")
                if name == "taskout.log":
                    task_data["job_data"] = parse_beaker_job_log(args, task_data["start_time"], link)
                elif name.startswith("SYSTEM-ROLE-"):
                    log_urls.append(link)
            task_data["logs"] = log_urls
            role = None
            task_data["avcs"] = {}
            for result in task.find_all("result"):
                match = re.match(r"^Test-role-([a-z0-9_-]+)", result.get("path"))
                if match:
                    role = match.group(1).replace("-", "_")
                match = re.search(r"avc_check", result.get("path"))
                if match and role:
                    log_url = result.find("log").get("href")
                    avc_data = parse_avc_log(args, log_url)
                    task_data["avcs"][role] = avc_data
                    role = None
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
            sys.stdout.write(" " + key + " [" + str(val) + "]")
        print("")
        job_data = task.get("job_data")
        if not job_data:
            continue
        print(
            f"  Status {job_data["status"]} - {len(job_data["passed"])} passed - "
            f"{len(job_data["failed"])} failed - {job_data["last_test"]} last test"
        )
        if job_data["status"] != "RUNNING" and job_data.get("duration"):
            print(f"  Duration {job_data["duration"]}")
        if args.failed_tests_to_show > 0:
            for failed_test in job_data["failed"][-args.failed_tests_to_show:]:  # fmt: skip
                print(f"    failed {failed_test}")
            print_avcs_and_tasks(args, task)
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
        info = get_beaker_job_info(args, job)
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


def print_ansible_errors(args, errors):
    if args.csv_errors:
        if args.csv_errors == "-":
            csv_f = sys.stdout
        else:
            csv_f = open(args.csv_errors, "w")
        fieldnames = ["error", "context_lines", "url"]
        writer = csv.DictWriter(csv_f, fieldnames=fieldnames)
        writer.writeheader()
        for error in errors:
            writer.writerow(error)
        if csv_f != sys.stdout:
            csv_f.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        help="github oauth token",
    )
    parser.add_argument(
        "--log-dir",
        help="log directory - will create if does not exist",
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
        "--print-all-avcs",
        default=False,
        action="store_true",
        help="print all AVCs - otherwise, just print count",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="-v -v to increase verbosity",
    )
    parser.add_argument(
        "--csv-errors",
        default="",
        help="write errors in csv format to this given file, or - for stdout",
    )

    args = parser.parse_args()

    if args.verbose > 1:
        logging.getLogger().setLevel(logging.DEBUG)
        #debug_requests_on()
        debug_requests_off()
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
        errors = get_logs_from_url(args)
        print_ansible_errors(args, errors)


if __name__ == "__main__":
    sys.exit(main())
