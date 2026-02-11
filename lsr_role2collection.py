#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) 2020 Matt Martz <matt@sivel.net>
# GNU General Public License v3.0+
#     (see https://www.gnu.org/licenses/gpl-3.0.txt)

# Usage:
# lsr-role2collection.py [--namespace COLLECTION_NAMESPACE]
#                        [--collection COLLECTION_NAME]
#                        --src-path COLLECTION_SRC_PATH
#                        --dest-path COLLECTION_DEST_PATH
#                        --role ROLE_NAME
#                        [--subrole-prefix STR]
#                        [--replace-dot STR]
#                        [-h]
# Or
#
# COLLECTION_SRC_PATH=/path/to/{src_owner} \
# COLLECTION_DEST_PATH=/path/to/collections \
# COLLECTION_NAMESPACE=mynamespace \
# COLLECTION_NAME=myname \
# lsr-role2collection.py --role ROLE_NAME
#   ROLE_NAME role must exist in COLLECTION_SRC_PATH
#   Converted collections are placed in COLLECTION_DEST_PATH/ansible_collections/COLLECTION_NAMESPACE/COLLECTION_NAME

import argparse
import errno
import fnmatch
import logging
import os
import re
import subprocess
import sys
import textwrap

from pathlib import Path
from ruamel.yaml import YAML
from shutil import copytree, copy2, copyfile, ignore_patterns, rmtree, which
from operator import itemgetter

ALL_ROLE_DIRS = [
    "action_plugins",
    "defaults",
    "examples",
    "files",
    "filter_plugins",
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

EXTRA_SCRIPT = "lsr_role2coll_extra_script"


class LSRException(Exception):
    pass


def get_role_dir(role_path, dirpath):
    dir_pth = Path(dirpath)
    if role_path == dir_pth:
        return None, None
    relpath = dir_pth.relative_to(role_path)
    base_dir = relpath.parts[0]
    if base_dir in ALL_ROLE_DIRS:
        return base_dir, relpath
    return None, None


def get_file_type(item):
    if isinstance(item, dict):
        if "galaxy_info" in item or "dependencies" in item:
            return "meta"
        return "vars"
    elif isinstance(item, list):
        return "tasks"
    else:
        raise LSRException(f"Error: unknown type of file: {item}")


def get_item_type(item):
    if isinstance(item, dict):
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

    def __init__(self, filepath, rolename, newrolename, args):
        self.filepath = filepath
        self.namespace = args["namespace"]
        self.collection = args["collection"]
        self.prefix = args["prefix"]
        self.subrole_prefix = args["subrole_prefix"]
        self.replace_dot = args["replace_dot"]
        self.rolename_regex = "[{0}.]".format(self.replace_dot)
        self.role_modules = args["role_modules"]
        self.src_owner = args["src_owner"]
        self.top_dir = args["top_dir"]
        self.rolename = rolename
        self.newrolename = newrolename
        self.extra_mapping_src_owner = args["extra_mapping_src_owner"]
        self.extra_mapping_src_role = args["extra_mapping_src_role"]
        self.extra_mapping_dest_prefix = args["extra_mapping_dest_prefix"]
        self.extra_mapping_dest_role = args["extra_mapping_dest_role"]
        buf = open(filepath, encoding="utf-8").read()
        self.ruamel_yaml = YAML(typ="rt")
        match = re.search(LSRFileTransformerBase.HEADER_RE, buf)
        if match:
            self.header = match.group(1)
        else:
            self.header = ""
        match = re.search(LSRFileTransformerBase.FOOTER_RE, buf)
        if match:
            self.footer = match.group(1) + "\n"
        else:
            self.footer = ""
        self.ruamel_yaml.default_flow_style = False
        self.ruamel_yaml.preserve_quotes = True
        self.ruamel_yaml.width = 1024
        self.ruamel_data = self.ruamel_yaml.load(buf)
        self.ruamel_yaml.indent(mapping=2, sequence=4, offset=2)
        self.file_type = get_file_type(self.ruamel_data)
        self.outputfile = None
        self.outputstream = sys.stdout

    def run(self):
        if self.file_type == "vars":
            self.handle_vars(self.ruamel_data)
        elif self.file_type == "meta":
            self.handle_meta(self.ruamel_data)
        else:
            for item in self.ruamel_data:
                self.handle_item(item)

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
            outstrm = open(self.outputfile, "w", encoding="utf-8")
        else:
            outstrm = self.outputstream
        self.ruamel_yaml.dump(self.ruamel_data, outstrm, transform=xform)

    def task_cb(self, task):
        """subclass will override"""
        pass

    def other_cb(self, item):
        """subclass will override"""
        pass

    def vars_cb(self, item):
        """subclass will override"""
        pass

    def meta_cb(self, item):
        """subclass will override"""
        pass

    def handle_item(self, item):
        """handle any type of item - call the appropriate handlers"""
        ans_type = get_item_type(item)
        self.handle_vars(item)
        self.handle_other(item)
        if ans_type == "task":
            self.handle_task(item)
        self.handle_task_list(item)

    def handle_other(self, item):
        """handle properties of Ansible item other than vars and tasks"""
        self.other_cb(item)

    def handle_vars(self, item):
        """handle vars of Ansible item"""
        self.vars_cb(item)

    def handle_meta(self, item):
        """handle meta/main.yml file"""
        self.meta_cb(item)

    def handle_task(self, task):
        """handle a single task"""
        self.task_cb(task)

    def handle_task_list(self, item):
        """item has one or more fields which hold a list of Task objects"""
        for kw in TASK_LIST_KWS:
            if kw in item:
                for task in item[kw]:
                    self.handle_item(task)


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
        transformer_args,
        is_role_dir=True,
        role_name=None,
        new_role_name=None,
        file_xfrm_cls=LSRFileTransformerBase,
    ):
        """Create a role transformer.  The user can specify the specific class
        to use for transforming each file, and the extra arguments to pass to the
        constructor of that class
        is_role_dir - if True, role_path is the role directory (with all of the usual role subdirs)
                      if False, just operate on the .yml files found in role_path"""
        self.role_name = role_name
        self.new_role_name = new_role_name
        self.role_path = role_path
        self.is_role_dir = is_role_dir
        self.transformer_args = transformer_args
        self.file_xfrm_cls = file_xfrm_cls
        if self.is_role_dir and not self.role_name:
            self.role_name = os.path.basename(self.role_path)

    def run(self):
        for dirpath, _, filenames in os.walk(self.role_path):
            if dirpath.endswith("/files") or dirpath.endswith("/templates"):
                continue
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
                    lsrft = self.file_xfrm_cls(
                        filepath,
                        self.role_name,
                        self.new_role_name,
                        self.transformer_args,
                    )
                    lsrft.run()
                    lsrft.write()
                except LSRException as lsrex:
                    logging.debug(f"Could not transform {filepath}: {lsrex}")


# ==============================================================================

ROLE_DIRS = (
    "defaults",
    "files",
    "handlers",
    "meta",
    "tasks",
    "templates",
    "vars",
)

