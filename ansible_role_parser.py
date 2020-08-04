#!/usr/bin/env python

import logging
import os
import re
import sys
from pathlib import Path
from ruamel.yaml import YAML

from ansible.errors import AnsibleParserError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.mod_args import ModuleArgsParser
from ansible.parsing.yaml.objects import AnsibleMapping, AnsibleSequence

if os.environ.get("LSR_DEBUG") == "true":
    logging.getLogger().setLevel(logging.DEBUG)


ROLE_DIRS = [
    "defaults",
    "examples",
    "files",
    "handlers",
    "library",
    "meta",
    "module_utils",
    "tasks",
    "templates",
    "tests",
    "vars",
]

PLAY_KEYS = {
    "gather_facts",
    "handlers",
    "hosts",
    "import_playbook",
    "post_tasks",
    "pre_tasks",
    "roles",
    "tasks",
}

TASK_LIST_KWS = [
    "always",
    "block",
    "handlers",
    "post_tasks",
    "pre_tasks",
    "rescue",
    "tasks",
]


class LSRException(Exception):
    pass


def get_role_dir(role_path, dirpath):
    if role_path == dirpath:
        return None, None
    dir_pth = Path(dirpath)
    relpath = dir_pth.relative_to(role_path)
    base_dir = relpath.parts[0]
    if base_dir in ROLE_DIRS:
        return base_dir, relpath
    return None, None


def get_file_type(item):
    if isinstance(item, AnsibleMapping):
        if "galaxy_info" in item or "dependencies" in item:
            return "meta"
        return "vars"
    elif isinstance(item, AnsibleSequence):
        return "tasks"
    else:
        raise LSRException(f"Error: unknown type of file: {item}")


def get_item_type(item):
    if isinstance(item, AnsibleMapping):
        for key in PLAY_KEYS:
            if key in item:
                return "play"
        if "block" in item:
            return "block"
        return "task"
    else:
        raise LSRException(f"Error: unknown type of item: {item}")


