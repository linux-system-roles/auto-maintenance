#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright: (c) 2020, Red Hat, Inc.
# SPDX-License-Identifier: MIT
"""This script is used to:
* Check all of the roles for new versions, and update `collection_release.yml`
  with the updated `ref` fields.
* Convert the roles to collection using [lsr_role2collection.py](#lsr_role2collectionpy)
* Update the version in `galaxy.yml`
* Build the collection file using `ansible-galaxy collection build`
* Check the collection using `galaxy-importer`
* Publish the collection using `ansible-galaxy collection publish`
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

from packaging.version import Version, InvalidVersion

DEFAULT_GIT_SITE = "https://github.com"
DEFAULT_GIT_ORG = "linux-system-roles"


def run_cmd(cmdlist, cwd=None, env=None):
    """Run the given cmdlist using subprocess.  Debug log the output.
    If check is true, this function will work like check_call.
    The return value is like subprocess.run"""
    kwargs = {}
    if env:
        kwargs["env"] = env
    rc = subprocess.run(
        cmdlist, cwd=cwd, encoding="utf-8", check=False, capture_output=True, **kwargs
    )
    logging.debug(
        f"{' '.join(cmdlist)} returned {rc.returncode} stdout {rc.stdout} stderr {rc.stderr}"
    )
    if rc.returncode != 0:
        raise subprocess.CalledProcessError(
            rc.returncode, cmdlist, rc.stdout, rc.stderr
        )
    return rc


def check_versions_updated(cur_ref, new_ref, versions_updated):
    """Compare versions and update list.

    If cur_ref and new_ref are both valid semantic versions,
    compare them, and indicate in versions_updated if the major,
    minor, and/or micro versions were updated."""

    try:
        cur_v = Version(cur_ref)
        new_v = Version(new_ref)
        if cur_v.major != new_v.major:
            versions_updated[0] = True
        if cur_v.minor != new_v.minor:
            versions_updated[1] = True
        if cur_v.micro != new_v.micro:
            versions_updated[2] = True
    except InvalidVersion as exc:
        logging.debug(f"Could not compare version {cur_ref} to {new_ref}: {exc}")
        if cur_ref != new_ref:
            versions_updated[3] = True


def get_latest_tag_hash(args, rolename, cur_ref, org, repo):
    """
    Get the latest tag, hash, and tag_is_latest from the upstream repo.

    Clone and/or update the local copies of the repos.  Get
    the latest tag and/or commit hash for each repo.  Indicate if
    the tag is the latest commit.
    """
    roledir = os.path.join(args.src_path, rolename)
    # clone and/or update role repo
    if os.path.isdir(roledir):
        _ = run_cmd(["git", "fetch"], roledir)
    else:
        _ = run_cmd(
            [
                "git",
                "-c",
                "advice.detachedHead=false",
                "clone",
                "-q",
                f"{DEFAULT_GIT_SITE}/{org}/{repo}",
                roledir,
            ],
        )
    branch_output = run_cmd(["git", "branch", "-r"], roledir)
    # determine what is the main branch, check it out, and update it
    mmatch = re.search(r"origin/HEAD -> origin/(\w+)", branch_output.stdout)
    main_branch = mmatch.group(1)
    _ = run_cmd(["bash", "-c", f"git checkout {main_branch}; git pull"], roledir)
    if args.no_update:
        # make sure cur_ref is checked out
        _ = run_cmd(["git", "checkout", cur_ref], roledir)
        return (None, None, None)
    # see if there have been any commits since the last time we checked
    count_output = run_cmd(
        ["bash", "-c", f"git log --oneline {cur_ref}.. | wc -l"],
        roledir,
    )
    if count_output.stdout == "0":
        logging.debug(f"no changes to role {rolename} since ref {cur_ref}")
        return (None, None, None)
    # get latest tag and commit hash
    describe_cmd = ["git", "describe", "--tags", "--long", "--abbrev=40"]
    describe_output = run_cmd(describe_cmd, roledir)
    tag, n_commits, g_hash = describe_output.stdout.strip().rsplit("-", 2)
    # commit hash - skip leading "g"
    return (tag, g_hash[1:], n_commits == "0")


def role_to_collection(
    args,
    rolename,
    namespace,
    collection_name,
    collection_readme,
    ignore_file_dir,
    ignore_file,
):
    roledir = os.path.join(args.src_path, rolename)
    subrole_prefix = f"private_{rolename}_subrole_"
    _ = run_cmd(
        [
            "python",
            "lsr_role2collection.py",
            "--src-owner",
            DEFAULT_GIT_ORG,
            "--role",
            rolename,
            "--src-path",
            args.src_path,
            "--dest-path",
            args.dest_path,
            "--namespace",
            namespace,
            "--collection",
            collection_name,
            "--subrole-prefix",
            subrole_prefix,
            "--readme",
            collection_readme,
        ]
    )
    role_ignore_file = os.path.join(roledir, ".sanity-ansible-ignore-2.9.txt")
    if os.path.isfile(role_ignore_file):
        if not os.path.isdir(ignore_file_dir):
            os.mkdir(ignore_file_dir)
        with open(ignore_file, "a") as ign_fd:
            with open(role_ignore_file, "r") as role_ign_fd:
                ign_fd.write(role_ign_fd.read())


def update_galaxy_version(args, galaxy, versions_updated):
    if args.no_update:
        return
    if (
        not versions_updated[3]
        and any(versions_updated[0:3])
        and not args.no_auto_version
    ):
        galaxy_ver = Version(galaxy["version"])
        major, minor, micro = galaxy_ver.release
        if versions_updated[0]:
            major = major + 1
            minor = 0
            micro = 0
        elif versions_updated[1]:
            minor = minor + 1
            micro = 0
        elif versions_updated[2]:
            micro = micro + 1
        galaxy["version"] = f"{major}.{minor}.{micro}"
    elif args.new_version:
        galaxy["version"] = args.new_version
    else:
        raise Exception(
            "No new-version given and cannot auto-update version.  "
            "Please examine the changes to the collection, determine what "
            "the new semantic version will be, and re-run this script with "
            "the --new-version argument"
        )
    # not worth trying to figure out how to do a round-trip yaml write here
    # not work using ruamel here
    # this is simple enough for re.sub
    with open(args.galaxy_yml.name) as gf:
        galaxy_str = gf.read()
        galaxy_str = re.sub(
            r"^version:.*$", f'version: "{galaxy["version"]}"', galaxy_str, flags=re.M
        )
    with open(args.galaxy_yml.name, "w") as gf:
        gf.write(galaxy_str)


def build_collection(args, coll_dir, ignore_file):
    collection_requirements = os.path.join(
        "lsr_role2collection", "collection_requirements.txt"
    )
    collection_requirements_dest = os.path.join(coll_dir, "requirements.txt")
    collection_bindep = os.path.join("lsr_role2collection", "collection_bindep.txt")
    collection_bindep_dest = os.path.join(coll_dir, "bindep.txt")
    ignore_file_src = os.path.join("lsr_role2collection", "extra-ignore-2.9.txt")
    ansible_lint = os.path.join("lsr_role2collection", ".ansible-lint")
    shutil.copy(args.galaxy_yml.name, coll_dir)
    shutil.copy(args.collection_release_yml.name, coll_dir)
    if os.path.exists(collection_requirements):
        shutil.copy(collection_requirements, collection_requirements_dest)
    if os.path.exists(collection_bindep):
        shutil.copy(collection_bindep, collection_bindep_dest)
    # removing dot files/dirs
    _ = run_cmd(["bash", "-c", f"rm -rf {coll_dir}/.[A-Za-z]*"])
    # copy required dot files like .ansible-lint here
    if os.path.exists(ansible_lint):
        shutil.copy(ansible_lint, coll_dir)
    if os.path.exists(ignore_file):
        with open(ignore_file, "a") as ign_fd:
            with open(ignore_file_src, "r") as role_ign_fd:
                ign_fd.write(role_ign_fd.read())

    build_args = ["ansible-galaxy", "collection", "build", "-v"]
    if args.force:
        build_args.append("-f")
    build_args.append(coll_dir)
    _ = run_cmd(build_args, args.dest_path)


def update_collection(args, galaxy, coll_rel):
    """
    Update refs in collection_release.yml.

    Use the latest tag for the ref.  If use_commit_hash is True
    and the latest commit is not tagged, use the commit hash of
    the latest commit for the ref.
    """
    coll_dir = os.path.join(
        args.dest_path, "ansible_collections", galaxy["namespace"], galaxy["name"]
    )
    if os.path.isdir(coll_dir):
        if args.force:
            shutil.rmtree(coll_dir)
        else:
            raise Exception(
                "collection dest_path {} already exists - remove or use --force".format(
                    coll_dir
                )
            )
    os.makedirs(coll_dir, exist_ok=True)
    ignore_file_dir = os.path.join(coll_dir, "tests", "sanity")
    ignore_file = os.path.join(ignore_file_dir, "ignore-2.9.txt")
    collection_readme = os.path.join("lsr_role2collection", "collection_readme.md")
    # major, minor, micro, hash
    versions_updated = [False, False, False, False]
    for rolename in args.include:
        cur_ref = coll_rel[rolename]["ref"]
        tag, cm_hash, tag_is_latest = get_latest_tag_hash(
            args,
            rolename,
            coll_rel[rolename]["ref"],
            coll_rel[rolename].get("org", DEFAULT_GIT_ORG),
            coll_rel[rolename].get("repo", rolename),
        )
        if tag or cm_hash:
            if tag_is_latest or not args.use_commit_hash:
                coll_rel[rolename]["ref"] = tag
            else:
                coll_rel[rolename]["ref"] = cm_hash
            if not tag_is_latest and not args.no_auto_version:
                logging.info(
                    f"role {rolename} tag {tag} is not the latest commit {cm_hash} "
                    "- cannot use auto version"
                )
            check_versions_updated(cur_ref, coll_rel[rolename]["ref"], versions_updated)
        role_to_collection(
            args,
            rolename,
            galaxy["namespace"],
            galaxy["name"],
            collection_readme,
            ignore_file_dir,
            ignore_file,
        )
    if not args.no_update:
        if not any(versions_updated):
            logging.info(
                "Nothing in the collection was changed - current collection is up-to-date"
            )
            return
        update_galaxy_version(args, galaxy, versions_updated)
        if not args.no_update:
            with open(args.collection_release_yml.name, "w") as crf:
                yaml.safe_dump(coll_rel, crf, sort_keys=True)

    build_collection(args, coll_dir, ignore_file)


def check_collection(args, galaxy):
    coll_file = (
        f"{args.dest_path}/{galaxy['namespace']}-{galaxy['name']}-"
        f"{galaxy['version']}.tar.gz"
    )
    gi_config = "lsr_role2collection/galaxy-importer.cfg"
    if os.path.exists(coll_file) and os.path.exists(gi_config):
        _ = run_cmd(
            ["python", "-m", "galaxy_importer.main", coll_file],
            args.dest_path,
            {"GALAXY_IMPORTER_CONFIG": gi_config},
        )


def publish_collection(args, galaxy):
    coll_file = (
        f"{args.dest_path}/{galaxy['namespace']}-{galaxy['name']}-"
        f"{galaxy['version']}.tar.gz"
    )
    if os.path.exists(coll_file):
        cmd = ["ansible-galaxy", "collection", "publish"]
        if args.no_wait:
            cmd.append("--no-wait")
        else:
            cmd.append("-vv")
        cmd.append(coll_file)
        _ = run_cmd(cmd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--galaxy-yml",
        type=open,
        default=os.environ.get("GALAXY_YML", "galaxy.yml"),
        help="Path/filename for galaxy.yml",
    )
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
        "--dest-path",
        type=str,
        default=os.environ.get(
            "COLLECTION_DEST_PATH", os.environ.get("HOME") + "/.ansible/collections"
        ),
        help=(
            "Path to collection base directory; collection directory structure "
            "will be created in DIR/ansible_collection/NAMESPACE/COLLECTION_NAME; "
            "collection package file will be created in DIR; "
            "default to ${HOME}/.ansible/collections"
        ),
    )
    parser.add_argument(
        "--force",
        default=False,
        action="store_true",
        help="Remove collection destination dir and file before creating",
    )
    parser.add_argument(
        "--no-auto-version",
        default=False,
        action="store_true",
        help=(
            "The script will try to automatically determine the new collection version based "
            "on the semantic version changes in the versions of the tags in the "
            "role repos.  If you do not want this, add this parameter."
        ),
    )
    parser.add_argument(
        "--new-version",
        default=None,
        type=str,
        help="The new semantic version to use for the collection.",
    )
    parser.add_argument(
        "--no-update",
        default=False,
        action="store_true",
        help=(
            "By default, this script will update collection-release-yml "
            "to the latest tags or commit hashes in the upstream role.  Set "
            "this flag if you want to manually update collection-release-yml "
            "and build the collection from that file."
        ),
    )
    parser.add_argument(
        "--publish",
        default=False,
        action="store_true",
        help="Publish the collection to Galaxy.",
    )
    parser.add_argument(
        "--no-wait",
        default=False,
        action="store_true",
        help="Do not wait for the collection to be published.  Default is to wait.",
    )
    parser.add_argument(
        "--use-commit-hash",
        default=False,
        action="store_true",
        help=(
            "By default, only version tags are used for refs - if True, use latest HEAD"
            " commit hash if not tagged"
        ),
    )
    parser.add_argument(
        "--debug",
        default=False,
        action="store_true",
        help="Turn on debug logging.",
    )
    parser.add_argument(
        "--exclude",
        default=[],
        action="append",
        help="Roles to exclude",
    )
    parser.add_argument(
        "--include",
        default=[],
        action="append",
        help="Roles to include",
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    galaxy = yaml.safe_load(args.galaxy_yml)
    args.galaxy_yml.close()
    coll_rel = yaml.safe_load(args.collection_release_yml)
    args.collection_release_yml.close()
    if not args.include:
        args.include = sorted(list(coll_rel.keys()))
    for item in args.exclude:
        del args.include[item]
    workdir = None
    if not args.src_path:
        workdir = tempfile.mkdtemp(suffix=".lsr", prefix="collection")
        args.src_path = workdir
    try:
        update_collection(args, galaxy, coll_rel)
        check_collection(args, galaxy)
        if args.publish:
            publish_collection(args, galaxy)
        logging.info("Done.")
    finally:
        if workdir:
            shutil.rmtree(workdir)


if __name__ == "__main__":
    sys.exit(main())
