#!/usr/bin/env python

import argparse
import copy
import csv
import datetime
import json
import logging
from operator import itemgetter
import os.path
import re
import subprocess
import requests

# import requests_cache
import shutil
import signal
import sys

try:
    from ghapi.all import GhApi
    from ghapi.page import paged as gh_paged
except ImportError:
    logging.debug("No ghapi library")

try:
    from bs4 import BeautifulSoup
except ImportError:
    logging.debug("No bs4 library - no soup for you")
from http.client import HTTPConnection

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    logging.debug("no gspread/oauth")

signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

# don't use cache for now - it interferes with stream=True
# needed to download large files
# requests_cache.install_cache("web_cache", backend="filesystem")

# there seems to be some problem on my system with IPV6 resolution
# downloads take forever - I guess it is trying to use IPV6 first,
# then it times out after a minute or so, then it falls back to IPV4
requests.packages.urllib3.util.connection.HAS_IPV6 = False


TIMING_INFO = []
TIMING_START_RE = re.compile(r"^=+ *$", re.MULTILINE)
TIMING_RE = re.compile(r" (\d+[.]\d\d)s$", re.MULTILINE)

# Regex to find IPv4 addresses following 'primary address: "'
PRIMARY_ADDRESS_RE = re.compile(
    r"primary address: (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
)


def get_timing_info(args, role, log_url, log_data):
    match = TIMING_START_RE.search(log_data)
    if match:
        newpos = match.end() + 1
        match = TIMING_RE.search(log_data[newpos:])
        if not match:
            logging.error(
                "Error: timing info not found in url [%s] log data [%s]",
                log_url,
                log_data[newpos : newpos + 100],  # noqa: E203
            )
        else:
            info = {"time": match.group(1), "role": role, "log_url": log_url}
            TIMING_INFO.append(info)


def print_timing_info(args):
    """Print timing information collected from log files."""
    if not args.timing_info or not TIMING_INFO:
        return

    print("\nTiming Information:")
    print("=" * 50)

    # Sort by time, longest first
    sorted_timing = sorted(TIMING_INFO, key=lambda x: float(x["time"]), reverse=True)

    for info in sorted_timing[:30]:
        print(f"{info['time']}s {info['role']} {info['log_url']}")


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
            self.dt_iso_str = (
                f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
                f"T{self.time},{self.milli}{self.gmt_offset}"
            )
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
            comp_fields = [
                "event_kind",
                "subj_prime",
                "subj_sec",
                "subj_label",
                "action",
                "obj_kind",
                "how",
            ]
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
        self.start_dt = hr_min_sec_to_dt(
            ref_dt, start_data["hour"], start_data["min"], start_data["sec"]
        )
        self.end_dt = hr_min_sec_to_dt(
            ref_dt, end_data["hour"], end_data["min"], end_data["sec"]
        )
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


def get_file_data(args, url_or_data, dest_file=None):
    """Download file from url and write to dest_file.  Create dest directory if needed."""
    verify = not args.disable_verify
    if dest_file and (args.force or not os.path.exists(dest_file)):
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
    if url_or_data.startswith("http"):
        url = url_or_data
        with requests.get(url, stream=True, verify=verify) as resp:
            resp.raise_for_status()
            if dest_file:
                with open(dest_file, "wb") as ff:
                    shutil.copyfileobj(resp.raw, ff)
            else:
                for line in resp.iter_lines():
                    yield line.decode("utf-8")
    else:  # assume it is the actual data
        if dest_file:
            with open(dest_file, "wb") as ff:
                ff.write(url_or_data)
        else:
            for line in url_or_data.splitlines():
                yield line


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


# upstream
SYSTEM_ROLE_UPSTREAM_LOG_RE = re.compile(
    r"/logs/tf_(?P<role>(tft-tests|[a-z0-9_]+))-(?P<pr_num>[0-9]+)_"
    r"(?P<platform_version>[a-zA-Z0-9-]+)-2[.][0-9]+_(?P<date>[0-9]+)-(?P<time>[0-9]+)"
    r"/artifacts/(?P<test_name>tests_[a-z0-9_]+)-"
    r"ANSIBLE-(?P<ansible_ver>[0-9.]+)-.*-(?P<test_status>SUCCESS|FAIL)[.](?P<suffix>log|json)$"
)


