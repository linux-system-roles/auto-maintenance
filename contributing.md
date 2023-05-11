This repo uses automation to build and release Fedora RPMs.  If you make
changes here, you may have to also update the automation here in `.packit.yaml`
and in the downstream Fedora dist-git which is currently
https://src.fedoraproject.org/rpms/linux-system-roles

For example, if you add or remove a file from dist-git, you will usually need to
update this repo `.packit.yaml` under `post-upstream-clone`.  The `CHANGELOG.md`
in dist-git is generated from this repo.

If you add or remove a role from the package, you will need to update
`collection_release.yml` which is used to generate the sources handling section
of the spec file.
