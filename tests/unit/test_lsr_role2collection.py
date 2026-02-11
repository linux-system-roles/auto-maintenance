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
newrolename = "newsystemrole"
otherroles = ["other0", "other1", "other2"]
newotherroles = ["newother0", "newother1", "newother2"]
prefix = namespace + "." + collection_name
prefixdot = prefix + "."
otherprefix = "mynamespace.mycollection"
otherprefixdot = "mynamespace.mycollection."

test_yaml_str = textwrap.dedent("""\
    # SPDX-License-Identifier: MIT
    ---
    - name: Ensure that the role runs with default parameters
      hosts: all
      {0}:
        - {1}
            {2} {3}{4}{5}
    """)


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
                params[n]["keyword"],
                params[n]["role_or_task_name"],
                params[n]["task_subkey"],
                params[n]["task_value"],
                params[n]["task_delim"],
                params[n]["task_subvalue"],
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
                params[n]["keyword"],
                params[n]["role_or_task_name"],
                params[n]["task_subkey"],
                params[n]["task_value"],
                params[n]["task_delim"],
                params[n]["task_subvalue"],
            )
            with open(filepath) as f:
                s = f.read()
            self.assertEqual(content.rstrip(), s.rstrip())

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
                "keyword": "roles",
                "role_or_task_name": "linux-system-roles." + rolename,
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": rolename,
            },
        ]
        post_params = [
            {
                "keyword": "roles",
                "role_or_task_name": prefix + "." + rolename,
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": rolename,
            },
        ]
        self.create_test_tree(Path(tmpdir.name), test_yaml_str, pre_params, ".yml")
        file_replace(
            Path(tmpdir.name),
            pre_params[1]["task_value"] + "." + pre_params[1]["task_subvalue"],
            prefixdot + pre_params[1]["task_subvalue"],
            ["*.yml"],
        )
        self.check_test_tree(Path(tmpdir.name), test_yaml_str, post_params, ".yml")

    def test_copy_tree_with_replace(self):
        """test copy_tree_with_replace"""

        pre_params = [
            {
                "keyword": "roles",
                "role_or_task_name": "linux-system-roles." + rolename,
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"{{ role_path }}/roles',
                "task_delim": "/",
                "task_subvalue": '__subrole_with__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"{{ role_path }}/roles',
                "task_delim": "/",
                "task_subvalue": 'subrole_no__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_tasks:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/tasks',
                "task_delim": "/",
                "task_subvalue": 'mytask.yml"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_vars:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/vars',
                "task_delim": "/",
                "task_subvalue": 'myvar.yml"',
            },
        ]
        post_params = [
            {
                "keyword": "roles",
                "role_or_task_name": prefix + "." + rolename,
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"' + prefix,
                "task_delim": ".",
                "task_subvalue": '__subrole_with__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"' + prefix,
                "task_delim": ".",
                "task_subvalue": 'subrole_no__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_tasks:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/tasks',
                "task_delim": "/",
                "task_subvalue": 'mytask.yml"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_vars:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/vars',
                "task_delim": "/",
                "task_subvalue": 'myvar.yml"',
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
            "namespace": namespace,
            "collection": collection_name,
            "prefix": prefixdot,
            "subrole_prefix": "",
            "replace_dot": "_",
            "role_modules": set(),
            "src_owner": "linux-system-roles",
            "top_dir": dest_path,
            "extra_mapping_src_owner": [],
            "extra_mapping_src_role": [],
            "extra_mapping_dest_prefix": [],
            "extra_mapping_dest_role": [],
        }
        copy_tree_with_replace(
            role_path,
            coll_path,
            rolename,
            rolename,
            MYTUPLE,
            transformer_args,
            isrole=True,
        )
        test_path = coll_path / "roles" / rolename / "tasks"
        self.check_test_tree(
            test_path, test_yaml_str, post_params, ".yml", is_vertical=False
        )
        shutil.rmtree(coll_path)

    def test_copy_tree_with_replace_with_newrolename(self):
        """test copy_tree_with_replace"""

        pre_params = [
            {
                "keyword": "roles",
                "role_or_task_name": "linux-system-roles." + rolename,
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": rolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"{{ role_path }}/roles',
                "task_delim": "/",
                "task_subvalue": '__subrole_with__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"{{ role_path }}/roles',
                "task_delim": "/",
                "task_subvalue": 'subrole_no__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_tasks:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/tasks',
                "task_delim": "/",
                "task_subvalue": 'mytask.yml"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_vars:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/vars',
                "task_delim": "/",
                "task_subvalue": 'myvar.yml"',
            },
        ]
        post_params = [
            {
                "keyword": "roles",
                "role_or_task_name": prefix + "." + newrolename,
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": newrolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": newrolename,
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"' + prefix,
                "task_delim": ".",
                "task_subvalue": '__subrole_with__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": '"' + prefix,
                "task_delim": ".",
                "task_subvalue": 'subrole_no__"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_tasks:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/tasks',
                "task_delim": "/",
                "task_subvalue": 'mytask.yml"',
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_vars:",
                "task_subkey": "-",
                "task_value": '"{{ role_path }}/roles/subrole/vars',
                "task_delim": "/",
                "task_subvalue": 'myvar.yml"',
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
            "namespace": namespace,
            "collection": collection_name,
            "prefix": prefixdot,
            "subrole_prefix": "",
            "replace_dot": "_",
            "role_modules": set(),
            "src_owner": "linux-system-roles",
            "top_dir": dest_path,
            "extra_mapping_src_owner": [],
            "extra_mapping_src_role": [],
            "extra_mapping_dest_prefix": [],
            "extra_mapping_dest_role": [],
        }
        copy_tree_with_replace(
            role_path,
            coll_path,
            rolename,
            newrolename,
            MYTUPLE,
            transformer_args,
            isrole=True,
        )
        test_path = coll_path / "roles" / newrolename / "tasks"
        self.check_test_tree(
            test_path, test_yaml_str, post_params, ".yml", is_vertical=False
        )
        shutil.rmtree(coll_path)

    def test_copy_tree_with_replace_extra_mapping(self):
        """test copy_tree_with_replace with extra_mapping"""

        pre_params = [
            {
                "keyword": "roles",
                "role_or_task_name": "linux-system-roles." + otherroles[0],
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": otherroles[1],
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": "linux-system-roles",
                "task_delim": ".",
                "task_subvalue": otherroles[2],
            },
        ]
        post_params = [
            {
                "keyword": "roles",
                "role_or_task_name": otherprefix + "." + newotherroles[0],
                "task_subkey": "",
                "task_value": "",
                "task_delim": "",
                "task_subvalue": "",
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "import_role:",
                "task_subkey": "name:",
                "task_value": otherprefix,
                "task_delim": ".",
                "task_subvalue": newotherroles[1],
            },
            {
                "keyword": "tasks",
                "role_or_task_name": "include_role:",
                "task_subkey": "name:",
                "task_value": prefix,
                "task_delim": ".",
                "task_subvalue": newotherroles[2],
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
            "namespace": namespace,
            "collection": collection_name,
            "prefix": prefixdot,
            "subrole_prefix": "",
            "replace_dot": "_",
            "role_modules": set(),
            "src_owner": "linux-system-roles",
            "top_dir": dest_path,
            "extra_mapping_src_owner": [
                "linux-system-roles",
                "linux-system-roles",
                None,
            ],
            "extra_mapping_src_role": [
                otherroles[0],
                otherroles[1],
                otherroles[2],
            ],
            "extra_mapping_dest_prefix": [otherprefixdot, otherprefixdot, None],
            "extra_mapping_dest_role": [
                newotherroles[0],
                newotherroles[1],
                newotherroles[2],
            ],
        }
        copy_tree_with_replace(
            role_path,
            coll_path,
            rolename,
            rolename,
            MYTUPLE,
            transformer_args,
            isrole=True,
        )
        test_path = coll_path / "roles" / rolename / "tasks"
        print(coll_path)
        self.check_test_tree(
            test_path, test_yaml_str, post_params, ".yml", is_vertical=False
        )
        shutil.rmtree(coll_path)

    def test_import_replace(self):
        module_names = ["util0", "util1"]
        src_module_utils = []
        src_module_dir_core = Path(src_path) / rolename / "module_utils"
        src_module_dir_core.mkdir(parents=True, exist_ok=True)
        for mn in module_names:
            _src_module_util = src_module_dir_core / (mn + ".py")
            _src_module_util.touch(exist_ok=True)
            src_module_utils.append(_src_module_util)
        dest_base_dir = (
            Path(dest_path) / "ansible_collections" / namespace / collection_name
        )
        dest_module_dir_core = dest_base_dir / "plugins" / "module_utils"
        dest_module_dir_core.mkdir(parents=True, exist_ok=True)
        dest_module_utils = []
        for mn in module_names:
            _dest_module_util = dest_module_dir_core / mn
            _dest_module_util.touch(exist_ok=True)
            dest_module_utils.append(_dest_module_util)
        input = bytes(
            "import os\nimport ansible.module_utils.{0}  # noqa:E501\nimport ansible.module_utils.{1} as local1  # noqa:E501\nimport re\n".format(
                module_names[0], module_names[1]
            ),
            "utf-8",
        )
        expected = bytes(
            "import os\nimport ansible_collections.{0}.{1}.plugins.module_utils.{2}  # noqa:E501\nimport ansible_collections.{0}.{1}.plugins.module_utils.{3} as local1  # noqa:E501\nimport re\n".format(
                namespace, collection_name, module_names[0], module_names[1]
            ),
            "utf-8",
        )
        IMPORT_RE = re.compile(
            rb"(\bimport) (ansible\.module_utils\.)(\S+)(.*)(\s+#.+|.*)$", flags=re.M
        )
        config["namespace"] = namespace
        config["collection"] = collection_name
        config["role"] = rolename
        config["src_path"] = Path(src_path) / rolename
        config["dest_path"] = dest_base_dir
        config["module_utils_dir"] = dest_module_dir_core
        config["module_utils"] = [
            [b"util0"],
            [b"util1"],
        ]
        config["additional_rewrites"] = []
        output = IMPORT_RE.sub(import_replace, input)
        self.assertEqual(output, expected)
        shutil.rmtree(src_module_dir_core)
        shutil.rmtree(dest_module_dir_core)

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
            textwrap.dedent("""\
                # pylint: disable=import-error, no-name-in-module
                {0}.basic import AnsibleModule
                {0}.{1} import {2}
                {0}.{1} import MyError
                {0}.{1}.{3} import (
                    ArgUtil,
                    ArgValidator_ListConnections,
                    ValidationError,
                )  # noqa:E501
                {0}.{1}.{4} import Util
                {0}.{1} import {5}
                """).format(
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
            textwrap.dedent("""\
                # pylint: disable=import-error, no-name-in-module
                from ansible.module_utils.basic import AnsibleModule
                {0}.{1}.{2}.plugins.module_utils.{3} import {4}
                {0}.{1}.{2}.plugins.module_utils.{3}.__init__ import MyError
                {0}.{1}.{2}.plugins.module_utils.{3}.{5} import (
                    ArgUtil,
                    ArgValidator_ListConnections,
                    ValidationError,
                )  # noqa:E501
                {0}.{1}.{2}.plugins.module_utils.{3}.{6} import Util
                {0}.{1}.{2}.plugins.module_utils.{3} import {7}
                """).format(
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
            rb"(\bfrom) (ansible\.module_utils\.?)(\S+)? import (\(*(?:\n|\r\n)?)(.+)(\s+#.+|.*)$",
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
