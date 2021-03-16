Linux System Roles Ansible Collection
=====================================

Linux System Roles is a set of roles for managing Linux system components.

## Currently supported distributions

* Fedora
* Red Hat Enterprise Linux (RHEL 6+)
* RHEL 6+ derivatives such as CentOS 6+

NOTE: Some roles are not supported in RHEL6 and RHEL7. For more details about the individual roles you are interested in, see the documentation.

## Dependencies

The following dependency is required for the Ansible Controller:
* jmespath

## Installation

There are currently two ways to use the Linux System Roles Collection in your setup.

### Installation from Ansible Galaxy

You can install the collection from Ansible Galaxy by running:
```
ansible-galaxy collection install fedora.linux_system_roles
```

After the installation, the roles are available as `fedora.linux_system_roles.<role_name>`.

Please see the [Using Ansible collections documentation](https://docs.ansible.com/ansible/devel/user_guide/collections_using.html) for further details.

### Installation via RPM

You can install the collection with the software package management tool `dnf` by running:
```
dnf install linux-system-roles
```

## Documentation

A list of all roles and their documentation can be found at https://linux-system-roles.github.io/ as well as in the Supported Roles section.

Once Linux System Roles Collection is installed, the individual role documentation is found at:
```
/usr/share/ansible/collections/ansible_collections/fedora/linux_system_roles/roles/<role_name>/README.md
```

## Support

### Supported Ansible Versions

The supported Ansible versions are aligned with currently maintained Ansible versions that support Collections (Ansible 2.9 and later). You can find the list of maintained Ansible versions [here](https://docs.ansible.com/ansible/latest/reference_appendices/release_and_maintenance.html#release-status).

### Modules and Plugins

The modules and other plugins in this collection are private, used only internally to the collection, unless otherwise noted.
