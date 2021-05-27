#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright: (c) 2021, Red Hat, Inc.
# SPDX-License-Identifier: MIT

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

DEFAULT_GIT_SITE = "https://github.com"
DEFAULT_GIT_ORG = "linux-system-roles"


def update_collection(src_path, coll_rel, use_commit_hash):
    """
    Update refs in collection_release.yml.

    Use the latest tag for the ref.  If use_commit_hash is True
    and the latest commit is not tagged, use the commit hash of
    the latest commit for the ref.
    """
    for rolename in coll_rel:
        if rolename.startswith("_"):
            continue
        roledir = os.path.join(src_path, rolename)
        if os.path.isdir(roledir):
            subprocess.check_call(["git", "fetch"], cwd=roledir)
        else:
            git_url = "{}/{}/{}".format(
                DEFAULT_GIT_SITE,
                coll_rel[rolename].get("org", DEFAULT_GIT_ORG),
                coll_rel[rolename].get("repo", rolename),
            )
            subprocess.check_call(
                [
                    "git",
                    "-c",
                    "advice.detachedHead=false",
                    "clone",
                    "-q",
                    git_url,
                    roledir,
                ]
            )
        branch_output = subprocess.run(
            ["git", "branch", "-r"], cwd=roledir, encoding="utf-8", stdout=subprocess.PIPE
        )
        if branch_output.returncode != 0:
            raise subprocess.CalledProcessError(
                f"git branch -r failed - {branch_output.stdout} {branch_output.stderr}"
            )
        mmatch = re.search(r'origin/HEAD -> origin/(\w+)', branch_output.stdout)
        main_branch = mmatch.group(1)
        subprocess.check_call(
            ["bash", "-c", f"git checkout {main_branch}; git pull"],
            cwd=roledir,
        )
        describe_cmd = ["git", "describe", "--tags"]
        describe_output = subprocess.run(
            describe_cmd, cwd=roledir, encoding="utf-8", stdout=subprocess.PIPE
        )
        if describe_output.returncode != 0:
            raise subprocess.CalledProcessError(
                f"{describe_cmd} failed - {describe_output.stdout} {describe_output.stderr}"
            )
        describe_ary = describe_output.stdout.strip().split("-")
        if len(describe_ary) == 1 or not use_commit_hash:
            gitref = describe_ary[0]  # tag
        else:
            gitref = describe_ary[2][1:]  # commit hash - skip leading "g"
        coll_rel[rolename]["ref"] = gitref


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--collection-release-yml",
        type=open,
        default=os.environ.get("COLLECTION_RELEASE_YML", "collection_release.yml"),
        help="Path/filename for collection_release.yml",
    )
    parser.add_argument(
        "--src-path",
        type=str,
        default=os.environ.get("COLLECTION_SRC_PATH"),
        help="Path to the directory containing the local clone of the role repos",
    )
    parser.add_argument(
        "--use-commit-hash",
        default=False,
        action="store_true",
        help="Only use version tags for refs - if True, use latest HEAD commit hash if not tagged",
    )
    args = parser.parse_args()

    coll_rel = yaml.safe_load(args.collection_release_yml)
    coll_rel["_filename"] = args.collection_release_yml.name
    workdir = None
    if not args.src_path:
        workdir = tempfile.mkdtemp(suffix=".lsr", prefix="collection")
        args.src_path = workdir
    try:
        update_collection(args.src_path, coll_rel, args.use_commit_hash)
        with open(coll_rel["_filename"], "w") as crf:
            del coll_rel["_filename"]
            yaml.dump(coll_rel, crf)
    finally:
        if workdir:
            shutil.rmtree(workdir)


if __name__ == "__main__":
    sys.exit(main())
