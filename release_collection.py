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

try:
    import yaml
except ImportError:
    import ruamel.yaml as yaml

import json

from distutils.version import StrictVersion

DEFAULT_GIT_SITE = "https://github.com"
DEFAULT_GIT_ORG = "linux-system-roles"


def run_cmd(cmdlist, cwd=None, env=None):
    """Run the given cmdlist using subprocess.  Debug log the output.
    If check is true, this function will work like check_call.
    The return value is like subprocess.run"""
    kwargs = {"env": os.environ}
    if env:
        kwargs["env"].update(env)
    rc = subprocess.run(
        cmdlist,
        cwd=cwd,
        encoding="utf-8",
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
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
        cur_v = StrictVersion(cur_ref)
        new_v = StrictVersion(new_ref)
        for idx in range(0, 3):
            if cur_v.version[idx] != new_v.version[idx]:
                versions_updated[idx] = True
    except ValueError as exc:
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


def process_ignore_and_lint_files(args, coll_dir):
    """Create collection ignore-VER.txt and .ansible-lint files from roles."""
    ignore_file_dir = os.path.join(coll_dir, "tests", "sanity")
    ansible_lint = {}
    for role_name in os.listdir(args.src_path):
        roledir = os.path.join(args.src_path, role_name)
        if (
            os.path.isdir(roledir)
            and os.path.isfile(os.path.join(roledir, "tasks", "main.yml"))
            and role_name in args.include
        ):
            for file_name in os.listdir(roledir):
                if file_name.startswith(".sanity-ansible-ignore-"):
                    if not os.path.isdir(ignore_file_dir):
                        os.mkdir(ignore_file_dir)
                    match = re.match(
                        r"^[.]sanity-ansible-ignore-(\d[\d.]+)[.]txt$", file_name
                    )
                    if match and match.groups() and match.group(1):
                        ver = match.group(1)
                        ignore_file = os.path.join(ignore_file_dir, f"ignore-{ver}.txt")
                        role_ignore_file = os.path.join(roledir, file_name)
                        with open(ignore_file, "a") as ign_fd:
                            with open(role_ignore_file, "r") as role_ign_fd:
                                ign_fd.write(role_ign_fd.read())
                elif file_name == ".ansible-lint":
                    role_ansible_lint = yaml.safe_load(
                        open(os.path.join(roledir, file_name))
                    )
                    for key, items in role_ansible_lint.items():
                        if key not in ansible_lint:
                            ansible_lint[key] = role_ansible_lint[key]
                            continue
                        for item in items:
                            if item not in ansible_lint[key]:
                                ansible_lint[key].append(item)
    if ansible_lint:
        yaml.safe_dump(ansible_lint, open(os.path.join(coll_dir, ".ansible-lint"), "w"))


def role_to_collection(
    args,
    rolename,
    namespace,
    collection_name,
    collection_readme,
):
    """Convert the role to collection format."""
    subrole_prefix = f"private_{rolename}_subrole_"
    _ = run_cmd(
        [
            sys.executable,
            "lsr_role2collection.py",
            "--src-owner",
            args.src_owner,
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


def update_galaxy_version(args, galaxy, versions_updated):
    if args.no_update:
        return
    if (
        not versions_updated[3]
        and any(versions_updated[0:3])
        and not args.no_auto_version
    ):
        galaxy_ver = StrictVersion(galaxy["version"])
        major, minor, micro = galaxy_ver.version
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


def build_collection(args, coll_dir, galaxy=None):
    collection_requirements = os.path.join(
        "lsr_role2collection", "collection_requirements.txt"
    )
    collection_requirements_dest = os.path.join(coll_dir, "requirements.txt")
    collection_bindep = os.path.join("lsr_role2collection", "collection_bindep.txt")
    collection_bindep_dest = os.path.join(coll_dir, "bindep.txt")
    # If --rpm, files such as galaxy.yml in coll_dir are being used.
    process_ignore_and_lint_files(args, coll_dir)
    if not args.rpm:
        if galaxy:
            with open(os.path.join(coll_dir, "galaxy.yml"), "w") as galaxy_fd:
                yaml.safe_dump(galaxy, galaxy_fd)
        else:
            shutil.copy(args.galaxy_yml.name, coll_dir)
        shutil.copy(args.collection_release_yml.name, coll_dir)
        if os.path.exists(collection_requirements):
            shutil.copy(collection_requirements, collection_requirements_dest)
        if os.path.exists(collection_bindep):
            shutil.copy(collection_bindep, collection_bindep_dest)
        # copy required dot files here, if any, before we remove them below

    # removing dot files/dirs
    keep_files = set([".ansible-lint"])
    for file_name in os.listdir(coll_dir):
        if file_name in keep_files:
            continue
        if re.match(r"^[.][a-zA-Z]+", file_name):
            full_name = os.path.join(coll_dir, file_name)
            if os.path.isdir(full_name):
                shutil.rmtree(full_name)
            else:
                os.unlink(full_name)

    if shutil.which("ansible-galaxy"):
        build_args = ["ansible-galaxy", "collection", "build", "-v"]
        if args.force:
            build_args.append("-f")
        build_args.append(coll_dir)
        _ = run_cmd(build_args, args.dest_path)
    else:
        logging.info("ansible-galaxy is skipped since it is not available.")


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
    collection_readme = os.path.join("lsr_role2collection", "collection_readme.md")
    # major, minor, micro, hash
    versions_updated = [False, False, False, False]
    for rolename in args.include:
        if not args.skip_git:
            cur_ref = coll_rel[rolename]["ref"]
            tag, cm_hash, tag_is_latest = get_latest_tag_hash(
                args,
                rolename,
                coll_rel[rolename]["ref"],
                coll_rel[rolename].get("org", args.src_owner),
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
                check_versions_updated(
                    cur_ref, coll_rel[rolename]["ref"], versions_updated
                )
        role_to_collection(
            args,
            rolename,
            galaxy["namespace"],
            galaxy["name"],
            collection_readme,
        )
        req_yml = os.path.join(args.src_path, rolename, "meta", "requirements.yml")
        if os.path.isfile(req_yml):
            req_yml_hsh = yaml.safe_load(open(req_yml))
            for coll in req_yml_hsh.get("collections", []):
                if isinstance(coll, dict):
                    coll_name = coll["name"]
                    coll_ver = coll.get("version", "*")
                else:
                    coll_name = coll
                    coll_ver = "*"
                galaxy_deps = galaxy.setdefault("dependencies", {})
                galaxy_deps[coll_name] = coll_ver
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

    build_collection(args, coll_dir, galaxy)


def find(path, name):
    """Find a file 'name' in or under the directory 'path'."""
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)


def process_rpm(args, default_galaxy, coll_rel):
    """
    Extract the contents of rpm.
    If the rpm contains galaxy.yml, use the file.
    Else if MANIFEST.json is found, use the info.
    Otherwise, it fails.
    Generate the collection artifact from the collection part
    of the extracted files.
    """
    workdir = tempfile.mkdtemp(suffix=".lsr", prefix="collection")
    cmdlist0 = ["rpm2cpio", args.rpm]
    p0 = subprocess.Popen(cmdlist0, cwd=workdir, stdout=subprocess.PIPE)
    cmdlist1 = ["cpio", "-id"]
    p1 = subprocess.Popen(cmdlist1, cwd=workdir, stdin=p0.stdout)
    p1.communicate()
    p0.communicate()
    logging.debug(f"{' '.join(cmdlist0)} returned {p0.returncode}")
    logging.debug(f"{' '.join(cmdlist1)} returned {p1.returncode}")
    if p0.returncode != 0:
        raise subprocess.CalledProcessError(
            p0.returncode, cmdlist0, p0.stdout, p0.stderr
        )
    if p1.returncode != 0:
        raise subprocess.CalledProcessError(
            p1.returncode, cmdlist1, p1.stdout, p1.stderr
        )

    tmp_coll = "{}/usr/share/ansible/collections/ansible_collections".format(workdir)
    if not os.path.exists(tmp_coll):
        raise Exception("Failed to extract {} from {}".format(tmp_coll, args.rpm))
    shutil.move(tmp_coll, workdir)
    shutil.rmtree("{}/usr".format(workdir))

    # If exists, use galaxy.yml in rpm
    galaxy_yml = find(workdir, "galaxy.yml")
    if galaxy_yml:
        args.galaxy_yml.close()
        args.galaxy_yml = open(galaxy_yml, "r")
        coll_dir = os.path.dirname(galaxy_yml)
        # override galaxy with the one in rpm
        galaxy = yaml.safe_load(args.galaxy_yml)
    # Otherwise, use the values in MANIFEST.json, if any.
    else:
        manifest_json = find(workdir, "MANIFEST.json")
        if manifest_json:
            with open(manifest_json) as mj:
                mj_contents = json.load(mj)
            galaxy = default_galaxy
            galaxy["namespace"] = mj_contents["collection_info"]["namespace"]
            galaxy["name"] = mj_contents["collection_info"]["name"]
            galaxy["version"] = mj_contents["collection_info"]["version"]
            galaxy["authors"] = mj_contents["collection_info"]["authors"]
            galaxy["description"] = mj_contents["collection_info"]["description"]
            coll_dir = os.path.dirname(manifest_json)
            new_galaxy_yml = "{}/galaxy.yml".format(coll_dir)
            args.galaxy_yml.close()
            args.galaxy_yml = open(new_galaxy_yml, "w")
            yaml.dump(galaxy, args.galaxy_yml)
            os.remove(manifest_json)
            files_json = "{}/FILES.json".format(coll_dir)
            if os.path.exists(files_json):
                os.remove(files_json)
        else:
            raise Exception("No galaxy.yml nor MANIFEST.json in {}".format(args.rpm))

    args.src_path = coll_dir
    build_collection(args, coll_dir)
    shutil.rmtree(workdir)

    return galaxy


def check_collection(args, galaxy):
    coll_file = (
        f"{args.dest_path}/{galaxy['namespace']}-{galaxy['name']}-"
        f"{galaxy['version']}.tar.gz"
    )
    gi_config = "lsr_role2collection/galaxy-importer.cfg"
    if os.path.exists(coll_file) and os.path.exists(gi_config):
        _ = run_cmd(
            [sys.executable, "-m", "galaxy_importer.main", coll_file],
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
        "--src-owner",
        type=str,
        default=os.environ.get("COLLECTION_SRC_OWNER", DEFAULT_GIT_ORG),
        help="Name of the role owner, in legacy role format OWNER.ROLENAME",
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
    parser.add_argument(
        "--rpm",
        default=None,
        type=str,
        help="Path to the rpm file for the input.",
    )
    parser.add_argument(
        "--skip-git",
        default=False,
        action="store_true",
        help="True when work with local src.",
    )
    parser.add_argument(
        "--skip-check",
        default=False,
        action="store_true",
        help="True when skip check with galaxy-importer.",
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

    # --rpm rpm_file is given.
    if args.rpm:
        # Check rpm_file exists.
        if not os.path.exists(args.rpm):
            logging.error("{}: No such file given with --rpm".format(args.rpm))
            return
        # If rpm_file is relative path, convert it to absolute path.
        if not os.path.isabs(args.rpm):
            rpm_dir = os.path.abspath(os.getcwd())
            args.rpm = "{0}/{1}".format(rpm_dir, args.rpm)

    workdir = None
    if not args.rpm and not args.src_path:
        workdir = tempfile.mkdtemp(suffix=".lsr", prefix="collection")
        args.src_path = workdir
    try:
        if args.rpm:
            galaxy = process_rpm(args, galaxy, coll_rel)
        else:
            update_collection(args, galaxy, coll_rel)
        if not args.skip_check:
            check_collection(args, galaxy)
        else:
            logging.debug("check_collection is skipped.")
        if args.publish:
            publish_collection(args, galaxy)
        logging.info("Done.")
    finally:
        if workdir:
            shutil.rmtree(workdir)


if __name__ == "__main__":
    sys.exit(main())
