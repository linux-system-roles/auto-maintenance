#!/usr/bin/env python

import os
import sys
import logging
import re
from pathlib import Path
import jinja2
import yaml
import json
import argparse

from ansible.errors import AnsibleParserError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.mod_args import ModuleArgsParser
from ansible.parsing.yaml.objects import AnsibleSequence, AnsibleMapping
from ansible.template import Templar
from ansible.plugins.loader import (
    filter_loader,
    lookup_loader,
    module_loader,
    test_loader,
)

if os.environ.get("LSR_DEBUG") == "true":
    logging.getLogger().setLevel(logging.DEBUG)

COLLECTION_DIRS = ["playbooks", "plugins", "roles", "tests"]

ANSIBLE_BUILTIN = "ansible.builtin"

JINJA2_BUILTIN = "jinja2"

LOCAL = "local"

COLLECTION_BUILTINS = {ANSIBLE_BUILTIN, JINJA2_BUILTIN}

ROLE_DIRS = [
    "meta",
    "defaults",
    "examples",
    "files",
    "filter_plugins",
    "handlers",
    "library",
    "module_utils",
    "playbooks",
    "roles",
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

# these are collection tests/ sub-directories that we know we do not
# need to process
SKIP_COLLECTION_TEST_DIRS = ["unit", "pytests"]


def get_role_dir(role_path, dirpath):
    """role_path is the path to a directory containing a role i.e. a directory
    containing a tasks/main.yml and one or more directories in ROLE_DIRS."""
    if role_path == dirpath:
        return None
    dir_pth = Path(dirpath)
    relpath = dir_pth.relative_to(role_path)
    base_dir = relpath.parts[0]
    if base_dir in ROLE_DIRS:
        return base_dir
    return None


def get_role_name(role_path):
    dir_pth = Path(role_path)
    if dir_pth.parts[-2] == "roles":
        return dir_pth.parts[-3] + "." + dir_pth.parts[-1]
    else:
        return dir_pth.parts[-1]


def get_file_type(item):
    if isinstance(item, AnsibleMapping):
        if "galaxy_info" in item or "dependencies" in item:
            return "meta"
        return "vars"
    elif isinstance(item, AnsibleSequence):
        return "tasks"
    else:
        return "unknown"


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


def handle_other(item, filectx):
    """handle properties of Ansible item other than vars and tasks"""
    if "when" in item:
        find_plugins_for_when_that(item["when"], filectx)


def __do_handle_vars(vars, filectx):
    if vars is None or not vars:
        return
    elif isinstance(vars, (int, bool, float)):
        return
    elif isinstance(vars, list):
        for item in vars:
            __do_handle_vars(item, filectx)
    elif isinstance(vars, dict):
        for key, item in vars.items():
            if filectx.filename.endswith("defaults/main.yml"):
                filectx.rolevars.add(key)
            __do_handle_vars(item, filectx)
    elif filectx.templar.is_template(vars):
        find_plugins(vars, filectx)


def handle_vars(item, filectx):
    """handle vars of Ansible item"""
    __do_handle_vars(item.get("vars"), filectx)


def handle_meta(item, filectx):
    """handle meta/main.yml file"""
    pass


PLUGIN_BUILTINS = set(["lookup", "q", "query"])


def is_builtin(plugin):
    return plugin in PLUGIN_BUILTINS


jinja2_macros = set()


class PluginItem(object):
    def __init__(
        self,
        collection,
        name,
        type,
        used_in_collection,
        used_in_role,
        relpth,
        lineno,
        is_test,
    ):
        """Name might be plain or fqcn."""
        ary = self.split_fqcn(name)
        self.name = ary[-1]
        self.collection = collection
        if collection != LOCAL and len(ary) > 1 and not ary[0] == collection:
            raise Exception(
                f"Given collection name {collection} does not match the plugin FQCN {name}"
            )
        self.type = type
        self.relpth = relpth
        self.lineno = lineno
        self.is_test = is_test
        self.used_in_collection = used_in_collection
        self.used_in_role = used_in_role
        self.orig_name = name

    def split_fqcn(self, name):
        ary = name.rsplit(".", 1)
        if len(ary) > 1:
            if ary[0] == "ansible.posix.system":
                # special case for some ansible.posix tests that use
                # ansible.posix.system.selinux:
                ary[0] = "ansible.posix"
            elif ary[0] == "community.general.system":
                ary[0] = "community.general"
        return ary

    def has_correct_fqcn(self):
        """The local plugin has correct FQCN if it matches the collection it was used in."""
        ary = self.split_fqcn(self.orig_name)
        if len(ary) < 2:
            return False  # not FQCN
        if self.collection == LOCAL:
            expected = self.used_in_collection + "." + self.name
            return expected == self.orig_name
        return True


class NumericOpItem(object):
    def __init__(
        self,
        collection_name,
        role_name,
        varname,
        opname,
        value,
        relpth,
        lineno,
        is_test,
    ):
        self.collection_name = collection_name
        self.role_name = role_name
        self.varname = varname
        self.opname = opname
        self.value = value
        self.relpth = relpth
        self.lineno = lineno
        self.is_test = is_test

    def __str__(self):
        if self.collection_name:
            where = self.collection_name + "."
        else:
            where = ""
        where = where + self.role_name
        return f"[{self.varname}] [{self.opname}] [{self.value}] at {where} {self.relpth}:{self.lineno}"


def node2plugin_type(nodetype):
    if nodetype == jinja2.nodes.Filter:
        return "filter"
    elif nodetype == jinja2.nodes.Test:
        return "test"
    elif nodetype == jinja2.nodes.Macro:
        return "macro"
    else:
        return "module"


MATH_OPS = (
    jinja2.nodes.Add,
    jinja2.nodes.Div,
    jinja2.nodes.Mod,
    jinja2.nodes.Mul,
    jinja2.nodes.Neg,
    jinja2.nodes.Pos,
    jinja2.nodes.Pow,
    jinja2.nodes.Sub,
)


# Look for places where a public variable is used in some
# sort of numeric operation that might require casting
# the variable to some numeric type. e.g.
# {{ if my_float_var < 1.0 }}
# should be
# {{ if my_float_var | float < 1.0 }}
# so comparisons, arithmetic, unary
# {{ 2 + my_int_var }}
# {{ -my_int_var }}
# These should be cast to int
# The return value is the variable name, the operation,
# and the value (or 0 for unary ops)
# The report at the end will also specify the location where
# the usage occurred
def get_bare_numeric_op(jinja_node, filectx):
    var_name, op_name, value = None, None, None
    if isinstance(jinja_node, jinja2.nodes.Compare):
        if (
            isinstance(jinja_node.expr, jinja2.nodes.Name)
            and jinja_node.expr.name in filectx.rolevars
            and isinstance(jinja_node.ops[0], jinja2.nodes.Operand)
            and isinstance(jinja_node.ops[0].expr, jinja2.nodes.Const)
            and isinstance(jinja_node.ops[0].expr.value, (int, float))
        ):
            var_name = jinja_node.expr.name
            op_name = jinja_node.ops[0].op
            value = jinja_node.ops[0].expr.value
        elif (
            isinstance(jinja_node.expr, jinja2.nodes.Const)
            and isinstance(jinja_node.expr.value, (int, float))
            and isinstance(jinja_node.ops[0], jinja2.nodes.Operand)
            and isinstance(jinja_node.ops[0].expr, jinja2.nodes.Name)
            and jinja_node.ops[0].expr.name in filectx.rolevars
        ):
            var_name = jinja_node.ops[0].expr.name
            op_name = jinja_node.ops[0].op
            value = jinja_node.expr.value
    elif isinstance(jinja_node, (jinja2.nodes.Neg, jinja2.nodes.Pos)):
        if (
            isinstance(jinja_node.node, jinja2.nodes.Name)
            and jinja_node.node.name in filectx.rolevars
        ):
            var_name = jinja_node.node.name
            op_name = jinja_node.operator
            value = 0  # unary operator, no other value
    else:
        if isinstance(jinja_node.left, jinja2.nodes.Name):
            var_name = jinja_node.left.name
            other = jinja_node.right
        elif isinstance(jinja_node.right, jinja2.nodes.Name):
            var_name = jinja_node.right.name
            other = jinja_node.left
        if (
            var_name in filectx.rolevars
            and isinstance(other, jinja2.nodes.Const)
            and isinstance(other.value, (int, float))
        ):
            op_name = jinja_node.operator
            value = other.value
        else:
            var_name = None
    return var_name, op_name, value


def find_plugins(args, filectx):
    if args is None or not args:
        return
    if isinstance(args, bytes):
        args = args.decode()
    if isinstance(args, str):
        try:
            tmpl = filectx.templar.environment.parse(source=args)
        except jinja2.exceptions.TemplateSyntaxError:
            logging.warning(
                f"the string [{args}] could not be processed as a Jinja2 template "
                f"at {filectx.filename}:{filectx.get_lineno(1)}"
            )
            return
        node_types = (
            jinja2.nodes.Call,
            jinja2.nodes.Filter,
            jinja2.nodes.Test,
            jinja2.nodes.Macro,
            jinja2.nodes.Compare,
        ) + MATH_OPS
        for item in tmpl.find_all(node_types):
            if isinstance(item, MATH_OPS) or isinstance(item, jinja2.nodes.Compare):
                var_name, op_name, value = get_bare_numeric_op(item, filectx)
                if var_name:
                    filectx.add_bare_numeric_op(
                        var_name, op_name, value, filectx.get_lineno(item.lineno)
                    )
                continue
            elif hasattr(item, "name"):
                item_name = item.name
            elif hasattr(item.node, "name"):
                item_name = item.node.name
            elif isinstance(item.node, jinja2.nodes.Getattr):
                logging.debug(f"\tskipping getattr call {item}")
                continue
            else:
                logging.warning(
                    f"unknown item {item} at {filectx.filename}:{item.lineno}"
                )
                continue
            if isinstance(item, jinja2.nodes.Macro):
                global jinja2_macros
                jinja2_macros.add(item_name)
                logging.debug(f"\titem {item_name} {item.__class__}")
                continue
            filectx.add_plugin(
                item_name, item.__class__, filectx.get_lineno(item.lineno)
            )
            if item_name in ["selectattr", "rejectattr"] and len(item.args) > 1:
                filectx.add_plugin(
                    item.args[1].value,
                    jinja2.nodes.Test,
                    filectx.get_lineno(item.lineno),
                )
            if item_name in ["select", "reject"] and item.args:
                filectx.add_plugin(
                    item.args[0].value,
                    jinja2.nodes.Test,
                    filectx.get_lineno(item.lineno),
                )
            if item_name == "map" and item.args:
                filectx.add_plugin(
                    item.args[0].value,
                    jinja2.nodes.Filter,
                    filectx.get_lineno(item.lineno),
                )
            if item_name in ["lookup", "query", "q"] and item.args:
                filectx.add_plugin(
                    item.args[0].value,
                    jinja2.nodes.Call,
                    filectx.get_lineno(item.lineno),
                )
    elif isinstance(args, list):
        for item in args:
            find_plugins(item, filectx)
    elif isinstance(args, dict):
        for item in args.values():
            find_plugins(item, filectx)
    elif isinstance(args, (bool, int, float)):
        pass
    else:
        logging.error(
            "Ignoring module argument %s of type %s at %s:%s",
            args,
            args.__class__,
            filectx.filename,
            filectx.get_lineno(1),
        )
    return


def find_plugins_for_when_that(val, filectx):
    """when or that - val can be string or list"""
    if val is None or isinstance(val, (bool, int, float)):
        pass
    elif isinstance(val, list):
        for item in val:
            find_plugins_for_when_that(item, filectx)
    else:
        if filectx.templar.is_template(val):
            find_plugins(val, filectx)
        else:
            find_plugins("{{ " + val + " }}", filectx)


def handle_task(task, filectx):
    """handle a single task"""
    mod_arg_parser = ModuleArgsParser(task)
    try:
        action, args, _ = mod_arg_parser.parse(skip_action_validation=True)
    except AnsibleParserError as e:
        logging.warning("Couldn't parse task at %s (%s)\n%s" % (task, e.message, task))
        return
    filectx.lineno = task.ansible_pos[1]
    if filectx.templar.is_template(args):
        logging.debug(f"\tmodule {action} has template {args}")
        find_plugins(args, filectx)
    elif action == "assert":
        find_plugins_for_when_that(args["that"], filectx)
    else:
        logging.debug(f"\tmodule {action} has no template {args}")
    if "when" in task:
        find_plugins_for_when_that(task["when"], filectx)
    filectx.add_plugin(action, "module", task.ansible_pos[1])


def handle_tasks(item, filectx):
    """item has one or more fields which hold a list of Task objects"""
    for kw in TASK_LIST_KWS:
        if kw in item:
            for task in item[kw]:
                handle_item(task, filectx)


def handle_item(item, filectx):
    handle_vars(item, filectx)
    item_type = get_item_type(item)
    if item_type == "task":
        handle_task(item, filectx)
    else:
        handle_other(item, filectx)
    handle_tasks(item, filectx)


def os_walk(from_path):
    if os.path.isdir(from_path) and not os.path.islink(from_path):
        for (dirpath, _, filenames) in os.walk(from_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                yield filepath


def os_listdir(from_path):
    if os.path.isdir(from_path) and not os.path.islink(from_path):
        for dirent in os.scandir(from_path):
            if dirent.is_symlink():
                continue
            yield dirent.name, dirent.path


def process_yml_file(filepath, ctx):
    ctx.filename = filepath
    ctx.lineno = 0
    if filepath.endswith("/vault-variables.yml"):
        logging.debug(f"skipping vault-variables.yml file {filepath}")
        return
    dl = DataLoader()
    ans_data = dl.load_from_file(filepath)
    if ans_data is None:
        logging.debug(f"file is empty {filepath}")
        return
    file_type = get_file_type(ans_data)
    if file_type == "vars":
        __do_handle_vars(ans_data, ctx)
    elif file_type == "meta":
        handle_meta(ans_data, ctx)
    elif ctx.in_tests() and filepath.endswith("requirements.yml"):
        handle_meta(ans_data, ctx)
    elif file_type == "unknown":
        logging.warning("Skipping file of unknown type: %s", filepath)
    else:
        for item in ans_data:
            handle_item(item, ctx)
    ctx.filename = None
    ctx.lineno = 0


def process_template(filepath, ctx):
    ctx.filename = filepath
    ctx.lineno = 0
    find_plugins(open(filepath).read(), ctx)
    ctx.filename = None
    ctx.lineno = 0


def process_templates_path(templates_path, ctx):
    for filepath in os_walk(templates_path):
        process_template(filepath, ctx)


def process_ansible_file(filepath, ctx):
    if filepath.endswith(".yml"):
        process_yml_file(filepath, ctx)
    elif filepath.endswith(".yaml"):
        process_yml_file(filepath, ctx)
    elif filepath.endswith(".j2"):
        process_template(filepath, ctx)


def process_ansible_yml_path(yml_path, ctx):
    """For role directories like tasks/, defaults/, vars/"""
    for filepath in os_walk(yml_path):
        process_ansible_file(filepath, ctx)


def process_reqs_file(path, ctx):
    legacy_rqf = "requirements.yml"
    coll_rqf = "collection-requirements.yml"
    for rqf in [legacy_rqf, coll_rqf]:
        reqs_file = os.path.join(path, rqf)
        if os.path.isfile(reqs_file):
            reqs = yaml.safe_load(open(reqs_file))
            if isinstance(reqs, dict):
                if ctx.in_tests():
                    ctx.role_test_reqs = reqs
                else:
                    ctx.role_reqs = reqs
                ctx.add_dependencies()
                if rqf == legacy_rqf:
                    logging.warning(
                        "Still using %s - please convert to %s instead",
                        reqs_file,
                        coll_rqf,
                    )


def process_role_meta_path(meta_path, ctx):
    process_reqs_file(meta_path, ctx)
    meta_main = os.path.join(meta_path, "main.yml")
    if os.path.isfile(meta_main) and not os.path.islink(meta_main):
        process_yml_file(meta_main, ctx)


def process_playbooks_path(playbooks_path, ctx):
    for _, itempath in os_listdir(playbooks_path):
        if os.path.isfile(itempath):
            process_ansible_file(itempath, ctx)
    # treat it like a role - look for vars/, tasks/, etc.
    process_role(playbooks_path, False, ctx)


def process_role_tests_path(tests_path, ctx):
    """Treat like a playbooks/ directory."""
    ctx.enter_tests()
    process_reqs_file(tests_path, ctx)
    process_playbooks_path(tests_path, ctx)
    ctx.exit_tests()


def process_integration_tests(integration_path, ctx):
    """Not sure what could be in here - just process as if it contains
    directories of plain old ansible yml files like tasks/
    except for the targets/ directory which is like a roles/
    directory"""
    ctx.in_collection_integration_tests = True
    for dirname, itempath in os_listdir(integration_path):
        if dirname == "targets":
            process_roles_path(itempath, ctx)
        else:
            process_ansible_yml_path(itempath, ctx)
    ctx.in_collection_integration_tests = False


def process_role(role_path, is_real_role, ctx):
    if is_real_role:
        if ctx.found_role_name is None:
            ctx.found_role_name = get_role_name(role_path)
        ctx.enter_role(ctx.found_role_name, role_path)
        ctx.add_local_plugins(role_path, "library")
        ctx.add_local_plugins(role_path, "filter_plugins")
    # process defaults to get role public api variables
    dirname = "defaults"
    dirpath = os.path.join(role_path, dirname)
    if os.path.isdir(dirpath) and not os.path.islink(dirpath):
        process_ansible_yml_path(dirpath, ctx)
    for dirname in ROLE_DIRS:
        if dirname == "defaults":
            continue
        dirpath = os.path.join(role_path, dirname)
        if not os.path.isdir(dirpath) or os.path.islink(dirpath):
            continue
        elif dirname == "meta":
            process_role_meta_path(dirpath, ctx)
        elif dirname == "templates":
            process_templates_path(dirpath, ctx)
        elif dirname == "tests":
            process_role_tests_path(dirpath, ctx)
        elif dirname == "playbooks":
            process_playbooks_path(dirpath, ctx)
        elif dirname == "roles":
            process_roles_path(dirpath, ctx)
        else:
            process_ansible_yml_path(dirpath, ctx)
    if is_real_role:
        ctx.exit_role()


def process_roles_path(pathname, ctx):
    """Pathname is the name of a directory containing one or more role subdirectories."""
    if not os.path.isdir(pathname) or os.path.islink(pathname):
        return
    for item_name, role_path in os_listdir(pathname):
        if item_name.startswith(".git"):
            continue
        if ctx.is_role(role_path):
            ctx.found_role_name = item_name
            process_role(role_path, True, ctx)
        elif ctx.in_collection_integration_tests:
            process_ansible_yml_path(role_path, ctx)
        else:
            logging.warning(f"Unexpected item {role_path} - not a role")


def process_collection_tests(pathname, ctx):
    """Look for system roles tests"""
    ctx.enter_tests()
    for dirname, dirpath in os_listdir(pathname):
        if dirname == "integration" and os.path.isdir(dirpath):
            process_integration_tests(dirpath, ctx)
        elif os.path.isfile(os.path.join(dirpath, "tests_default.yml")):
            ctx.enter_role(dirname, dirpath)
            process_role_tests_path(dirpath, ctx)
            ctx.exit_role()
        elif os.path.isdir(dirpath) and dirname in SKIP_COLLECTION_TEST_DIRS:
            continue
        elif os.path.isfile(dirpath):
            process_ansible_file(dirpath, ctx)
        elif os.path.isdir(dirpath):
            # don't know what this is - process like ansible yml files
            process_ansible_yml_path(dirpath, ctx)

    ctx.exit_tests()


def process_collection_roles(pathname, ctx):
    process_roles_path(pathname, ctx)


def get_collection_plugins(pathname, ctx):
    plugin_dir = os.path.join(pathname, "plugins")
    if os.path.isdir(plugin_dir):
        for dirname, _ in os_listdir(plugin_dir):
            ctx.add_local_plugins(plugin_dir, dirname)


def process_collection(pathname, ctx):
    """Pathname is a directory like /path/to/ansible_collections/NAMESPACE/NAME."""
    collection_pth = Path(pathname)
    if ctx.found_collection_name is None:
        ctx.found_collection_name = ".".join(collection_pth.parts[-2:])
    ctx.enter_collection(ctx.found_collection_name, pathname)
    ctx.add_dependencies()
    get_collection_plugins(pathname, ctx)
    process_collection_roles(str(collection_pth / "roles"), ctx)
    process_collection_tests(str(collection_pth / "tests"), ctx)
    ctx.exit_collection()


def process_collections(pathname, ctx):
    for namespace, coll_path in os_listdir(pathname):
        if not os.path.isdir(coll_path):
            logging.warning(
                f"Unexpected item {coll_path} is not a collection directory"
            )
            continue
        for name, collection_path in os_listdir(coll_path):
            ctx.found_collection_name = namespace + "." + name
            process_collection(collection_path, ctx)


def process_path(pathname, ctx):
    pathname = os.path.abspath(pathname)
    ary = os.path.split(pathname)
    if ary[-1] == "ansible_collections":
        process_collections(pathname, ctx)
    elif ary[-1] == "roles":
        process_roles_path(pathname, ctx)
    elif ctx.is_collection(pathname):
        process_collection(pathname, ctx)
    elif ctx.is_role(pathname):
        process_role(pathname, True, ctx)
    else:
        logging.warning(f"{pathname} is not a recognized path - skipping")


def collection_match(coll1, coll2):
    return coll1 == coll2 or coll2.startswith(coll1 + ".")


def is_builtin_collection(collection):
    for coll in COLLECTION_BUILTINS:
        if collection_match(coll, collection):
            return True
    return False


class SearchCtx(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.plugins = []
        self.collection_name = []
        self.role_name = []
        self.templar = Templar(loader=None)
        self.local_plugins = []  # plugins defined by the collection/role being scanned
        self.found_collection_name = None
        self.found_role_name = None
        self.tests_stack = []
        self.pathname = None
        self.filename = None
        self.role_pathname = None
        self.lineno = 0
        self.in_collection_integration_tests = False
        self.errors = []
        self.dependencies = []  # collection and/or role dependencies
        self.test_dependencies = []  # collection and/or role dependencies for tests
        self.role_reqs = {}  # role meta/collection-requirements.yml, if any
        self.role_test_reqs = {}  # role tests/collection-requirements.yml, if any
        self.manifest_json = {}
        self.galaxy_yml = {}
        self.rolevars = set()
        self.numeric_ops = []

    def enter_collection(self, collection_name, pathname):
        if len(self.collection_name) > 0:
            raise Exception(
                f"Error: cannot enter collection {collection_name} - already in collection {self.collection_name}"
            )
        self.collection_name.append(collection_name)
        self.local_plugins.insert(0, set())
        self.dependencies.insert(0, set())
        self.test_dependencies.insert(0, set())
        self.pathname = pathname

    def exit_collection(self):
        if len(self.collection_name) < 1:
            raise Exception("Error: cannot exit collection - not in a collection")
        self.collection_name.pop()
        self.found_collection_name = None
        if len(self.local_plugins) > 0:
            del self.local_plugins[0]
        if len(self.dependencies) > 0:
            del self.dependencies[0]
        if len(self.test_dependencies) > 0:
            del self.test_dependencies[0]
        self.pathname = None
        self.manifest_json = {}
        self.galaxy_yml = {}

    def enter_role(self, role_name, pathname):
        if self.in_tests():
            self.role_name.append("tests")
        if len(self.role_name) == 0:
            self.role_pathname = pathname
        self.role_name.append(role_name)
        self.local_plugins.insert(0, set())
        self.dependencies.insert(0, set())
        self.test_dependencies.insert(0, set())

    def exit_role(self):
        if len(self.role_name) < 1:
            raise Exception("Error: cannot exit role - not in a role")
        self.role_name.pop()
        if self.in_tests():
            self.role_name.pop()
        self.found_role_name = None
        if len(self.local_plugins) > 0:
            del self.local_plugins[0]
        if len(self.dependencies) > 0:
            del self.dependencies[0]
        if len(self.test_dependencies) > 0:
            del self.test_dependencies[0]
        if len(self.role_name) == 0:
            self.role_pathname = None
        self.role_reqs = {}
        self.role_test_reqs = {}

    def enter_tests(self):
        self.tests_stack.append(True)

    def exit_tests(self):
        if self.in_tests():
            self.tests_stack.pop()

    def in_tests(self):
        return len(self.tests_stack) > 0

    def get_collection(self):
        if len(self.collection_name) > 0:
            return self.collection_name[-1]
        else:
            return None

    def get_role_fq(self):
        if len(self.role_name) > 0:
            return ".".join(self.role_name)
        else:
            return None

    def get_role_current(self):
        if len(self.role_name) > 0:
            return self.role_name[-1]
        else:
            return None

    def is_collection(self, pathname):
        manifest_json = Path(os.path.join(pathname, "MANIFEST.json"))
        if manifest_json.is_file():
            with open(manifest_json) as mjf:
                hsh = json.load(mjf)
                self.found_collection_name = (
                    hsh["collection_info"]["namespace"]
                    + "."
                    + hsh["collection_info"]["name"]
                )
                self.manifest_json = hsh
            return True
        galaxy_yml = Path(os.path.join(pathname, "galaxy.yml"))
        if galaxy_yml.is_file():
            with open(galaxy_yml) as gyf:
                hsh = yaml.safe_load(gyf)
                self.found_collection_name = hsh["namespace"] + "." + hsh["name"]
                self.galaxy_yml = hsh
            return True
        self.found_collection_name = None
        self.manifest_json = {}
        self.galaxy_yml = {}
        return False

    def is_role(self, pathname):
        tasks_main = Path(os.path.join(pathname, "tasks", "main.yml"))
        if not tasks_main.is_file():
            tasks_main = Path(os.path.join(pathname, "tasks", "main.yaml"))
        if tasks_main.is_file():
            self.found_role_name = tasks_main.parts[-3]
            return True
        self.found_role_name = None
        return False

    def _load_plugins_from_file(self, plugin_subdir, plugin_file, plugins):
        filename = str(plugin_subdir / plugin_file)
        file_str = open(filename).read()
        match = re.search(r"\n(class FilterModule.*?)(\n\S|$)", file_str, re.S)
        if match and match.group(1):
            myg = {}
            myl = {}
            code_str = match.group(1) + "\n"
            while True:
                try:
                    exec(code_str, myg, myl)
                    fm = myl["FilterModule"]()
                    fltrs = fm.filters()
                    plugins.update(set(fltrs.keys()))
                    break
                except NameError as ne:
                    match = re.match(r"^name '(\S+)' is not defined$", str(ne))
                    if match and match.groups() and match.group(1):
                        myg[match.group(1)] = True
                        myl[match.group(1)] = True
                    else:
                        logging.error(
                            "unable to parse filter plugins from {filename}: {code_str}"
                        )
                        raise ne
        match = re.search(r"\n(class TestModule.*?)(\n\S|$)", file_str, re.S)
        if match and match.group(1):
            myg = {}
            myl = {}
            code_str = match.group(1) + "\n"
            while True:
                try:
                    exec(code_str, myg, myl)
                    fm = myl["TestModule"]()
                    tests = fm.tests()
                    plugins.update(set(tests.keys()))
                    break
                except NameError as ne:
                    match = re.match(r"^name '(\S+)' is not defined$", str(ne))
                    if match and match.groups() and match.group(1):
                        myg[match.group(1)] = True
                        myl[match.group(1)] = True
                    else:
                        logging.error(
                            "unable to parse test plugins from {filename}: {code_str}"
                        )
                        raise ne

    # I think this method is not possible - loading an entire module has a
    # much larger chance of random code execution than just the FilterModule
    # part of the code
    # def _load_plugins_from_file(self, plugin_subdir, plugin_file, plugins):
    #     filename = str(plugin_subdir / plugin_file)
    #     module_name = filename.replace("/", ".")
    #     spec = importlib.util.spec_from_file_location(module_name, filename)
    #     module = importlib.util.module_from_spec(spec)
    #     sys.modules[module_name] = module
    #     spec.loader.exec_module(module)

    def add_local_plugins(self, parent_dir, plugin_dir):
        if plugin_dir == "module_utils":
            return
        plugin_subdir = Path(os.path.join(parent_dir, plugin_dir))
        if plugin_subdir.is_dir():
            for plugin_file in plugin_subdir.iterdir():
                plugins = set()
                if plugin_file.is_file() and str(plugin_file).endswith(".py"):
                    try:
                        self._load_plugins_from_file(
                            plugin_subdir, plugin_file, plugins
                        )
                    except Exception as exc:
                        logging.error(
                            "Could not parse plugins from {plugin_file} - skipping"
                        )
                        logging.debug("Exception %s", exc)
                        continue
                if (
                    not plugins
                    and plugin_file.is_file()
                    and plugin_file.stem != "__init__"
                ):
                    # assumes local plugins can be referred to by FQCN but not FQRN
                    plugins.add(plugin_file.stem)
                if plugins:
                    self.local_plugins[0].update(plugins)
                    collection_name = self.get_collection()
                    if collection_name:
                        for plugin in plugins:
                            self.local_plugins[0].add(collection_name + "." + plugin)

    def is_local_plugin(self, plugin_name):
        for plugin_set in self.local_plugins:
            if plugin_name in plugin_set:
                return True
        return False

    def add_plugin(self, plugin_name, plugin_type, lineno):
        pathname = self.pathname
        if pathname is None:
            pathname = self.role_pathname
        pth = Path(pathname)
        fpth = Path(self.filename)
        relpth = str(fpth.relative_to(pth))
        collection_name = self.get_collection()
        role_name = self.get_role_fq()
        if plugin_name == "include_role" or plugin_name == "import_role":
            collection = ANSIBLE_BUILTIN
            plugin_type = "module"
        elif self.is_local_plugin(plugin_name):
            collection = LOCAL
            plugin_type = node2plugin_type(plugin_type)
            logging.debug(
                f"\tplugin {plugin_name}:{plugin_type} at {relpth}:{lineno} is local to the collection/role"
            )
        elif self.templar.is_template(plugin_name):
            logging.warning(
                f"Unable to find plugin from template [{plugin_name}] at {relpth}:{lineno}"
            )
            return
        else:
            collection, plugin_type = self.get_plugin_collection(
                plugin_name,
                plugin_type,
            )
        if (
            collection != "UNKNOWN"
            and collection != "macro"
            and collection != LOCAL
            and not is_builtin_collection(collection)
            and not self.is_dependency(collection)
        ):
            self.errors.append(
                f"collection {collection} is not declared as a dependency for plugin {plugin_name} at {relpth}:{lineno}"
            )
        if plugin_name.startswith("ansible.builtin."):
            plugin_name = plugin_name.replace("ansible.builtin.", "")
        self.plugins.append(
            PluginItem(
                collection,
                plugin_name,
                plugin_type,
                collection_name,
                role_name,
                str(relpth),
                lineno,
                self.in_tests(),
            )
        )

    def add_bare_numeric_op(self, varname, opname, value, lineno):
        pathname = self.pathname
        if pathname is None:
            pathname = self.role_pathname
        pth = Path(pathname)
        fpth = Path(self.filename)
        relpth = str(fpth.relative_to(pth))
        collection_name = self.get_collection()
        role_name = self.get_role_fq()
        self.numeric_ops.append(
            NumericOpItem(
                collection_name,
                role_name,
                varname,
                opname,
                value,
                str(relpth),
                lineno,
                self.in_tests(),
            )
        )

    def get_lineno(self, other_lineno):
        if self.lineno:
            return self.lineno
        else:
            return other_lineno

    def get_plugin_collection(self, plugin, plugintype):
        """Find the collection that the plugin comes from.  Some plugins
        may come from jinja2 e.g. builtin filters and tests.  The plugintype
        field specifies the plugin type - "module" means an Ansible module,
        or one of the jinja2 types like jinja2.nodes.Filter.  If the plugintype
        is an ambiguous type like jinja2.nodes.Call, this function will first
        look for filters, then tests, then lookups."""
        collection = None
        convert_it = False
        if plugintype == "module":
            ctx = module_loader.find_plugin_with_context(plugin)
            collection = ctx.plugin_resolved_collection
            if not collection:
                collection = "UNKNOWN"
                self.errors.append(
                    f"{self.filename}:{self.lineno}:module plugin named {plugin} not found"
                )

            return (collection, "module")
        else:
            if plugintype in [jinja2.nodes.Filter, jinja2.nodes.Call]:
                if plugin in jinja2.defaults.DEFAULT_NAMESPACE:
                    collection = "jinja2.defaults"
                elif plugin in jinja2.filters.FILTERS:
                    collection = "jinja2.filters"
                else:
                    ctx = filter_loader.find_plugin_with_context(plugin)
                    collection = ctx.plugin_resolved_collection
                    if not collection and plugin in self.templar.environment.filters:
                        collection = self.templar.environment.filters[plugin].__module__
                        convert_it = True
                    if not collection and plugintype == jinja2.nodes.Filter:
                        collection = "UNKNOWN"
                        self.errors.append(
                            f"{self.filename}:{self.lineno}:filter plugin named {plugin} not found"
                        )
                if collection:
                    returntype = "filter"
            if not collection and plugintype in [jinja2.nodes.Test, jinja2.nodes.Call]:
                if plugin in jinja2.tests.TESTS:
                    collection = "jinja2.tests"
                else:
                    ctx = test_loader.find_plugin_with_context(plugin)
                    collection = ctx.plugin_resolved_collection
                    if not collection and plugin in self.templar.environment.tests:
                        collection = self.templar.environment.tests[plugin].__module__
                        convert_it = True
                    if not collection and plugintype == jinja2.nodes.Test:
                        self.errors.append(
                            f"{self.filename}:{self.lineno}:test plugin named {plugin} not found"
                        )
                        return ("UNKNOWN", "test")
                if collection:
                    returntype = "test"
            if not collection and plugintype == jinja2.nodes.Call:
                ctx = lookup_loader.find_plugin_with_context(plugin)
                if ctx.plugin_resolved_collection:
                    collection = ctx.plugin_resolved_collection
                    returntype = "lookup"
                elif is_builtin(plugin):
                    collection = ANSIBLE_BUILTIN
                    returntype = "lookup"
            if not collection and plugin in jinja2_macros:
                collection = "macro"
                returntype = "macro"
        if not collection:
            collection = "UNKNOWN"
            returntype = "UNKNOWN"
            self.errors.append(
                f"{self.filename}:{self.lineno}:plugin named {plugin} not found"
            )
        # convert collection to namespace.name format if in python module format
        if convert_it:
            if collection == "functools":
                collection = ANSIBLE_BUILTIN
            elif collection == "genericpath":
                collection = ANSIBLE_BUILTIN
            elif collection == "json":
                collection = ANSIBLE_BUILTIN
            elif collection == "ansible.template":
                collection = ANSIBLE_BUILTIN
            elif collection == "itertools":
                collection = ANSIBLE_BUILTIN
            elif collection.startswith("ansible_collections.ansible.builtin"):
                collection = ANSIBLE_BUILTIN
            elif collection.startswith("ansible.plugins."):
                collection = ANSIBLE_BUILTIN
            elif collection == "posixpath":
                collection = ANSIBLE_BUILTIN
        return (collection, returntype)

    def add_dependencies(self):
        for dep in self.manifest_json.get("dependencies", {}):
            if self.in_tests():
                self.test_dependencies[0].add(dep)
            else:
                self.dependencies[0].add(dep)
        for dep in self.galaxy_yml.get("dependencies", {}):
            if self.in_tests():
                self.test_dependencies[0].add(dep)
            else:
                self.dependencies[0].add(dep)
        for dep in self.role_reqs.get("collections", []):
            if isinstance(dep, dict):
                self.dependencies[0].add(dep["name"])
            else:
                self.dependencies[0].add(dep)
        for dep in self.role_test_reqs.get("collections", []):
            if isinstance(dep, dict):
                self.test_dependencies[0].add(dep["name"])
            else:
                self.test_dependencies[0].add(dep)

    def is_dependency(self, coll_name):
        for dep_set in self.dependencies:
            if coll_name in dep_set:
                return True
        if self.in_tests():
            for dep_set in self.test_dependencies:
                if coll_name in dep_set:
                    return True
        return False


def usage():
    return f"""
    You must create an environment (e.g. python venv or VM) which uses
    ansible 4.x and jinja2.7 e.g.
      python -mvenv .venv
      . .venv/bin/activate
      pip install 'ansible==4.*' 'jinja2==2.7.*'
    Then run this script using that environment.
    Each argument is the name of a directory containing a role, a collection,
    a 'roles' directory containing multiple roles, or an 'ansible_collections'
    directory containing multiple collections.  Examples:
    {sys.argv[0]} ~/linux-system-roles/network
    {sys.argv[0]} /usr/share/ansible/roles
    {sys.argv[0]} ~/.ansible/collections/ansible_collections
    {sys.argv[0]} .
    You can mix and match these on the command line.
    The output will be a list of ansible and jinja built-in plugins used.
    The usage is broken down into plugins used at runtime, and plugins used
    only during testing.  Following the list of built-in plugins, each
    non built-in plugin will be listed, followed by the roles in which they
    are used (or other non-role files e.g. collection playbooks, tests), followed
    by the file in which the plugin is used, and the number of lines in the file
    where the plugin is used.
    The '--details' flag will print every file and line number where the plugin
    is used.  NOTE: The line number reported is the line number where the task
    begins, which may not be where the usage of the plugin is.
    """


def fqcn_is_wrong(check_fqcn, item):
    return (
        check_fqcn == "all"
        or (check_fqcn == "modules" and item.type == "module")
        or (check_fqcn == "plugins" and item.type != "module")
    ) and not item.has_correct_fqcn()


def main():
    parser = argparse.ArgumentParser(add_help=True, usage=usage())
    parser.add_argument(
        "paths",
        type=str,
        nargs="+",
        help="Ansible role or collection path.",
    )
    parser.add_argument(
        "--details",
        default=False,
        action="store_true",
        help="Show every file and line number where the plugin is used.",
    )
    parser.add_argument(
        "--check-fqcn",
        choices=["plugins", "modules", "all"],
        default="",
        help="Look for non-builtin plugins/modules that are not in FQCN format and error if found.",
    )
    args = parser.parse_args()
    all_plugins = []
    all_numeric_ops = []
    testing_plugins = {}
    runtime_plugins = {}
    testing_num_ops = []
    runtime_num_ops = []
    ctx = SearchCtx()
    errors = []
    for pth in args.paths:
        process_path(pth, ctx)
        all_plugins.extend(ctx.plugins)
        all_numeric_ops.extend(ctx.numeric_ops)
        errors.extend(ctx.errors)
        ctx.reset()
    for item in all_numeric_ops:
        if item.is_test:
            testing_num_ops.append(item)
        else:
            runtime_num_ops.append(item)
    for item in all_plugins:
        if item.type == "macro":
            continue
        key = item.collection + "." + item.name + ":" + item.type
        if item.is_test:
            hsh = testing_plugins
        else:
            hsh = runtime_plugins
        subitem = hsh.setdefault(key, {"roles": {}, "collections": {}})
        subitem["name"] = item.name
        subitem["type"] = item.type
        subitem["collection"] = item.collection
        location = ""
        if item.used_in_collection:
            location = item.used_in_collection
        if item.used_in_role:
            if location:
                location += "."
            location += item.used_in_role
        if item.used_in_role:
            location_item = subitem["roles"].setdefault(location, {})
        elif item.used_in_collection:
            location_item = subitem["collections"].setdefault(location, {})
        location_item.setdefault(item.relpth, []).append(item.lineno)
        if (
            args.check_fqcn
            and not is_builtin_collection(key)
            and fqcn_is_wrong(args.check_fqcn, item)
        ):
            errors.append(
                f"ERROR: not FQCN: {item.orig_name} at {item.relpth}:{item.lineno}"
            )

    builtin_collections = COLLECTION_BUILTINS
    builtin_collections.add(LOCAL)
    for hsh in [runtime_plugins, testing_plugins]:
        if hsh == runtime_plugins:
            desc = "at runtime"
        else:
            desc = "in testing"
        for collection in builtin_collections:
            for plugintype in ["module", "filter", "test", "lookup"]:
                thelist = [
                    xx["name"]
                    for xx in hsh.values()
                    if collection_match(collection, xx["collection"])
                    and xx["type"] == plugintype
                ]
                if thelist:
                    print(f"The following {collection} {plugintype}s are used {desc}:")
                    print(f"{' '.join(sorted(thelist))}")
        if len(hsh) > 0:
            print(f"\nThe following additional plugins are used {desc}:")
        for key in sorted(hsh):
            if is_builtin_collection(key):
                continue
            item = hsh[key]
            if len(item["roles"].keys()):
                print(f"{item['collection']}.{item['name']} type: {item['type']}")
            for role in sorted(item["roles"].keys()):
                print(f"\trole: {role}")
                location_item = item["roles"][role]
                for relpth in sorted(location_item.keys()):
                    if args.details:
                        for lineno in location_item[relpth]:
                            print(f"\t\t{relpth}:{lineno}")
                    else:
                        print(f"\t\tfile: {relpth} lines: {len(location_item[relpth])}")
            for collection in sorted(item["collections"].keys()):
                print(f"\tcollection: {collection}")
                location_item = item["collections"][collection]
                for relpth in sorted(location_item.keys()):
                    if args.details:
                        for lineno in location_item[relpth]:
                            print(f"\t\t{relpth}:{lineno}")
                    else:
                        print(f"\t\tfile: {relpth} lines: {len(location_item[relpth])}")
    print("\n")
    for lst, desc in [(runtime_num_ops, "at runtime"), (testing_num_ops, "in testing")]:
        if not lst:
            continue
        if args.details:
            print(
                f"ERROR: The following numeric operations found {desc} need int or float cast filters:"
            )
        for item in lst:
            if args.details:
                print(
                    f"[{item.varname}] [{item.opname}] [{item.value}] at {item.relpth}:{item.lineno}"
                )
            errors.append(item)
        print("\n")

    print(f"Found {len(errors)} errors")
    for msg in errors:
        print(msg)
    return len(errors)


if __name__ == "__main__":
    sys.exit(main())