PLUGINS = (
    "action_plugins",
    "become_plugins",
    "cache_plugins",
    "callback_plugins",
    "cliconf_plugins",
    "connection_plugins",
    "doc_fragments",
    "filter_plugins",
    "httpapi_plugins",
    "inventory_plugins",
    "library",
    "lookup_plugins",
    "module_utils",
    "netconf_plugins",
    "shell_plugins",
    "strategy_plugins",
    "terminal_plugins",
    "test_plugins",
    "vars_plugins",
)

TESTS = ("tests",)

DOCS = (
    "docs",
    "design_docs",
    "examples",
    "README.md",
    "README.html",
    "DCO",
)

TOX = (
    ".flake8",
    ".pre-commit-config.yaml",
    ".pydocstyle",
    ".travis",
    ".travis.yml",
    ".yamllint_defaults.yml",
    ".yamllint.yml",
    ".yamllint.yaml",
    "ansible_pytest_extra_requirements.txt",
    "custom_requirements.txt",
    "molecule",
    "molecule_extra_requirements.txt",
    "pylintrc",
    "pylint_extra_requirements.txt",
    "pytest_extra_requirements.txt",
    "tox.ini",
    "tuned_requirements.txt",
    ".pandoc_template.html5",  # contains smart quotes - ansible-test does not like
)

DO_NOT_COPY = (
    ".github",
    ".gitignore",
    ".lgtm.yml",
    ".tox",
    ".venv",
    "artifacts",
    "run_pylint.py",
    "scripts",
    "semaphore",
    "standard-inventory-qcow2",
    "Vagrantfile",
    "CHANGELOG",
)

ALL_DIRS = ROLE_DIRS + PLUGINS + TESTS + DOCS + DO_NOT_COPY

IMPORT_RE = re.compile(
    rb"(\bimport) (ansible\.module_utils\.)(\S+)(.*)(\s+#.+|.*)$", flags=re.M
)
FROM_RE = re.compile(
    rb"(\bfrom) (ansible\.module_utils\.?)(\S+)? import (\(*(?:\n|\r\n)?)(\S+)(\s+#.+|.*)$",
    flags=re.M,
)

if os.environ.get("LSR_DEBUG") == "true":
    logging.getLogger().setLevel(logging.DEBUG)
elif os.environ.get("LSR_INFO") == "true":
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.getLogger().setLevel(logging.ERROR)


class LSRFileTransformer(LSRFileTransformerBase):
    """Do the role file transforms - fix role names, add FQCN
    to module names, etc."""

    def convert_rolename(self, rolename, lsr_rolename=None):
        """convert the given rolename to the new name"""
        if rolename.count(".") == 1:
            _src_owner, _rolename_base = rolename.split(".")
        else:
            _src_owner = None
            _rolename_base = rolename
        if not lsr_rolename:
            lsr_rolename = self.src_owner + "." + self.rolename
        logging.debug(f"\ttask role {rolename}")
        new_name = None
        if rolename == lsr_rolename or self.comp_rolenames(rolename, self.rolename):
            new_name = self.prefix + self.newrolename
        elif _rolename_base and _rolename_base in self.extra_mapping_src_role:
            _src_role_index = self.extra_mapping_src_role.index(_rolename_base)
            # --extra-mapping "SRC_OWNER0.SRC_ROLE0:DEST_PREFIX[.]DEST_ROLE1,
            #                  SRC_ROLE1:DEST_PREFIX[.]DEST_ROLE1"
            # current _rolename_base is SRC_ROLE0 and
            #   _src_owner is None or _src_owner is SRC_OWNER0
            # or current _rolename_base is SRC_ROLE1
            if (
                not _src_owner
                or (_src_owner == self.extra_mapping_src_owner[_src_role_index])
                or (
                    not self.extra_mapping_src_owner[_src_role_index]
                    and _src_owner == self.src_owner
                )
            ):
                new_name = "{0}{1}".format(
                    (
                        self.extra_mapping_dest_prefix[_src_role_index]
                        if self.extra_mapping_dest_prefix[_src_role_index]
                        else self.prefix
                    ),
                    self.extra_mapping_dest_role[_src_role_index],
                )
        elif rolename.startswith("{{ role_path }}"):
            match = re.match(r"{{ role_path }}/roles/([\w\d.]+)", rolename)
            if match.group(1).startswith(self.subrole_prefix):
                new_name = self.prefix + match.group(1).replace(".", self.replace_dot)
            else:
                new_name = (
                    self.prefix
                    + self.subrole_prefix
                    + match.group(1).replace(".", self.replace_dot)
                )
        return new_name

    def task_cb(self, task):
        """do something with a task item"""
        module_name = None
        role_module_name = None
        is_include_or_import = False
        is_include_vars = False
        mods = ["include_role", "import_role", "include_vars"]
        # add fqcn versions
        mods = mods + ["ansible.builtin." + xx for xx in mods]
        for mod in mods:
            if mod in task:
                module_name = mod
                is_include_or_import = mod.endswith("include_role") or mod.endswith(
                    "import_role"
                )
                is_include_vars = mod.endswith("include_vars")
                break
        if module_name is None:
            for rm in self.role_modules:
                if rm in task:
                    module_name = rm
                    role_module_name = rm
                    break
        if is_include_or_import:
            new_rolename = self.convert_rolename(task[module_name]["name"])
            if new_rolename:
                task[module_name]["name"] = new_rolename
        elif is_include_vars:
            """
            Convert include_vars in the test playbook.
            include_vars: path/to/{src_owner}.ROLENAME/file_or_dir
            or
            include_vars:
              file|dir: path/to/{src_owner}.ROLENAME/file_or_dir
            Note: If the path is relative and not inside a role,
            it will be parsed relative to the playbook.
            To solve it, the relative path is converted to the absolute path.
            """
            _src_owner_match = "/" + self.src_owner + "."
            _src_owner_pattern = r".*/{0}[.](\w+)/([\w\d./]+)".format(self.src_owner)
            if isinstance(task[module_name], dict):
                _key = None
                if (
                    "file" in task[module_name].keys()
                    and _src_owner_match in task[module_name]["file"]
                ):
                    _key = "file"
                elif (
                    "dir" in task[module_name].keys()
                    and _src_owner_match in task[module_name]["dir"]
                ):
                    _key = "dir"
                if _key:
                    _path = task[module_name][_key]
                    _match = re.match(_src_owner_pattern, _path)
                    task[module_name][_key] = (
                        "{0}/ansible_collections/{1}/{2}/roles/{3}/{4}".format(
                            self.top_dir,
                            self.namespace,
                            self.collection,
                            _match.group(1),
                            _match.group(2),
                        )
                    )
            elif (
                isinstance(task[module_name], str)
                and _src_owner_match in task[module_name]
            ):
                _path = task[module_name]
                _match = re.match(_src_owner_pattern, _path)
                task[module_name] = (
                    "{0}/ansible_collections/{1}/{2}/roles/{3}/{4}".format(
                        self.top_dir,
                        self.namespace,
                        self.collection,
                        _match.group(1),
                        _match.group(2),
                    )
                )
        elif role_module_name:
            logging.debug(f"\ttask role module {role_module_name}")
            # assumes task is an orderreddict
            idx = tuple(task).index(role_module_name)
            val = task[role_module_name]
            task.insert(idx, self.prefix + role_module_name, val)
            del task[role_module_name]

    def other_cb(self, item):
        """do something with the other non-task information in an item
        this is where you will get e.g. the `roles` keyword from a play"""
        self.change_roles(item, "roles")

    def vars_cb(self, item):
        """handle vars of Ansible item, or vars from a vars file"""
        for var in item.get("vars", []):
            logging.debug(f"\tvar = {var}")
            if var == "roletoinclude":
                lsr_rolename = self.src_owner + "." + self.rolename
                if item["vars"][var] == lsr_rolename:
                    item["vars"][var] = self.prefix + self.newrolename
        return

    def meta_cb(self, item):
        """hand a meta/main.yml style file"""
        self.change_roles(item, "dependencies")

    def comp_rolenames(self, name0, name1):
        if name0 == name1:
            return True
        else:
            # self.rolename_regex is default to "[_.]".
            core0 = re.sub(self.rolename_regex, "", name0)
            core1 = re.sub(self.rolename_regex, "", name1)
            return core0 == core1

    def change_roles(self, item, roles_kw):
        """ru_item is an item which may contain a roles or dependencies
        specifier - the roles_kw is either "roles" or "dependencies"
        """
        lsr_rolename = self.src_owner + "." + self.rolename
        for idx, role in enumerate(item.get(roles_kw, [])):
            changed = False
            # role could be
            #   ordereddict([('name', 'linux-system-roles.ROLENAME')])
            # or
            #   'linux-system-roles.ROLENAME'
            if isinstance(role, dict):
                if "name" in role:
                    key = "name"
                else:
                    key = "role"
                new_rolename = self.convert_rolename(role[key], lsr_rolename)
                if new_rolename:
                    role[key] = new_rolename
                    changed = True
            else:
                new_rolename = self.convert_rolename(role, lsr_rolename)
                if new_rolename:
                    role = new_rolename
                    changed = True
            if changed:
                item[roles_kw][idx] = role

    def write(self):
        """assume we are operating on files already copied to the dest dir,
        so write file in-place"""
        self.outputfile = self.filepath
        super().write()


