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
# COLLECTION_SRC_PATH=/path/to/linux-system-roles \
# COLLECTION_DEST_PATH=/path/to/collections \
# COLLECTION_NAMESPACE=mynamespace \
# COLLECTION_NAME=myname \
# lsr-role2collection.py --role ROLE_NAME
#   ROLE_NAME role must exist in COLLECTION_SRC_PATH
#   Converted collections are placed in COLLECTION_DEST_PATH/ansible_collections/COLLECTION_NAMESPACE/COLLECTION_NAME

import argparse
import errno
import logging
import os
import re
import fnmatch
import sys
import textwrap
from shutil import copytree, copy2, ignore_patterns, rmtree
from ansible_role_parser import LSRFileTransformerBase, LSRTransformer, get_role_modules

from pathlib import Path

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
    "DCO",
)

TOX = (
    ".ansible-lint",
    ".flake8",
    ".pre-commit-config.yaml",
    ".pydocstyle",
    ".travis",
    ".travis.yml",
    ".yamllint_defaults.yml",
    ".yamllint.yml",
    "ansible_pytest_extra_requirements.txt",
    "custom_requirements.txt",
    "molecule",
    "molecule_extra_requirements.txt",
    "pylintrc",
    "pylint_extra_requirements.txt",
    "pytest_extra_requirements.txt",
    "tox.ini",
    "tuned_requirements.txt",
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
)

ALL_DIRS = ROLE_DIRS + PLUGINS + TESTS + DOCS + DO_NOT_COPY

IMPORT_RE = re.compile(br"(\bimport) (ansible\.module_utils\.)(\S+)(.*)$", flags=re.M)
FROM_RE = re.compile(
    br"(\bfrom) (ansible\.module_utils\.?)(\S+)? import (\(*(?:\n|\r\n)?)(.+)$",
    flags=re.M,
)

if os.environ.get("LSR_DEBUG") == "true":
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.getLogger().setLevel(logging.ERROR)


class LSRFileTransformer(LSRFileTransformerBase):
    """Do the role file transforms - fix role names, add FQCN
    to module names, etc."""

    def task_cb(self, a_task, ru_task, module_name, module_args, delegate_to):
        """do something with a task item"""
        if module_name == "include_role" or module_name == "import_role":
            rolename = ru_task[module_name]["name"]
            lsr_rolename = "linux-system-roles." + self.rolename
            logging.debug(f"\ttask role {rolename}")
            if rolename == self.rolename or rolename == lsr_rolename:
                ru_task[module_name]["name"] = prefix + self.rolename
            elif rolename.startswith("{{ role_path }}"):
                match = re.match(r"{{ role_path }}/roles/([\w\d\.]+)", rolename)
                if match.group(1).startswith(subrole_prefix):
                    ru_task[module_name]["name"] = prefix + match.group(1).replace(
                        ".", replace_dot
                    )
                else:
                    ru_task[module_name]["name"] = (
                        prefix
                        + subrole_prefix
                        + match.group(1).replace(".", replace_dot)
                    )
        elif module_name in role_modules:
            logging.debug(f"\ttask role module {module_name}")
            # assumes ru_task is an orderreddict
            idx = tuple(ru_task).index(module_name)
            val = ru_task.pop(module_name)
            ru_task.insert(idx, prefix + module_name, val)

    def other_cb(self, a_item, ru_item):
        """do something with the other non-task information in an item
        this is where you will get e.g. the `roles` keyword from a play"""
        self.change_roles(ru_item, "roles")

    def vars_cb(self, a_item, ru_item):
        """handle vars of Ansible item, or vars from a vars file"""
        for var in a_item.get("vars", []):
            logging.debug(f"\tvar = {var}")
        return

    def meta_cb(self, a_item, ru_item):
        """hand a meta/main.yml style file"""
        self.change_roles(ru_item, "dependencies")

    def comp_rolenames(self, name0, name1):
        if name0 == name1:
            return True
        else:
            core0 = re.sub("[_\\.]", "", name0)
            core1 = re.sub("[_\\.]", "", name1)
            if core0 == core1:
                return True
            else:
                return False

    def change_roles(self, ru_item, roles_kw):
        """ru_item is an item which may contain a roles or dependencies
        specifier - the roles_kw is either "roles" or "dependencies"
        """
        lsr_rolename = "linux-system-roles." + self.rolename
        for idx, role in enumerate(ru_item.get(roles_kw, [])):
            changed = False
            if isinstance(role, dict):
                if "name" in role:
                    key = "name"
                else:
                    key = "role"
                if role[key] == lsr_rolename or self.comp_rolenames(
                    role[key], self.rolename
                ):
                    role[key] = prefix + self.rolename
                    changed = True
            elif role == lsr_rolename or self.comp_rolenames(role, self.rolename):
                role = prefix + self.rolename
                changed = True
            if changed:
                ru_item[roles_kw][idx] = role

    def write(self):
        """assume we are operating on files already copied to the dest dir,
        so write file in-place"""
        self.outputfile = self.filepath
        super().write()