# beaker
SYSTEM_ROLE_LOG_RE = re.compile(
    r"/SYSTEM-ROLE-(?P<role>[a-z0-9_]+)_(?P<test_name>tests_[a-z0-9_]+"
    r"[.]yml)-.*-ANSIBLE-(?P<ansible_ver>[0-9.]+).*[.](?P<suffix>log|json)$"
)


# testing farm
SYSTEM_ROLE_TF_LOG_RE = re.compile(
    r"/data/(?P<role>[a-z0-9_]+)-(?P<test_name>tests_[a-z0-9_]+)"
    r"-ANSIBLE-(?P<ansible_ver>[0-9.]+)-(?P<tf_job_name>[0-9a-z_]+)"
    r"-(?P<test_status>SUCCESS|FAIL)[.](?P<suffix>log|json)$"
)


# local log file - legacy format
SYSTEM_ROLE_LOG_LEGACY = re.compile(
    r"-system-roles[./](?P<role>[a-z0-9_]+)/tests/(?P<test_name>tests_[a-z0-9_]+)[.](yml[.])?(?P<suffix>log|json)$"
)


# local log file - collection format
SYSTEM_ROLE_LOG_COLLECTION = re.compile(
    r"_system_roles/tests/(?P<role>[a-z0-9_]+)/(?P<test_name>tests_[a-z0-9_]+)[.](yml[.])?(?P<suffix>log|json)$"
)


# parse the given log file name or url and extract and return the data
def log_file_or_url_to_data(log_file_or_url):
    for rx in (
        SYSTEM_ROLE_UPSTREAM_LOG_RE,
        SYSTEM_ROLE_LOG_RE,
        SYSTEM_ROLE_TF_LOG_RE,
        SYSTEM_ROLE_LOG_LEGACY,
        SYSTEM_ROLE_LOG_COLLECTION,
    ):
        match = rx.search(log_file_or_url)
        if match:
            return match.groupdict()
    return {}


def get_lsr_stat_items(log_data):
    start_token = "SYSTEM ROLES ERRORS BEGIN v1"
    end_token = "SYSTEM ROLES ERRORS END v1"
    start_pos = log_data.find(start_token)
    while start_pos > 0:
        # check for nested errors, like the wrapper tests
        # just check for one level of nesting
        start_pos2 = log_data.find(start_token, start_pos + 1)
        end_pos = log_data.find(end_token, start_pos)
        if start_pos2 > 0 and start_pos2 < end_pos:
            end_pos = log_data.find(end_token, start_pos2)
            end_pos = log_data.find(end_token, end_pos + 1)
        if end_pos == -1:
            logging.error("Error: end token [%s] not found", end_token)
            return None
        start_pos += len(start_token)
        yield json.loads(log_data[start_pos:end_pos])
        start_pos = log_data.find(start_token, end_pos + 1)


# these are the fields that are added to each error
# The key is the name of the field as we want it to appear in the output
# The value is a dict with the following keys:
# - error_item_key: the name of the field in the error item
# - var_name: the name of the local variable with the value
# - default: the default value to use if the field is not present
ERROR_FIELDS = {
    "Ansible Version": {
        "error_item_key": "ansible_version",
        "var_name": "ansible_version",
        "default": "",
    },
    "Task": {"error_item_key": "task_name", "var_name": "current_task", "default": ""},
    "Task Path": {
        "error_item_key": "task_path",
        "var_name": "task_path",
        "default": "",
    },
    "Url": {"error_item_key": "log_url", "var_name": "log_url", "default": ""},
    "Detail": {"error_item_key": "message", "var_name": "detail", "default": ""},
    "Role": {"error_item_key": "role", "var_name": "role", "default": ""},
    "Parents": {"error_item_key": "parents", "var_name": "parents", "default": []},
    "Stdout": {"error_item_key": "stdout", "var_name": "stdout", "default": ""},
    "Stderr": {"error_item_key": "stderr", "var_name": "stderr", "default": ""},
    "RC": {"error_item_key": "rc", "var_name": "rc", "default": 0},
    "Start": {"error_item_key": "start_time", "var_name": "start_time", "default": ""},
    "End": {"error_item_key": "end_time", "var_name": "end_time", "default": ""},
    "Host": {"error_item_key": "host", "var_name": "host", "default": ""},
}


