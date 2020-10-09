# SPDX-License-Identifier: GPL-2.0-or-later
"""unit tests for lsr_role2collection"""

import os
import re
import shutil
import tempfile
import textwrap
from pathlib import Path
import unittest

from lsr_role2collection import (
    file_replace,
    copy_tree_with_replace,
    cleanup_symlinks,
    import_replace,
    from_replace,
    gather_module_utils_parts,
    add_rolename,
    config,
)

src_path = os.environ.get("COLLECTION_SRC_PATH", "/var/tmp/linux-system-roles")
dest_path = os.environ.get("COLLECTION_DEST_PATH", "/var/tmp/collections")
namespace = os.environ.get("COLLECTION_NAMESPACE", "fedora")
collection_name = os.environ.get("COLLECTION_NAME", "system_roles")
rolename = "systemrole"
prefix = namespace + "." + collection_name
prefixdot = prefix + "."

test_yaml_str = textwrap.dedent(
    """\
    # SPDX-License-Identifier: MIT
    ---
    - name: Ensure that the role runs with default parameters
      hosts: all
      tasks:
        - name: default task
          {0}:
            {1} {2}{3}{4}
    """
)


class LSRRole2Collection(unittest.TestCase):
    """test lsr_role2collection"""

    def create_test_tree(self, top, template, params, ext, is_vertical=True):
        path = top
        for n in range(len(params)):
            if is_vertical:
                path /= "sub" + str(n)
            path.mkdir(parents=True, exist_ok=True)
            filename = "test" + str(n) + ext
            filepath = path / filename
            content = template.format(
                params[n]["key"],
                params[n]["subkey"],
                params[n]["value"],
                params[n]["delim"],
                params[n]["subvalue"],
            )
            with open(filepath, "w") as f:
                f.write(content)

    def check_test_tree(self, top, template, params, ext, is_vertical=True):
        path = top
        for n in range(len(params)):
            if is_vertical:
                path /= "sub" + str(n)
            filename = "test" + str(n) + ext
            filepath = path / filename
            content = template.format(
                params[n]["key"],
                params[n]["subkey"],
                params[n]["value"],
                params[n]["delim"],
                params[n]["subvalue"],
            )
            with open(filepath) as f:
                s = f.read()
            self.assertEqual(content, s)

    def create_test_link(self, path, link, target, is_target):
        path.mkdir(parents=True, exist_ok=True)
        (path / link).symlink_to(target, target_is_directory=is_target)

    def check_test_link(self, path, exists):
        self.assertEqual(path.exists(), exists)

    def test_file_replace(self):
        """test file_replace"""

        tmpdir = tempfile.TemporaryDirectory()
        pre_params = [
            {
                "key": "roles",
                "subkey": "-",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "import_role",
                "subkey": "name:",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
        ]
        post_params = [
            {
                "key": "roles",
                "subkey": "-",
                "value": prefix,
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "import_role",
                "subkey": "name:",
                "value": prefix,
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": prefix,
                "delim": ".",
                "subvalue": rolename,
            },
        ]
        self.create_test_tree(Path(tmpdir.name), test_yaml_str, pre_params, ".yml")
        file_replace(
            Path(tmpdir.name),
            pre_params[0]["value"] + "." + pre_params[0]["subvalue"],
            prefixdot + pre_params[0]["subvalue"],
            ["*.yml"],
        )
        self.check_test_tree(Path(tmpdir.name), test_yaml_str, post_params, ".yml")

    def test_copy_tree_with_replace(self):
        """test copy_tree_with_replace"""

        pre_params = [
            {
                "key": "roles",
                "subkey": "-",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "import_role",
                "subkey": "name:",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": '"{{ role_path }}/roles',
                "delim": "/",
                "subvalue": '__subrole_with__"',
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": '"{{ role_path }}/roles',
                "delim": "/",
                "subvalue": 'subrole_no__"',
            },
            {
                "key": "include_tasks",
                "subkey": "-",
                "value": '"{{ role_path }}/roles/subrole/tasks',
                "delim": "/",
                "subvalue": 'mytask.yml"',
            },
            {
                "key": "include_vars",
                "subkey": "-",
                "value": '"{{ role_path }}/roles/subrole/vars',
                "delim": "/",
                "subvalue": 'myvar.yml"',
            },
        ]
        post_params = [
            {
                "key": "roles",
                "subkey": "-",
                "value": prefix,
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "import_role",
                "subkey": "name:",
                "value": prefix,
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": prefix,
                "delim": ".",
                "subvalue": rolename,
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": '"' + prefix,
                "delim": ".",
                "subvalue": '__subrole_with__"',
            },
            {
                "key": "include_role",
                "subkey": "name:",
                "value": '"' + prefix,
                "delim": ".",
                "subvalue": 'subrole_no__"',
            },
            {
                "key": "include_tasks",
                "subkey": "-",
                "value": '"{{ role_path }}/roles/subrole/tasks',
                "delim": "/",
                "subvalue": 'mytask.yml"',
            },
            {
                "key": "include_vars",
                "subkey": "-",
                "value": '"{{ role_path }}/roles/subrole/vars',
                "delim": "/",
                "subvalue": 'myvar.yml"',
            },
        ]
        MYTUPLE = ("tasks",)
        tmpdir = tempfile.TemporaryDirectory()
        role_path = Path(tmpdir.name) / "linux-system-roles" / rolename
        coll_path = (
            Path(dest_path) / "ansible_collections" / namespace / collection_name
        )
        self.create_test_tree(
            role_path / "tasks", test_yaml_str, pre_params, ".yml", is_vertical=False
        )
        transformer_args = {
            "prefix": prefixdot,
            "subrole_prefix": "",
            "replace_dot": "_",
            "role_modules": set(),
        }
        copy_tree_with_replace(
            role_path, coll_path, rolename, MYTUPLE, transformer_args, isrole=True
        )
        test_path = coll_path / "roles" / rolename / "tasks"
        self.check_test_tree(
            test_path, test_yaml_str, post_params, ".yml", is_vertical=False
        )
        shutil.rmtree(coll_path)

    def test_cleanup_symlinks(self):
        """test cleanup_symlinks"""

        params = [
            {
                "key": "roles",
                "subkey": "-",
                "value": "linux-system-roles",
                "delim": ".",
                "subvalue": rolename,
            },
        ]
        tmpdir = tempfile.TemporaryDirectory()
        coll_path = (
            Path(tmpdir.name) / "ansible_collections" / namespace / collection_name
        )
        role_path = coll_path / "roles" / rolename
        self.create_test_tree(
            role_path / "tasks", test_yaml_str, params, ".yml", is_vertical=False
        )
        test_path = coll_path / "tests" / rolename
        self.create_test_tree(
            test_path, test_yaml_str, params, ".yml", is_vertical=False
        )
        link = "linux-system-roles." + rolename
        test_role_path = test_path / "roles"
        # case 1. tests/roles/linux-system-roles.systemrole -> roles/systemrole
        self.create_test_link(test_role_path, link, role_path, True)
        cleanup_symlinks(test_path, rolename)
        self.check_test_link(test_role_path, False)
        # case 2. tests/roles/linux-system-roles.systemrole -> roles/systemrole
        #         tests/roles/some_file
        self.create_test_link(test_role_path, link, role_path, True)
        self.create_test_tree(
            test_role_path, test_yaml_str, params, ".yml", is_vertical=False
        )
        cleanup_symlinks(test_path, rolename)
        self.check_test_link(test_role_path, True)
        self.check_test_link(test_role_path / link, False)
        shutil.rmtree(test_role_path)
        # case 3. tests/roles/linux-system-roles.systemrole -> roles/systemrole
        #         tests/roles/some_symlinks
        self.create_test_link(test_role_path, link, role_path, True)
        extralink = "extralink"
        self.create_test_link(test_role_path, extralink, role_path, True)
        cleanup_symlinks(test_path, rolename)
        self.check_test_link(test_role_path, True)
        self.check_test_link(test_role_path / link, False)
        self.check_test_link(test_role_path / extralink, True)
        shutil.rmtree(test_role_path)

    def test_import_replace(self):
        module_name = "util0"
        src_module_dir = Path(src_path) / rolename / "module_utils" / module_name
        src_module_dir.mkdir(parents=True, exist_ok=True)
        dest_base_dir = (
            Path(dest_path) / "ansible_collections" / namespace / collection_name
        )
        dest_module_dir_core = dest_base_dir / "plugins" / "module_utils"
        dest_module_dir = dest_module_dir_core / module_name
        dest_module_dir.mkdir(parents=True, exist_ok=True)
        input = bytes(
            "import os\nimport ansible.module_utils.{0}\nimport re\n".format(
                module_name
            ),
            "utf-8",
        )
        expected = bytes(
            "import os\nimport ansible_collections.{0}.{1}.plugins.module_utils.{2}\nimport re\n".format(
                namespace, collection_name, module_name
            ),
            "utf-8",
        )
        IMPORT_RE = re.compile(
            br"(\bimport) (ansible\.module_utils\.)(\S+)(.*)$", flags=re.M
        )
        config["namespace"] = namespace
        config["collection"] = collection_name
        config["role"] = rolename
        config["src_path"] = Path(src_path) / rolename
        config["dest_path"] = dest_base_dir
        config["module_utils_dir"] = dest_module_dir_core
        config["module_utils"] = [
            [b"util0"],
            [b"util0", b"test3"],
            [b"util0", b"test2"],
            [b"util0", b"test1"],
            [b"util0", b"test0"],
        ]
        config["additional_rewrites"] = []
        output = IMPORT_RE.sub(import_replace, input)
        self.assertEqual(output, expected)
        shutil.rmtree(src_module_dir)
        shutil.rmtree(dest_module_dir)

    def test_from_replace(self):
        module_name = "util0"
        src_module_dir = Path(src_path) / rolename / "module_utils" / module_name
        src_module_dir.mkdir(parents=True, exist_ok=True)
        dest_base_dir = (
            Path(dest_path) / "ansible_collections" / namespace / collection_name
        )
        dest_module_dir_core = dest_base_dir / "plugins" / "module_utils"
        dest_module_dir = dest_module_dir_core / module_name
        dest_module_dir.mkdir(parents=True, exist_ok=True)

        test_files = ["test0", "test1", "test2", "test3", "__init__"]
        for f in test_files:
            fpath = dest_module_dir / (f + ".py")
            fpath.touch(exist_ok=True)
        gather_module_utils_parts(dest_module_dir_core)

        input = bytes(
            textwrap.dedent(
                """\
                # pylint: disable=import-error, no-name-in-module
                {0}.basic import AnsibleModule
                {0}.{1} import {2}
                {0}.{1} import MyError
                {0}.{1}.{3} import (
                    ArgUtil,
                    ArgValidator_ListConnections,    ValidationError,
                )
                {0}.{1}.{4} import Util
                {0}.{1} import {5}
                """
            ).format(
                "from ansible.module_utils",
                module_name,
                test_files[0],
                test_files[1],
                test_files[2],
                test_files[3],
            ),
            "utf-8",
        )
        expected = bytes(
            textwrap.dedent(
                """\
                # pylint: disable=import-error, no-name-in-module
                from ansible.module_utils.basic import AnsibleModule
                {0}.{1}.{2}.plugins.module_utils.{3} import {4}
                {0}.{1}.{2}.plugins.module_utils.{3}.__init__ import MyError
                {0}.{1}.{2}.plugins.module_utils.{3}.{5} import (
                    ArgUtil,
                    ArgValidator_ListConnections,    ValidationError,
                )
                {0}.{1}.{2}.plugins.module_utils.{3}.{6} import Util
                {0}.{1}.{2}.plugins.module_utils.{3} import {7}
                """
            ).format(
                "from ansible_collections",
                namespace,
                collection_name,
                module_name,
                test_files[0],
                test_files[1],
                test_files[2],
                test_files[3],
            ),
            "utf-8",
        )
        FROM_RE = re.compile(
            br"(\bfrom) (ansible\.module_utils\.?)(\S+)? import (\(*(?:\n|\r\n)?)(.+)$",
            flags=re.M,
        )
        config["namespace"] = namespace
        config["collection"] = collection_name
        config["role"] = rolename
        config["src_path"] = Path(src_path) / rolename
        config["dest_path"] = dest_base_dir
        config["module_utils_dir"] = dest_module_dir_core
        config["module_utils"] = [
            [b"util0"],
            [b"util0", b"test3"],
            [b"util0", b"test2"],
            [b"util0", b"test1"],
            [b"util0", b"test0"],
        ]
        config["additional_rewrites"] = []
        output = FROM_RE.sub(from_replace, input)
        self.assertEqual(output, expected)
        shutil.rmtree(src_module_dir)
        shutil.rmtree(dest_module_dir)

    def test_add_rolename(self):
        input = "README.md"
        expected = "README-" + rolename + ".md"
        output = add_rolename(input, rolename)
        self.assertEqual(output, expected)

        input = "README.test.md"
        expected = "README.test-" + rolename + ".md"
        output = add_rolename(input, rolename)
        self.assertEqual(output, expected)

        input = "LICENSE"
        expected = "LICENSE-" + rolename
        output = add_rolename(input, rolename)
        self.assertEqual(output, expected)
