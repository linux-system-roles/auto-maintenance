#!/usr/bin/python3

import datetime
import re
import jenkins
import json
import os

# import pprint
import requests
import sys
import yaml

JenkinsException = Exception
NotFoundException = Exception

cfg = yaml.safe_load(open(os.path.join(os.environ["HOME"], ".config", "jenkins.yml")))
url = cfg[cfg["current"]]["url"]
username = cfg[cfg["current"]]["username"]
job_name = cfg[cfg["current"]]["job_name"]

server = jenkins.Jenkins(url, username=username)
job = server.get_job_info(job_name, depth=0, fetch_all_builds=False)
# yaml.safe_dump(job, open("junk.yml", "w"))
task_nums = [build["number"] for build in job["builds"]]
# key is task num - val is full content of task
tasks_info = {}
# max task age in seconds
MAX_TASK_AGE = datetime.timedelta(seconds=int(os.environ.get("MAX_TASK_AGE", "86400")))
now = datetime.datetime.now()

BUILD_ARTIFACT = "%(folder_url)sjob/%(short_name)s/%(number)s/artifact/%(artifact)s"


def get_build_artifact(server, name, number, artifact):
    """Get artifacts from job
    :param name: Job name, ``str``
    :param number: Build number, ``str`` (also accepts ``int``)
    :param artifact: Artifact relative path, ``str``
    :returns: artifact to download, ``dict``
    """
    folder_url, short_name = server._get_job_folder(name)
    try:
        response = server.jenkins_open(
            requests.Request("GET", server._build_url(BUILD_ARTIFACT, locals()))
        )
        if response:
            return json.loads(response)
        else:
            raise JenkinsException("job[%s] number[%s] does not exist" % (name, number))
    except requests.exceptions.HTTPError:
        raise JenkinsException("job[%s] number[%s] does not exist" % (name, number))
    except ValueError:
        raise JenkinsException(
            "Could not parse JSON info for job[%s] number[%s]" % (name, number)
        )
    except NotFoundException:
        # This can happen if the artifact is not found
        return None


def get_pr_status_label(task, short=True):
    for action in task["actions"]:
        if action["_class"] == "hudson.model.ParametersAction":
            for param in action["parameters"]:
                if param["name"] == "pipeline_state_reporter_options":
                    label = param["value"].split("=")[1]
                    if label.endswith("/(citool)"):
                        label = label.replace("/(citool)", "")
                    if short:
                        match = re.match(r"^(RHEL-\d+[.]\d+)[^/]+(/.+)$", label)
                        if match:
                            label = match.group(1) + match.group(2)
                        match = re.match(r"^(CentOS-\d+)[^/]+(/.+)$", label)
                        if match:
                            label = match.group(1) + match.group(2)
                    return label


def get_pr_info(task):
    for action in task["actions"]:
        if action["_class"] == "hudson.model.ParametersAction":
            for param in action["parameters"]:
                if param["name"] == "github_options":
                    val = param["value"].split("=")[1]
                    org, repo, pr = val.split(":")[0:3]
                    if org == "linux-system-roles":
                        return (repo, pr)
                    else:
                        return (org + "/" + repo, pr)


def get_queued_time(task):
    for action in task["actions"]:
        if action["_class"] == "jenkins.metrics.impl.TimeInQueueAction":
            return str(int(action["buildableDurationMillis"] / 1000))


def get_test_status(task):
    status = ""
    for action in task["actions"]:
        if "_class" not in action:
            continue
        if action["_class"] == "com.jenkinsci.plugins.badge.action.BadgeAction":
            if "pipeline" in action["text"]:
                continue
            status = action["text"]
            break
    if not status:
        status = task["result"]
    if status == "Tests did not run correctly":
        status = "CANCELLED"
    status = status.replace("Tests ", "")
    return status


def format_queued_task(task, ignored):
    label = get_pr_status_label(task)
    role, prnum = get_pr_info(task)
    ts = datetime.datetime.fromtimestamp(task["inQueueSince"] / 1000).isoformat(
        timespec="seconds"
    )
    if task["why"].startswith("Waiting for next available executor"):
        why = "waiting on executor"
    else:
        why = task["why"]
    return (str(task["id"]), ts, role, prnum, label, why)


def format_running_task(task, ts):
    label = get_pr_status_label(task)
    role, prnum = get_pr_info(task)
    queue_time = get_queued_time(task)
    tsstr = ts.isoformat(timespec="seconds")
    return (task["id"], tsstr, role, prnum, label, queue_time)


