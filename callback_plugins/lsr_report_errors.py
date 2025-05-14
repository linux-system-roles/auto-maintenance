# original code from Ansible
# (c) 2016, Matt Martz <matt@sivel.net>
# (c) 2017 Ansible Project
# New features from Red Hat
# (c) 2025 Red Hat, Inc.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

# Make coding more python3-ish
from __future__ import absolute_import, division, print_function
import os
import datetime
import json

from functools import partial

from ansible.module_utils._text import to_text
from ansible.parsing.ajson import AnsibleJSONEncoder
from ansible.plugins.callback import CallbackBase
from ansible.release import __version__


__metaclass__ = type

DOCUMENTATION = """
    name: lsr_report_errors
    short_description: Report errors encountered in Ansible playbook runs
    description:
        - Report errors encountered in Ansible playbook runs
    type: stdout
    requirements:
      - Set as stdout in config
    options:
      lsr_json_indent:
        name: Use indenting for the JSON output
        description:
            - If specified, use this many spaces for indenting in the JSON output.
            - If <= 0, write to a single line.
        default: 4
        env:
          - name: ANSIBLE_LSR_JSON_INDENT
        ini:
          - key: lsr_json_indent
            section: defaults
        type: integer
      lsr_json_output_dir:
        name: Output directory
        description: Output directory - by default, output goes into regular log output
        env:
          - name: ANSIBLE_LSR_JSON_OUTPUT_DIR
        ini:
          - key: lsr_json_output_dir
            section: defaults
        type: str
"""


LOCKSTEP_CALLBACKS = frozenset(("linear", "debug"))
PARENT_ACTIONS = frozenset(
    ("include_role", "include_tasks", "import_role", "import_tasks", "import")
)


def current_time():
    return "%sZ" % datetime.datetime.now(datetime.timezone.utc).isoformat()


