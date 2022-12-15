#!/usr/bin/python3

import datetime
import re
import jenkins
import json
import os
import signal

# import pprint
import requests
import sys
import yaml

signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

JenkinsException = Exception
NotFoundException = Exception

cfg = yaml.safe_load(open(os.path.join(os.environ["HOME"], ".config", "jenkins.yml")))
url = cfg[cfg["current"]]["url"]
username = cfg[cfg["current"]]["username"]
job_name = cfg[cfg["current"]]["job_name"]
ssh_private_key = cfg[cfg["current"]].get("ssh_private_key")
ssh_user = cfg[cfg["current"]].get("ssh_user")
token = cfg[cfg["current"]].get("token")

kwargs = {"username": username}
if token:
    kwargs["password"] = token
server = jenkins.Jenkins(url, **kwargs)
job = server.get_job_info(job_name, depth=0, fetch_all_builds=False)
# yaml.safe_dump(job, open("junk.yml", "w"))
task_nums = [build["number"] for build in job["builds"]]
# key is task num - val is full content of task
tasks_info = {}
# max task age in seconds
MAX_TASK_AGE = datetime.timedelta(seconds=int(os.environ.get("MAX_TASK_AGE", "86400")))
now = datetime.datetime.now()
now_tz = now.astimezone()

BUILD_ARTIFACT = "%(folder_url)sjob/%(short_name)s/%(number)s/artifact/%(artifact)s"

CONSOLE_TZ = "Z"
CONSOLE_TS_FMT = "%Y-%m-%d %H:%M:%S%z"


def time_to_local(ts_str, start_ts):
    """Convert console time string to local time."""
    dt_ts_str = start_ts.date().isoformat() + " " + ts_str + CONSOLE_TZ
    dt = datetime.datetime.strptime(dt_ts_str, CONSOLE_TS_FMT).astimezone(now_tz.tzinfo)
    return dt


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
                        else:
                            match = re.match(r"^(CentOS-Stream-\d+)(/.+)$", label)
                            if match:
                                label = match.group(1).replace(
                                    "-Stream", ""
                                ) + match.group(2)
                            else:
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
        if action.get("_class") == "jenkins.metrics.impl.TimeInQueueAction":
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


def get_task_ts(server, task_num):
    """Return the task info and timestamp."""
    global tasks_info
    task, ts = tasks_info.get(task_num, (None, None))
    if task is None:
        task = server.get_build_info(job_name, task_num)
        ts = datetime.datetime.fromtimestamp(task["timestamp"] / 1000)
        tasks_info[task_num] = (task, ts)
    return (task, ts)


def task_iter(task_nums, server):
    """Iterate through task nums returning task info and timestamp."""
    for num in task_nums:
        task, ts = get_task_ts(server, num)
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
    size = 0
    for task in queue_info:
        size = size + 1
        if task["task"]["name"] == job_name:
            print(format_fields(task, "queued", None))
    print(f"Queue size: {size}")


def print_completed_tasks(server, task_nums, args):
    print(format_fields(None, "completed", None, True))
    for task, ts in task_iter(task_nums, server):
        if not task["result"] is None:
            print(format_fields(task, "completed", ts))


def cancel_tasks(server, task_nums, args):
    """Cancel given tasks."""
    for num in args:
        print(f"Stopping {num}")
        server.stop_build(job_name, num)


def print_task_info(server, task_nums, args):
    """Print info for given build numbers."""
    for num in args:
        task = server.get_build_info(job_name, int(num))
        yaml.safe_dump(task, sys.stdout)


def get_node_info_for_task(server, task_num):
    """Print the node info for the given task."""
    task = server.get_build_info(job_name, task_num)
    node_name = task["builtOn"]
    node = server.get_node_info(node_name)
    description = node["description"]
    match = re.search(r"HOSTNAME=([0-9.]+)", description)
    if match:
        return {"node_name": node_name, "ip": match.group(1)}
    else:
        print(f"ERROR: for node_name {node_name} description unknown {description}")
        return {"node_name": node_name, "ip": "unknown"}