def lsr_copyleaf(src, dest, symlinks=True, ignore=None):
    if src.is_symlink() and symlinks:
        # symlinks=True --> symlink in dest
        copyfile(src, dest, follow_symlinks=(not symlinks))
    elif src.is_dir():
        # symlinks=True --> symlink in dest
        # symlinks=False --> copy in dest
        copytree(src, dest, symlinks=symlinks, ignore=ignore)
    else:
        copyfile(src, dest)


# Once python 3.8 is available in Travis CI,
# replace lsr_copytree with shutil.copytree with dirs_exist_ok=True.
def lsr_copytree(src, dest, symlinks=True, dirs_exist_ok=False, ignore=None):
    if dest.exists():
        if dest.is_dir():
            for sr in src.iterdir():
                subsrc = src / sr.name
                subdest = dest / sr.name
                if ignore:
                    if sr.name != ignore:
                        if subsrc.is_dir():
                            if subdest.exists() and dirs_exist_ok:
                                rmtree(subdest)
                            lsr_copytree(
                                subsrc,
                                subdest,
                                symlinks=symlinks,
                                ignore=ignore,
                                dirs_exist_ok=True,
                            )
                        else:
                            if subdest.exists() and dirs_exist_ok:
                                subdest.unlink()
                            lsr_copyleaf(
                                subsrc, subdest, symlinks=symlinks, ignore=ignore
                            )
                else:
                    if subsrc.is_dir():
                        if subdest.exists() and dirs_exist_ok:
                            rmtree(subdest)
                        lsr_copytree(
                            subsrc,
                            subdest,
                            symlinks=symlinks,
                            dirs_exist_ok=dirs_exist_ok,
                        )
                    else:
                        if (subdest.exists() or subdest.is_symlink()) and dirs_exist_ok:
                            subdest.unlink()
                        # symlinks=False --> copy in dest
                        copy2(subsrc, subdest, follow_symlinks=(not symlinks))
        else:
            if dest.exists() and dirs_exist_ok:
                dest.unlink()
            lsr_copyleaf(src, dest, symlinks=symlinks, ignore=ignore)
    else:
        lsr_copyleaf(src, dest, symlinks=symlinks, ignore=ignore)


def dir_to_plugin(v):
    if v[-8:] == "_plugins":
        return v[:-8]
    elif v == "library":
        return "modules"
    return v


def file_replace(path, find, replace, file_patterns):
    """
    Replace a pattern `find` with `replace` in the files that match
    `file_patterns` under `path`.
    """
    for root, dirs, files in os.walk(os.path.abspath(path)):
        for file_pattern in file_patterns:
            for filename in fnmatch.filter(files, file_pattern):
                filepath = os.path.join(root, filename)
                with open(filepath, encoding="utf-8") as f:
                    s = f.read()
                s = re.sub(find, replace, s)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(s)


def copy_tree_with_replace(
    src_path,
    dest_path,
    role,
    new_role,
    TUPLE,
    transformer_args,
    isrole=True,
    ignoreme=None,
    symlinks=True,
):
    """
    1. Copy files and dirs in the dir to
       DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE/dir
       or
       DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/dir/ROLE.
    2. Parse the source tree to look for task_roles
    3. Replace the task_roles with FQCN
    """
    for dirname in TUPLE:
        src = src_path / dirname
        if src.is_dir():
            if isrole:
                dest = dest_path / "roles" / new_role / dirname
            else:
                dest = dest_path / dirname / new_role
            logging.info(f"Copying role {src} to {dest}")
            if ignoreme:
                lsr_copytree(
                    src,
                    dest,
                    ignore=ignore_patterns(*ignoreme),
                    symlinks=symlinks,
                    dirs_exist_ok=True,
                )
            else:
                lsr_copytree(src, dest, symlinks=symlinks, dirs_exist_ok=True)
            lsrxfrm = LSRTransformer(
                dest, transformer_args, False, role, new_role, LSRFileTransformer
            )
            lsrxfrm.run()


def cleanup_symlinks(path, role, rmlist):
    """
    Clean up symlinks in tests/roles
    """
    if path.exists():
        nodes = sorted(list(path.rglob("*")), reverse=True)
        for node in nodes:
            for item in rmlist:
                if item == node.name:
                    if node.is_symlink():
                        node.unlink()
            if (
                node.is_dir()
                and (
                    r"linux-system-roles." + role == node.name
                    or (role == "sshd" and node.name == "ansible-sshd")
                )
                and not any(node.iterdir())
            ):
                node.rmdir()
        roles_dir = path / "roles"
        if roles_dir.exists():
            for sr in roles_dir.iterdir():
                if sr.is_symlink():
                    sr.unlink()
            if not any(roles_dir.iterdir()):
                roles_dir.rmdir()


def gather_module_utils_parts(module_utils_dir):
    module_utils = []
    if module_utils_dir.is_dir():
        for root, dirs, files in os.walk(module_utils_dir):
            for filename in files:
                if os.path.splitext(filename)[1] != ".py":
                    continue
                full_path = (Path(root) / filename).relative_to(module_utils_dir)
                parts = bytes(full_path)[:-3].split(b"/")
                if parts[-1] == b"__init__":
                    del parts[-1]
                module_utils.append(parts)
    return module_utils


