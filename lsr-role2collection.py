#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) 2020 Matt Martz <matt@sivel.net>
# GNU General Public License v3.0+
#     (see https://www.gnu.org/licenses/gpl-3.0.txt)

# Usage:
# lsr-role2collection.py [--namespace NAMESPACE]
#                        [--collection COLLECTION]
#                        --src-path SRC_PATH
#                        --dest-path DEST_PATH
#                        --role ROLE | --molecule
#                        (if --molecule is set, SRC_PATH/template is expected)
#                        [--replace-dot STR]
#                        [-h]

import argparse
import os
import re
import fnmatch
from shutil import copytree, copy2, ignore_patterns, rmtree
import ansible_role_parser

from pathlib import Path

ROLE_DIRS = (
    'defaults',
    'files',
    'handlers',
    'meta',
    'tasks',
    'templates',
    'vars',
)

PLUGINS = (
    'action_plugins',
    'become_plugins',
    'cache_plugins',
    'callback_plugins',
    'cliconf_plugins',
    'connection_plugins',
    'doc_fragments',
    'filter_plugins',
    'httpapi_plugins',
    'inventory_plugins',
    'library',
    'lookup_plugins',
    'module_utils',
    'netconf_plugins',
    'shell_plugins',
    'strategy_plugins',
    'terminal_plugins',
    'test_plugins',
    'vars_plugins'
)

TESTS = (
    'tests',
)

DOCS = (
    'docs',
    'design_docs',
    'examples',
    'README.md',
    'DCO',
)

MOLECULE = (
    '.ansible-lint',
    'custom_requirements.txt',
    'molecule',
    'molecule_extra_requirements.txt',
    'tox.ini',
    '.travis',
    '.travis.yml',
    '.yamllint_defaults.yml',
    '.yamllint.yml',
)

DO_NOT_COPY = (
    '.github',
    '.gitignore',
    '.lgtm.yml',
    '.tox',
    '.venv',
    'ansible_pytest_extra_requirements.txt',
    'artifacts',
    'pylint_extra_requirements.txt',
    'pylintrc',
    'pytest_extra_requirements.txt',
    'run_pylint.py',
    'scripts',
    'semaphore',
    'standard-inventory-qcow2',
    'tuned_requirements.txt',
)

# Do not add -ROLENAME to the copied extra file.
EXTRA_NO_ROLENAME = (
)

# Do not add a link in this tuple to the main README.md.
NO_README_LINK = (
    'rsyslog',
)

ALL_DIRS = ROLE_DIRS + PLUGINS + TESTS + DOCS + MOLECULE + DO_NOT_COPY

IMPORT_RE = re.compile(
    br'(\bimport) (ansible\.module_utils\.)(\S+)(.*)$',
    flags=re.M
)
FROM_RE = re.compile(
    br'(\bfrom) (ansible\.module_utils\.?)(\S+)? import (\(*(?:\n|\r\n)?)(.+)$',
    flags=re.M
)
FROM2DOTS_RE = re.compile(
    br'(\bfrom) \.\.(module_utils\.)(\S+) import (.+)$',
    flags=re.M
)


def dir_to_plugin(v):
    if v[-8:] == '_plugins':
        return v[:-8]
    elif v == 'library':
        return 'modules'
    return v