# Once python 3.8 is available in Travis CI,
# replace lsr_copytree with shutil.copytree with dirs_exist_ok=True.
def lsr_copytree(src, dest, symlinks=False, dirs_exist_ok=False, ignore=None):
    ipatterns = ignore_patterns(ignore)
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
                            copytree(
                                subsrc, subdest, symlinks=symlinks, ignore=ipatterns
                            )
                        else:
                            copy2(subsrc, subdest, follow_symlinks=symlinks)
                else:
                    if subsrc.is_dir():
                        if subdest.exists() and dirs_exist_ok:
                            rmtree(subdest)
                        copytree(subsrc, subdest, symlinks=symlinks)
                    else:
                        copy2(subsrc, subdest, follow_symlinks=symlinks)
        elif ignore:
            dest.unlink()
            copytree(src, dest, ignore=ipatterns, symlinks=symlinks)
        else:
            dest.unlink()
            copytree(src, dest, symlinks=symlinks)
    elif ignore:
        copytree(src, dest, ignore=ipatterns, symlinks=symlinks)
    else:
        copytree(src, dest, symlinks=symlinks)


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
                with open(filepath) as f:
                    s = f.read()
                s = re.sub(find, replace, s)
                with open(filepath, "w") as f:
                    f.write(s)


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
    default=os.environ.get("COLLECTION_NAME", "system_roles"),
    help="Collection name; default to system_roles",
)
parser.add_argument(
    "--dest-path",
    type=Path,
    default=os.environ.get("COLLECTION_DEST_PATH", HOME + "/.ansible/collections"),
    help="Path to parent of collection where role should be migrated",
)
parser.add_argument(
    "--src-path",
    type=Path,
    default=os.environ.get("COLLECTION_SRC_PATH", HOME + "/linux-system-roles"),
    help="Path to linux-system-roles",
)
parser.add_argument(
    "--role",
    type=str,
    default=os.environ.get("COLLECTION_ROLE"),
    help="Role to convert to collection",
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
args, unknown = parser.parse_known_args()

role = args.role
if not role:
    parser.print_help()
    print("Message: role is not specified.")
    os._exit(errno.EINVAL)

namespace = args.namespace
collection = args.collection
prefix = namespace + "." + collection + "."
top_dest_path = args.dest_path.resolve()
replace_dot = args.replace_dot
subrole_prefix = args.subrole_prefix

dest_path = Path.joinpath(
    top_dest_path, "ansible_collections/" + namespace + "/" + collection
)
os.makedirs(dest_path, exist_ok=True)

roles_dir = dest_path / "roles"
tests_dir = dest_path / "tests"
plugin_dir = dest_path / "plugins"
modules_dir = plugin_dir / "modules"
module_utils_dir = plugin_dir / "module_utils"
docs_dir = dest_path / "docs"


def copy_tree_with_replace(
    src_path, dest_path, prefix, role, TUPLE, isrole=True, ignoreme=None, symlinks=True
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
                dest = roles_dir / role / dirname
            else:
                dest = dest_path / dirname / role
            print(f"Copying role {src} to {dest}")
            if ignoreme:
                copytree(
                    src,
                    dest,
                    ignore=ignore_patterns(ignoreme),
                    symlinks=symlinks,
                )
            else:
                copytree(src, dest, symlinks=symlinks)
            lsrxfrm = LSRTransformer(dest, False, role, LSRFileTransformer)
            lsrxfrm.run()


# Run with --role ROLE
src_path = args.src_path.resolve() / role
if not src_path.exists():
    print(f"Error: {src_path} does not exists.")
    sys.exit(errno.ENOENT)
_extras = set(os.listdir(src_path)).difference(ALL_DIRS)
try:
    _extras.remove(".git")
except KeyError:
    pass
extras = [src_path / e for e in _extras]

# get role modules - will need to find and convert these to use FQCN
role_modules = get_role_modules(src_path)

# Role - copy subdirectories, tasks, defaults, vars, etc., in the system role to
# DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE.
copy_tree_with_replace(src_path, dest_path, prefix, role, ROLE_DIRS)

# ==============================================================================


def cleanup_symlinks(path, role):
    """
    Clean up symlinks in tests/roles
    - Remove symlinks.
    - If linux-system-roles.rolename is an empty dir, rmdir it.
    """
    if path.exists():
        nodes = sorted(list(path.rglob("*")), reverse=True)
        for node in nodes:
            if node.is_symlink() and r"linux-system-roles." + role == node.name:
                node.unlink()
            elif (
                node.is_dir()
                and r"linux-system-roles." + role == node.name
                and not any(node.iterdir())
            ):
                node.rmdir()
        roles_dir = path / "roles"
        if roles_dir.exists() and not any(roles_dir.iterdir()):
            roles_dir.rmdir()


copy_tree_with_replace(
    src_path, dest_path, prefix, role, TESTS, isrole=False, ignoreme="artifacts"
)

# remove symlinks in the tests/role, then updating the rolename to the collection format
cleanup_symlinks(tests_dir / role, role)

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
        s = textwrap.dedent(
            """\
            # {0} {1} collections

            {2}
            <!--ts-->
              * [{3}](roles/{4})
            <!--te-->
            """
        ).format(namespace, collection, comment, title, rolename + "/" + filename)
        with open(main_doc, "w") as f:
            f.write(s)
    else:
        with open(main_doc) as f:
            s = f.read()
        if comment not in s:
            text = (
                s
                + textwrap.dedent(
                    """\

                {2}
                <!--ts-->
                  * [{3}](roles/{4})
                <!--te-->
                """
                ).format(
                    namespace, collection, comment, title, rolename + "/" + filename
                )
            )
        else:
            find = r"({0}\n<!--ts-->\n)(( |\*|\w|\[|\]|\(|\)|\.|/|-|\n|\r)+)".format(
                comment
            )
            replace = r"\1\2  * [{0}](roles/{1})\n".format(
                title, rolename + "/" + filename
            )
            text = re.sub(find, replace, s, flags=re.M)
        with open(main_doc, "w") as f:
            f.write(text)


# Copy docs, design_docs, and examples to
# DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/docs/ROLE.
# Copy README.md to DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE.
# Generate a top level README.md which contains links to roles/ROLE/README.md.
def process_readme(src_path, filename, rolename, original=None, issubrole=False):
    """
    Copy src_path/filename to dest_path/docs/rolename.
    filename could be README.md, README-something.md, or something.md.
    Create a primary README.md in dest_path, which points to dest_path/docs/rolename/filename
    with the title rolename or rolename-something.
    """
    src = src_path / filename
    dest = roles_dir / rolename / filename
    # copy
    print(f"Copying doc {filename} to {dest}")
    copy2(src, dest, follow_symlinks=False)
    dest = roles_dir / rolename
    file_patterns = ["*.md"]
    file_replace(
        dest, "linux-system-roles." + rolename, prefix + rolename, file_patterns
    )
    if original:
        file_replace(dest, original, prefix + rolename, file_patterns)
    if issubrole:
        comment = "## Private Roles"
    else:
        comment = "## Supported Linux System Roles"
    update_readme(src_path, filename, rolename, comment, issubrole)


dest = dest_path / "docs" / role
for doc in DOCS:
    src = src_path / doc
    if src.is_dir():
        print(f"Copying docs {src} to {dest}")
        lsr_copytree(
            src,
            dest,
            symlinks=False,
            ignore="roles",
            dirs_exist_ok=True,
        )
        if doc == "examples":
            lsrxfrm = LSRTransformer(dest, False, role, LSRFileTransformer)
            lsrxfrm.run()
    elif src.is_file():
        process_readme(src_path, doc, role)

# Remove symlinks in the docs/role (e.g., in the examples).
# Update the rolename to the collection format as done in the tests.
cleanup_symlinks(dest, role)

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
                print(f"Copying plugin {sr} to {dest}")
                lsr_copytree(sr, dest)
            else:
                # Otherwise, copy it to the plugins/plugin_name/ROLE
                dest = plugin_dir / plugin_name / role
                dest.mkdir(parents=True, exist_ok=True)
                print(f"Copying plugin {sr} to {dest}")
                copy2(sr, dest, follow_symlinks=False)
    else:
        dest = plugin_dir / plugin_name
        print(f"Copying plugin {src} to {dest}")
        lsr_copytree(src, dest)


def gather_module_utils_parts(module_utils_dir):
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


def import_replace(match):
    """
    If 'import ansible.module_utils.something ...' matches,
    'import ansible_collections.NAMESPACE.COLLECTION.plugins.module_utils.something ...'
    is returned to replace.
    """
    parts = match.group(3).split(b".")
    match_group3 = match.group(3)
    src_module_path = src_path / "module_utils" / match.group(3).decode("utf-8")
    dest_module_path0 = module_utils_dir / match.group(3).decode("utf-8")
    dest_module_path1 = module_utils_dir / role
    if len(parts) == 1:
        if not src_module_path.is_dir() and (
            dest_module_path0.is_dir() or dest_module_path1.is_dir()
        ):
            match_group3 = (role + "." + match.group(3).decode("utf-8")).encode()
            parts = match_group3.split(b".")
    if parts in module_utils:
        if match.group(1) == b"import" and match.group(4) == b"":
            additional_rewrites.append(parts)
            if src_module_path.exists() or Path(str(src_module_path + ".py")).exists():
                return b"import ansible_collections.%s.%s.plugins.module_utils.%s" % (
                    bytes(namespace, "utf-8"),
                    bytes(collection, "utf-8"),
                    match_group3,
                )
            else:
                return (
                    b"import ansible_collections.%s.%s.plugins.module_utils.%s as %s"
                    % (
                        bytes(namespace, "utf-8"),
                        bytes(collection, "utf-8"),
                        match_group3,
                        parts[-1],
                    )
                )
        return b"%s ansible_collections.%s.%s.plugins.module_utils.%s%s" % (
            match.group(1),
            bytes(namespace, "utf-8"),
            bytes(collection, "utf-8"),
            match_group3,
            match.group(4),
        )
    return match.group(0)


def get_candidates(parts3, parts5):
    from_file0 = module_utils_dir
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
        src_module_path = src_path / "module_utils" / match.group(3).decode("utf-8")
        dest_module_path0 = module_utils_dir / match.group(3).decode("utf-8")
        dest_module_path1 = module_utils_dir / role
        if not src_module_path.is_dir() and (
            dest_module_path0.is_dir() or dest_module_path1.is_dir()
        ):
            match_group3 = (role + "." + match.group(3).decode("utf-8")).encode()
            parts3 = match_group3.split(b".")
    if parts3 in module_utils:
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
                b"%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s"
                % (
                    match.group(1),
                    bytes(namespace, "utf-8"),
                    bytes(collection, "utf-8"),
                    match_group3,
                    match.group(4),
                    match.group(5),
                )
            )
        else:
            return b"%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s" % (
                match.group(1),
                bytes(namespace, "utf-8"),
                bytes(collection, "utf-8"),
                match_group3,
                match.group(4),
                match.group(5),
            )
    if parts5 in module_utils:
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
                    b"%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s"
                    % (
                        match.group(1),
                        bytes(namespace, "utf-8"),
                        bytes(collection, "utf-8"),
                        match.group(3),
                        match.group(4),
                        match.group(5),
                    )
                )
            else:
                return b"%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s" % (
                    match.group(1),
                    bytes(namespace, "utf-8"),
                    bytes(collection, "utf-8"),
                    match.group(3),
                    match.group(4),
                    match.group(5),
                )
        if (
            from_file0.is_file()
            or from_file1.is_file()
            or lfrom_file0.is_file()
            or lfrom_file1.is_file()
        ):
            return b"%s ansible_collections.%s.%s.plugins.module_utils import %s%s" % (
                match.group(1),
                bytes(namespace, "utf-8"),
                bytes(collection, "utf-8"),
                match.group(4),
                match.group(5),
            )
        else:
            return b"%s ansible_collections.%s.%s.plugins.module_utils.__init__ import %s%s" % (
                match.group(1),
                bytes(namespace, "utf-8"),
                bytes(collection, "utf-8"),
                match.group(4),
                match.group(5),
            )
    return match.group(0)


