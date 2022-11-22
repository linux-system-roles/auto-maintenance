Changelog
=========

[1.30.5] - 2022-11-22
---------------------

### Bug Fixes

- cockpit - ansible-core 2.14 support - remove another warn
- vpn - only check for firewall ipsec service if managing firewall (#76)


[1.30.4] - 2022-11-20
---------------------

### Bug Fixes

- logging - cert cleanup needs to use getcert stop-tracking (#300)


[1.30.3] - 2022-11-18
---------------------

### Bug Fixes

- podman - ensure role works with podman 4.3
- podman - ensure role works with ansible-core 2.14
- podman - ensure role passes ansible-lint 6.x


[1.30.2] - 2022-11-16
---------------------

### Bug Fixes

- cockpit - make role work with ansible-core 2.14 - fix ansible-lint 6.x issues (#81)


[1.30.1] - 2022-11-15
---------------------

[1.30.0] - 2022-11-02
---------------------

### New Features

- ad_integration - New Role
- cockpit - Use the firewall role and the selinux role from the cockpit role (#76)
- cockpit - Introduce cockpit_manage_firewall to use the firewall role to
- cockpit - Add the test check task tasks/check_port.yml for verifying the
- cockpit - Add meta/collection-requirements.yml.
- cockpit - Introduce cockpit_manage_selinux to use the selinux role to
- cockpit - Use the certificate role to create the cert and the key (#78)
- cockpit - Introduce a variable cockpit_certificates to set the certificate_requests.
- cockpit - Update README so that using the certificate role is recommended.
- network - Support looking up named route table in routing rule
- network - Support 'route_metric4' for initscripts provider
- network - Support the DNS priority
- podman - New Role

### Bug Fixes

- network - bond: improve the validation for setting peer_notif_delay
- network - bond: test arp_all_targets only when arp_interval is enabled
- network - bond: attach ports when creating the bonding connection


[1.29.0] - 2022-11-02
---------------------

### New Features

- ha_cluster - Use the firewall role and the selinux role from the ha_cluster role
- ha_cluster - Introduce ha_cluster_manage_firewall to use the firewall role to
- ha_cluster - Introduce ha_cluster_manage_selinux to use the selinux role to
- ha_cluster - Add the test check task tasks/check_firewall_selinux.yml for
- ha_cluster - Use the certificate role to create the cert and the key
- ha_cluster - Introduce a variable ha_cluster_pcsd_certificates to set the certificate_requests.
- ha_cluster - add support for configuring qnetd
- ha_cluster - add support for configuring qdevice
- ha_cluster - qdevice and qnetd documentation
- logging - Use the firewall role, the selinux role, and the certificate role from the logging role (#293)
- logging - Introduce logging_manage_firewall to use the firewall role to manage
- logging - Introduce logging_manage_selinux to use the selinux role to manage
- logging - Add the test check task check_firewall_selinux.yml for verify the
- logging - Use the certificate role to generate certificates in the logging role
- logging - Introduce logging_certificates variable to specify parameters for
- metrics - Use the firewall role and the selinux role from the metrics role
- metrics - Introduce metrics_manage_firewall to use the firewall role to
- metrics - Introduce metrics_manage_selinux to use the selinux role to
- metrics - Add the test check task check_firewall_selinux.yml for verify
- metrics - Skip calling the firewall role when the managed node is rhel-6.
- metrics - When metrics_manage_firewall and metrics_manage_selinux are set
- nbde_server - Add support for custom ports (#38)
- nbde_server - Introduce nbde_server_manage_firewall and nbde_server_manage_selinux
- nbde_server - If nbde_server_manage_firewall is set to true, use the firewall
- nbde_server - If nbde_server_manage_selinux is set to true, use the selinux
- postfix - Use the firewall role and the selinux role from the postfix role (#56)
- postfix - Introduce postfix_manage_firewall to use the firewall role to
- postfix - Introduce postfix_manage_selinux to use the selinux role to
- postfix - Add the test check task tasks/check_firewall_selinux.yml for
- postfix - Add meta/collection-requirements.yml.
- vpn - Use the firewall role and the selinux role from the vpn role (#70)
- vpn - Introduce vpn_manage_firewall to enable the firewall role to manage
- vpn - Introduce vpn_manage_selinux to enable the selinux role to manage
- vpn - Add the test check task check_firewall_selinux.yml for verify the
- vpn - Add meta/collection-requirements.yml

### Bug Fixes

- ha_cluster - fix decoding variables from an Ansible vault
- ha_cluster - add a test for vault-encrypted variables
- ha_cluster - adapt tests with vault-encrypted variables for CI
- ha_cluster - use a real temporary directory for test secrets
- ha_cluster - fix checking hacluster password
- ha_cluster - update sbd config file template
- ha_cluster - fix installing qnetd and pcs packages
- ha_cluster - fix auth for qnetd host
- metrics - grafana: small wording tweak to grafana v8/v9 action names
- metrics - grafana: include config file for Grafana v9
- metrics - grafana: update grafana.ini to permit all grafana-pcp plugin components
- nbde_client - correct clevis askpass unit conditional (#81)
- nbde_client - Add default clevis luks askpass unit (#79)
- nbde_client - use no_log: true where secrets might be revealed
- storage - Master thin support size fix (#299)
- storage - percent specified 'size' of thin pool volume is now properly
- storage - percentage size thin volume now correctly references its parent device
- storage - percentage values are now accepted size for thin pool size


[1.28.0] - 2022-10-31
---------------------

### New Features

- ssh - Add final version of the option RequiredRSASize (#53)
- sshd - Adding support for OpenWrt 21.03
- sshd - Add final version of RequiredRSASize

### Bug Fixes

- sshd - Update source template to match generated files


[1.27.0] - 2022-09-19
---------------------

### New Features

- selinux - add 'local' parameter to seport (#124)
- selinux - `local: true`:
- sshd - Make drop-in config file functionality configurable by user
- timesync - adding support fpr Oracle Linux 6,7,8 and 9
- vpn - Various improvements required to connect to a managed remote host (#65)

### Bug Fixes

- certificate - Move Debian to Python 3 packages
- ha_cluster - only install and setup fence-virt on x86_64 hosts (#64)
- ssh - cast value to string in jinja macro (#50)
- sshd - Allow user to override variables
- timesync - Update chrony.conf.j2
- timesync - Updated: type casting in overall timesync templates for testing
- timesync - Updated: type casting adjusted (timesync_max_distance <= int)
- vpn - Check for /usr/bin/openssl on controller - do not use package_facts (#66)


[1.26.1] - 2022-08-05
---------------------

### Bug Fixes

- network - network_state: improve state comparison for achieving idempotency
- network - argument_validator: fix IPRouteUtils.get_route_tables_mapping() for whitespace


[1.26.0] - 2022-08-03
---------------------

### New Features

- cockpit - Add customization of port (#67)
- firewall - feature - add/remove interfaces by PCI ID
- logging - Support startmsg.regex and endmsg.regex in the files inputs.
- network - Support the nmstate network state configuration
- selinux - Added setting of seuser and selevel for completeness (#108)
- ssh - add RSAMinSize parameter (#45)

### Bug Fixes

- ha_cluster - readme: describe limitations of udp transports (#56)
- kernel_settings - Set the kernel_settings_reboot_required when reboot needed (#93)
- metrics - docs: make minimum redis and grafana versions more clear
- metrics - restart pmie, pmlogger if changed, do not wait for handler
- nbde_client - Sets needed spacing for appended rd.neednet parameter (#68)
- network - IfcfgUtil: Remediate `connection_seems_active()` for controller
- sshd - Add CHANGELOG.md
- sshd - Add changelog_to_tag.yml to .github/workflows
- sshd - add parameter RSAMinSize
- sshd - Add parameter RSAMinSize to Match blocks
- storage - Update README.md with latest changes (#290)

[1.24.2] - 2022-06-15
---------------------

### Bug Fixes

- sshd - The role still supports 2.9

[1.24.1] - 2022-06-13
---------------------

### New Features

- storage - check for thinlv name before assigning to thinlv\_params

### Bug Fixes

- ha_cluster - s/ansible\_play\_hosts\_all/ansible\_play\_hosts/ where applicable
- logging - Fix including a var file in set\_vars.yml
- sshd - Fix various linting issues
- sshd - Addition notes about secondary variables

[1.24.0] - 2022-06-02
---------------------

### New Features

- network - IfcfgUtil: Remediate `connection_seems_active()` for controller
- storage - LVM RAID raid0 level support
- storage - Thin pool support

### Bug Fixes

- firewall - fix: state not required for masquerade and ICMP block inversion
- firewall - Fix deprecated syntax in Readme
- ha_cluster - If ansible\_hostname includes '\_' the role fails with `invalid characters in salt`
- sshd - Remove kvm from virtualization platforms

[1.23.0] - 2022-05-25
---------------------

### New Features

- network - infiniband: Add the setting description
- network - infiniband: Reject the interface name for the ipoib connection
- network - infiniband: Reject the invalid pkey value
- network - infiniband: Change the default value of `p_key` into `None`

### Bug Fixes

- network - infiniband: Fix the bug of wrongly checking whether the device exists

[1.22.1] - 2022-05-16
---------------------

### New Features

- metrics - Add CentOS 9 platform variables for each role
- sshd - Unbreak FIPS detection and stabilize failing tests and GH actions
- sshd - Make sure Include is in the main configuration file when drop-in directory is used
- sshd - Make the role FIPS-aware
- storage - add support for mount\_options

### Bug Fixes

- ha_cluster - additional fix for password\_hash salt length
- sshd - Fix runtime directory check condition
- sshd - README: fix meta/make\_option\_lists link

[1.22.0] - 2022-05-02
---------------------

### New Features

- firewall - Added ability to restore Firewalld defaults

[1.21.0] - 2022-04-27
---------------------

### New Features

- logging - support gather\_facts: false
- metrics - Add a metrics\_from\_postfix boolean flag for the metrics role
- network - support playbooks which use gather_facts: false

### Bug Fixes

- metrics - Resolve race condition with starting pmdapostfix
- metrics - Ensure a postfix log file exists for pmdapostfix to start
- postfix - fix ansible-lint issues

[1.20.0] - 2022-04-25
---------------------

### New Features

- firewall - support gather\_facts: false; support setup-snapshot.yml
- ha_cluster - Add support for SBD devices
- ha_cluster - support gather\_facts: false; support setup-snapshot.yml
- ha_cluster - add support for configuring bundle resources
- kdump - support gather\_facts: false; support setup-snapshot.yml
- kernel_settings - support gather\_facts: false; support setup-snapshot.yml
- metrics - Provide pcp_\single\_control option for control.d vs control files
- nbde_client - support gather\_facts: false; support setup-snapshot.yml
- nbde_server - support gather\_facts: false; support setup-snapshot.yml
- network - Add support for routing rules
- network - Util: Normalize address family value before getting prefix length
- postfix - support gather\_facts: false; support setup-snapshot.yml
- selinux - support gather\_facts: false; support setup-snapshot.yml
- ssh - support gather\_facts: false; support setup-snapshot.yml
- sshd - Ensure the ansible facts are available
- sshd - Move the common variables to separate file
- sshd - Clarify the magic number
- sshd - Reuse the list of skipped virtualization environments
- sshd - Update documentation with recent changes
- sshd - Introduce default hostkeys to check when using drop-in directory
- sshd - Add another virtualization platform exception
- sshd - Update templates to apply FIPS hostkeys filter
- storage - add xfsprogs for non-cloud-init systems
- storage - allow role to work with gather\_facts: false
- storage - add setup snapshot to install packages into snapshot
- timesync - support gather\_facts: false; support setup-snapshot.yml
- tlog - support gather\_facts: false; support setup-snapshot.yml
- vpn - support gather\_facts: false; support setup-snapshot.yml

### Bug Fixes

- ha_cluster - Pcs fixes
- network - fix: class Python26CompatTestCase broken by minor python versions
- sshd - Avoid unnecessary use of 'and' in 'when' conditions
- sshd - Unbreak FIPS detection and hostkey filtering
- sshd - Set explicit path to the main configuration file to work well with the drop-in directory
- sshd - Fix runtime directory check

[1.19.0] - 2022-04-06
---------------------

### New Features

- ha_cluster - add support for advanced corosync configuration
- logging - Add log handling in case the target Elasticsearch is unavailable
- logging - RFE - support template, severity and facility options
- logging - Add support for multiline logs in oVirt vdsm.log
- storage - Less verbosity by default
- tlog - Execute authselect to update nsswitch

[1.18.2] - 2022-03-31
---------------------

### Bug Fixes

- nbde_client - network-flush: reset autoconnect-priority to zero

[1.18.1] - 2022-03-29
---------------------

### New Features

- nbde_client - Add dracut module for disabling autoconnect within initrd

[1.18.0] - 2022-03-15
---------------------

### New Features

- metrics - Support metrics from postfix mail servers
- metrics - Add "follow: yes" to the template task in the mssql and elasticsearch subrole.
- network - Add support for Rocky Linux
- postfix - Remove outdated ansible managed header and use {{ ansible\_managed | comment }}
- postfix - Add "previous: replaced" functionality to postfix\_conf dict to reset postfix configuration

### Bug Fixes

- network - bond: Fix supporting the infiniband ports in active-backup mode
- postfix - Fix some issues in the role, more info in commits
- timesync - handle errors with stopping services

[1.17.0] - 2022-02-22
---------------------

### New Features

- firewall - ensure that changes to target take effect immediately
- firewall - Add ability to set the default zone
- ha_cluster - add SBD support

### Bug Fixes

- tlog - tlog does not own sssd.conf - so use ini\_file to manage it

[1.16.0] - 2022-02-15
---------------------

### New Features

- certificate - System Roles should consistently use ansible\_managed in configuration files it manages
- network - NetworkManager provider: Support all available bonding modes and options
- network - Support routing tables in static routes
- tlog - System Roles should consistently use ansible\_managed in configuration files it manages
- vpn - System Roles should consistently use ansible\_managed in configuration files it manages

### Bug Fixes

- certificate - fix python black errors
- ha_cluster - fix default pcsd permissions
- network - Fix setting DNS search settings when only one IP family is enabled
- network - Fix switching from initscripts to NetworkManager 1.18

[1.15.2] - 2022-02-08
---------------------

### New Features

- kdump - use kdumpctl reset-crashkernel on rhel9
- vpn - script to convert vpn\_ipaddr to FQCN

[1.15.1] - 2022-01-27
---------------------

### New Features

- firewall - Added implicit firewalld reload for when a custom zone is added or removed

### Bug Fixes

- cockpit - Skip/undocumented obsolete packages
- kernel_settings - make tuned.conf have correct ansible\_managed comment
- logging - make purge and reset idempotent
- metrics - Address PyYAML vulnerability

[1.15.0] - 2022-01-18
---------------------

### New Features

- logging - Refactor logging\_purge\_confs and logging\_restore\_confs.

[1.14.0] - 2022-01-17
---------------------

### New Features

- timesync - Initial version for Debian

### Bug Fixes

- nbde_client - Add network flushing before setting up network

[1.13.0] - 2022-01-11
---------------------

### New Features

- ha_cluster - add support for configuring resource constraints
- logging - Add logging\_restore\_confs variable to restore backup.
- metrics - Specify grafana username/password
- Changes - Support matching network interfaces by their device path such as PCI address
- storage - Add LVM RAID specific parameters to module\_args
- storage - Added support for LVM RAID volumes
- storage - Add support for creating and managing LVM cache volumes
- storage - Nested module params checking
- storage - Refined safe\_mode condition in create\_members
- vpn - use custom vpn\_ipaddr filter

### Bug Fixes

- Changes - Support ansible-core 2.11 and 2.12
- timesync - Fix an issue if a service is listed by service\_facts that does not have the 'status' property defined

[1.12.0] - 2021-12-06
---------------------

### New Features

- firewall - Added support for RHEL 7
- firewall - Added runtime and permanent flags to documentation.
- kdump - Add reboot required
- ssh - Add new configuration options from Openssh 8.7p1

[1.11.0] - 2021-12-03
---------------------

### New Features

- cockpit - Add option to use an existing certificate
- storage - add support for storage\_udevadm\_trigger
- storage - Add workaround for the service\_facts module for Ansible \< 2.12

### Bug Fixes

- timesync - evaluate is\_ntp\_default as boolean, not string
- timesync - reject services which have a status == not-found
- timesync - also reject masked and failed services

[1.10.1] - 2021-11-08
---------------------

### New Features

- kernel_settings - make role work with ansible-core-2.11 ansible-lint and ansible-test
- kernel_settings - support ansible-core 2.12; ansible-plugin-scan; py39
- logging - support python 39, ansible-core 2.12, ansible-plugin-scan
- metrics - support python 39, ansible-core 2.12, ansible-plugin-scan
- nbde_client - support python 39, ansible-core 2.12, ansible-plugin-scan
- nbde_client - add regenerate-all to the dracut command
- nbde_server - support python 39, ansible-core 2.12, ansible-plugin-scan
- postfix - support python 39, ansible-core 2.12, ansible-plugin-scan
- selinux - support python 39, ansible-core 2.12, ansible-plugin-scan
- ssh - support python 39, ansible-core 2.12, ansible-plugin-scan
- storage - support python 39, ansible-core 2.12, ansible-plugin-scan
- storage - Add support for Rocky Linux 8
- timesync - make role work with ansible-core-2.11 ansible-lint and ansible-test
- tlog - support python 39, ansible-core 2.12, ansible-plugin-scan
- vpn - support python 39, ansible-core 2.12, ansible-plugin-scan

### Bug Fixes

- ha_cluster - fix ansible-lint issues
- logging - missing quotes around immark module interval option
- nbde_server - fix python black issues
- selinux - fix ansible-lint issues

[1.10.0] - 2021-10-07
---------------------

### New Features

- ha_cluster - use firewall-cmd instead of firewalld module
- ha_cluster - replace rhsm\_repository with subscription-manager cli
- ha_cluster - Use the openssl command-line interface instead of the openssl module
- logging - Use {{ ansible\_managed | comment }} to fix multi-line ansible\_managed
- logging - Performance improvement
- logging - Replacing seport module with the semanage command line.
- logging - Add uid and pwd parameters
- logging - Use the openssl command-line interface instead of the openssl module
- sshd - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- storage - Replace crypttab with lineinfile
- storage - replace json\_query with selectattr and map
- timesync - replace json\_query with selectattr/map

### Bug Fixes

- cockpit - Use {{ ansible\_managed | comment }} to fix multi-line ansible\_managed
- cockpit - use apt-get install -y
- ha_cluster - fix password\_hash salt length
- kdump - Use {{ ansible\_managed | comment }} to fix multi-line ansible\_managed
- kdump - remove authorized\_key; use ansible builtins
- kernel_settings - Use {{ ansible\_managed | comment }} to fix multi-line ansible\_managed
- logging - Eliminate redundant loop.
- selinux - Fix version comparisons for ansible\_distribution\_major\_version
- ssh - Use {{ ansible\_managed | comment }} to fix multi-line ansible\_managed
- sshd - Use {{ ansible_managed | comment }} to fix multi-line ansible_managed
- sshd - FIX: indentation including tests
- timesync - Use {{ ansible\_managed | comment }} to fix multi-line ansible\_managed
- vpn - do not use json\_query - not needed here
- vpn - use wait\_for\_connection instead of wait\_for with ssh

[1.9.2] - 2021-08-24
---------------------

### New Features

- logging - Allowing the case, tls is false and key/certs vars are configured.

### Bug Fixes

- logging - Update copy tasks conditions with tls true

[1.9.1] - 2021-08-17
---------------------

### Bug Fixes

- metrics - bpftrace: follow bpftrace.conf symlink for latest PCP versions

[1.9.0] - 2021-08-12
---------------------

### New Features

- certificate - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- ha_cluster - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- kdump - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- kernel_settings - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- logging - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- metrics - Raise supported Ansible version to 2.9
- nbde_client - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- nbde_server - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- network - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- network - wifi: Add Simultaneous Authentication of Equals(SAE) support
- postfix - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- selinux - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- ssh - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- sshd - Add Debian 11 \(bullseye\) support
- sshd - Workaround namespace feature also for RHEL6
- storage - Raise supported Ansible version to 2.9
- timesync - Raise supported Ansible version to 2.9
- tlog - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9
- vpn - Drop support for Ansible 2.8 by bumping the Ansible version to 2.9

### Bug Fixes

- sshd - Fix wrong template file

[1.8.5] - 2021-08-08
---------------------

### New Features

- storage - use volume1\_size; check for expected error

[1.8.4] - 2021-08-06
---------------------

### New Features

- certificate - Instead of the unarchive module, use "tar" command for backup.

### Bug Fixes

- logging - do not warn about unarchive or leading slashes
- logging - python2 renders server\_host list incorrectly
- logging - FIX README false variable name
- logging - use correct python-cryptography package

[1.8.2] - 2021-08-03
---------------------

### New Features

- sshd - Add support for RHEL 9 and adjust tests for it

[1.8.1] - 2021-07-29
---------------------

### Bug Fixes

- storage - omit unnecessary conditional - deadcode reported by static scanner

[1.8.0] - 2021-07-28
---------------------

### New Features

- certificate - Instead of the archive module, use "tar" command for backup.
- logging - Add a support for list value to server\_host in the elasticsearch output
- logging - Instead of the archive module, use "tar" command for backup.
- storage - percentage-based volume size \(lvm only\)

### Bug Fixes

- network - fix yamllint issue - indentation
- network - connections: workaround DeprecationWarning for NM.SettingEthtool.set_feature()

[1.7.0] - 2021-07-15
---------------------

### New Features

- ha_cluster - add pacemaker cluster properties configuration
- network - Only show stderr_lines by default
- network - Add 'auto_gateway' option

### Bug Fixes

- ha_cluster - do not fail if openssl is not installed
- network - nm: Fix the incorrect change indication for dns option
- network - nm: Fix the incorrect change indication when apply the same config twice
- network - fix: dhclient is already running for `nm-bond`
- storage - Fixed volume relabeling

[1.6.0] - 2021-07-07
---------------------

### New Features

- crypto_policies - rename 'policy modules' to 'subpolicies'
- storage - LVMVDO support

[1.5.0] - 2021-06-21
---------------------

### New Features

- kdump - use localhost if no SSH\_CONNECTION env. var.
- sshd - Add configuration options from OpenSSH 8.6p1
- sshd - Rename sshd\_namespace\_append to sshd\_config\_namespace
- sshd - Support for appending a snippet to configuration file
- sshd - Update meta data and README
- sshd - use state: absent instead of state: missing
- sshd - \[FreeBSD\] Add Subsystem to \_sshd\_defaults
- sshd - UsePrivilegeSeparation is deprecated since 2017/OpenSSH 7.5 - https://www.openssh.com/txt/re
- sshd - examples: Provide simple example playbook

### Bug Fixes

- nbde_client - fix python black formatting errors
- ssh - Fix variable precedence for ssh\_drop\_in\_name
- sshd - Fix variable precedence when invoked through legacy "roles:"
- sshd - Fix issues found by linters - enable all tests on all repos - remove suppressions
- sshd - README: Document missing exported variable

[1.4.0] - 2021-06-04
---------------------

### New Features

- selinux - Update semanage task to not specify Fedora since it also runs on RHEL/CentOS 8
- sshd - Skip defaults when appending configuration
- sshd - README: Reword the option description and provide example
- sshd - Remove boolean comparison and regenerate templates
- sshd - Support for appending a snippet to configuration file
- sshd - Update source template files used to generate final template
- timesync - Add NTS support

### Bug Fixes

- metrics - \_\_pcp\_target\_hosts not defined so loop doesn't run

[1.3.0] - 2021-05-27
---------------------

### Initial Release