def get_error_field(error_item, error_item_key, local_vars, var_name, default):
    if error_item and error_item_key in error_item:
        return error_item[error_item_key]
    if var_name in local_vars:
        return local_vars[var_name]
    return default


def get_error_fields(error_item, local_vars):
    error_with_fields = {}
    for name, field in ERROR_FIELDS.items():
        error_with_fields[name] = get_error_field(
            error_item,
            field["error_item_key"],
            local_vars,
            field["var_name"],
            field["default"],
        )
    return error_with_fields


def parse_lsr_error_log(args, log_url, log_data, extra_fields={}):
    errors = []
    url_data = log_file_or_url_to_data(log_url)
    role = url_data.get("role")
    for data in get_lsr_stat_items(log_data):
        for error_item in data:
            error = copy.deepcopy(extra_fields)
            error.update(get_error_fields(error_item, locals()))
            errors.append(error)
    return errors


def get_errors_from_ansible_log(args, log_url, extra_fields={}):
    errors = []
    current_task = None
    total_failed = 0
    total_unreachable = 0
    task_lines = []
    task_has_fatal = False
    task_path = None

    logging.debug("Getting errors from ansible log [%s]", log_url)
    data = log_file_or_url_to_data(log_url)
    role = data.get("role")
    ansible_version = data.get("ansible_ver")
    if args.role != ["ALL"] and role not in args.role:
        logging.info(
            "Skipping log - role [%s] not in args.role [%s]: [%s]",
            role,
            str(args.role),
            log_url,
        )
        return []
    if log_url.startswith("http://") or log_url.startswith("https://"):
        verify = not args.disable_verify
        log_data = requests.get(log_url, verify=verify).content.decode("utf-8")
    else:  # assume a local file
        log_data = open(log_url).read()

    get_timing_info(args, role, log_url, log_data)

    errors = parse_lsr_error_log(args, log_url, log_data, extra_fields)
    if errors:
        total_failed = len(errors)
    else:
        logging.info(
            "No system roles error stats found in log file %s - parsing ansible log",
            log_url,
        )
        for line in log_data.splitlines():
            if (
                line.startswith("TASK ")
                or line.startswith("PLAY ")
                or line.startswith("META ")
            ):
                # end of current task and possibly start of new task
                if task_lines and task_has_fatal:
                    # Extract task name from the first task line
                    task_match = re.search(r"TASK\s\[(.*?)\]", task_lines[0])
                    if task_match:
                        current_task = task_match.group(1)
                    # end task
                    error = copy.deepcopy(extra_fields)
                    detail = copy.deepcopy(task_lines[3:])
                    error.update(get_error_fields({}, locals()))
                    errors.append(error)
                if line.startswith("TASK "):
                    task_lines = [line.strip()]
                else:
                    task_lines = []
                task_has_fatal = False
                task_path = None
            elif task_lines:
                task_lines.append(line.strip())
                if line.startswith("fatal:"):
                    task_has_fatal = True
                elif line.startswith("failed:"):
                    task_has_fatal = True
                elif line.startswith("task path:"):
                    task_path_match = re.search(r"task path: (.*)", line)
                    if task_path_match:
                        task_path = task_path_match.group(1)
                elif line.startswith("...ignoring"):
                    task_has_fatal = False
            else:
                match = re.search(r"\sunreachable=(\d+)\s+failed=(\d+)\s", line)
                if match:
                    total_unreachable += int(match.group(1))
                    total_failed += int(match.group(2))

    logging.debug(
        "Found [%d] errors and Ansible reported [%d] failures",
        len(errors),
        total_failed,
    )
    if total_unreachable == 0 and total_failed == 0:
        errors = []
    for error in errors:
        error["Fails expected"] = total_failed

    return errors


# This works like the dict get method but with a list of keys
# and it checks each one to see if it is null or not
# if the key is an int, assume it is a list index
def get_from_nested_dict(dd, key_list, default=None):
    for key in key_list:
        if isinstance(key, int) and isinstance(dd, list):
            if len(dd) > key:
                dd = dd[key]
            else:
                dd = {}
        elif isinstance(dd, dict):
            dd = dd.get(key)
        if not dd:
            dd = {}
    if not dd:
        dd = default
    return dd