# Update the python codes which import modules in plugins/{modules,modules_dir}.
additional_rewrites = []
module_utils = []
gather_module_utils_parts(module_utils_dir)
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
                        re.escape(br"ansible.module_utils.%s" % b".".join(rewrite))
                    )
                    new_text = pattern.sub(rewrite[-1], new_text)

                if text != new_text:
                    print("Rewriting imports for {}".format(full_path))
                    full_path.write_bytes(new_text)
                    additional_rewrites[:] = []

# ==============================================================================


def add_rolename(filename, rolename):
    """
    A file with an extension, e.g., README.md is converted to README-rolename.md
    A file with no extension, e.g., LICENSE is to LICENSE-rolename
    """
    if filename.find(".", 1) > 0:
        with_rolename = re.sub(
            r"([\w\d_\.]*)(\.)([\w\d]*)",
            r"\1" + "-" + rolename + r"\2" + r"\3",
            filename,
        )
    else:
        with_rolename = filename + "-" + rolename
    return with_rolename


# Before handling extra files, clean up tox/travis files.
for tox in TOX:
    tox_obj = dest_path / tox
    if tox_obj.is_dir():
        rmtree(tox_obj)
    elif tox_obj.exists():
        tox_obj.unlink()
# Extra files and directories including the sub-roles
for extra in extras:
    if extra.name.endswith(".md"):
        # E.g., contributing.md, README-devel.md and README-testing.md
        process_readme(extra.parent, extra.name, role)
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
                copy_tree_with_replace(sr, dest_path, prefix, dr, ROLE_DIRS)
                # copy tests dir to dest_path/"tests"
                copy_tree_with_replace(
                    sr, dest_path, prefix, dr, TESTS, isrole=False, ignoreme="artifacts"
                )
                # remove symlinks in the tests/role, then updating the rolename to the collection format
                cleanup_symlinks(tests_dir / dr, dr)
                # copy README.md to dest_path/roles/sr.name
                readme = sr / "README.md"
                if readme.is_file():
                    process_readme(
                        sr, "README.md", dr, original=sr.name, issubrole=True
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
        # Other extra directories are copied to the collection dir as they are.
        else:
            dest = dest_path / extra.name
            print(f"Copying extra {extra} to {dest}")
            copytree(extra, dest)
    # Other extra files.
    else:
        if extra.name.endswith(".yml") and "playbook" in extra.name:
            # some-playbook.yml is copied to playbooks/role dir.
            dest = dest_path / "playbooks" / role
            dest.mkdir(parents=True, exist_ok=True)
        elif extra.name in TOX:
            # If the file in the TOX tuple, it is copied to the collection dir as it is.
            dest = dest_path / extra.name
        else:
            # If the extra file 'filename' has no extension, it is copied to the collection dir as
            # 'filename-ROLE'. If the extra file is 'filename.ext', it is copied to 'filename-ROLE.ext'.
            dest = dest_path / add_rolename(extra.name, role)
        print(f"Copying extra {extra} to {dest}")
        copy2(extra, dest, follow_symlinks=False)

default_collections_paths = "~/.ansible/collections:/usr/share/ansible/collections"
default_collections_paths_list = list(
    map(os.path.expanduser, default_collections_paths.split(":"))
)
current_dest = os.path.expanduser(str(top_dest_path))
# top_dest_path is not in the default collections path.
# suggest to run ansible-playbook with ANSIBLE_COLLECTIONS_PATHS env var.
if current_dest not in default_collections_paths_list:
    ansible_collections_paths = current_dest + ":" + default_collections_paths
    print(
        f"Run ansible-playbook with environment variable ANSIBLE_COLLECTIONS_PATHS={ansible_collections_paths}"
    )
