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
    'pylint_extra_requirements.txt',
    'pylintrc',
    'pytest_extra_requirements.txt',
    'ansible_pytest_extra_requirements.txt',
    '.gitignore',
    '.lgtm.yml',
    'semaphore',
    'artifacts',
    'standard-inventory-qcow2',
    'scripts',
    '.venv',
    '.tox',
)

EXTRA_NO_ROLENAME = (
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
    required=True,
    help='Path to parent of collection where role should be migrated',
)
parser.add_argument(
    '--src-path',
    type=Path,
    required=True,
    help='Path to linux-system-role',
)
parser.add_argument(
    '--role',
    type=str,
    help='Role to convert to collection',
)
parser.add_argument(
    '--replace-dot',
    type=str,
    default='_',
    help='If sub-role name contains dots, replace them with the given value; default to "_"',
)
parser.add_argument(
    '--molecule',
    action='store_true',
    help='if set, molecule is copied from SRC_PATH/template, which must exist. --role ROLE is ignored.'
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


# Copy linux system roles
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

# Copy roles
for role_dir in ROLE_DIRS:
    src = src_path / role_dir
    if not src.is_dir():
        continue
    dest = output / 'roles' / src_path.name / role_dir
    print(f'Copying role {src} to {dest}')
    copytree(
        src,
        dest,
        symlinks=True,
        dirs_exist_ok=True
    )

# Copy tests
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

# Adjust role names to the collections style.
def remove_or_reset_symlinks(path, role, lsr_reset=False):
    '''
    Clean up roles/linux-system-roles.rolename.
    - Remove symlinks.
    - If lsr_reset is true and the symlink is linux-system-roles.rolename,
      recreate the symplink which targets to ../../../roles/rolename.
    - If linux-system-roles.rolename is an empty dir, rmdir it.
    '''
    nodes = sorted(list(path.rglob('*')), reverse=True)
    for node in nodes:
        if node.is_symlink():
            node.unlink()
            if lsr_reset and r'linux-system-roles.' + role == node.name:
                node.symlink_to('../../../roles/' + role)
        elif node.is_dir() and r'linux-system-roles.' + role == node.name and not any(node.iterdir()):
            node.rmdir()


def recursive_grep(path, find, file_patterns):
    '''
    Check if a pattern `find` is found in the files that match
    `file_patterns` under `path`.
    '''
    for root, dirs, files in os.walk(os.path.abspath(path)):
        for file_pattern in file_patterns:
            for filename in fnmatch.filter(files, file_pattern):
                filepath = os.path.join(root, filename)
                with open(filepath) as f:
                    s = f.read()
                if find in s:
                    return True
    return False


def file_replace(path, find, replace, file_patterns):
    '''
    Replace a pattern `find` with `replace` in the files that match
    `file_patterns` under `path`.
    '''
    for root, dirs, files in os.walk(os.path.abspath(path)):
        for file_pattern in file_patterns:
            for filename in fnmatch.filter(files, file_pattern):
                filepath = os.path.join(root, filename)
                with open(filepath) as f:
                    s = f.read()
                s = re.sub(find, replace, s)
                with open(filepath, "w") as f:
                    f.write(s)


def replace_rolename_with_collection(path, role, collection):
    '''
    Replace `linux-system-roles.rolename` with `namespace.collection.rolename`
    in the given dir `path` recursively.
    '''
    find = r"( *name: | *- name: | *- | *roletoinclude: | *role: | *- role: )(linux-system-roles\.{0}\b|{0}\b)".format(role, role)
    replace = r"\1" + namespace + "." + collection + "." + role
    file_patterns = ['*.yml', '*.md']
    file_replace(path, find, replace, file_patterns)


def symlink_n_rolename(path, role, collection):
    '''
    Handle rolename issues in the test playbooks.
    '''
    if path.exists():
        replace_rolename_with_collection(path, role, collection)
        # linux-system-roles.role is left, which is not replaceable with FQCN
        file_patterns = ['*.yml']
        find = 'linux-system-roles.{0}'.format(role)
        # There is a code which requires a symlink to the role.
        # E.g., file: roles/linux-system-roles.kernel_settings/vars/main.yml
        # in kernel_settings/tests/tests_simple_settings.yml:
        if recursive_grep(path, find, file_patterns):
            lsr_reset = True
        else:
            lsr_reset = False
        remove_or_reset_symlinks(path, role, lsr_reset)
        roles_dir = path / 'roles'
        if roles_dir.exists() and not any(roles_dir.iterdir()):
            roles_dir.rmdir()


# remove symlinks in the tests/role, then updating the rolename to the collection format
test_role_path = output / 'tests' / role
symlink_n_rolename(test_role_path, role, collection)

# replace "{{ role_path }}/roles/rolename" with namespace.collection.rolename in role_dir
role_dir = output / 'roles' / role
find = "{{ role_path }}/roles/(.*)"
replace = namespace + "." + collection + ".\\1"
file_patterns = ['*.yml', '*.md']
file_replace(role_dir, find, replace, file_patterns)

# Create tests_defaults.yml in tests for the molecule test.
tests_default = output / 'tests' / 'tests_default.yml'
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


# Copy docs, design_docs, examples and README.md files
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


def process_readme(src_path, filename, output, rolename):
    docs_path = output / Path('docs')
    docs_path.mkdir(parents=True, exist_ok=True)
    src = src_path / filename
    # copy
    with_rolename = add_rolename(filename, rolename)
    dest = docs_path / with_rolename
    print(f'Copying doc {filename} to {dest}')
    copy2(
        src,
        dest,
        follow_symlinks=False
    )
    prim_doc = output / 'README.md'
    if filename == 'README.md':
        title = role
    elif filename.startswith('README'):
        m = re.match('(README-)(.*)(\.md)', filename)
        title = role + '-' + m.group(2)
    else:
        title = role + '-' + filename.replace('.md', '')
    if not prim_doc.exists():
        s = '# {0} {1} collections\n\n## Contents\n<!--ts-->\n  * [{2}](docs/{3})\n<!--te-->'.format(namespace, collection, title, with_rolename)
        with open(prim_doc, "w") as f:
            f.write(s)
    else:
        with open(prim_doc) as f:
            s = f.read()
        replace = '  * [{0}](docs/{1})\n<!--te-->'.format(title, with_rolename)
        s = re.sub('<!--te-->', replace, s)
        with open(prim_doc, "w") as f:
            f.write(s)


docs_path = output / Path('docs')
dest = docs_path / role
for doc in DOCS:
    src = src_path / doc
    if src.is_dir():
        print(f'Copying role {src} to {dest}')
        copytree(
            src,
            dest,
            symlinks=False,
            ignore=ignore_patterns('roles'),
            dirs_exist_ok=True
        )
    elif doc == 'README.md':
        process_readme(src_path, doc, output, role)

# remove symlinks in the docs/role, then updating the rolename to the collection format
docs_role_path = output / 'docs' / role
symlink_n_rolename(docs_role_path, role, collection)

# plugins
for plugin_dir in PLUGINS:
    src = src_path / plugin_dir
    plugin = dir_to_plugin(plugin_dir)
    if not src.is_dir():
        continue
    dest = output / 'plugins' / plugin
    print(f'Copying plugin {src} to {dest}')
    copytree(
        src,
        dest,
        dirs_exist_ok=True
    )

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

additional_rewrites = []


def import_replace(match):
    parts = match.group(3).split(b'.')
    if parts in module_utils:
        if match.group(1) == b'import' and match.group(4) == b'':
            additional_rewrites.append(parts)
            return b'import ansible_collections.%s.%s.plugins.module_utils.%s as %s' % \
                (bytes(namespace, 'utf-8'), bytes(collection, 'utf-8', (match.group(3), parts[-1]))
            )
        return b'%s ansible_collections.%s.%s.plugins.module_utils.%s%s' % \
            (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
             match.group(3), match.group(4))
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


# from_replace
# case 1: from ansible.module_utils.certificate.providers import PROVIDERS
# if plugins/module_utils/certificate/providers/{PROVIDERS,providers}.py does not exist:
#   return 'from ansible_collections.fedora.system_roles.plugins.module_utils.certificate.providers.__init__ import PROVIDERS'
#
# case 2: from ansible.module_utils.certificate.providers.certmonger import (\n
# if plugins/module_utils/certificate/providers/certmonger.py exists:
#   return 'from ansible_collections.fedora.system_roles.plugins.module_utils.certificate.providers.certmonger import (\n'

# group1 - from; group2 - ansible.module_utils;
# group3 - name if any; group4 - ( if any; group5 - identifier
def from_replace(match):
    try:
        parts3 = match.group(3).split(b'.')
    except AttributeError:
        parts3 = []
    try:
        parts5 = match.group(5).split(b'.')
    except AttributeError:
        parts5 = []
    if parts3 in module_utils:
        from_file0, lfrom_file0, from_file1, lfrom_file1 = get_candidates(parts3, parts5)
        if from_file0.is_file() or from_file1.is_file() or \
           lfrom_file0.is_file() or lfrom_file1.is_file():
            return b'%s ansible_collections.%s.%s.plugins.module_utils.%s import %s%s' % \
                (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                 match.group(3), match.group(4), match.group(5))
        else:
            return b'%s ansible_collections.%s.%s.plugins.module_utils.%s.__init__ import %s%s' % \
                (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
                 match.group(3), match.group(4), match.group(5))
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
    try:
        parts3 = match.group(3).split(b'.')
    except AttributeError:
        parts3 = None
    parts4 = match.group(4).split(b'.')
    if parts3 in module_utils:
        return b'%s ansible_collections.%s.%s.plugins.module_utils.%s import %s' % \
            (match.group(1), bytes(namespace, 'utf-8'), bytes(collection, 'utf-8'),
             match.group(3), match.group(4))
    return match.group(0)


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

for extra in extras:
    if extra.name.endswith('.md'):
        process_readme(extra.parent, extra.name, output, role)
    elif extra.is_dir():
        if extra.name == 'roles':
            for sr in extra.iterdir():
                src = extra / sr
                # If a role name contains '.', replace it with args.replace_dot
                dr = sr.name.replace('.', args.replace_dot)
                dest = output / extra.name / dr
                print(f'Copying extra {src} to {dest}')
                copytree(
                    src,
                    dest,
                    dirs_exist_ok=True
                )
                if sr.name != dr:
                    # replace "sr.name" with "dr" in role_dir
                    role_dir = output / 'roles'
                    file_patterns = ['*.yml', '*.md']
                    file_replace(role_dir, re.escape(sr.name), dr, file_patterns)
        else:
            dest = output / extra.name
            print(f'Copying extra {extra} to {dest}')
            copytree(
                extra,
                dest,
                dirs_exist_ok=True
            )
    else:
        # some-playbook.yml is copied to playbooks/role dir.
        if extra.name.endswith('.yml') and 'playbook' in extra.name:
            dest = output / 'playbooks' / role
            dest.mkdir(parents=True, exist_ok=True)
        elif extra.name in EXTRA_NO_ROLENAME:
            dest = output / extra.name
        else:
            dest = output / add_rolename(extra.name, role)
        print(f'Copying extra {extra} to {dest}')
        copy2(
            extra,
            dest,
            follow_symlinks=False
        )

# ansible.cfg for the collection path
ansiblecfg = output / 'ansible.cfg'
s = '[defaults]\ncollections_paths = ' + str(dest_path) + ':~/.ansible/collections:/usr/share/ansible/collections'
with open(ansiblecfg, "w") as f:
    f.write(s)

print(f'Run ansible-playbook with environment variable ANSIBLE_CONFIG={ansiblecfg}')