# python lsr-role2collection.py /src_path/linux-system-roles/logging /dest_path/ansible_collections/fedora/system_roles
# positional arguments:
#  ROLE_PATH        Path to a role to migrate
#  COLLECTION_PATH  Path to collection where role should be migrated
parser = argparse.ArgumentParser()
parser.add_argument(
    '--namespace',
    type=str,
    default=os.environ.get("COLLECTION_NAMESPACE", "fedora"),
    help='Collection namespace; default to fedora',
)
parser.add_argument(
    '--collection',
    type=str,
    default=os.environ.get("COLLECTION_NAME", "system_roles"),
    help='Collection name; default to system_roles',
)
parser.add_argument(
    '--dest-path',
    type=Path,
    default=os.environ.get("COLLECTION_DEST_PATH"),
    help='Path to parent of collection where role should be migrated',
)
parser.add_argument(
    '--src-path',
    type=Path,
    default=os.environ.get("COLLECTION_SRC_PATH"),
    help='Path to linux-system-role',
)
parser.add_argument(
    '--role',
    type=str,
    default=os.environ.get("COLLECTION_ROLE"),
    help='Role to convert to collection',
)
parser.add_argument(
    '--molecule',
    action='store_true',
    default=os.environ.get("COLLECTION_MOLECULE", False),
    help='If set, molecule is copied from SRC_PATH/template, which must exist. In that case "--role ROLE" is ignored.'
)
parser.add_argument(
    '--replace-dot',
    type=str,
    default=os.environ.get("COLLECTION_REPLACE_DOT", "_"),
    help='If sub-role name contains dots, replace them with the given value; default to "_"',
)
args = parser.parse_args()

namespace = args.namespace
collection = args.collection
role = args.role
dest_path = args.dest_path.resolve()
output = Path.joinpath(dest_path, "ansible_collections/" + namespace + "/" + collection)
output.mkdir(parents=True, exist_ok=True)

# Copy molecule related files and directories from linux-system-roles/template.
if args.molecule:
    src_path = args.src_path.resolve() / 'template'
    if not src_path.exists():
        print(f'Error: {src_path} does not exists.')
        os._exit(errno.NOENT)
    for mol in MOLECULE:
        src = src_path / mol
        dest = output / mol
        print(f'Copying {src} to {dest}')
        if src.is_dir():
            copytree(
                src,
                dest,
                symlinks=True,
                dirs_exist_ok=True
            )
        elif src.exists():
            dest = output / mol
            copy2(
                src,
                dest,
                follow_symlinks=False
            )
            if mol == '.yamllint.yml':
                with open(dest) as f:
                    s = f.read()
                if not '\nrules:' in s:
                    s = s + '\nrules:'
                # disabling truthy
                m = re.match(r'([\w\d\s\.\'\|"/#:-]*\n)( *truthy: disable)', s, flags=re.M)
                if not (m and m.group(2)):
                    s = s + '\n  truthy: disable\n'
                # disabling line-length
                m = re.match(r'([\w\d\s\.\'\|"/#:-]*\n)( *line-length: disable)', s, flags=re.M)
                if not (m and m.group(2)):
                    s = s + '  line-length: disable\n'
                with open(dest, "w") as f:
                    f.write(s)
    os._exit(os.EX_OK)

# ==============================================================================

# Run with --role ROLE
src_path = args.src_path.resolve() / role
if not src_path.exists():
    print(f'Error: {src_path} does not exists.')
    sys.exit(errno.NOENT)
_extras = set(os.listdir(src_path)).difference(ALL_DIRS)
try:
    _extras.remove('.git')
except KeyError:
    pass
extras = [src_path / e for e in _extras]

# Role - copy subdirectories, tasks, defaults, vars, etc., in the system role to
# DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE.
for role_dir in ROLE_DIRS:
    src = src_path / role_dir
    if not src.is_dir():
        continue
    dest = output / 'roles' / role / role_dir
    print(f'Copying role {src} to {dest}')
    copytree(
        src,
        dest,
        symlinks=True,
        dirs_exist_ok=True
    )
    ansible_role_parser.parse_role(str(src))

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


# Replace "{{ role_path }}/roles/rolename" with "rolename" in role_dir.
find = "{{ role_path }}/roles/([\w\d]*['\"])"
replace = "\\1"
file_patterns = ['*.yml', '*.md']
file_replace(role_dir, find, replace, file_patterns)

# Replace "{{ role_path }}/roles/rolename/{tasks,vars,defaults}/main.yml" with
# "rolename/{tasks,vars,defaults}/main.yml" in role_dir.
find = "{{ role_path }}/roles/([\w\d\./]*)$"
replace = "\\1"
file_replace(role_dir, find, replace, file_patterns)

# ==============================================================================