def import_replace(match):
    """
    If 'import ansible.module_utils.something ...' matches,
    'import ansible_collections.NAMESPACE.COLLECTION.plugins.module_utils.something ...'
    is returned to replace.
    """
    _src_path = config["src_path"]
    _namespace = config["namespace"]
    _collection = config["collection"]
    _role = config["role"]
    _module_utils = config["module_utils"]
    _additional_rewrites = config["additional_rewrites"]
    _module_utils_dir = config["module_utils_dir"]
    parts = match.group(3).split(b".")
    match_group3 = match.group(3)
    src_module_path = _src_path / "module_utils" / match.group(3).decode("utf-8")
    dest_module_path0 = _module_utils_dir / match.group(3).decode("utf-8")
    dest_module_path1 = _module_utils_dir / _role
    if len(parts) == 1:
        if not src_module_path.is_dir() and (
            dest_module_path0.is_dir() or dest_module_path1.is_dir()
        ):
            match_group3 = (_role + "." + match.group(3).decode("utf-8")).encode()
            parts = match_group3.split(b".")
    if parts in _module_utils:
        if match.group(1) == b"import" and match.group(4) == b"":
            _additional_rewrites.append(parts)
            if src_module_path.exists() or Path(str(src_module_path) + ".py").exists():
                return b"import ansible_collections.%s.%s.plugins.module_utils.%s%s" % (
                    bytes(_namespace, "utf-8"),
                    bytes(_collection, "utf-8"),
                    match_group3,
                    match.group(5),
                )
            else:
                return (
                    b"import ansible_collections.%s.%s.plugins.module_utils.%s as %s%s"
                    % (
                        bytes(_namespace, "utf-8"),
                        bytes(_collection, "utf-8"),
                        match_group3,
                        parts[-1],
                        match.group(5),
                    )
                )
        return b"%s ansible_collections.%s.%s.plugins.module_utils.%s%s%s" % (
            match.group(1),
            bytes(_namespace, "utf-8"),
            bytes(_collection, "utf-8"),
            match_group3,
            match.group(4),
            match.group(5),
        )
    return match.group(0)


def get_candidates(parts3, parts5):
    from_file0 = config["dest_path"] / "plugins" / "module_utils"
    for p3 in parts3:
        from_file0 = from_file0 / p3.decode("utf-8")
    from_file1 = from_file0
    for p5 in parts5:
        from_file1 = from_file1 / p5.decode("utf-8").strip(", ")
    from_file0 = Path(str(from_file0) + ".py")
    lfrom_file0 = Path(str(from_file0).lower())
    from_file1 = Path(str(from_file1) + ".py")
    lfrom_file1 = Path(str(from_file1).lower())
    return from_file0, lfrom_file0, from_file1, lfrom_file1


def from_replace(match):
    """
    case 1:
    If it matches:
      from ansible.module_utils.ROLE.somedir import module
    and if plugins/module_utils/ROLE/somedir/module.py does not exist
    in the converted tree,
    'from ansible_collections.NAMESPACE.COLLECTION.plugins.module_utils.ROLE.somedir.__init__ import module'
    is returned to replace.

    case 2:
    If it matches:
      from ansible.module_utils.ROLE.subdir.something import (\n
    and if plugins/module_utils/ROLE/subdir/something.py exists in the
    converted tree,
    'from ansible_collections.NAMESPACE.COLLECTION.plugins.module_utils.ROLE.subdir.something import (\n'
    is returned to replace.

    Legend:
    - group1 - from
    - group2 - ansible.module_utils
    - group3 - name if any
    - group4 - ( if any
    - group5 - identifier
    """
    _src_path = config["src_path"]
    _namespace = config["namespace"]
    _collection = config["collection"]
    _role = config["role"]
    _module_utils = config["module_utils"]
    _module_utils_dir = config["module_utils_dir"]
    try:
        parts3 = match.group(3).split(b".")
    except AttributeError:
        parts3 = []
    try:
        parts5 = match.group(5).split(b".")
    except AttributeError:
        parts5 = []
    # parts3 (e.g., [b'ROLE', b'subdir', b'module']) matches one module_utils or
    # size of parts3 is 1 (e.g., [b'module']), in this case, module.py was moved
    # to ROLE/module.py or module is a dir.
    # If latter, match.group(3) has to be converted to b'ROLE.module'.
    match_group3 = match.group(3)
    if len(parts3) == 1:
        src_module_path = _src_path / "module_utils" / match.group(3).decode("utf-8")
        dest_module_path0 = _module_utils_dir / match.group(3).decode("utf-8")
        dest_module_path1 = _module_utils_dir / _role
        if not src_module_path.is_dir() and (
            dest_module_path0.is_dir() or dest_module_path1.is_dir()
        ):
            match_group3 = (_role + "." + match.group(3).decode("utf-8")).encode()
            parts3 = match_group3.split(b".")
    if parts3 in _module_utils:
        from_file0, lfrom_file0, from_file1, lfrom_file1 = get_candidates(
            parts3, parts5
        )
        if (
            from_file0.is_file()
            or from_file1.is_file()
            or lfrom_file0.is_file()
            or lfrom_file1.is_file()
        ):
            return (
                b"%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s%s"
                % (
                    match.group(1),
                    bytes(_namespace, "utf-8"),
                    bytes(_collection, "utf-8"),
                    match_group3,
                    match.group(4),
                    match.group(5),
                    match.group(6),
                )
            )
        else:
            return (
                b"%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s%s"
                % (
                    match.group(1),
                    bytes(_namespace, "utf-8"),
                    bytes(_collection, "utf-8"),
                    match_group3,
                    match.group(4),
                    match.group(5),
                    match.group(6),
                )
            )
    if parts5 in _module_utils:
        from_file0, lfrom_file0, from_file1, lfrom_file1 = get_candidates(
            parts3, parts5
        )
        if parts3:
            if (
                from_file0.is_file()
                or from_file1.is_file()
                or lfrom_file0.is_file()
                or lfrom_file1.is_file()
            ):
                return (
                    b"%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s%s"
                    % (
                        match.group(1),
                        bytes(_namespace, "utf-8"),
                        bytes(_collection, "utf-8"),
                        match.group(3),
                        match.group(4),
                        match.group(5),
                        match.group(6),
                    )
                )
            else:
                return (
                    b"%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s%s"
                    % (
                        match.group(1),
                        bytes(_namespace, "utf-8"),
                        bytes(_collection, "utf-8"),
                        match.group(3),
                        match.group(4),
                        match.group(5),
                        match.group(6),
                    )
                )
        if (
            from_file0.is_file()
            or from_file1.is_file()
            or lfrom_file0.is_file()
            or lfrom_file1.is_file()
        ):
            return (
                b"%s ansible_collections.%s.%s.plugins.module_utils import %s%s%s"
                % (
                    match.group(1),
                    bytes(_namespace, "utf-8"),
                    bytes(_collection, "utf-8"),
                    match.group(4),
                    match.group(5),
                    match.group(6),
                )
            )
        else:
            return (
                b"%s ansible_collections.%s.%s.plugins.module_utils.__init__ import %s%s%s"
                % (
                    match.group(1),
                    bytes(_namespace, "utf-8"),
                    bytes(_collection, "utf-8"),
                    match.group(4),
                    match.group(5),
                    match.group(6),
                )
            )
    return match.group(0)


