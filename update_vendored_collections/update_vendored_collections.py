#!/usr/bin/env python

import argparse
import os
import re
import shutil
import subprocess
import sys
import yaml
import glob
import datetime


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


def clone_repo(repo, branch, rpkg_cmd):
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


def spec_replace_sources(content, collection_tarballs):
    print("Replacing sources in the spec file")
    for collection, tarball in collection_tarballs.items():
        content = re.sub(
            collection.replace(".", "-") + ".*$", tarball, content, flags=re.MULTILINE
        )
    return content


def spec_add_changelog(content, collection_tarballs, lines):
    print("Adding changelog entry to the spec file")
    for line in lines:
        if line == "%changelog\n":
            current_version = re.sub(".*> - ", "", next(lines)).strip()
            new_version = current_version[:-1] + str(
                int(re.sub(".*-", "", current_version)) + 1
            )
            changelog_date = datetime.datetime.now().strftime("%a %b %d %Y")
            meta_line = f"* {changelog_date} Sergei Petrosian <spetrosi@redhat.com> - {new_version}\n"
            comment_line = f"- Update {', '.join(collection_tarballs.keys())}\n\n"
            content = re.sub(
                "%changelog\n", "%changelog\n" + meta_line + comment_line, content
            )
            return content


def update_spec(collection_tarballs, repo):
    with open(os.path.join(repo, "linux-system-roles.spec"), "r") as f:
        content = f.read()
        f.seek(0)
        lines = iter(f.readlines())
    content = spec_replace_sources(content, collection_tarballs)
    content = spec_add_changelog(content, collection_tarballs, lines)
    with open(os.path.join(repo, "linux-system-roles.spec"), "w") as f:
        f.write(content)


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


def repo_configure_credentials(repo, repo_user, repo_email):
    print(f"Configuring the {repo} repository to use {repo_user} credentials")
    cmd = ["git", "config", "user.name", repo_user]
    run_cmd(cmd, repo)
    cmd = ["git", "config", "user.email", repo_email]
    run_cmd(cmd, repo)


def repo_add_remote(repo, repo_user, repo_url):
    print(f"Adding {repo_user} remote to the {repo} repository")
    cmd = ["git", "remote"]
    remotes = run_cmd(cmd, repo)
    if repo_user not in remotes.stdout:
        cmd = ["git", "remote", "add", repo_user, repo_url]
        run_cmd(cmd, repo)
    else:
        print(f"Remote {repo_user} already exists, continuing")


def repo_commit_changes(repo, commit_message, branch, files_list):
    print(f"Checking out the {branch} branch")
    cmd = ["git", "checkout", "-B", branch]
    run_cmd(cmd, repo)
    print(f"Staging {', '.join(files_list)}")
    for file in files_list:
        cmd = ["git", "add", file]
        run_cmd(cmd, repo)
    print("Committing changes")
    cmd = ["git", "commit", "--message", commit_message]
    run_cmd(cmd, repo)


def repo_force_push(repo, remote, branch):
    print(f"Pushing to the {remote}/{branch} branch")
    cmd = ["git", "push", remote, branch, "--force"]
    run_cmd(cmd, repo)


def update_vendored_collections_yml(hsh, collection_tarballs, requirements):
    collections_versions = {}
    updated_requirements = {"collections": []}
    for collection, tarball in collection_tarballs.items():
        version = re.sub(".tar.gz", "", re.sub(".*-", "", tarball))
        collections_versions.update({collection: version})
    for coll in hsh["collections"]:
        for collection, version in collections_versions.items():
            if coll["name"] == collection:
                updated_requirements["collections"].append(
                    {"name": coll["name"], "version": version}
                )
    print(f"Update {requirements} with fresh collections versions")
    with open(requirements, "w") as f:
        yaml.dump(updated_requirements, f)


def delete_files(centos_repo, fedora_repo, collection_tarballs):
    for repo in centos_repo, fedora_repo:
        print(f"Removing the {repo} repository")
        shutil.rmtree(repo)
    print(f"Removing the {', '.join(collection_tarballs.values())} collection tarballs")
    for tarball in collection_tarballs.values():
        os.remove(tarball)


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
    centos_branch = "c9s"
    fedora_repo = "linux-system-roles"
    fedora_branch = "rawhide"
    fedora_user = "linuxsystemroles"
    fedora_email = "systemroles-owner@lists.fedorahosted.org"
    fedora_fork_url = "ssh://linuxsystemroles@pkgs.fedoraproject.org/forks/linuxsystemroles/rpms/linux-system-roles.git"
    fedora_push_branch = "update-vendored-collections"
    auto_maintenance_repo = sys.path[0]
    auto_maintenance_remote = "origin"
    auto_maintenance_push_branch = fedora_push_branch
    centpkg_cmd = "centpkg"
    fedpkg_cmd = "fedpkg"
    requirements = args.requirements
    hsh = yaml.safe_load(open(requirements))
    collection_tarballs = {}

    for coll in hsh["collections"]:
        collection_tarballs.update(get_updated_collection_tarball(coll))
    if len(collection_tarballs) != 0:
        """Make a CentOS scratch build"""
        clone_repo(centos_repo, centos_branch, centpkg_cmd)
        copy_tarballs_to_repo(collection_tarballs, centos_repo)
        update_spec(collection_tarballs, centos_repo)
        build_url = scratch_build(centpkg_cmd, centos_repo)

        """Push spec file with updated collection tarballs to Fedora"""
        clone_repo(fedora_repo, fedora_branch, fedpkg_cmd)
        copy_tarballs_to_repo(collection_tarballs, fedora_repo)
        update_spec(collection_tarballs, fedora_repo)
        repo_configure_credentials(fedora_repo, fedora_user, fedora_email)
        repo_add_remote(fedora_repo, fedora_user, fedora_fork_url)
        fedora_commit_message = f"""
Update vendored collections tarballs

The following tarball(s) have updates:
{', '.join(collection_tarballs.keys())}
The CentOS scratch build URL:
{build_url}
"""
        repo_commit_changes(
            fedora_repo,
            fedora_commit_message,
            fedora_push_branch,
            ["linux-system-roles.spec"],
        )
        repo_force_push(fedora_repo, fedora_user, fedora_push_branch)

        """Update vendored_collections.yml and push to GitHub"""
        update_vendored_collections_yml(hsh, collection_tarballs, requirements)
        open_pr_url = (
            "https://src.fedoraproject.org/fork/linuxsystemroles/rpms/linux-system-roles/diff/"
            "rawhide..update-vendored-collections"
        )
        auto_maintenance_commit_message = f"""
Update {requirements}

The following collection tarball(s) have updates:
{', '.join(collection_tarballs.keys())}
The CentOS scratch build URL:
{build_url}
AI: @spetrosi to open a PR for linux-system-roles. This requires logging in as linuxsystemroles user:
{open_pr_url}
CC: @richm @nhosoi
"""
        repo_commit_changes(
            auto_maintenance_repo,
            auto_maintenance_commit_message,
            auto_maintenance_push_branch,
            [requirements],
        )
        repo_force_push(
            auto_maintenance_repo, auto_maintenance_remote, auto_maintenance_push_branch
        )


if __name__ == "__main__":
    sys.exit(main())
