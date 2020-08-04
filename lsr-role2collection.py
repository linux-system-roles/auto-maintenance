#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) 2020 Matt Martz <matt@sivel.net>
# GNU General Public License v3.0+
#     (see https://www.gnu.org/licenses/gpl-3.0.txt)

# python lsr-role2collection.py /src_path/linux-system-roles/logging /dest_path/ansible_collections/redhat/system_roles

import argparse
import os
import re
import shutil

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
    'molecule',
)

DOCS = (
    'docs',
    'design_docs',
)

ALL_DIRS = ROLE_DIRS + PLUGINS + TESTS + DOCS

IMPORT_RE = re.compile(
    br'(\bimport) (ansible\.module_utils\.)(\S+)(.*)$',
    flags=re.M
)
FROM_RE = re.compile(
    br'(\bfrom) (ansible\.module_utils\.?)(\S+)? import (.+)$',
    flags=re.M
)


def dir_to_plugin(v):
    if v[-8:] == '_plugins':
        return v[:-8]
    elif v == 'library':
        return 'modules'
    return v


# python lsr-role2collection.py /src_path/linux-system-roles/logging /dest_path/ansible_collections/redhat/system_roles
# positional arguments:
#  ROLE_PATH        Path to a role to migrate
#  COLLECTION_PATH  Path to collection where role should be migrated
parser = argparse.ArgumentParser()
parser.add_argument(
    '--namespace',
    type=str,
    default=os.environ.get("COLLECTION_NAMESPACE", "redhat"),
    help='Collection namespace; default to redhat',
)
parser.add_argument(
    '--name',
    type=str,
    default=os.environ.get("COLLECTION_NAME", "system_roles"),
    help='Collection name; default to system_roles',
)
parser.add_argument(
    '--dest-path',
    type=Path,
    help='Path to parent of collection where role should be migrated',
)
parser.add_argument(
    '--src-path',
    type=Path,
    help='Path to linux-system-role',
)
parser.add_argument(
    '--role',
    type=str,
    help='Role to convert to collection',
)
args = parser.parse_args()

#path = Path.joinpath(args.src_path.resolve(), args.role)

role = args.role
path = args.src_path.resolve() / role
output = Path.joinpath(args.dest_path.resolve(), "ansible_collections/" + args.namespace + "/" + args.name)
output.mkdir(parents=True, exist_ok=True)

_extras = set(os.listdir(path)).difference(ALL_DIRS)
try:
    _extras.remove('.git')
except KeyError:
    pass
extras = [path / e for e in _extras]

# roles
for role_dir in ROLE_DIRS:
    src = path / role_dir
    if not src.is_dir():
        continue
    dest = output / 'roles' / path.name / role_dir
    print(f'Copying role {src} to {dest}')
    shutil.copytree(
        src,
        dest,
        symlinks=True,
        dirs_exist_ok=True
    )

# tests, molecules
for tests in TESTS:
    src = path / tests
    if src.is_dir():
        dest = output / tests / role
        print(f'Copying role {src} to {dest}')
        shutil.copytree(
            src,
            dest,
            symlinks=True,
            dirs_exist_ok=True
        )

# docs, design_docs
for docs in DOCS:
    src = path / docs
    if src.is_dir():
        dest = output / Path('docs') / role
        print(f'Copying role {src} to {dest}')
        shutil.copytree(
            src,
            dest,
            symlinks=True,
            dirs_exist_ok=True
        )

# plugins
for plugin_dir in PLUGINS:
    src = path / plugin_dir
    plugin = dir_to_plugin(plugin_dir)
    if not src.is_dir():
        continue
    dest = output / 'plugins' / plugin
    print(f'Copying plugin {src} to {dest}')
    shutil.copytree(
        src,
        dest,
        dirs_exist_ok=True
    )

module_utils = []
module_utils_dir = path / 'module_utils'
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
            return (
                b'import ..module_utils.%s as %s' % (match.group(3), parts[-1])
            )
        return b'%s ..module_utils.%s%s' % match.group(1, 3, 4)
    return match.group(0)


def from_replace(match):
    try:
        parts3 = match.group(3).split(b'.')
    except AttributeError:
        parts3 = None
    parts4 = match.group(4).split(b'.')
    if parts3 in module_utils:
        return b'%s ..module_utils.%s import %s' % match.group(1, 3, 4)
    if parts4 in module_utils:
        if parts3:
            return b'%s ..module_utils.%s import %s' % match.group(1, 3, 4)
        return b'%s ..module_utils import %s' % match.group(1, 4)
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
        dest = output / extra.name.replace(".md",  "-" + role + ".md")
    elif extra.name.endswith('.yml'):
        dest = output / extra.name.replace(".yml",  "-" + role + ".yml")
    else:
        dest = output / (extra.name + "-" + role)
    print(f'Copying extra {extra} to {dest}')
    if extra.is_dir():
        shutil.copytree(
            extra,
            dest,
            dirs_exist_ok=True
        )
    else:
        shutil.copy2(
            extra,
            dest,
            follow_symlinks=False
        )
