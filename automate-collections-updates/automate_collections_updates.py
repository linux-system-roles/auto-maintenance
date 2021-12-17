#!/usr/bin/env python

import argparse
import os
import re
import shutil
import subprocess
import sys
import yaml
import glob


def set_rpkg_cmd(target_os):
    if target_os == "centos-stream":
        return "centpkg"
    elif target_os == "rhel":
        return "rhpkg"
    else:
        raise NameError(
            "The --target-os argument must be set to either centos-stream or rhel"
        )


def run_cmd(cmd, cwd):
    try:
        cmd_out = subprocess.run(cmd, stdout=subprocess.PIPE, encoding="utf-8", cwd=cwd)
        return cmd_out
    except subprocess.CalledProcessError as e:
        return e.output


def get_updated_collection_tarball(coll):
    coll_name = coll["name"]
    cmd = [
        "ansible-galaxy",
        "collection",
        "download",
        "-n",
        "-p",
        ".",
        coll_name,
    ]
    print(f"Downloading the {coll_name} collection tarball")
    cmd_out = run_cmd(cmd, os.path.curdir)
    pat = f"Collection '{coll_name}:([^']+)' was downloaded successfully"
    coll_latest_ver = re.search(pat, cmd_out.stdout).group(1)
    coll_tar = coll_name.replace(".", "-") + "-" + coll_latest_ver + ".tar.gz"
    if coll_latest_ver == coll["version"]:
        print(
            f"{coll_name} {coll_latest_ver} is of latest version, removing {coll_tar}"
        )
        os.remove(coll_tar)
        return {}
    else:
        print(f"{coll_name} has update {coll_latest_ver}")
        return {coll_name: coll_tar}


def clone_repo(rpkg_cmd, branch, repo):
    cmd = [
        rpkg_cmd,
        "clone",
        repo,
        "--branch",
        branch,
        "--",
        "--single-branch",
    ]
    print(f"Cloning {repo}")
    run_cmd(cmd, os.path.curdir)


def move_tarballs_to_repo(collection_tarballs, repo):
    print(f"Moving {', '.join(collection_tarballs.values())} to {repo}")
    for tarball in collection_tarballs.values():
        shutil.move(os.path.abspath(tarball), os.path.join(repo, tarball))


def upload_sources(rpkg_cmd, collection_tarballs, repo):
    print(f"Uploading {', '.join(collection_tarballs.values())} sources to {repo}")
    cmd = [rpkg_cmd, "upload", *collection_tarballs.values()]
    run_cmd(cmd, repo)


def replace_sources_in_spec(collection_tarballs, repo):
    print("Replacing sources in the spec file")
    for collection, tarball in collection_tarballs.items():
        with open(os.path.join(repo, "linux-system-roles.spec"), "r") as f:
            content = f.read()
            re.sub(collection + ".*$", tarball, content, flags=re.M)


def scratch_build(rpkg_cmd, repo):
    print("Building SRPM")
    cmd = [rpkg_cmd, "srpm"]
    run_cmd(cmd, repo)
    print("Performing the scratch build using the SRPM")
    srpm = glob.glob(os.path.join(repo, "*.src.rpm"))
    cmd = [rpkg_cmd, "scratch-build", "--srpm", os.path.basename(srpm[0]), "--nowait"]
    cmd_out = run_cmd(cmd, repo)
    pat = "Task info: (.*$)"
    build_url = re.search(pat, cmd_out.stdout).group(1)
    return build_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--requirements",
        type=str,
        default=os.environ.get("REQUIREMENTS_YML", "requirements.yml"),
        help="Path/filename for requirements.yml",
    )
    parser.add_argument(
        "--target-os",
        type=str,
        default=os.environ.get("TARGET_OS", "centos-stream"),
        help="The target OS to work on. Either centos-stream or rhel.",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=os.environ.get("BRANCH", "c9s"),
        help="The branch of the repository to work on.",
    )

    args = parser.parse_args()
    target_os = args.target_os
    branch = args.branch
    repo = "rhel-system-roles"
    rpkg_cmd = set_rpkg_cmd(target_os)
    hsh = yaml.safe_load(open(args.requirements))
    collection_tarballs = {}

    for coll in hsh["collections"]:
        collection_tarballs.update(get_updated_collection_tarball(coll))
    if len(collection_tarballs) != 0:
        clone_repo(rpkg_cmd, branch, repo)
        move_tarballs_to_repo(collection_tarballs, repo)
        upload_sources(rpkg_cmd, collection_tarballs, repo)
        replace_sources_in_spec(collection_tarballs, repo)
        build_url = scratch_build(rpkg_cmd, repo)
        # TODO: Share build_url somewhere
        print(f"See build progress at {build_url}")
        print("Cleaning up the downloaded repository")
        shutil.rmtree(repo)


if __name__ == "__main__":
    sys.exit(main())