class Parents(object):
    def __init__(self):
        self.parents = []
        self.files = []

    def push_or_pop(self, path_obj):
        # import pdb; pdb.set_trace()
        path = path_obj.get_path()
        file_name, line_no = path.split(":")
        if self.files and file_name == self.files[-1]:
            # update the location
            self.parents[-1] = path
            return
        try:
            # if this file is one of our parents, pop
            # the stack down to that parent
            idx = self.files.index(file_name)
            # pop elements after file_name
            # assumes no recursion
            self.files = self.files[:idx]
            self.parents = self.parents[:idx]
        except ValueError:
            # we have not seen this file yet, so must be
            # a new include
            pass
        self.parents.append(path)
        self.files.append(file_name)

    def clear(self):
        self.parents = []
        self.files = []

    def get_parents(self):
        return self.parents[:]


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "lsr_report_errors"
    CALLBACK_NEEDS_WHITELIST = False  # wokeignore:rule=whitelist
    CALLBACK_NEEDS_ENABLED = False

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display)
        self.errors = []
        self._is_lockstep = False

        self.set_options()

        self._json_indent = self.get_option("lsr_json_indent")
        if self._json_indent <= 0:
            self._json_indent = None
        self._write_log_name = None
        self.parents = Parents()

    def reset(self):
        self.parents.clear()
        self.errors = []

    def _new_play(self, play):
        self._is_lockstep = play.strategy in LOCKSTEP_CALLBACKS
        return {
            "play": {
                "name": play.get_name(),
                "id": to_text(play._uuid),
                "path": to_text(play.get_path()),
                "duration": {"start": current_time()},
                "playbook_path": self._playbook_path,
                "playbook_name": self._playbook_name,
            },
            "tasks": [],
        }

    def _new_task(self, task):
        return {
            "task": {
                "name": task.get_name(),
                "id": to_text(task._uuid),
                "path": to_text(task.get_path()),
                "duration": {"start": current_time()},
            },
            "hosts": {},
        }

    def v2_playbook_on_start(self, playbook):
        self._playbook_name = os.path.splitext(os.path.basename(playbook._file_name))[0]
        self._playbook_path = playbook._file_name
        if self._playbook_name.startswith("tests_"):
            # only write to the name of the test log
            self._write_log_name = self._playbook_name + ".json"
        self.parents.clear()

    def v2_playbook_on_play_start(self, play):
        self.parents.push_or_pop(play)

    def v2_runner_on_start(self, host, task):
        if self._is_lockstep:
            return
        self._current_task = self._new_task(task)
        self.parents.push_or_pop(task)

    def v2_playbook_on_task_start(self, task, is_conditional):
        if not self._is_lockstep:
            return
        self._current_task = self._new_task(task)
        self.parents.push_or_pop(task)

    def v2_playbook_on_handler_task_start(self, task):
        if not self._is_lockstep:
            return
        self._current_task = self._new_task(task)
        self.parents.push_or_pop(task)

    def v2_playbook_on_stats(self, stats):
        """Display info about playbook statistics"""

        output_dir = self.get_option("lsr_json_output_dir")
        if output_dir:
            if self._write_log_name:
                os.makedirs(output_dir, exist_ok=True)
                output_file = os.path.join(output_dir, self._write_log_name)
                with open(output_file, "w") as of:
                    json.dump(
                        self.errors,
                        of,
                        cls=AnsibleJSONEncoder,
                        indent=self._json_indent,
                        sort_keys=True,
                    )
        else:
            self._display.display("SYSTEM ROLES ERRORS BEGIN v1")
            self._display.display(
                json.dumps(
                    self.errors,
                    cls=AnsibleJSONEncoder,
                    indent=self._json_indent,
                    sort_keys=True,
                )
            )
            self._display.display("SYSTEM ROLES ERRORS END v1")
        self.reset()

    def _record_task_result(self, on_info, result, **kwargs):
        """This function is used as a partial to add failed/skipped info in a single method"""
        if on_info.get("failed"):
            task_path = self._current_task["task"]["path"]
            parents = self.parents.get_parents()
            if parents[-1] == task_path:
                parents.pop()

            host = os.path.basename(result._host.name)
            task_name = result._task.name
            if "results" in result._result:
                results = result._result["results"]
            else:
                results = [result._result]
            for result_item in results:
                message = result_item.get(
                    "msg", result_item.get("censored", "No message could be found")
                )
                start_time = result_item.get(
                    "start", self._current_task["task"]["duration"]["start"]
                )
                end_time = result_item.get("end", current_time())
                error = {
                    "host": host,
                    "task_name": task_name,
                    "task_path": task_path,
                    "ansible_version": __version__,
                    "parents": parents,
                    "message": message,
                    "start_time": start_time,
                    "end_time": end_time,
                }
                loop_label = result_item.get("_ansible_item_label")
                loop_item_key = result_item.get("ansible_loop_var")
                if loop_label or loop_item_key:
                    if loop_item_key:
                        error["loop_var"] = loop_item_key
                        loop_item = result_item[loop_item_key]
                    else:
                        loop_item = None
                    if loop_item and loop_item == message:
                        loop_item = "<same as message>"
                    if loop_label and loop_label == loop_item:
                        loop_label = "<same as loop_item>"
                    if loop_label and loop_label == message:
                        loop_label = "<same as message>"
                    if loop_item:
                        error["loop_item"] = loop_item
                    if loop_label:
                        error["loop_label"] = loop_label
                if "delta" in result_item:
                    error["delta"] = result_item["delta"]
                if "rc" in result_item:
                    error["rc"] = result_item["rc"]
                if "attempts" in result_item:
                    error["attempts"] = result_item["attempts"]
                self.errors.append(error)

    def __getattribute__(self, name):
        """Return ``_record_task_result`` partial with a dict containing skipped/failed if necessary"""
        if name not in (
            "v2_runner_on_ok",
            "v2_runner_on_failed",
            "v2_runner_on_unreachable",
            "v2_runner_on_skipped",
        ):
            return object.__getattribute__(self, name)

        on = name.rsplit("_", 1)[1]

        on_info = {}
        if on in ("failed", "skipped"):
            on_info[on] = True

        return partial(self._record_task_result, on_info)
