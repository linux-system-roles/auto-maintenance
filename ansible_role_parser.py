#!/usr/bin/env python

import os
import sys
import logging
from pathlib import Path

from ansible.errors import AnsibleParserError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.mod_args import ModuleArgsParser
from ansible.parsing.yaml.objects import AnsibleSequence, AnsibleMapping

if os.environ.get("LSR_DEBUG") == "true":
    logging.getLogger().setLevel(logging.DEBUG)


ROLE_DIRS = ["defaults", "examples", "files", "handlers", "library", "meta",
    "module_utils", "tasks", "templates", "tests", "vars"]

PLAY_KEYS = {
    "gather_facts",
    "handlers",
    "hosts",
    "import_playbook",
    "post_tasks",
    "pre_tasks",
    "roles"
    "tasks",
}


def is_role_dir(role_path, dirpath):
    if role_path == dirpath:
        return False
    dir_pth = Path(dirpath)
    relpath = dir_pth.relative_to(role_path)
    base_dir = relpath.parts[0]
    return base_dir in ROLE_DIRS

def get_file_type(item):
    if isinstance(item, AnsibleMapping):
        if "galaxy_info" in item or "dependencies" in item:
            return "meta"
        return "vars"
    elif isinstance(item, AnsibleSequence):
        return "tasks"
    else:
        raise Exception(f"Error: unknown type of file: {item}")


def get_item_type(item):
    if isinstance(item, AnsibleMapping):
        for key in PLAY_KEYS:
            if key in item:
                return "play"
        if "block" in item:
            return "block"
        return "task"
    else:
        raise Exception(f"Error: unknown type of item: {item}")

def handle_other(item, filepath):
    """handle properties of Ansible item other than vars and tasks"""
    for role in item.get("roles", []):
        print(f"roles item role {role} - {filepath}")
    return

def handle_vars(item, filepath):
    """handle vars of Ansible item"""
    for var in item.get("vars", []):
        logging.debug(f"\tvar = {var}")
    return

def handle_meta(item, filepath):
    """handle meta/main.yml file"""
    for role in item.get("dependencies", []):
        print(f"meta dependencies role {role} - {filepath}")

def handle_task(task, role_modules, filepath):
    """handle a single task"""
    mod_arg_parser = ModuleArgsParser(task)
    try:
        action, _, _ = mod_arg_parser.parse(skip_action_validation=True)
    except AnsibleParserError as e:
        raise SystemExit("Couldn't parse task at %s (%s)\n%s" % (task, e.message, task))
    if action == "include_role" or action == "import_role":
        print(f"task role {task[action]['name']} - {filepath}")
    elif action in role_modules:
        print(f"task role module {action} - {filepath}")
    handle_tasks(task, role_modules, filepath)

def handle_task_list(tasks, role_modules, filepath):
    """item is a list of Ansible Task objects"""
    for task in tasks:
        if "block" in task:
            handle_tasks(task, role_modules, filepath)
        else:
            handle_task(task, role_modules, filepath)
    
def handle_tasks(item, role_modules, filepath):
    """item has one or more fields which hold a list of Task objects"""
    if "always" in item:
        handle_task_list(item["always"], role_modules, filepath)
    if "block" in item:
        handle_task_list(item["block"], role_modules, filepath)
    if "handlers" in item:
        handle_task_list(item["post_tasks"], role_modules, filepath)
    if "pre_tasks" in item:
        handle_task_list(item["pre_tasks"], role_modules, filepath)
    if "post_tasks" in item:
        handle_task_list(item["post_tasks"], role_modules, filepath)
    if "rescue" in item:
        handle_task_list(item["rescue"], role_modules, filepath)
    if "tasks" in item:
        handle_task_list(item["tasks"], role_modules, filepath)

def parse_role(role_path):
    role_modules = set()
    library_path = Path(os.path.join(role_path, "library"))
    if library_path.is_dir():
        for mod_file in library_path.iterdir():
            if mod_file.is_file() and mod_file.stem != "__init__":
                role_modules.add(mod_file.stem)
    for (dirpath, _, filenames) in os.walk(role_path):
        if not is_role_dir(role_path, dirpath):
            continue
        for filename in filenames:
            if not filename.endswith(".yml"):
                continue
            filepath = os.path.join(dirpath, filename)
            dl = DataLoader()
            ans_data = dl.load_from_file(filepath)
            if ans_data is None:
                print(f"file is empty {filepath}")
                continue
            file_type = get_file_type(ans_data)
            if file_type == "vars":
                handle_vars(item, filepath)
                continue
            if file_type == "meta":
                handle_meta(item, filepath)
                continue
            for item in ans_data:
                ans_type = get_item_type(item)
                handle_vars(item, filepath)
                handle_other(item, filepath)
                if ans_type == "task":
                    handle_task(item, role_modules, filepath)
                handle_tasks(item, role_modules, filepath)

for role_path in sys.argv[1:]:
    parse_role(role_path)