# Tests - copy files and dirs in the tests to
# DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/tests/ROLE.
def copy_tests(src_path, role):
    for tests in TESTS:
        src = src_path / tests
        if src.is_dir():
            dest = output / tests / role
            print(f'Copying role {src} to {dest}')
            copytree(
                src,
                dest,
                ignore=ignore_patterns('artifacts'),
                symlinks=True,
                dirs_exist_ok=True
            )
        ansible_role_parser.parse_role(str(src))


# Adjust role names to the collections style.
def remove_or_reset_symlinks(path, role):
    """
    Clean up roles/linux-system-roles.rolename.
    - Remove symlinks.
    - If linux-system-roles.rolename is an empty dir, rmdir it.
    """
    nodes = sorted(list(path.rglob('*')), reverse=True)
    for node in nodes:
        if node.is_symlink():
            node.unlink()
        elif node.is_dir() and r'linux-system-roles.' + role == node.name and not any(node.iterdir()):
            node.rmdir()


def recursive_grep(path, find, file_patterns):
    """
    Check if a pattern `find` is found in the files that match
    `file_patterns` under `path`.
    """
    for root, dirs, files in os.walk(os.path.abspath(path)):
        for file_pattern in file_patterns:
            for filename in fnmatch.filter(files, file_pattern):
                filepath = os.path.join(root, filename)
                with open(filepath) as f:
                    s = f.read()
                if find in s:
                    return True
    return False


def replace_rolename_with_collection(path, namespace, collection, role):
    """
    Replace the roles or include_role values, ROLE or `linux-system-roles.ROLE`, are replaced
    with `NAMESPACE.COLLECTION.ROLE` in the given dir `path` recursively.
    """
    find = r"( *name: | *- name: | *- | *roletoinclude: | *role: | *- role: )(linux-system-roles\.{0}\b)".format(role, role)
    replace = r"\1" + namespace + "." + collection + "." + role
    file_patterns = ['*.yml', '*.md']
    file_replace(path, find, replace, file_patterns)


def symlink_n_rolename(path, namespace, collection, role):
    """
    Handle rolename issues in the test playbooks.
    """
    if path.exists():
        replace_rolename_with_collection(path, namespace, collection, role)
        remove_or_reset_symlinks(path, role)
        roles_dir = path / 'roles'
        if roles_dir.exists() and not any(roles_dir.iterdir()):
            roles_dir.rmdir()


# Create tests_defaults.yml in tests for the molecule test.
def add_to_tests_defaults(namespace, collection, role):
    tests_default = output / 'tests' / 'tests_default.yml'
    tests_default.parent.mkdir(parents=True, exist_ok=True)
    if tests_default.exists():
        with open(tests_default) as f:
            s = f.read()
        s = '{0}    - {1}.{2}.{3}\n'.format(s, namespace, collection, role)
        with open(tests_default, "w") as f:
            f.write(s)
    else:
        s = '---\n- name: Ensure that the role runs with default parameters\n  hosts: all\n  roles:\n    - {0}.{1}.{2}\n'.format(namespace, collection, role)
        with open(tests_default, "w") as f:
            f.write(s)

copy_tests(src_path, role)
# remove symlinks in the tests/role, then updating the rolename to the collection format
symlink_n_rolename(output / 'tests' / role, namespace, collection, role)
add_to_tests_defaults(namespace, collection, role)

# ==============================================================================

# Copy docs, design_docs, and examples to 
# DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/docs/ROLE.
# Copy README.md to DEST_PATH/ansible_collections/NAMESPACE/COLLECTION/roles/ROLE.
# Generate a top level README.md which contains links to roles/ROLE/README.md.
def process_readme(src_path, filename, rolename):
    """
    Copy src_path/filename to output/docs/rolename.
    filename could be README.md, README-something.md, or something.md.
    Create a primary README.md in output, which points to output/docs/rolename/filename
    with the title rolename or rolename-something.
    """
    src = src_path / filename
    dest = output / 'roles' / rolename / filename
    # copy
    print(f'Copying doc {filename} to {dest}')
    copy2(
        src,
        dest,
        follow_symlinks=False
    )
    if not rolename in NO_README_LINK and filename.startswith('README'):
        if filename == 'README.md':
            title = rolename
        elif filename.startswith('README-'):
            m = re.match('(README-)(.*)(\.md)', filename)
            title = rolename + '-' + m.group(2)
        main_doc = output / 'README.md'
        if not main_doc.exists():
            s = '# {0} {1} collections\n\n## Supported Linux System Roles\n<!--ts-->\n  * [{2}](roles/{3})\n<!--te-->'.format(namespace, collection, title, rolename + '/' + filename)
            with open(main_doc, "w") as f:
                f.write(s)
        else:
            with open(main_doc) as f:
                s = f.read()
            replace = '  * [{0}](roles/{1})\n<!--te-->'.format(title, rolename + '/' + filename)
            s = re.sub('<!--te-->', replace, s)
            with open(main_doc, "w") as f:
                f.write(s)