def add_rolename(filename, rolename):
    """
    A file with an extension, e.g., README.md is converted to README-rolename.md
    A file with no extension, e.g., LICENSE is to LICENSE-rolename
    """
    if filename.find(".", 1) > 0:
        with_rolename = re.sub(
            r"([\w\d_\.]+)(\.)([\w\d]*)",
            r"\1" + "-" + rolename + r"\2" + r"\3",
            filename,
        )
    else:
        with_rolename = filename + "-" + rolename
    return with_rolename


def process_ansible_lint(extra, dest, new_role):
    """Fixup paths to refer to collection."""
    yml = YAML(typ="rt")
    yml.default_flow_style = False
    yml.preserve_quotes = True
    yml.width = 1024
    yml.explicit_start = True

    with open(extra) as af_src:
        ansible_lint = yml.load(af_src)
        yml.indent(mapping=2, sequence=4, offset=2)
        with open(dest, "w") as af_dest:
            for key, items in list(ansible_lint.items()):
                if key == "exclude_paths":
                    for idx, item in list(enumerate(items)):
                        if item.startswith("tests/"):
                            new_item = item.replace("tests/", "tests/" + new_role + "/")
                        else:
                            # make relative to collection role
                            new_item = "roles/" + new_role + "/" + item
                        ansible_lint["exclude_paths"][idx] = new_item
            yml.dump(ansible_lint, af_dest)


config = {}