def get_task_tests_info(server, task_num):
    """Get the info for all of the tests of a task given a task num."""
    pat_pr = r"^ +lsr-github:github --pull-request= --pull-request=linux-system-roles:(?P<role>[^:]+):(?P<pr>[^:]+):.*$"
    rx_pr = re.compile(pat_pr)
    pat_test = (
        r"^[|] dist-git-(?P<role>[^-]+)-[^/]+/tests/(?P<test>[^ ]+) +[|] +(?P<stage>[^ ]+) +[|]"
        r" +(?P<state>[^ ]+) +[|] +(?P<result>[^ ]+) +[|] +(?P<arch>[^ ]+) +(?P<platform>[^ ]+) .*"
    )
    rx_test = re.compile(pat_test)
    pat_guest_id = r" [|] +([a-zA-Z0-9]{8}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{12}) +[|]"
    rx_guest_id = re.compile(pat_guest_id)
    pat_workspace = r"^Building remotely on .* in workspace (?P<workspace>[^ ]+)$"
    rx_workspace = re.compile(pat_workspace)
    pat_work_test_dir = (
        r"^.*dist-git-[^ ]+ working directory 'work-([^.]+.yml)([^']+)'.*$"
    )
    rx_work_test_dir = re.compile(pat_work_test_dir)
    pat_provision_start = (
        r"^.*\[(?P<ts_prov>[0-9:]+)\] .*\[dist-git-[^/]+/tests/(?P<test>tests[^.]+[.]yml)\].* "
        r"starting guest provisioning.*$"
    )
    rx_provision_start = re.compile(pat_provision_start)
    pat_guest_setup_start = (
        r"^.*\[(?P<ts_setup>[0-9:]+)\] .*\[dist-git-[^/]+/tests/(?P<test>tests[^.]+[.]yml)\].* "
        r"starting guest setup.*$"
    )
    rx_guest_setup_start = re.compile(pat_guest_setup_start)
    pat_test_start = (
        r"^.*\[(?P<ts_start>[0-9:]+)\] .*\[dist-git-[^/]+/tests/(?P<test>tests[^.]+[.]yml)\].* "
        r"starting tests execution.*$"
    )
    rx_test_start = re.compile(pat_test_start)
    pat_test_end = (
        r"^.*\[(?P<ts_end>[0-9:]+)\] .*\[dist-git-[^/]+/tests/(?P<test>tests[^.]+[.]yml)\].* "
        r"cleanup finished.*$"
    )
    rx_test_end = re.compile(pat_test_end)

    task, ts = get_task_ts(server, task_num)
    console = server.get_build_console_output(job_name, task_num)
    console_lines = console.split("\n")
    tests = {}
    info = {"tests": tests, "start": ts.isoformat(timespec="seconds")}
    last_test = ""
    for line in console_lines:
        match = rx_guest_id.search(line)
        if match and last_test:
            tests[last_test]["guest_id"] = match.group(1)
        elif last_test:
            tests[last_test]["guest_id"] = "unknown"
        match = rx_test.match(line)
        if match:
            test = match.group("test")
            tests.setdefault(test, {}).update(match.groupdict())
            info.update(match.groupdict())
            last_test = test
        else:
            last_test = ""
        match = rx_pr.match(line)
        if match:
            info.update(match.groupdict())
        match = rx_workspace.match(line)
        if match:
            info.update(match.groupdict())
        match = rx_work_test_dir.match(line)
        if match:
            test = match.group(1)
            work_dir = "work-" + test + match.group(2)
            tests.setdefault(test, {})["work_dir"] = work_dir
        for rx in (
            rx_provision_start,
            rx_guest_setup_start,
            rx_test_start,
            rx_test_end,
        ):
            match = rx.match(line)
            if match:
                test = match.group(2)
                grp_dict = match.groupdict()
                for kk, vv in match.groupdict().items():
                    if kk == "test":
                        continue
                    dt = time_to_local(vv, ts)
                    grp_dict[kk] = dt.strftime("%Y-%m-%dT%H:%M:%S")
                tests.setdefault(test, {}).update(grp_dict)

    node_info = get_node_info_for_task(server, task_num)
    info.update(node_info)
    return info