def get_logs_from_artifacts_page(args, url):
    """The url is the directory of the artifacts from a pr CI tests run."""
    logging.info("Getting results from %s", url)
    verify = not args.disable_verify
    response = requests.get(url, verify=verify)
    parsed_html = BeautifulSoup(response.text, "html.parser")
    if args.all_statuses:
        # grab all logs
        log_re = re.compile(r"[.]log$")
    else:
        # grab only something-FAIL.log
        log_re = re.compile(r"-FAIL[.]log$")
    # get directory name
    # info_re = re.compile(r"/logs/([^/]+)/")
    # match = info_re.search(url)
    # directory = match.group(1)  # unused for now
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
    errors = []
    for org, repo, pr_num in prs:
        for status in get_statuses(gh, org, repo, pr_num):
            if status.target_url:
                errors.extend(get_logs_from_artifacts_page(args, status.target_url))
            else:
                logging.info(
                    f"No logs for [{org}/{repo}/{pr_num}/{status.context}]: {status.description}"
                )
    return errors


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
    verify = not args.disable_verify
    response = requests.get(args.log_url, verify=verify)
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
                url = args.log_url + "/" + log_dir + "artifacts"
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
        r":: \[ +(?P<status>[A-Z]+) +\] :: Test ((?P<role>[a-z0-9_]+)/)?(?P<test_name>tests_[^ ]+)"
    )
    test_re = re.compile(test_re_str)
    test_role_re_str = r"^::\s+Test role: (?P<role>[a-z0-9_]+)"
    test_role_re = re.compile(test_role_re_str)
    duration_re = re.compile(r"Duration: ([0-9a-zA-Z_]+)")
    start_dt = None
    start_data = None
    job_data = {
        "roles": {},
        "passed": [],
        "failed": [],
        "status": "RUNNING",
        "last_test": "N/A",
        "last_line": "",
    }
    role = None  # Upstream-testsuite does not report role name in test_re
    for line in get_file_data(args, taskout_url):
        job_data["last_line"] = line
        match = duration_re.search(line)
        if match:
            job_data["duration"] = match.group(1)
        match = result_re.search(line)
        if match:
            job_data["status"] = match.group(1)
            break
        match = test_role_re.match(line)
        if match:
            role = match.group(1)
        match = test_re.search(line)
        if match:
            data = match.groupdict()
            if data["role"] is None:
                data["role"] = role
            if (
                data["role"] in job_data["roles"]
                and data["test_name"] in job_data["roles"][data["role"]]
            ):
                logging.debug(
                    "Already processed result for [%s/%s] - skipping [%s]",
                    data["role"],
                    data["test_name"],
                    line,
                )
                continue
            if not start_dt:
                # figure out TZ offset and set in start_dt
                start_dt = start_dt_utc.replace(
                    hour=int(data["hour"]),
                    minute=int(data["min"]),
                    second=int(data["sec"]),
                )
                hour_offset = round((start_dt - start_dt_utc).total_seconds() / 3600.0)
                tz_str = f"{hour_offset:+03d}00"
                dt_with_tz = datetime.datetime.strptime(tz_str, "%z")
                start_dt = start_dt.replace(tzinfo=dt_with_tz.tzinfo)
            if data["status"] == "BEGIN":
                job_data["last_test"] = data["role"] + "/" + data["test_name"]
                start_data = data
            elif start_data:
                btr = BeakerTestRec(start_dt, start_data, data)
                job_data["roles"].setdefault(data["role"], {})[data["test_name"]] = btr
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
    if job.endswith(".xml"):  # a URL or a local file
        if job.startswith("http://") or job.startswith("https://"):
            verify = not args.disable_verify
            xml_data = requests.get(job, verify=verify).content
        else:
            xml_data = open(job).read()
        bs = BeautifulSoup(xml_data, "xml")
    else:  # assume it is a job number like J:1213552
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
    image = ""
    collection = ""
    ansible_gathering = ""
    for param in bs.find_all("param"):
        if param.get("name") == "IMAGE":
            data["image"] = param.get("value")
            image = data["image"]
        if param.get("name") == "SYSTEM_ROLES_USE_COLLECTIONS":
            data["collection"] = param.get("value")
            collection = data["collection"]
        if param.get("name") == "ANSIBLE_GATHERING":
            data["ansible_gathering"] = param.get("value")
            ansible_gathering = data["ansible_gathering"]
    extra_fields = {}
    for field in ["distro", "arch", "image", "collection", "ansible_gathering"]:
        extra_fields[field] = data.get(field, "N/A")
    logging.info(
        "Begin processing logs for beaker job [%s] [%s] [%s] [%s] [%s] [%s] [%s]",
        data["distro"],
        data["arch"],
        data["whiteboard"],
        data["job"],
        image,
        collection,
        ansible_gathering,
    )
    for task in bs.find_all("task"):
        task_data = {"errors": []}
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
        if task_data["name"].endswith("basic-smoke-test") or task_data["name"].endswith(
            "Upstream-testsuite"
        ):
            if task_data["name"].endswith("basic-smoke-test"):
                task_data["name"] = "basic-smoke-test"
            else:
                task_data["name"] = "Upstream-testsuite"
            extra_fields["test_name"] = task_data["name"]
            log_urls = []
            for log in task.find("logs"):
                if hasattr(log, "get"):
                    link = log.get("href")
                    name = log.get("name")
                    if name == "taskout.log":
                        logging.debug("    Processing job log [%s]", link)
                        task_data["job_data"] = parse_beaker_job_log(
                            args, task_data["start_time"], link
                        )
                    elif name.startswith("SYSTEM-ROLE-"):
                        log_urls.append(link)
            task_data["logs"] = log_urls
            if args.gather_errors:
                for log in log_urls:
                    match = SYSTEM_ROLE_LOG_RE.search(log)
                    if match:
                        role = match.group("role")
                        test_name = match.group("test_name")
                        btr = (
                            task_data["job_data"]
                            .get("roles", {})
                            .get(role, {})
                            .get(test_name)
                        )
                        if btr and btr.status != "PASS":
                            logging.debug("    Processing test log [%s]", log)
                            task_data["errors"].extend(
                                get_errors_from_ansible_log(
                                    args, log, extra_fields=extra_fields
                                )
                            )

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
            f"  Status {job_data['status']} - {len(job_data['passed'])} passed - "
            f"{len(job_data['failed'])} failed - {job_data['last_test']} last test"
        )
        print("    Last line: " + job_data["last_line"])
        if job_data["status"] != "RUNNING" and job_data.get("duration"):
            print(f"  Duration {job_data['duration']}")
        if args.failed_tests_to_show > 0:
            for failed_test in job_data["failed"][-args.failed_tests_to_show:]:  # fmt: skip
                print(f"    failed {failed_test}")
            print_avcs_and_tasks(args, task)
    print("")


