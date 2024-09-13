# Linux System Roles

## Description

Linux System Roles is a set of roles for managing Linux system components.

## Requirements

If installing from RPM, the dependencies will be installed with the package.
Otherwise, the dependencies are listed in `requirements.txt` and/or `bindep.txt`.

## Installation

There are currently two ways to use the Linux System Roles Collection in your setup.

### Installation from Ansible Galaxy

Before using this collection, you need to install it with the `ansible-galaxy` command-line tool:

```shell
ansible-galaxy collection install fedora.linux_system_roles
```

After the installation, the roles are available as `fedora.linux_system_roles.<role_name>`.

You can also include it in a requirements.yml file and install it with ansible-galaxy collection install -r requirements.yml, using the format:

```yaml
collections:
  - name: fedora.linux_system_roles
```

Note that if you install any collections with `ansible-galaxy`, they will not be upgraded automatically when you upgrade the Ansible package.
To upgrade the collection to the latest available version, run the following command:

```shell
ansible-galaxy collection install fedora.linux_system_roles --upgrade
```

You can also install a specific version of the collection, for example, if you need to downgrade when something is broken in the latest version (please report an issue in this repository). Use the following syntax to install version 1.0.0:

```shell
ansible-galaxy collection install fedora.linux_system_roles:==1.0.0
```

See [using Ansible collections](https://docs.ansible.com/ansible/devel/user_guide/collections_using.html) for more details.

### Installation via RPM

You can install the collection with the software package management tool `dnf` by running:

```shell
dnf install linux-system-roles
```

## Use Cases

This collection provides Ansible roles that manage different Linux subsystems.


A list of all roles and their documentation can be found at https://linux-system-roles.github.io/ as well as in the Supported Roles section.

Once Linux System Roles Collection is installed, the individual role documentation is found at:

```
/usr/share/ansible/collections/ansible_collections/fedora/linux_system_roles/roles/<role_name>/README.md
```

## Contributing (Optional)

If you wish to contribute to roles within this collection, feel free to open a pull request for the role's upstream repository at https://github.com/linux-system-roles/.

We recommend that prior to submitting a PR, you familiarize yourself with our [Contribution Guidelines](https://linux-system-roles.github.io/contribute.html).

## Support

### Currently supported distributions

* Fedora
* Red Hat Enterprise Linux (RHEL 6+)
* RHEL 6+ derivatives such as CentOS 6+

NOTE: Some roles are not supported in RHEL6 and RHEL7. For more details about the individual roles you are interested in, see the documentation.

### Supported Ansible Versions

The supported Ansible versions are aligned with currently maintained Ansible versions that support Collections (Ansible 2.9 and later). For the list of maintained Ansible versions, see [Releases and maintenance](https://docs.ansible.com/ansible/latest/reference_appendices/release_and_maintenance.html#release-status) in Ansible documentation.

### Modules and Plugins

The modules and other plugins in this collection are private, used only internally to the collection, unless otherwise noted.

## Release Notes and Roadmap

For the list of versions and their changelog, see CHANGELOG.md within this collection.

## License Information

* GPL-2.0-or-later
* GPL-3.0-only
* GPL-3.0-or-later
* LGPL-3.0-only
* MIT
* BSD-3-Clause