docs_path = output / Path('docs')
dest = docs_path / role
for doc in DOCS:
    src = src_path / doc
    if src.is_dir():
        print(f'Copying docs {src} to {dest}')
        copytree(
            src,
            dest,
            symlinks=False,
            ignore=ignore_patterns('roles'),
            dirs_exist_ok=True
        )
    elif src.is_file():
        process_readme(src_path, doc, role)

# Remove symlinks in the docs/role (e.g., in the examples).
# Update the rolename to the collection format as done in the tests.
docs_role_path = output / 'docs' / role
symlink_n_rolename(docs_role_path, namespace, collection, role)

# ==============================================================================

# Copy library, module_utils, plugins
# Library and plugins are copied to output/plugins
# If plugin is in SUBDIR (currently, just module_utils),
#   module_utils/*.py are to output/plugins/module_utils/ROLE/*.py
#   module_utils/subdir/*.py are to output/plugins/module_utils/subdir/*.py
SUBDIR = (
    'module_utils',
)
for plugin in PLUGINS:
    src = src_path / plugin
    plugin_name = dir_to_plugin(plugin)
    if not src.is_dir():
        continue
    if plugin in SUBDIR:
        for sr in src.iterdir():
            if sr.is_dir():
                # If src/sr is a directory, copy it to the dest
                dest = output / 'plugins' / plugin_name / sr.name
                print(f'Copying plugin {sr} to {dest}')
                copytree(
                    sr,
                    dest,
                    dirs_exist_ok=True
                )
            else:
                # Otherwise, copy it to the plugins/plugin_name/ROLE
                dest = output / 'plugins' / plugin_name / role
                dest.mkdir(parents=True, exist_ok=True)
                print(f'Copying plugin {sr} to {dest}')
                copy2(
                    sr,
                    dest,
                    follow_symlinks=False
                )
    else:
        dest = output / 'plugins' / plugin_name
        print(f'Copying plugin {src} to {dest}')
        copytree(
            src,
            dest,
            dirs_exist_ok=True
        )

additional_rewrites = []
module_utils = []
module_utils_dir = output / 'plugins' / 'module_utils'
if module_utils_dir.is_dir():
    for root, dirs, files in os.walk(module_utils_dir):
        for filename in files:
            if os.path.splitext(filename)[1] != '.py':
                continue
            full_path = (Path(root) / filename).relative_to(module_utils_dir)
            parts = bytes(full_path)[:-3].split(b'/')
            if parts[-1] == b'__init__':
                del parts[-1]
            module_utils.append(parts)