def get_logs_from_beaker(args):
    beaker_jobs = []
    if args.beaker_job == ["ALL"]:
        result = subprocess.run(
            ["bkr", "job-list", "--mine", "--format=list"],
            capture_output=True,
            text=True,
            check=True,
        )
        beaker_jobs = result.stdout.split("\n")
    elif args.beaker_job:
        beaker_jobs = args.beaker_job

    errors = []
    for job in beaker_jobs:
        if not job:
            continue
        info = get_beaker_job_info(args, job)
        print_beaker_job_info(args, info)
        for task in info["tasks"]:
            task_errors = task.get("errors")
            if task_errors:
                errors.extend(task_errors)
    print_ansible_errors(args, errors)


def parse_tf_job_log(args, url, ref_dt):
    test_re_str = (
        r"^(?P<hour>[0-9]{2}):(?P<min>[0-9]{2}):(?P<sec>[0-9]{2})\s+out: :: "
        r"\[ [0-9]{2}:[0-9]{2}:[0-9]{2} \] "
        r":: \[ +(?P<status>[A-Z]+) +\] :: (?P<role>[a-z0-9_]+): (?P<test_name>tests_[^ ]+) "
        r"with ANSIBLE-(?P<ansible_ver>[0-9.]+) on (?P<managed_node>\S+)"
    )
    test_re = re.compile(test_re_str)
    job_data = {
        "roles": {},
        "passed": [],
        "failed": [],
        "status": "running",
        "last_test": "N/A",
        "last_line": "",
        "ip_addresses": [],
    }
    for line in get_file_data(args, url):
        job_data["last_line"] = line

        # Scan for IP addresses if requested
        if args.get_addresses:
            ip_matches = PRIMARY_ADDRESS_RE.findall(line)
            if ip_matches:
                job_data["ip_addresses"].extend(ip_matches)

        match = test_re.search(line)
        if match:
            data = match.groupdict()
            test_data = (
                job_data["roles"]
                .setdefault(data["role"], {})
                .setdefault(data["test_name"], {})
            )
            test_name = data["role"] + "/" + data["test_name"]
            dt = ref_dt.replace(
                hour=int(data["hour"]),
                minute=int(data["min"]),
                second=int(data["sec"]),
            )
            if dt < ref_dt:
                # time wrapped around
                dt = dt + datetime.timedelta(days=1)
            if data["status"] == "BEGIN":
                test_data["start_dt"] = dt
                job_data["last_test"] = test_name
            else:
                test_data["end_dt"] = dt
                test_data["status"] = data["status"]
                if data["status"] == "PASS":
                    job_data["passed"].append(test_name)
                else:
                    job_data["failed"].append(test_name)
            job_data["roles"][data["role"]][data["test_name"]] = test_data

    # Remove duplicate IP addresses
    if args.get_addresses:
        job_data["ip_addresses"] = list(set(job_data["ip_addresses"]))
        logging.debug(f"Found IP addresses: {job_data['ip_addresses']} in {url}")

    return job_data