class LSRFileTransformerBase(object):

    # we used to try to not deindent comment lines in the Ansible yaml,
    # but this changed the indentation when comments were used in
    # literal strings, which caused test failures - so for now, we
    # have to live with poorly indented Ansible comments . . .
    # INDENT_RE = re.compile(r'^  (?! *#)', flags=re.MULTILINE)
    INDENT_RE = re.compile(r"^  ", flags=re.MULTILINE)
    HEADER_RE = re.compile(r"^(---\n|.*\n---\n)", flags=re.DOTALL)
    FOOTER_RE = re.compile(r"\n([.][.][.]|[.][.][.]\n.*)$", flags=re.DOTALL)

    def __init__(self, filepath, rolename):
        self.filepath = filepath
        dl = DataLoader()
        self.ans_data = dl.load_from_file(filepath)
        if self.ans_data is None:
            raise LSRException(f"file is empty {filepath}")
        self.file_type = get_file_type(self.ans_data)
        self.rolename = rolename
        buf = open(filepath).read()
        self.ruamel_yaml = YAML(typ="rt")
        match = re.search(LSRFileTransformerBase.HEADER_RE, buf)
        if match:
            self.header = match.group(1)
        else:
            self.header = ""
        match = re.search(LSRFileTransformerBase.FOOTER_RE, buf)
        if match:
            self.footer = match.group(1)
        else:
            self.footer = ""
        self.ruamel_yaml.default_flow_style = False
        self.ruamel_yaml.preserve_quotes = True
        self.ruamel_yaml.width = 1024
        self.ruamel_data = self.ruamel_yaml.load(buf)
        self.ruamel_yaml.indent(mapping=2, sequence=4, offset=2)
        self.outputfile = None
        self.outputstream = sys.stdout

    def run(self):
        if self.file_type == "vars":
            self.handle_vars(self.ans_data, self.ruamel_data)
        elif self.file_type == "meta":
            self.handle_meta(self.ans_data, self.ruamel_data)
        else:
            for a_item, ru_item in zip(self.ans_data, self.ruamel_data):
                self.handle_item(a_item, ru_item)

    def write(self):
        def xform(thing):
            logging.debug(f"xform thing {thing}")
            if self.file_type == "tasks":
                thing = re.sub(LSRFileTransformerBase.INDENT_RE, "", thing)
            thing = self.header + thing
            if not thing.endswith("\n"):
                thing = thing + "\n"
            thing = thing + self.footer
            return thing

        if self.outputfile:
            outstrm = open(self.outputfile, "w")
        else:
            outstrm = self.outputstream
        self.ruamel_yaml.dump(self.ruamel_data, outstrm, transform=xform)

    def task_cb(self, a_task, ru_task, module_name, module_args, delegate_to):
        """subclass will override"""
        pass

    def other_cb(self, a_item, ru_item):
        """subclass will override"""
        pass

    def vars_cb(self, a_item, ru_item):
        """subclass will override"""
        pass

    def meta_cb(self, a_item, ru_item):
        """subclass will override"""
        pass

    def handle_item(self, a_item, ru_item):
        """handle any type of item - call the appropriate handlers"""
        ans_type = get_item_type(a_item)
        self.handle_vars(a_item, ru_item)
        self.handle_other(a_item, ru_item)
        if ans_type == "task":
            self.handle_task(a_item, ru_item)
        self.handle_task_list(a_item, ru_item)

    def handle_other(self, a_item, ru_item):
        """handle properties of Ansible item other than vars and tasks"""
        self.other_cb(a_item, ru_item)

    def handle_vars(self, a_item, ru_item):
        """handle vars of Ansible item"""
        self.vars_cb(a_item, ru_item)

    def handle_meta(self, a_item, ru_item):
        """handle meta/main.yml file"""
        self.meta_cb(a_item, ru_item)

    def handle_task(self, a_task, ru_task):
        """handle a single task"""
        mod_arg_parser = ModuleArgsParser(a_task)
        try:
            action, args, delegate_to = mod_arg_parser.parse(
                skip_action_validation=True
            )
        except AnsibleParserError as e:
            raise LSRException(
                "Couldn't parse task at %s (%s)\n%s"
                % (a_task.ansible_pos, e.message, a_task)
            )
        self.task_cb(a_task, ru_task, action, args, delegate_to)

    def handle_task_list(self, a_item, ru_item):
        """item has one or more fields which hold a list of Task objects"""
        for kw in TASK_LIST_KWS:
            if kw in a_item:
                for a_task, ru_task in zip(a_item[kw], ru_item[kw]):
                    self.handle_item(a_task, ru_task)


def get_role_modules(role_path):
    """get the modules from the role
    returns a set() of module names"""
    role_modules = set()
    library_path = Path(os.path.join(role_path, "library"))
    if library_path.is_dir():
        for mod_file in library_path.iterdir():
            if mod_file.is_file() and mod_file.stem != "__init__":
                role_modules.add(mod_file.stem)
    return role_modules


class LSRTransformer(object):
    """Transform all of the .yml files in a role or role subdir"""

    def __init__(
        self,
        role_path,
        is_role_dir=True,
        role_name=None,
        file_xfrm_cls=LSRFileTransformerBase,
    ):
        """Create a role transformer.  The user can specify the specific class
        to use for transforming each file, and the extra arguments to pass to the
        constructor of that class
        is_role_dir - if True, role_path is the role directory (with all of the usual role subdirs)
                      if False, just operate on the .yml files found in role_path"""
        self.role_name = role_name
        self.role_path = role_path
        self.is_role_dir = is_role_dir
        self.file_xfrm_cls = file_xfrm_cls
        if self.is_role_dir and not self.role_name:
            self.role_name = os.path.basename(self.role_path)

    def run(self):
        for (dirpath, _, filenames) in os.walk(self.role_path):
            if self.is_role_dir:
                role_dir, _ = get_role_dir(self.role_path, dirpath)
                if not role_dir:
                    continue
            for filename in filenames:
                if not filename.endswith(".yml"):
                    continue
                filepath = os.path.join(dirpath, filename)
                logging.debug(f"filepath {filepath}")
                try:
                    lsrft = self.file_xfrm_cls(filepath, self.role_name)
                    lsrft.run()
                    lsrft.write()
                except LSRException as lsrex:
                    logging.debug(f"Could not transform {filepath}: {lsrex}")


if __name__ == "__main__":
    for role_path in sys.argv[1:]:
        lsrxfrm = LSRTransformer(role_path)
        lsrxfrm.run()