def role2collection():
    HOME = os.environ.get("HOME")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--namespace",
        type=str,
        default=os.environ.get("COLLECTION_NAMESPACE", "fedora"),
        help="Collection namespace; default to fedora",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=os.environ.get("COLLECTION_NAME", "linux_system_roles"),
        help="Collection name; default to linux_system_roles",
    )
    parser.add_argument(
        "--dest-path",
        type=Path,
        default=os.environ.get("COLLECTION_DEST_PATH", HOME + "/.ansible/collections"),
        help="Path to parent of collection where role should be migrated; default to ${HOME}/.ansible/collections",
    )
    parser.add_argument(
        "--tests-dest-path",
        type=Path,
        default=os.environ.get("COLLECTION_TESTS_DEST_PATH", None),
        help="Path to parent of tests directory in which rolename directory is created and test scripts are copied to the directory; default to DEST_PATH/NAMESPACE/COLLECTION",  # noqa:E501
    )
    parser.add_argument(
        "--src-path",
        type=Path,
        default=os.environ.get("COLLECTION_SRC_PATH", HOME + "/linux-system-roles"),
        help="Path to the parent directory of the source role; default to ${HOME}/linux-system-roles",
    )
    parser.add_argument(
        "--src-owner",
        type=str,
        default=os.environ.get("COLLECTION_SRC_OWNER", ""),
        help='Owner of the role in github. If the parent directory name in SRC_PATH is not the github owner, may need to set to it, e.g., "linux-system-roles"; default to the parent directory of SRC_PATH',  # noqa:E501
    )
    parser.add_argument(
        "--role",
        type=str,
        default=os.environ.get("COLLECTION_ROLE"),
        help="Role to convert to collection",
    )
    parser.add_argument(
        "--new-role",
        type=str,
        default=os.environ.get("COLLECTION_NEW_ROLE"),
        help="Role to convert to collection; specify if different from the original role; default to the value of '--role'.",  # noqa:E501
    )
    parser.add_argument(
        "--replace-dot",
        type=str,
        default=os.environ.get("COLLECTION_REPLACE_DOT", "_"),
        help=(
            "If sub-role name contains dots, replace them with the specified value; "
            "default to '_'"
        ),
    )
    parser.add_argument(
        "--subrole-prefix",
        type=str,
        default=os.environ.get("COLLECTION_SUBROLE_PREFIX", ""),
        help=(
            "If sub-role name does not start with the specified value, "
            "change the name to start with the value; default to an empty string"
        ),
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=os.environ.get("COLLECTION_README", None),
        help="Path to the readme file used in top README.md",
    )
    parser.add_argument(
        "--extra-mapping",
        type=str,
        default=os.environ.get("COLLECTION_EXTRA_MAPPING", ""),
        help=(
            "This is a comma delimited list of extra mappings to apply when "
            "converting the files - this replaces the given role name with "
            "collection format with the optional given namespace and collection "
            "as well as the given FQCN with other FQCN. In addition, if 'fedora."
            "linux_system_roles:NAMESPACE.COLLECTION' is in the mapping, "
            "'fedora.linux_system_roles' is converted to 'NAMESPACE.COLLECTION'."
        ),
    )
    default_meta_runtime = Path(__file__).parent / "lsr_role2collection" / "runtime.yml"
    parser.add_argument(
        "--meta-runtime",
        type=str,
        default=os.environ.get("COLLECTION_META_RUNTIME", default_meta_runtime),
        help=(
            "This is the path to the collection meta/runtime.yml - the default "
            f"is {default_meta_runtime}."
        ),
    )
    parser.add_argument(
        "--extra-script",
        type=Path,
        default=os.environ.get("COLLECTION_EXTRA_SCRIPT"),
        help=(
            "Executable script to run to do any extra conversions - the default "
            f"is {EXTRA_SCRIPT} in the role root directory."
        ),
    )
    args, unknown = parser.parse_known_args()

    role = args.role
    if not role:
        parser.print_help()
        logging.error("Message: role is not specified.")
        os._exit(errno.EINVAL)

    src_meta_runtime = Path(args.meta_runtime)
    if not src_meta_runtime.exists():
        parser.print_help()
        logging.error("There is no source file specified for the meta/runtime.yml")
        os._exit(errno.EINVAL)

    new_role = args.new_role
    if not new_role:
        new_role = role

    namespace = args.namespace
    collection = args.collection
    prefix = namespace + "." + collection + "."
    top_dest_path = args.dest_path.resolve()
    current_dest = os.path.expanduser(str(top_dest_path))
    replace_dot = args.replace_dot
    subrole_prefix = args.subrole_prefix
    readme_path = args.readme

    # Assume fedora is the default namespace and linux_system_roles is
    # the default collection.
    #
    # Input: "a-owner.role0:newrole0,\
    #         a-owner.role1:linux_system_roles.role1,\
    #         a-owner.role2:fedora.linux_system_roles.role2,\
    #         my_namespace.my_collection.role3:redhat.rhel_system_roles.role3,\
    #         my_namespace.my_collection.role4:linux_system_roles.role4,\
    #         my_namespace.my_collection.role5:role5,\
    #         my_namespace0.my_collection0:my_namespace1.my_collection1"
    # Output:
    # [
    #   {'src_name': {'src_owner': 'linux-system-roles', 'role': 'role0'},
    #    'dest_name': {'dest_prefix': None, 'role': 'newrole0'}},
    #   {'src_name': {'src_owner': 'a-owner', 'role': 'role1'},
    #    'dest_name': {'dest_prefix': 'fedora.linux_system_roles', 'role': 'role1'},
    #   {'src_name': {'src_owner': 'a-owner', 'role': 'role2'},
    #    'dest_name': {'dest_prefix': 'fedora.linux_system_roles', 'role': 'role2'}}
    # ],
    # [
    #   {'src_name': {'src_coll': 'my_namespace.my_collection.role3'},
    #    'dest_name': {'dest_coll': 'redhat.rhel_system_roles.role3}},
    #   {'src_name': {'src_coll': 'my_namespace.my_collection.role4'},
    #    'dest_name': {'dest_coll': 'fedora.linux_system_roles.role4}},
    #   {'src_name': {'src_coll': 'my_namespace.my_collection.role3'},
    #    'dest_name': {'dest_coll': 'fedora.linux_system_roles.role3'}},
    #   {'src_name': {'src_coll': 'my_namespace0.my_collection0'},
    #    'dest_name': {'dest_coll': 'my_namespace1.my_collection1'}},
    # ]
    # Note: Skip if the role in the given src_name is the role to be converted.
    def parse_extra_mapping(mapping_str, namespace, collection, role):
        _mapping_list = mapping_str.split(",")
        _mapping_role_list = []
        _mapping_coll_list = []
        for _map in _mapping_list:
            _item = _map.split(":")
            if len(_item) == 2:
                # src and dest are identical
                if _item[0] == _item[1]:
                    continue
                _mapping_dict = {}
                _src = _item[0].split(".")
                _src_name = {}
                if len(_src) == 1:
                    # "rolename"
                    if _src[0] == role:
                        continue
                    _src_name["src_owner"] = None
                    _src_name["role"] = _src[0]
                    _mapping_dict["src_name"] = _src_name
                elif len(_src) == 2:
                    # "linux-system-roles.rolename" or "fedora.linux_system_roles"
                    if _src[1] == role:
                        continue
                    elif _src[0] == "fedora" and _src[1] == "linux_system_roles":
                        _src_name["src_coll"] = _item[0]
                    else:
                        _src_name["src_owner"] = _src[0]
                        _src_name["role"] = _src[1]
                    _mapping_dict["src_name"] = _src_name
                elif len(_src) == 3:
                    # FQCN
                    _src_name["src_coll"] = _item[0]
                    _mapping_dict["src_name"] = _src_name

                _dest = _item[1].split(".")
                _dest_name = {}
                if len(_src) == 1 or len(_src) == 2:
                    if len(_dest) == 1:
                        # "rolename"
                        _dest_name["dest_prefix"] = None
                        _dest_name["role"] = _dest[0]
                    elif len(_dest) == 2:
                        # "collection.rolename" or "namespace.collection"
                        if (
                            _src[0] == "fedora" and _src[1] == "linux_system_roles"
                        ) or (_dest[0] == namespace and _dest[1] == collection):
                            _dest_name["dest_coll"] = _item[1]
                        else:
                            _dest_name["dest_prefix"] = "{0}.{1}.".format(
                                namespace, _dest[0]
                            )
                            _dest_name["role"] = _dest[1]
                    elif len(_dest) == 3:
                        # "namespace.collection.rolename"
                        _dest_name["dest_prefix"] = "{0}.{1}.".format(
                            _dest[0], _dest[1]
                        )
                        _dest_name["role"] = _dest[2]
                    _mapping_dict["dest_name"] = _dest_name
                    if (
                        "dest_coll" in _dest_name.keys()
                        and _dest_name["dest_coll"] == _item[1]
                    ):
                        _mapping_coll_list.append(_mapping_dict)
                    else:
                        _mapping_role_list.append(_mapping_dict)
                elif len(_src) == 3:
                    if len(_dest) == 1:
                        # "rolename"
                        _dest_name["dest_coll"] = "{0}.{1}.{2}".format(
                            namespace, collection, _item[1]
                        )
                    elif len(_dest) == 2:
                        # "collection.rolename"
                        _dest_name["dest_coll"] = "{0}.{1}".format(namespace, _item[1])
                    elif len(_dest) == 3:
                        # FQCN
                        _dest_name["dest_coll"] = _item[1]
                    _mapping_dict["dest_name"] = _dest_name
                    _mapping_coll_list.append(_mapping_dict)
                else:
                    print(
                        "ERROR: Ignoring invalid extra-mapping value {0}".format(_map)
                    )
        return _mapping_role_list, _mapping_coll_list

    extra_mapping, extra_coll_mapping = parse_extra_mapping(
        args.extra_mapping, namespace, collection, role
    )

    extra_mapping_src_owner = list(
        map(itemgetter("src_owner"), list(map(itemgetter("src_name"), extra_mapping)))
    )
    extra_mapping_src_role = list(
        map(itemgetter("role"), list(map(itemgetter("src_name"), extra_mapping)))
    )
    extra_mapping_dest_prefix = list(
        map(
            itemgetter("dest_prefix"), list(map(itemgetter("dest_name"), extra_mapping))
        )
    )
    extra_mapping_dest_role = list(
        map(itemgetter("role"), list(map(itemgetter("dest_name"), extra_mapping)))
    )

    dest_path = Path.joinpath(
        top_dest_path, "ansible_collections/" + namespace + "/" + collection
    )
    _tests_dest_path = args.tests_dest_path
    if _tests_dest_path:
        tests_dest_path = Path(_tests_dest_path)
    else:
        tests_dest_path = dest_path

    os.makedirs(dest_path, exist_ok=True)

    roles_dir = dest_path / "roles"
    tests_dir = tests_dest_path / "tests"
    plugin_dir = dest_path / "plugins"
    modules_dir = plugin_dir / "modules"
    module_utils_dir = plugin_dir / "module_utils"
    docs_dir = dest_path / "docs"
    meta_dir = dest_path / "meta"

    src_path = args.src_path.resolve()
    src_owner = args.src_owner
    if not src_owner:
        src_owner = os.path.basename(src_path)
    _tasks_main = src_path / "tasks/main.yml"
    if not _tasks_main.exists():
        src_path = src_path / role
        _tasks_main = src_path / "tasks/main.yml"

    if not _tasks_main.exists():
        logging.error(
            f"Neither {src_path} nor {src_path.parent} is a role top directory."
        )
        sys.exit(errno.ENOENT)

    extra_script = args.extra_script
    if extra_script and not which(extra_script):
        logging.error(f"The extra-script {extra_script} is not an executable.")
        sys.exit(errno.ENOENT)
    elif not extra_script:
        extra_script = src_path / EXTRA_SCRIPT
        if not which(extra_script):
            extra_script = None

    _extras = set(os.listdir(src_path)).difference(ALL_DIRS)
    for dir in (".git", "plans"):
        try:
            _extras.remove(dir)
        except KeyError:
            pass
    extras = [src_path / e for e in _extras]

    global config
    config = {
        "namespace": namespace,
        "collection": collection,
        "role": new_role,
        "src_path": src_path,
        "dest_path": dest_path,
        "module_utils_dir": module_utils_dir,
    }

    transformer_args = {
        "namespace": namespace,
        "collection": collection,
        "prefix": prefix,
        "subrole_prefix": subrole_prefix,
        "replace_dot": replace_dot,
        # get role modules - will need to find and convert these to use FQCN
        "role_modules": get_role_modules(src_path),
        "src_owner": src_owner,
        "top_dir": current_dest,
        "extra_mapping_src_owner": extra_mapping_src_owner,
        "extra_mapping_src_role": extra_mapping_src_role,
        "extra_mapping_dest_prefix": extra_mapping_dest_prefix,
        "extra_mapping_dest_role": extra_mapping_dest_role,
    }

    # Role - copy subdirectories, tasks, defaults, vars, etc., in the system role to
    # DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE.
    copy_tree_with_replace(
        src_path, dest_path, role, new_role, ROLE_DIRS, transformer_args
    )

    # ==============================================================================

    copy_tree_with_replace(
        src_path,
        tests_dest_path,
        role,
        new_role,
        TESTS,
        transformer_args,
        isrole=False,
        ignoreme=[
            "artifacts",
            "linux-system-roles.*",
            "__pycache__",
            ".git*",
            "ansible-sshd",
        ],
    )

    # remove symlinks in the tests/role.
    removeme = ["library", "modules", "module_utils", "roles"]
    cleanup_symlinks(tests_dir / new_role, role, removeme)

    # ==============================================================================

    def update_readme(src_path, filename, rolename, comment, issubrole=False):
        if not filename.startswith("README"):
            return
        if filename == "README.md":
            title = rolename
        else:
            m = re.match(r"README(.*)(\.md)", filename)
            title = rolename + m.group(1)
        main_doc = dest_path / "README.md"
        if not main_doc.exists():
            if readme_path and Path(readme_path).exists():
                with open(readme_path, encoding="utf-8") as f:
                    _s = f.read()
            else:
                _s = textwrap.dedent("""\
                    # {0} {1} collections
                    """).format(namespace, collection)

            s = textwrap.dedent("""\
                {0}

                {1}

                <!--ts-->
                  * {2}
                <!--te-->
                """).format(_s, comment, title)
            with open(main_doc, "w", encoding="utf-8") as f:
                f.write(s)
        else:
            with open(main_doc, encoding="utf-8") as f:
                s = f.read()
            role_link = "{0}".format(title)
            if role_link not in s:
                if comment not in s:
                    text = s + textwrap.dedent("""\

                        {2}

                        <!--ts-->
                          * {3}
                        <!--te-->
                        """).format(namespace, collection, comment, role_link)
                else:
                    find = r"({0}\n\n<!--ts-->\n)(( |\*|\w|\[|\]|\(|\)|\.|/|-|\n|\r)+)".format(
                        comment
                    )
                    replace = r"\1\2  * {0}\n".format(role_link)
                    text = re.sub(find, replace, s, flags=re.M)
                with open(main_doc, "w", encoding="utf-8") as f:
                    f.write(text)

    # Copy docs, design_docs, and examples to
    # DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/docs/ROLE.
    # Copy README.md to DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE.
    # Generate a top level README.md which contains links to roles/ROLE/README.md.
    def process_readme(
        src_path, filename, role, new_role, original=None, issubrole=False
    ):
        """
        Copy src_path/filename to dest_path/docs/new_role.
        filename could be README.md, README-something.md, or something.md.
        Create a primary README.md in dest_path, which points to dest_path/docs/new_role/filename
        with the title new_role or new_role-something.
        """
        src = src_path / filename
        dest = roles_dir / new_role / filename
        # copy
        logging.info(f"Copying doc {filename} to {dest}")
        copy2(src, dest, follow_symlinks=False)
        dest = roles_dir / new_role
        file_patterns = ["*.md", "*.html"]
        file_replace(dest, src_owner + "." + role, prefix + new_role, file_patterns)
        # --extra-mapping SRCROLENAME:DESTROLENAME(or FQCN)
        for _emap in extra_mapping:
            # Replacing SRC_OWNER.ROLE with FQCN
            _from = "{0}.{1}".format(
                (
                    _emap["src_name"]["src_owner"]
                    if _emap["src_name"]["src_owner"]
                    else src_owner
                ),
                _emap["src_name"]["role"],
            )
            _to = "{0}{1}".format(
                (
                    _emap["dest_name"]["dest_prefix"]
                    if _emap["dest_name"]["dest_prefix"]
                    else prefix
                ),
                _emap["dest_name"]["role"],
            )
            file_replace(dest, _from, _to, file_patterns)
            # Replacing unprefixed ROLE with FQCN
            _from = " {0}".format(_emap["src_name"]["role"])
            _to = " {0}{1}".format(
                (
                    _emap["dest_name"]["dest_prefix"]
                    if _emap["dest_name"]["dest_prefix"]
                    else prefix
                ),
                _emap["dest_name"]["role"],
            )
            file_replace(dest, _from, _to, file_patterns)
        if original:
            file_replace(dest, original, prefix + new_role, file_patterns)
        if filename == "README.md":
            if issubrole:
                comment = "### Private Roles"
            else:
                comment = "### Supported Roles"
            update_readme(src_path, filename, new_role, comment, issubrole)

    ignoreme = ["linux-system-roles.*"]
    dest = docs_dir / new_role
    for doc in DOCS:
        src = src_path / doc
        if src.is_dir():
            logging.info(f"Copying docs {src} to {dest}")
            lsr_copytree(
                src,
                dest,
                symlinks=False,
                ignore=ignore_patterns(*ignoreme),
                dirs_exist_ok=True,
            )
            if doc == "examples":
                lsrxfrm = LSRTransformer(
                    dest,
                    transformer_args,
                    False,
                    role,
                    new_role,
                    LSRFileTransformer,
                )
                lsrxfrm.run()
        elif src.is_file():
            process_readme(src_path, doc, role, new_role)

    # Remove symlinks in the docs/role (e.g., in the examples).
    removeme = ["library", "modules", "module_utils", "roles"]
    cleanup_symlinks(dest, new_role, removeme)

    # ==============================================================================

    # Copy library, module_utils, plugins
    # Library and plugins are copied to dest_path/plugins
    # If plugin is in SUBDIR (currently, just module_utils),
    #   module_utils/*.py are to dest_path/plugins/module_utils/ROLE/*.py
    #   module_utils/subdir/*.py are to dest_path/plugins/module_utils/subdir/*.py
    SUBDIR = ("module_utils",)
    for plugin in PLUGINS:
        src = src_path / plugin
        plugin_name = dir_to_plugin(plugin)
        if not src.is_dir():
            continue
        if plugin in SUBDIR:
            for sr in src.iterdir():
                if sr.is_dir():
                    # If src/sr is a directory, copy it to the dest
                    dest = plugin_dir / plugin_name / sr.name
                    logging.info(f"Copying plugin {sr} to {dest}")
                    lsr_copytree(sr, dest)
                else:
                    # Otherwise, copy it to the plugins/plugin_name/ROLE
                    dest = plugin_dir / plugin_name / new_role
                    dest.mkdir(parents=True, exist_ok=True)
                    logging.info(f"Copying plugin {sr} to {dest}")
                    copy2(sr, dest, follow_symlinks=False)
        else:
            dest = plugin_dir / plugin_name
            logging.info(f"Copying plugin {src} to {dest}")
            lsr_copytree(src, dest)

    # Update the python codes which import modules in plugins/{modules,modules_dir}.
    config["module_utils"] = gather_module_utils_parts(module_utils_dir)
    additional_rewrites = []
    config["additional_rewrites"] = additional_rewrites
    for rewrite_dir in (module_utils_dir, modules_dir):
        if rewrite_dir.is_dir():
            for root, dirs, files in os.walk(rewrite_dir):
                for filename in files:
                    if os.path.splitext(filename)[1] != ".py":
                        continue
                    full_path = Path(root) / filename
                    text = full_path.read_bytes()
                    new_text = IMPORT_RE.sub(import_replace, text)
                    new_text = FROM_RE.sub(from_replace, new_text)
                    for rewrite in additional_rewrites:
                        pattern = re.compile(
                            re.escape(rb"ansible.module_utils.%s" % b".".join(rewrite))
                        )
                        new_text = pattern.sub(rewrite[-1], new_text)

                    if text != new_text:
                        logging.info("Rewriting imports for {}".format(full_path))
                        full_path.write_bytes(new_text)
                        additional_rewrites[:] = []

    # ==============================================================================

    # Extra files and directories including the sub-roles
    for extra in extras:
        if extra.name in TOX:
            continue
        if extra.name.endswith(".md"):
            # E.g., contributing.md, README-devel.md and README-testing.md
            process_readme(extra.parent, extra.name, role, new_role)
        elif extra.is_dir():
            # Copying sub-roles to the roles dir and its tests and README are also
            # handled in the same way as the parent role's are.
            if extra.name == "roles":
                for sr in extra.iterdir():
                    # If a role name contains '.', replace it with replace_dot
                    # convert nested subroles to prefix name with subrole_prefix.
                    dr = sr.name.replace(".", replace_dot)
                    if subrole_prefix and not dr.startswith(subrole_prefix):
                        dr = subrole_prefix + dr
                    copy_tree_with_replace(
                        sr, dest_path, dr, dr, ROLE_DIRS, transformer_args
                    )
                    # copy tests dir to dest_path/"tests"
                    copy_tree_with_replace(
                        sr,
                        tests_dest_path,
                        dr,
                        dr,
                        TESTS,
                        transformer_args,
                        isrole=False,
                        ignoreme=[
                            "artifacts",
                            "linux-system-roles.*",
                            "__pycache__",
                            ".git*",
                        ],
                    )
                    # remove symlinks in the tests/new_role.
                    removeme = ["library", "modules", "module_utils", "roles"]
                    cleanup_symlinks(tests_dir / dr, dr, removeme)
                    # copy README.md to dest_path/roles/sr.name
                    _readme = sr / "README.md"
                    if _readme.is_file():
                        process_readme(
                            sr, "README.md", dr, dr, original=sr.name, issubrole=True
                        )
                    if sr.name != dr:
                        # replace "sr.name" with "dr" in role_dir
                        dirs = ["roles", "docs", "tests"]
                        for dir in dirs:
                            role_dir = dest_path / dir
                            file_patterns = ["*.yml", "*.md"]
                            file_replace(
                                role_dir,
                                re.escape("\b" + sr.name + "\b"),
                                dr,
                                file_patterns,
                            )
            elif extra.name == ".ostree":
                # copy to role directory within collection
                dest = dest_path / "roles" / new_role / extra.name
                logging.info(f"Copying extra {extra} to {dest}")
                lsr_copytree(extra, dest)
            # Other extra directories are copied to the collection dir as they are.
            else:
                dest = dest_path / extra.name
                logging.info(f"Copying extra {extra} to {dest}")
                lsr_copytree(extra, dest)
        # Other extra files.
        else:
            do_copy = True
            if extra.name.endswith(".yml") and "playbook" in extra.name:
                # some-playbook.yml is copied to docs/role dir.
                dest = dest_path / "docs" / new_role
                dest.mkdir(parents=True, exist_ok=True)
            elif extra.name == ".ansible-lint":
                # process .ansible-lint
                dest = dest_path / "roles" / new_role / ".ansible-lint"
                process_ansible_lint(extra, dest, new_role)
                do_copy = False
            else:
                # If the extra file 'filename' has no extension, it is copied to the collection dir as
                # 'filename-ROLE'. If the extra file is 'filename.ext', it is copied to 'filename-ROLE.ext'.
                dest = dest_path / add_rolename(extra.name, new_role)
            if do_copy:
                logging.info(f"Copying extra {extra} to {dest}")
                copy2(extra, dest, follow_symlinks=False)

    dest = dest_path / "docs" / new_role
    if dest.is_dir():
        lsrxfrm = LSRTransformer(
            dest, transformer_args, False, role, new_role, LSRFileTransformer
        )
        lsrxfrm.run()

    if not meta_dir.exists():
        meta_dir.mkdir()
    copyfile(src_meta_runtime, meta_dir / "runtime.yml")

    if extra_script:
        env = {}
        env.update(os.environ)
        env.update(
            {
                "LSR_ROLES_DIR": roles_dir / role,
                "LSR_TESTS_DIR": tests_dir / role,
                "LSR_NAMESPACE": namespace,
                "LSR_COLLECTION": collection,
                "LSR_ROLE": role,
                "LSR_NEW_ROLE": new_role,
            }
        )
        subprocess.check_call(
            [str(extra_script.resolve())],
            cwd=roles_dir / role,
            env=env,
        )

    # Handle --extra-mapping FQCN0:FQCN1 or FQCN2:ROLE3
    file_patterns = ["*.yml", "*.md"]
    for _emap in extra_coll_mapping:
        # Replacing SRC_OWNER.ROLE with FQCN
        _from = "{0}".format(_emap["src_name"]["src_coll"])
        _to = "{0}".format(_emap["dest_name"]["dest_coll"])
        # role
        file_replace(roles_dir / new_role, _from, _to, file_patterns)
        # subroles
        for sr in roles_dir.iterdir():
            if sr.name.startswith(subrole_prefix):
                file_replace(roles_dir / sr.name, _from, _to, file_patterns)
        # tests
        file_replace(tests_dir / new_role, _from, _to, file_patterns)
        # docs
        file_replace(docs_dir / new_role, _from, _to, file_patterns)
        # meta
        file_replace(meta_dir, _from, _to, file_patterns)

    # Copy processed README.md to the docs dir after renaming it to README_ROLENAME.md
    role_readmes = [
        roles_dir / new_role / "README.md",
        roles_dir / new_role / "README.html",
    ]
    for readme in role_readmes:
        if readme.is_file():
            if not docs_dir.is_dir():
                if docs_dir.exists():
                    docs_dir.unlink()
                docs_dir.mkdir()
            docs_readme = docs_dir / "README_{0}{1}".format(
                new_role, os.path.splitext(readme)[1]
            )
            copyfile(readme, docs_readme)

    # Copy CHANGELOG.md to the docs dir after renaming it to CHANGELOG_ROLENAME.md
    changelog_md = src_path / "CHANGELOG.md"
    if changelog_md.is_file():
        if not docs_dir.is_dir():
            if docs_dir.exists():
                docs_dir.unlink()
            docs_dir.mkdir()
        role_changelog_md = docs_dir / "CHANGELOG_{0}.md".format(new_role)
        copyfile(changelog_md, role_changelog_md)

    default_collections_paths = "~/.ansible/collections:/usr/share/ansible/collections"
    default_collections_paths_list = list(
        map(os.path.expanduser, default_collections_paths.split(":"))
    )
    # top_dest_path is not in the default collections path.
    # suggest to run ansible-playbook with ANSIBLE_COLLECTIONS_PATH env var.
    if current_dest not in default_collections_paths_list:
        ansible_collections_paths = current_dest + ":" + default_collections_paths
        logging.debug(
            f"Run ansible-playbook with environment variable ANSIBLE_COLLECTIONS_PATH={ansible_collections_paths}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(role2collection())