def get_testing_farm_result(args):
    rv = []
    errors = []
    verify = not args.disable_verify
    for url in args.testing_farm_job_url:
        result = requests.get(url, verify=verify).json()
        data = {}
        environments_requested = get_from_nested_dict(
            result, ["environments_requested", 0], {}
        )
        data["compose_controller"] = get_from_nested_dict(
            environments_requested,
            ["os", "compose"],
            get_from_nested_dict(
                environments_requested, ["variables", "COMPOSE_CONTROLLER"], ""
            ),
        )
        data["arch_controller"] = get_from_nested_dict(
            environments_requested,
            ["variables", "ARCH_CONTROLLER"],
            get_from_nested_dict(environments_requested, ["arch"], ""),
        )
        for var in [
            "ARCH_MANAGED_NODE",
            "COMPOSE_MANAGED_NODE",
            "SR_ANSIBLE_GATHERING",
            "SR_USE_COLLECTIONS",
            "SR_EXCLUDED_TESTS",
            "SR_ONLY_TESTS",
        ]:
            data[var.lower()] = get_from_nested_dict(
                environments_requested, ["variables", var], ""
            )
        sr_role_name = get_from_nested_dict(
            environments_requested, ["variables", "SR_ROLE_NAME"], ""
        )
        if result["state"] == "queued":
            artifacts_url = "QUEUED"
            pipeline_type = "QUEUED"
        else:
            artifacts_url = get_from_nested_dict(result, ["run", "artifacts"], "")
            pipeline_type = get_from_nested_dict(
                result, ["settings", "pipeline", "type"], ""
            )
        build = get_from_nested_dict(
            environments_requested, ["settings", "provisioning", "tags", "build"], ""
        )
        data.update(
            {
                "plan_filter": get_from_nested_dict(
                    result, ["test", "fmf", "plan_filter"], ""
                ),
                "state": result["state"],
                "artifacts_url": artifacts_url,
                "pipeline_type": pipeline_type,
                "queued_time": result["queued_time"],
                "run_time": result["run_time"],
                "created_ts": datetime.datetime.fromisoformat(
                    result["created"] + "+00:00"
                ),
                "updated_ts": datetime.datetime.fromisoformat(
                    result["updated"] + "+00:00"
                ),
                "passed": [],
                "failed": [],
                "role": "ALL" if sr_role_name == "" else sr_role_name,
                "build": build,
                "ip_addresses": [],
            }
        )
        extra_error_fields = {
            "Managed Compose": data["compose_managed_node"],
            "Managed Arch": data["arch_managed_node"],
            "Control Compose": data["compose_controller"],
            "Control Arch": data["arch_controller"],
            "Ansible Gathering": data["sr_ansible_gathering"],
            "Use Collections": data["sr_use_collections"],
            "Build": data["build"],
        }
        if result["result"]:
            if "overall" in result["result"]:
                data["result"] = result["result"]["overall"]
            if result["result"].get("xunit_url"):
                data["xunit_url"] = result["result"]["xunit_url"]

                xml_data = requests.get(data["xunit_url"], verify=verify).content
                bs = BeautifulSoup(xml_data, "xml")
                for log_set in bs.find_all("logs"):
                    for log_item in log_set.find_all("log", href=SYSTEM_ROLE_TF_LOG_RE):
                        log_url = log_item.attrs["href"]
                        match = SYSTEM_ROLE_TF_LOG_RE.search(log_url)
                        test_result = match.groupdict()
                        status = test_result["test_status"]
                        if status == "SUCCESS":
                            data["passed"].append(test_result)
                        else:
                            data["failed"].append(test_result)
                        if args.all_statuses or status == "FAIL":
                            errors.extend(
                                get_errors_from_ansible_log(
                                    args, log_url, extra_error_fields
                                )
                            )
        elif result["run"] and "artifacts" in result["run"]:
            results_xml = result["run"]["artifacts"] + "/results.xml"
            xml_data = requests.get(results_xml, verify=verify).content
            bs = BeautifulSoup(xml_data, "xml")
            for log_item in bs.find_all("log", href=re.compile(r"/log.txt$")):
                data["job_data"] = parse_tf_job_log(
                    args, log_item.attrs["href"], data["created_ts"]
                )
                data["passed"].extend(data["job_data"]["passed"])
                data["failed"].extend(data["job_data"]["failed"])
                if args.get_addresses and "ip_addresses" in data["job_data"]:
                    data["ip_addresses"] = data["job_data"]["ip_addresses"]
        elif result["state"] == "queued":
            data["result"] = "queued"

        rv.append(data)
    return rv, errors