def import_replace(match):
    """
    If 'import ansible.module_utils.something ...' matches,
    'import ansible_collections.NAMESPACE.COLLECTION.plugins.module_utils.something ...'
    is returned to replace.
    """
    parts = match.group(3).split(b'.')
    if len(parts) == 1:
        match_group3 = (role + '.' + match.group(3).decode("utf-8")).encode()
        parts = match_group3.split(b'.')
    if parts in module_utils:
        if match.group(1) == b'import' and match.group(4) == b'':
            additional_rewrites.append(parts)
            return b'import ansible_collections.%s.%s.plugins.module_utils.%s as %s' % \
                (bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'), match_group3, parts[-1])
        return b'%s ansible_collections.%s.%s.plugins.module_utils.%s%s' % \
            (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
             match_group3, match.group(4))
    return match.group(0)


def get_candidates(parts3, parts5):
    from_file0 = module_utils_dir
    for p3 in parts3:
        from_file0 = from_file0 / p3.decode('utf-8')
    from_file1 = from_file0
    for p5 in parts5:
        from_file1 = from_file1 / p5.decode('utf-8').strip(', ')
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
        parts3 = match.group(3).split(b'.')
    except AttributeError:
        parts3 = []
    try:
        parts5 = match.group(5).split(b'.')
    except AttributeError:
        parts5 = []
    # parts3 (e.g., [b'ROLE', b'subdir', b'module']) matches one module_utils or
    # size of parts3 is 1 (e.g., [b'module']), in this case, module.py was moved to ROLE/module.py.
    # If latter, match.group(3) has to be converted to b'ROLE.module'.
    if len(parts3) == 1:
        match_group3 = (role + '.' + match.group(3).decode("utf-8")).encode()
        parts3 = match_group3.split(b'.')
    else:
        match_group3 = match.group(3)
    if parts3 in module_utils:
        from_file0, lfrom_file0, from_file1, lfrom_file1 = get_candidates(parts3, parts5)
        if from_file0.is_file() or from_file1.is_file() or \
           lfrom_file0.is_file() or lfrom_file1.is_file():
            return b'%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s' % \
                (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                 match_group3, match.group(4), match.group(5))
        else:
            return b'%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s' % \
                (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                 match_group3, match.group(4), match.group(5))
    if parts5 in module_utils:
        from_file0, lfrom_file0, from_file1, lfrom_file1 = get_candidates(parts3, parts5)
        if parts3:
            if from_file0.is_file() or from_file1.is_file() or \
               lfrom_file0.is_file() or lfrom_file1.is_file():
                return b'%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s' % \
                    (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                     match.group(3), match.group(4), match.group(5))
            else:
                return b'%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s' % \
                    (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                     match.group(3), match.group(4), match.group(5))
        if from_file0.is_file() or from_file1.is_file() or \
            lfrom_file0.is_file() or lfrom_file1.is_file():
            return b'%s ansible_collections.%s.%s.plugins.module_utils import %s%s' % \
                (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                 match.group(4), match.group(5))
        else:
            return b'%s ansible_collections.%s.%s.plugins.module_utils.__init__ import %s%s' % \
                (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                 match.group(4), match.group(5))
    return match.group(0)


def from_2dots_replace(match):
    """
    If 'from ..module_utils.something import identifier' matches,
    'from ansible_collections.NAMESPACE.COLLECTION.plugins.module_utils.something import identifier'
    is returned to replaced.
    """
    try:
        parts3 = match.group(3).split(b'.')
    except AttributeError:
        parts3 = None
    if len(parts3) == 1:
        match_group3 = (role + '.' + match.group(3).decode("utf-8")).encode()
        parts3 = match_group3.split(b'.')
    parts4 = match.group(4).split(b'.')
    if parts3 in module_utils:
        return b'%s ansible_collections.%s.%s.plugins.module_utils.%s import %s' % \
            (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
             match_group3, match.group(4))
    return match.group(0)

# Update the python codes which import modules in plugins/{modules,modules_dir}.
modules_dir = output / 'plugins' / 'modules'
for rewrite_dir in (module_utils_dir, modules_dir):
    if rewrite_dir.is_dir():
        for root, dirs, files in os.walk(rewrite_dir):
            for filename in files:
                if os.path.splitext(filename)[1] != '.py':
                    continue
                full_path = (Path(root) / filename)
                text = full_path.read_bytes()

                new_text = IMPORT_RE.sub(
                    import_replace,
                    text
                )

                new_text = FROM_RE.sub(
                    from_replace,
                    new_text
                )

                new_text = FROM2DOTS_RE.sub(
                    from_2dots_replace,
                    new_text
                )

                for rewrite in additional_rewrites:
                    pattern = re.compile(
                        re.escape(
                            br'ansible.module_utils.%s' % b'.'.join(rewrite)
                        )
                    )
                    new_text = pattern.sub(
                        rewrite[-1],
                        new_text
                    )

                if text != new_text:
                    print('Rewriting imports for {}'.format(full_path))
                    full_path.write_bytes(new_text)
                    additional_rewrites[:] = []

# ==============================================================================

def add_rolename(filename, rolename):
    """
    A file with an extension, e.g., README.md is converted to README-rolename.md
    A file with no extension, e.g., LICENSE is to LICENSE-rolename
    """
    if filename.find('.', 1) > 0:
        with_rolename = re.sub('(\.[A-Za-z0-1]*$)', '-' + rolename + r'\1', filename)
    else:
        with_rolename = filename + "-" + rolename
    return with_rolename


# Extra files and directories including the sub-roles
for extra in extras:
    if extra.name.endswith('.md'):
        # E.g., contributing.md, README-devel.md and README-testing.md
        process_readme(extra.parent, extra.name, role)
    elif extra.is_dir():
        # Copying sub-roles to the roles dir and its tests and README are also
        # handled in the same way as the parent role's are.
        if extra.name == 'roles':
            for sr in extra.iterdir():
                # If a role name contains '.', replace it with args.replace_dot
                dr = sr.name.replace('.', args.replace_dot)
                for role_dir in ROLE_DIRS:
                    src = sr / role_dir
                    if not src.is_dir():
                        continue
                    dest = output / extra.name / dr / role_dir
                    print(f'Copying role {src} to {dest}')
                    copytree(
                        src,
                        dest,
                        symlinks=True,
                        dirs_exist_ok=True
                    )
                # copy tests dir to output/'tests'
                copy_tests(sr, dr)
                # remove symlinks in the tests/role, then updating the rolename to the collection format
                symlink_n_rolename(output / 'tests' / dr, namespace, collection, dr)
                add_to_tests_defaults(namespace, collection, dr)
                # copy README.md to output/roles/sr.name
                readme = sr / 'README.md'
                if readme.is_file():
                    process_readme(sr, 'README.md', dr)
                if sr.name != dr:
                    # replace "sr.name" with "dr" in role_dir
                    dirs = ['roles', 'docs', 'tests']
                    for dir in dirs:
                        role_dir = output / dir
                        file_patterns = ['*.yml', '*.md']
                        file_replace(role_dir, re.escape(sr.name), dr, file_patterns)
        # Other extra directories are copied to the collection dir as they are.
        else:
            dest = output / extra.name
            print(f'Copying extra {extra} to {dest}')
            copytree(
                extra,
                dest,
                dirs_exist_ok=True
            )
    # Other extra files.
    else:
        if extra.name.endswith('.yml') and 'playbook' in extra.name:
            # some-playbook.yml is copied to playbooks/role dir.
            dest = output / 'playbooks' / role
            dest.mkdir(parents=True, exist_ok=True)
        elif extra.name in EXTRA_NO_ROLENAME:
            # If the file in the EXTRA_NO_ROLENAME tuple, it is copied to the collection
            # dir as it is.
            dest = output / extra.name
        else:
            # If the extra file 'filename' has no extension, it is copied to the collection dir as
            # 'filename-ROLE'. If the extra file is 'filename.ext', it is copied to 'filename-ROLE.ext'.
            dest = output / add_rolename(extra.name, role)
        print(f'Copying extra {extra} to {dest}')
        copy2(
            extra,
            dest,
            follow_symlinks=False
        )

default_collections_paths = '~/.ansible/collections:/usr/share/ansible/collections'
default_collections_paths_list = list(map(os.path.expanduser, default_collections_paths.split(':')))
current_dest = os.path.expanduser(str(dest_path))
# dest_path is not in the default collections path.
# suggest to run ansible-playbook with ANSIBLE_COLLECTIONS_PATHS env var.
if not current_dest in default_collections_paths_list:
    ansible_collections_paths = current_dest + ':' + default_collections_paths
    print(f'Run ansible-playbook with environment variable ANSIBLE_COLLECTIONS_PATHS={ansible_collections_paths}')
