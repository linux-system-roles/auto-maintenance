#!/usr/bin/env python
"""Update requirements.yml with latest collection versions."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import yaml
import tarfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vendored_collections",
        type=str,
        default=os.environ.get("VENDORED_COLLECTIONS", "vendored_collections.yml"),
        help="Path/filename for vendored_collections.yml",
    )
    parser.add_argument(
        "--target-os",
        type=str,
        default=os.environ.get("TARGET_OS", "centos-stream"),
        help="The target OS to work on. Either centos-stream or rhel.",
    )
    parser.add_argument(
        "--repo-url",
        type=str,
        default=os.environ.get("REPO_URL"),
        help="The URL to the repository to work on.",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=os.environ.get("BRANCH"),
        help="The branch of the repository to work on.",
    )
    args = parser.parse_args()

    hsh = yaml.safe_load(open(args.vendored_collections))
    collection_tarballs = {}

    target_os = args.target_os
    repo_url = args.repo_url
    branch = args.branch
    repo = "rhel-system-roles"
    if target_os == "centos-stream":
        pkg_command = "centpkg"
    elif target_os == "rhel":
        pkg_command = "rhpkg"
    else:
        sys.exit(
            "The --target-os argument must be set to either centos-stream or rhel"
        )

    for coll in hsh["collections"]:
        coll_install_dir = tempfile.mkdtemp()
        coll_name = coll["name"]
        coll_content_values = set()
        for values in list(coll["content"].values()):
            for value in values:
                coll_content_values.add(value)
        coll_dir = os.path.join(
            coll_install_dir,
            "ansible_collections",
            coll_name.split(".")[0],
            coll_name.split(".")[1],
        )
        cmd = [
            "ansible-galaxy",
            "collection",
            "install",
            "-n",
            "-vv",
            "--force",
            "-p",
            coll_install_dir,
            coll_name,
        ]
        try:
            """Get the latest version of the given collection"""
            print(f"Installing the {coll_name} collection.")
            out = subprocess.run(cmd, stdout=subprocess.PIPE, encoding="utf-8")
            pat = f"Installing '{coll_name}:([^']+)' to"
            coll_latest_ver = re.search(pat, out.stdout).group(1)
            if coll_latest_ver == coll["version"]:
                print(f"{coll_name} is of latest version. Skipping.")
            else:
                print(f"Searching {coll_name} changelog for updates.")
                for value in coll_content_values:
                    changelog = yaml.safe_load(
                        open(os.path.join(coll_dir, "changelogs/changelog.yaml"))
                    )
                    item = re.search(
                        value, yaml.dump(changelog["releases"][coll_latest_ver])
                    )
                    if item is not None:
                        print(
                            f"{item.group()} is mentioned in latest {coll_name} changelog."
                        )
                        """Add coll_name key to collection_tarballs"""
                        collection_tarballs[coll_name] = ""
            if coll_name in collection_tarballs.keys():
                tar = tarfile.open(
                    coll_name.replace(".", "-") + "-" + coll_latest_ver + ".tar.gz",
                    "w:gz",
                )
                """Create collection tarballs"""
                for name in os.listdir(coll_dir):
                    tar.add(name=str(os.path.join(coll_dir, name)), arcname=str(name))
                tar.close()
                collection_tarballs[coll_name] = os.path.basename(tar.name)
                print(f"Collection tarball {os.path.basename(tar.name)} is created.")
            else:
                print(
                    f"Latest {coll_name} changelog does not list updates for the vendored modules."
                )
        finally:
            shutil.rmtree(coll_install_dir)
    if len(collection_tarballs) != 0:
        try:
            print(
                [
                    "git",
                    "clone",
                    repo_url,
                    "--branch",
                    branch,
                    "--single-branch",
                ]
            )
            subprocess.run(
                [
                    "git",
                    "clone",
                    repo_url,
                    "--branch",
                    branch,
                    "--single-branch",
                ]
            )
            """Move tarballs to the repo directory"""
            for tarball in collection_tarballs.values():
                shutil.move(os.path.abspath(tarball), os.path.join(repo, tarball))
            """Upload new sources"""
            os.chdir(repo)
            subprocess.run(
                [pkg_command, "upload", " ".join(collection_tarballs.values())]
            )
            """Replace sources in the spec file"""
            for collection, tarball in collection_tarballs.items():
                with open("linux-system-roles.spec", "r") as f:
                    content = f.read()
                    re.sub(collection + ".*$", tarball, content, flags=re.M)
            if pkg_command == "centpkg":
                out = subprocess.run(
                    [pkg_command, "scratch-build", "--nowait"],
                    stdout=subprocess.PIPE,
                    encoding="utf-8",
                )
            elif pkg_command == "rhpkg":
                out = subprocess.run(
                    [pkg_command, "scratch-build", "--srpm", "--nowait"],
                    stdout=subprocess.PIPE,
                    encoding="utf-8",
                )
            pat = "Task info: (.*$)"
            build_url = re.search(pat, out.stdout).group(1)
            print(f"Build info: {build_url}")
            # TODO: Share build_url somewhere
        finally:
            print("Cleaning up the downloaded repository")
            # os.chdir("..")
            # shutil.rmtree(repo)


if __name__ == "__main__":
    sys.exit(main())