def print_testing_farm_result(args, result):
    max_line_len = 120
    indent = ""
    line = indent
    sep = ""
    for key in sorted(result.keys()):
        val = result[key]
        if key == "ip_addresses":
            val = ",".join(val)
        elif not val or isinstance(val, (list, dict)):
            continue
        new_val = f"{sep}{key}={val}"
        if len(line) + len(new_val) > max_line_len:
            print(line)
            indent = "  "
            line = indent + f"{key}={val}"
            sep = " "
        else:
            line += new_val
            sep = " "
    print(line)
    print(
        f"  Result {result.get('result', 'running')} - {len(result['passed'])} passed - "
        f"{len(result['failed'])} failed"
    )
    if result.get("result", "running") == "running" and "job_data" in result:
        print("  last line: " + result["job_data"]["last_line"])
    if args.failed_tests_to_show > 0 and result.get("failed"):
        print("  Failures:")
        for failed_test in result["failed"][-args.failed_tests_to_show:]:  # fmt: skip
            print(f"    failed {failed_test}")
    print("")


def sanitize_for_actions(text):
    return re.sub(r"^::", " ::", text, flags=re.M)


def print_ansible_errors(args, errors):
    if not errors:
        print("No errors found")
        return
    headings = list(errors[0].keys())
    if args.csv_errors:
        if args.csv_errors == "-":
            csv_f = sys.stdout
        else:
            csv_f = open(args.csv_errors, "w")
        writer = csv.DictWriter(csv_f, fieldnames=headings)
        writer.writeheader()
        for error in errors:
            writer.writerow(error)
        if csv_f != sys.stdout:
            csv_f.close()
    if args.gspread:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            args.gspread_creds, scope
        )
        gc = gspread.authorize(credentials)
        if args.gspread == "NEW":
            # create a new spreadsheet
            sh = gc.create("LSR testing spreadsheet")
            # need to show url to new spreadsheet
            # and share with given user
        else:
            sh = gc.open_by_url(args.gspread)
        if args.gspread_worksheet_title:
            worksheets = [
                ws for ws in sh.worksheets() if ws.title == args.gspread_worksheet_title
            ]
            if worksheets:
                worksheet = worksheets[0]
            else:
                worksheet = sh.add_worksheet(args.gspread_worksheet_title, 1, 1)
        else:
            worksheet = sh.get_worksheet(0)
            worksheet.clear()
        values = [headings]
        current_value = {}
        if args.group_by:
            errors = sorted(errors, key=itemgetter(*args.group_by))
            for key in args.group_by:
                current_value[key] = None
        for error in errors:
            value_list = []
            for key in headings:
                item = error[key]
                if key in current_value:
                    if item == current_value.get(key):
                        item = ""
                    else:
                        current_value[key] = item
                if isinstance(item, list):
                    value = "\n".join(item)
                else:
                    value = str(item)
                if len(value) > 5000:
                    value = value[:5000] + ".... truncated"
                value_list.append(value)
            values.append(value_list)
        sh.values_update(
            worksheet.title, {"valueInputOption": "USER_ENTERED"}, {"values": values}
        )
    if args.github_action_format:
        for error in errors:
            print(f"::group::{os.path.basename(error['Url'])} {error['Task']}")
            for field in [
                "Ansible Version",
                "Task Path",
                "Role",
                "Url",
                "RC",
                "Start",
                "End",
                "Host",
            ]:
                value = error.get(field)
                if value or value == 0:
                    print(f"{field}: {value}")
            parents = error.get("Parents")
            if parents:
                print("Parents:")
                for parent in parents:
                    print(f"    {parent}")
            for field in ["Detail", "Stdout", "Stderr"]:
                value = error.get(field)
                if value:
                    print(f"\n{field}:")
                    if isinstance(value, list):
                        value = "\n".join(value)
                    sanitized = sanitize_for_actions(value)
                    print(sanitized)
            print("::endgroup::")