def format_completed_task(task, ts):
    label = get_pr_status_label(task)
    role, prnum = get_pr_info(task)
    queue_time = get_queued_time(task)
    status = get_test_status(task)
    duration = str(int(task["duration"] / 1000))
    tsstr = ts.isoformat(timespec="seconds")
    return (task["id"], tsstr, role, prnum, label, duration, queue_time, status)


FORMATS = {
    "queued": {
        "hdr": ("QueueID", "Queued Since", "Role", "PR", "Platform", "Queue Reason"),
        "fmt": "{:8s} {:19s} {:15s} {:3s} {:22s} {:20s}",
        "fn": format_queued_task,
    },
    "running": {
        "hdr": ("TaskID", "Started At", "Role", "PR", "Platform", "Queue Time"),
        "fmt": "{:8s} {:19s} {:15s} {:3s} {:22s} {:10s}",
        "fn": format_running_task,
    },
    "completed": {
        "hdr": (
            "TaskID",
            "Started At",
            "Role",
            "PR",
            "Platform",
            "Duration",
            "Queue Time",
            "Status",
        ),
        "fmt": "{:8s} {:19s} {:15s} {:3s} {:22s} {:8s} {:10s} {:10s}",
        "fn": format_completed_task,
    },
}


def format_fields(task, task_state, ts, is_header=False):
    # task_state is one of queued, running, completed
    fmt = FORMATS[task_state]["fmt"]
    if is_header:
        data = FORMATS[task_state]["hdr"]
    else:
        data = FORMATS[task_state]["fn"](task, ts)
    # print(f"fmt {fmt} data {data}")
    return fmt.format(*data)


def task_iter(task_nums, server):
    for num in task_nums:
        global tasks_info
        task, ts = tasks_info.get(num, (None, None))
        if task is None:
            task = server.get_build_info(job_name, num)
            ts = datetime.datetime.fromtimestamp(task["timestamp"] / 1000)
            tasks_info[num] = (task, ts)
        if now - ts < MAX_TASK_AGE:
            yield (task, ts)
        else:
            break


def print_running_tasks(server, task_nums, args):
    print(format_fields(None, "running", None, True))
    for task, ts in task_iter(task_nums, server):
        if task["result"] is None:
            print(format_fields(task, "running", ts))
    # pprint.pprint(lastbuild)
    # relpath = "work-tests_configure_ha_cluster.ymlT7FqqE/ansible-output.txt"
    # #not in version 1.7.0
    # artifact = get_build_artifact(server, job_name, lastnum, relpath)
    # pprint.pprint(artifact)
    # console = server.get_build_console_output(job_name, lastnum)
    # console_lines = console.split("\n")
    # pprint.pprint(console_lines[-10:])
    # not permitted
    # plugins = server.get_plugins()
    # print(plugins)
    # node = server.get_node_info(lastbuild["builtOn"])
    # pprint.pprint(node)


def print_queued_tasks(server, task_nums, args):
    print(format_fields(None, "queued", None, True))
    queue_info = server.get_queue_info()
    for task in queue_info:
        if task["task"]["name"] == job_name:
            print(format_fields(task, "queued", None))


def print_completed_tasks(server, task_nums, args):
    print(format_fields(None, "completed", None, True))
    for task, ts in task_iter(task_nums, server):
        if not task["result"] is None:
            print(format_fields(task, "completed", ts))


def stop_tasks(server, task_nums, args):
    """Stop tasks matching the display_name pattern."""
    for num in task_nums:
        global tasks_info
        task = tasks_info.setdefault(num, server.get_build_info(job_name, num))
        task_name = task["displayName"]
        if re.search(args[0], task_name) and task["result"] is None:
            print(f"Stopping {num} {task_name}")
            server.stop_build(job_name, num)


def print_task_info(server, task_nums, args):
    """Print info for given build numbers."""
    for num in args:
        task = server.get_build_info(job_name, int(num))
        yaml.safe_dump(task, sys.stdout)


if len(sys.argv) > 1:
    locals()[sys.argv[1]](server, task_nums, sys.argv[2:])
else:
    print("Queued tasks:")
    print_queued_tasks(server, task_nums, [])
    print("\nRunning tasks:")
    print_running_tasks(server, task_nums, [])
    print("\nCompleted tasks:")
    print_completed_tasks(server, task_nums, [])