def print_task_tests_info(server, task_nums, args):
    """Print tests information for a given task."""
    info = get_task_tests_info(server, int(args[0]))
    print(
        f"Role:{info['role']} PR:{info['pr']} Platform:{info['platform']} Arch:{info['arch']} Start:{info['start']}"
    )
    print(f"Node:{info['node_name']} IP:{info['ip']} Workspace:{info['workspace']}")
    fmt = "{:20s} {:10s} {:10s} {:36s} {} {}"
    print(fmt.format("Stage", "State", "Result", "GuestID", "Test", "Workdir"))
    for test, data in info["tests"].items():
        print(
            fmt.format(
                data["stage"],
                data["state"],
                data["result"],
                data["guest_id"],
                test,
                data.get("work_dir", "unknown"),
            )
        )
        print(
            f"ts_prov:{data.get('ts_prov', 'None')} ts_setup:{data.get('ts_setup', 'None')} "
            f"ts_start:{data.get('ts_start', 'None')} ts_end:{data.get('ts_end', 'None')}"
        )


def print_task_console(server, task_nums, args):
    console = server.get_build_console_output(job_name, int(args[0]))
    last = int(args[1])
    console_lines = "\n".join(console.split("\n")[-last:])
    print(console_lines)


def print_node_info(server, task_nums, args):
    """Print info for given build node."""
    for node_name in args:
        node = server.get_node_info(node_name)
        yaml.safe_dump(node, sys.stdout)


# def get_workspace_file(ip, workspace_dir, work_test_dir, guest_id, file_type):
#     """Get the file from the workspace dir on the Jenkins server."""
#     if file_type == "ansible":
#         pass
#     cmd = f"scp -i {ssh_private_key} {ssh_user}@{ip}:"
#     subprocess.run(cmd)


def cancel_duplicate_tasks(server, task_nums, args):
    """Stop duplicate queued and running tasks.  Keep the newest one."""
    found_keys = set()
    queue_info = server.get_queue_info()
    for task in queue_info:
        if task["task"]["name"] == job_name:
            label = get_pr_status_label(task, False)
            role, prnum = get_pr_info(task)
            key = f"{label}:{role}:{prnum}"
            if key in found_keys:
                tsstr = datetime.datetime.fromtimestamp(
                    task["inQueueSince"] / 1000
                ).isoformat(timespec="seconds")
                print(f"Cancelling duplicate queued task {task['id']} {key} {tsstr}")
                server.cancel_queue(task["id"])
            else:
                found_keys.add(key)
    for task, ts in task_iter(task_nums, server):
        if task["result"] is None:
            label = get_pr_status_label(task, False)
            role, prnum = get_pr_info(task)
            key = f"{label}:{role}:{prnum}"
            if key in found_keys:
                tsstr = ts.isoformat(timespec="seconds")
                print(f"Cancelling duplicate running task {task['id']} {key} {tsstr}")
                server.stop_build(job_name, task["id"])
            else:
                found_keys.add(key)


def print_test_failures(server, task_nums, args):
    """Print test failures for tasks matching args."""
    role, prnum, label = None, None, None
    if len(args) > 0:
        role = args[0]
    if len(args) > 1:
        prnum = args[1]
    if len(args) > 2:
        label = args[2]
    for task, ts in task_iter(task_nums, server):
        if task["result"] is None:
            task_label = get_pr_status_label(task)
            task_role, task_prnum = get_pr_info(task)
            if (
                role == task_role
                and (prnum is None or prnum == task_prnum)
                and (label is None or label == task_label)
            ):
                info = get_task_tests_info(server, int(task["id"]))
                for test, data in info["tests"].items():
                    if data["result"] not in ["PASSED", "UNDEFINED"]:
                        print(
                            f"{task_role} {task_prnum} {task_label} {test} {info['start']}"
                        )


if len(sys.argv) > 1:
    locals()[sys.argv[1]](server, task_nums, sys.argv[2:])
else:
    print("Queued tasks:")
    print_queued_tasks(server, task_nums, [])
    print("\nRunning tasks:")
    print_running_tasks(server, task_nums, [])
    print("\nCompleted tasks:")
    print_completed_tasks(server, task_nums, [])