def parse_arguments():
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
        nargs="*",
        help="beaker jobs to get logs for - use ALL to get logs from all jobs",
    )
    parser.add_argument(
        "--failed-tests-to-show",
        type=int,
        default=0,
        help="for beaker logs, show this many failed tests",
    )
    parser.add_argument(
        "--lsr-error-log",
        default=[],
        nargs="*",
        help="lsr error log file from lsr_report_errors.py",
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
    parser.add_argument(
        "--gspread",
        default="",
        help="update this google spreadsheet - or use NEW to create a new one",
    )
    parser.add_argument(
        "--gspread-worksheet-title",
        default="",
        help="write to the worksheet with this name - will ensure worksheet exists",
    )
    parser.add_argument(
        "--gspread-creds",
        default=os.environ["HOME"] + "/.config/gspread/google_secret.json",
        help="path to google spreadsheet api credentials",
    )
    parser.add_argument(
        "--group-by",
        default=[],
        action="append",
        help="For gspread - group items by these columns",
    )
    parser.add_argument(
        "--disable-verify",
        default=False,
        action="store_true",
        help="disable CA cert verify (use requests verify=False)",
    )
    parser.add_argument(
        "--gather-errors",
        default=False,
        action="store_true",
        help="Scan all logs for Ansible errors/failures",
    )
    parser.add_argument(
        "--testing-farm-job-url",
        "--tf-job-url",
        default=[],
        nargs="*",
        help="url of testing farm job api e.g. https://api.dev.testing-farm.io/v0.1/requests/xxxxx",
    )
    parser.add_argument(
        "--github-action-format",
        "--gh-format",
        default=False,
        action="store_true",
        help="Write errors in GitHub Actions-friendly format",
    )
    parser.add_argument(
        "--timing-info",
        default=False,
        action="store_true",
        help="print timing info",
    )
    parser.add_argument(
        "--get-addresses",
        default=False,
        action="store_true",
        help="scan artifacts for IP addresses and add to result data",
    )

    args = parser.parse_args()
    return args


def main():
    args = parse_arguments()

    if args.verbose > 1:
        logging.getLogger().setLevel(logging.DEBUG)
        # debug_requests_on()
    elif args.verbose > 0:
        logging.getLogger().setLevel(logging.INFO)

    if args.csv_errors or args.gspread or args.github_action_format:
        args.gather_errors = True

    if args.testing_farm_job_url:
        result_statuses = {}
        results, failures = get_testing_farm_result(args)
        for result in results:
            result_status = result.get("result", "running")
            result_statuses[result_status] = result_statuses.get(result_status, 0) + 1
            print_testing_farm_result(args, result)
        print(f"Result statuses: {result_statuses}")
        print_ansible_errors(args, failures)
    elif args.lsr_error_log:
        errors = []
        for log_url in args.lsr_error_log:
            errors.extend(get_errors_from_ansible_log(args, log_url))
        print_ansible_errors(args, errors)
    elif args.beaker_job:
        get_logs_from_beaker(args)
    elif any((args.github_repo, args.github_pr, args.github_pr_search)):
        errors = get_logs_from_github(args)
        print_ansible_errors(args, errors)
    elif args.log_url:
        errors = get_logs_from_url(args)
        print_ansible_errors(args, errors)

    if args.timing_info:
        print_timing_info(args)


if __name__ == "__main__":
    sys.exit(main())
