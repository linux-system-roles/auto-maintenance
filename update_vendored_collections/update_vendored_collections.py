#!/usr/bin/env python

import argparse
import os
import re
import shutil
import subprocess
import sys
import yaml
import glob


def run_cmd(cmd, cwd):
    try:
        cmd_out = subprocess.run(
            cmd, encoding="utf-8", cwd=cwd, check=True, capture_output=True
        )
        return cmd_out
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.stderr)


def get_updated_collection_tarball(coll):
    coll_name = coll["name"]
    cmd = [
        "ansible-galaxy",
        "collection",
        "download",
        "--no-deps",
        "--download-path",
        ".",
        coll_name,
    ]
    print(f"Downloading the {coll_name} collection tarball")
    cmd_out = run_cmd(cmd, os.path.curdir)
    pat = f"Collection '{coll_name}:([^']+)' was downloaded successfully"
    coll_latest_ver = re.search(pat, cmd_out.stdout).group(1)
    coll_tar = coll_name.replace(".", "-") + "-" + coll_latest_ver + ".tar.gz"
    if "Skipping Galaxy server" in cmd_out.stderr:
        os.remove(coll_tar)
        raise RuntimeError(
            "Cannot access Automation Hub, check if the token is provided"
        )
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
    if os.path.exists(repo):
        print(f"{repo} directory already exists, removing")
        shutil.rmtree(repo)
    # --anonymous is required to clone over HTTPS and avoid SSH authentication
    cmd = [
        rpkg_cmd,
        "clone",
        "--anonymous",
        repo,
        "--branch",
        branch,
        "--",
        "--single-branch",
    ]
    print(f"Cloning {repo}")
    run_cmd(cmd, os.path.curdir)


def copy_tarballs_to_repo(collection_tarballs, repo):
    print(f"Copying {', '.join(collection_tarballs.values())} to {repo}")
    for tarball in collection_tarballs.values():
        shutil.copy(os.path.abspath(tarball), os.path.join(repo, tarball))


def replace_sources_in_spec(collection_tarballs, repo):
    print("Replacing sources in the spec file")
    for collection, tarball in collection_tarballs.items():
        with open(os.path.join(repo, "linux-system-roles.spec"), "r+") as f:
            content = f.read()
            content = re.sub(collection.replace(".", "-") + ".*$", tarball, content, flags=re.MULTILINE)
            f.seek(0)
            f.write(content)
            f.truncate()


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
        default=os.environ.get("REQUIREMENTS_YML", "vendored_collections.yml"),
        help="Path/filename for file containing vendored collections in the requirements.yml format",
    )

    args = parser.parse_args()
    centos_repo = "rhel-system-roles"
    fedora_repo = "linux-system-roles"
    centpkg_cmd = "centpkg"
    fedpkg_cmd = "fedpkg"
    hsh = yaml.safe_load(open(args.requirements))
    collection_tarballs = {}

    for coll in hsh["collections"]:
        collection_tarballs.update(get_updated_collection_tarball(coll))
    if len(collection_tarballs) != 0:
        clone_repo(centpkg_cmd, "c9s", centos_repo)
        copy_tarballs_to_repo(collection_tarballs, centos_repo)
        replace_sources_in_spec(collection_tarballs, centos_repo)
        build_url = scratch_build(centpkg_cmd, centos_repo)
        # TODO: Share build_url somewhere
        print(f"See build progress at {build_url}")
        clone_repo(fedpkg_cmd, "rawhide", fedora_repo)
        copy_tarballs_to_repo(collection_tarballs, fedora_repo)
        replace_sources_in_spec(collection_tarballs, fedora_repo)
        print(f"Removing the {centos_repo} repository")
        shutil.rmtree(centos_repo)
        print(f"Removing the {collection_tarballs} collection tarballs")
        for tarball in collection_tarballs.values():
            os.remove(tarball)


if __name__ == "__main__":
    sys.exit(main())
