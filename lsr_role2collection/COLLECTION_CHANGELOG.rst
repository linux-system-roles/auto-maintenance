Changelog
=========

[1.20.1-1] - 2022-09-27
-------------------------

Bug Fix
~~~~~~~~~~~~

- `ssh,sshd - Sync on final OpenSSH option name RequiredRSASize in ssh and sshd roles <https://bugzilla.redhat.com/show_bug.cgi?id=2129873>`__

[1.20.0-1] - 2022-08-04
-------------------------

New Features
~~~~~~~~~~~~

- `cockpit - Add customization of port <https://bugzilla.redhat.com/show_bug.cgi?id=2115152>`__

- `firewall-system-role: add ability to add interface to zone by PCI device ID <https://bugzilla.redhat.com/show_bug.cgi?id=2100942>`__

- `firewall - support for firewall_config - gather firewall facts <https://bugzilla.redhat.com/show_bug.cgi?id=2115154>`__

- `logging - Support startmsg.regex and endmsg.regex in the files inputs <https://bugzilla.redhat.com/show_bug.cgi?id=2112145>`__

- `selinux - Added setting of seuser and selevel for completeness <https://bugzilla.redhat.com/show_bug.cgi?id=2115157>`__

Bug Fix
~~~~~~~~~~~~

- `network - fix IPRouteUtils.get_route_tables_mapping() to accept any whitespace sequence <https://bugzilla.redhat.com/show_bug.cgi?id=2115886>`__

- `nbde_client - Sets proper spacing for parameter rd.neednet=1 <https://bugzilla.redhat.com/show_bug.cgi?id=2115156>`__

- `ssh sshd - ssh, sshd: RSAMinSize parameter definition is missing <https://bugzilla.redhat.com/show_bug.cgi?id=2109998>`__

- `storage - [RHEL9] [WARNING]: The loop variable 'storage_test_volume' is already in use. You should set the `loop_var` value in the `loop_control` option for the task to something else to avoid variable collisions and unexpected behavior. <https://bugzilla.redhat.com/show_bug.cgi?id=2082736>`__

[1.19.3-1] - 2022-07-01
-------------------------

New Features
~~~~~~~~~~~~

- `firewall - support add/modify/delete services <https://bugzilla.redhat.com/show_bug.cgi?id=2100292>`__

- `network - [network] Support managing the network through nmstate schema <https://bugzilla.redhat.com/show_bug.cgi?id=2072385>`__

- `storage - support for adding/removing disks to/from storage pools <https://bugzilla.redhat.com/show_bug.cgi?id=2072742>`__

- `storage - support for attaching cache volumes to existing volumes <https://bugzilla.redhat.com/show_bug.cgi?id=2072746>`__

Bug Fix
~~~~~~~~~~~~

- `crypto_policies - rhel 8.7 default policy is FUTURE not DEFAULT <https://bugzilla.redhat.com/show_bug.cgi?id=2100251>`__

- `firewall - forward_port should accept list of string or list of dict <https://bugzilla.redhat.com/show_bug.cgi?id=2100605>`__

- `metrics - document minimum supported redis version required by rhel-system-roles <https://bugzilla.redhat.com/show_bug.cgi?id=2100286>`__

- `metrics - restart pmie, pmlogger if changed, do not wait for handler <https://bugzilla.redhat.com/show_bug.cgi?id=2100294>`__

- `storage - [RHEL9] _storage_test_pool_pvs get wrong data type in test-verify-pool-members.yml <https://bugzilla.redhat.com/show_bug.cgi?id=2044119>`__

[1.19.2-1] - 2022-06-15
-------------------------

New Features
~~~~~~~~~~~~

- `sshd system role should be able to optionally manage /etc/ssh/sshd_config on RHEL 9 <https://bugzilla.redhat.com/show_bug.cgi?id=2052086>`__

[1.19.1-1] - 2022-06-13
-------------------------

New Features
~~~~~~~~~~~~

- `storage - support for creating and managing LVM thin pools/LVs <https://bugzilla.redhat.com/show_bug.cgi?id=2072745>`__

- `All roles should support running with gather_facts: false <https://bugzilla.redhat.com/show_bug.cgi?id=2078989>`__

Bug Fix
~~~~~~~~~~~~

- `ha_cluster - Move tasks that set up CI environment to roles tasks/ dir <https://bugzilla.redhat.com/show_bug.cgi?id=2093438>`__

[1.19.0-1] - 2022-06-06
-------------------------

New Features
~~~~~~~~~~~~

- `storage - support for creating and managing LVM thin pools/LVs <https://bugzilla.redhat.com/show_bug.cgi?id=2072745>`__

- `firewall - state no longer required for masquerade and ICMP block inversion <https://bugzilla.redhat.com/show_bug.cgi?id=2093423>`__

Bug Fix
~~~~~~~~~~~~

- `firewall - Update Ansible syntax in Firewall system role README.md file examples <https://bugzilla.redhat.com/show_bug.cgi?id=2094096>`__

- `storage role raid_level "striped" is not supported <https://bugzilla.redhat.com/show_bug.cgi?id=2083410>`__

- `network: the controller device is not completely cleaned up in the bond tests. <https://bugzilla.redhat.com/show_bug.cgi?id=2089872>`__

- `ha_cluster - Move tasks that set up CI environment to roles tasks/ dir <https://bugzilla.redhat.com/show_bug.cgi?id=2093438>`__

[1.18.0-1] - 2022-05-02
-------------------------

New Features
~~~~~~~~~~~~

- `firewall - [Improvement] Allow System Role to reset to default Firewalld Settings <https://bugzilla.redhat.com/show_bug.cgi?id=2043010>`__

- `metrics - add an option to the metrics role to enable postfix metric collection <https://bugzilla.redhat.com/show_bug.cgi?id=2051737>`__

- `network - Rework the infiniband support <https://bugzilla.redhat.com/show_bug.cgi?id=2086965>`__

- `sshd system role should not assume that RHEL 9 /etc/ssh/sshd_config has "Include > /etc/ssh/sshd_config.d/*.conf" <https://bugzilla.redhat.com/show_bug.cgi?id=2052081>`__

- `sshd system role should be able to optionally manage /etc/ssh/sshd_config on RHEL 9 <https://bugzilla.redhat.com/show_bug.cgi?id=2052086>`__

Bug Fix
~~~~~~~~~~~~

- `storage role cannot set mount_options for volumes <https://bugzilla.redhat.com/show_bug.cgi?id=2083376>`__

[1.17.0-1] - 2022-04-25
-------------------------

New Features
~~~~~~~~~~~~

- `All roles should support running with gather_facts: false <https://bugzilla.redhat.com/show_bug.cgi?id=2078989>`__

- `ha_cluster - support advanced corosync configuration <https://bugzilla.redhat.com/show_bug.cgi?id=2065337>`__

- `ha_cluster - support SBD fencing <https://bugzilla.redhat.com/show_bug.cgi?id=2079626>`__

- `ha_cluster - add support for configuring bundle resources <https://bugzilla.redhat.com/show_bug.cgi?id=2073519>`__

- `logging - Logging - RFE - support template, severity and facility options <https://bugzilla.redhat.com/show_bug.cgi?id=2075119>`__

- `metrics - consistently use ansible_managed in configuration files managed by role [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2065392>`__

- `metrics - add an option to the metrics role to enable postfix metric collection <https://bugzilla.redhat.com/show_bug.cgi?id=2051737>`__

- `nbde_client - NBDE client system role does not support servers with static IP addresses [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2070462>`__

- `network - Extend rhel-system-roles.network feature set to support routing rules <https://bugzilla.redhat.com/show_bug.cgi?id=2079622>`__

- `postfix - consistently use ansible_managed in configuration files managed by role [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2065393>`__

- `postfix - Postfix RHEL System Role should provide the ability to replace config and reset configuration back to default [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2065383>`__

- `storage - RFE storage Less verbosity by default <https://bugzilla.redhat.com/show_bug.cgi?id=2079627>`__

Bug Fix
~~~~~~~~~~~~

- `firewall - Firewall system role Ansible deprecation warning related to "include" <https://bugzilla.redhat.com/show_bug.cgi?id=2061511>`__

- `kernel_settings error configobj not found on RHEL 8.6 managed hosts <https://bugzilla.redhat.com/show_bug.cgi?id=2060525>`__

- `logging tests fail during cleanup if no cloud-init on system <https://bugzilla.redhat.com/show_bug.cgi?id=2058799>`__

- `metrics - Metrics role, with "metrics_from_mssql" option does not configure /var/lib/pcp/pmdas/mssql/mssql.conf on first run <https://bugzilla.redhat.com/show_bug.cgi?id=2060523>`__

- `network - bond: fix typo in supporting the infiniband ports in active-backup mode [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2065394>`__

- `network - pytest failed when running with nm providers in the rhel-8.5 beaker machine [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2066911>`__

- `network - consistently use ansible_managed in configuration files managed by role [rhel-9.1.0] <https://bugzilla.redhat.com/show_bug.cgi?id=2065382>`__

- `sshd - FIPS mode detection in SSHD role is wrong <https://bugzilla.redhat.com/show_bug.cgi?id=2073605>`__

- `timesync: basic-smoke test failure in timesync/tests_ntp.yml <https://bugzilla.redhat.com/show_bug.cgi?id=2060524>`__

- `tlog - Tlog role - Enabling session recording configuration does not work due to RHEL9 SSSD files provider default <https://bugzilla.redhat.com/show_bug.cgi?id=2071804>`__

[1.16.3-1] - 2022-04-07
-------------------------

Bug Fix
~~~~~~~~~~~~

- `tlog - Tlog role - Enabling session recording configuration does not work due to RHEL9 SSSD files provider default <https://bugzilla.redhat.com/show_bug.cgi?id=2071804>`__

[1.16.2-1] - 2022-03-31
-------------------------

New Features
~~~~~~~~~~~~

- `nbde_client - NBDE client system role does not support servers with static IP addresses <https://bugzilla.redhat.com/show_bug.cgi?id=2031555>`__

[1.16.1-1] - 2022-03-29
-------------------------

New Features
~~~~~~~~~~~~

- `nbde_client - NBDE client system role does not support servers with static IP addresses <https://bugzilla.redhat.com/show_bug.cgi?id=2031555>`__

[1.16.0-1] - 2022-03-15
-------------------------

New Features
~~~~~~~~~~~~

- `network - consistently use ansible_managed in configuration files managed by role <https://bugzilla.redhat.com/show_bug.cgi?id=2057657>`__

- `metrics - consistently use ansible_managed in configuration files managed by role <https://bugzilla.redhat.com/show_bug.cgi?id=2057647>`__

- `postfix - consistently use ansible_managed in configuration files managed by role <https://bugzilla.redhat.com/show_bug.cgi?id=2057662>`__

- `postfix - Postfix RHEL System Role should provide the ability to replace config and reset configuration back to default <https://bugzilla.redhat.com/show_bug.cgi?id=2058780>`__

Bug Fix
~~~~~~~~~~~~

- `network - pytest failed when running with nm providers in the rhel-8.5 beaker machine <https://bugzilla.redhat.com/show_bug.cgi?id=2064401>`__

- `network - bond: fix typo in supporting the infiniband ports in active-backup mode <https://bugzilla.redhat.com/show_bug.cgi?id=2064391>`__

[1.15.1-1] - 2022-03-03
-------------------------

Bug Fix
~~~~~~~~~~~~

- `kernel_settings error configobj not found on RHEL 8.6 managed hosts <https://bugzilla.redhat.com/show_bug.cgi?id=2058756>`__

- `timesync: basic-smoke test failure in timesync/tests_ntp.yml <https://bugzilla.redhat.com/show_bug.cgi?id=2058645>`__

[1.15.0-2] - 2022-03-01
-------------------------

Bug Fix
~~~~~~~~~~~~

- `metrics - Metrics role, with "metrics_from_mssql" option does not configure /var/lib/pcp/pmdas/mssql/mssql.conf on first run <https://bugzilla.redhat.com/show_bug.cgi?id=2058777>`__

[1.15.0-1] - 2022-02-24
-------------------------

New Features
~~~~~~~~~~~~

- `firewall - - Firewall RHEL System Role should be able to set default zone <https://bugzilla.redhat.com/show_bug.cgi?id=2022461>`__

Bug Fix
~~~~~~~~~~~~

- `firewall - ensure target changes take effect immediately <https://bugzilla.redhat.com/show_bug.cgi?id=2057164>`__

- `network: tests_802_1x_nm, tests_802_1x_updated_nm fails because of missing hostapd in EPEL <https://bugzilla.redhat.com/show_bug.cgi?id=2053861>`__

[1.14.0-1] - 2022-02-21
-------------------------

New Features
~~~~~~~~~~~~

- `network - Add more bonding options to rhel-system-roles.network <https://bugzilla.redhat.com/show_bug.cgi?id=2054435>`__

- `certificate - should consistently use ansible_managed in hook scripts <https://bugzilla.redhat.com/show_bug.cgi?id=2054368>`__

- `tlog - consistently use ansible_managed in configuration files managed by role <https://bugzilla.redhat.com/show_bug.cgi?id=2054367>`__

- `vpn - consistently use ansible_managed in configuration files managed by role <https://bugzilla.redhat.com/show_bug.cgi?id=2054369>`__

Bug Fix
~~~~~~~~~~~~

- `ha_cluster - set permissions for haclient group <https://bugzilla.redhat.com/show_bug.cgi?id=2049754>`__

[1.13.0-1] - 2022-02-14
-------------------------

New Features
~~~~~~~~~~~~

- `storage - Add support for RAID volumes (lvm-only) <https://bugzilla.redhat.com/show_bug.cgi?id=2016518>`__

- `storage - Add support for cached volumes (lvm-only) <https://bugzilla.redhat.com/show_bug.cgi?id=2016517>`__

- `nbde_client - NBDE client system role does not support servers with static IP addresses <https://bugzilla.redhat.com/show_bug.cgi?id=2031555>`__

- `ha_cluster - Support for creating resource constraints (Location, Ordering, etc.) <https://bugzilla.redhat.com/show_bug.cgi?id=2041634>`__

- `network - Support Routing Tables in static routes in Network Role <https://bugzilla.redhat.com/show_bug.cgi?id=2049798>`__

Bug Fix
~~~~~~~~~~~~

- `metrics role can't be re-run if the Grafana admin password has been changed <https://bugzilla.redhat.com/show_bug.cgi?id=2041632>`__

- `firewall - ensure zone exists and can be used in subsequent operations <https://bugzilla.redhat.com/show_bug.cgi?id=2024775>`__

- `network - Failure to activate connection: nm-manager-error-quark: No suitable device found for this connection <https://bugzilla.redhat.com/show_bug.cgi?id=2038957>`__

- `network - Set DNS search setting only for enabled IP protocols <https://bugzilla.redhat.com/show_bug.cgi?id=2004899>`__

[1.12.1-1] - 2022-02-08
-------------------------

Bug Fix
~~~~~~~~~~~~

- `vpn: template error while templating string: no filter named 'vpn_ipaddr' <https://bugzilla.redhat.com/show_bug.cgi?id=2050341>`__

- `kdump: Unable to start service kdump: Job for kdump.service failed because the control process exited with error code. <https://bugzilla.redhat.com/show_bug.cgi?id=2050419>`__

[1.12.0-2] - 2022-02-03
-------------------------

New Features
~~~~~~~~~~~~

- `Support ansible-core 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2012298>`__

[1.12.0-1] - 2022-01-27
-------------------------

Bug Fix
~~~~~~~~~~~~

- `logging - Logging role "logging_purge_confs" option not properly working <https://bugzilla.redhat.com/show_bug.cgi?id=2039106>`__

- `kernel_settings role should use ansible_managed in its configuration file <https://bugzilla.redhat.com/show_bug.cgi?id=2047506>`__

[1.11.0-1] - 2021-12-02
-------------------------

New Features
~~~~~~~~~~~~

- `Support ansible-core 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2012298>`__

- `cockpit - Please include "cockpit" role <https://bugzilla.redhat.com/show_bug.cgi?id=2021028>`__

- `Support ansible-core 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2012298>`__

- `ssh/tests_all_options.yml: "assertion": "'StdinNull yes' in config.content | b64decode ", failure <https://bugzilla.redhat.com/show_bug.cgi?id=2029427>`__

- `Support ansible-core 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2012298>`__

Bug Fix
~~~~~~~~~~~~

- `timesync: Failure related to missing ntp/ntpd package/service on RHEL-9 host <https://bugzilla.redhat.com/show_bug.cgi?id=2029463>`__

- `logging role missing quotes for immark module interval value <https://bugzilla.redhat.com/show_bug.cgi?id=2021676>`__

- `kdump: support reboot required and reboot ok <https://bugzilla.redhat.com/show_bug.cgi?id=2029602>`__

- `sshd - should detect FIPS mode and handle tasks correctly in FIPS mode <https://bugzilla.redhat.com/show_bug.cgi?id=2029634>`__

[1.10.0-1] - 2021-11-08
-------------------------

New Features
~~~~~~~~~~~~

- `cockpit - Please include "cockpit" role <https://bugzilla.redhat.com/show_bug.cgi?id=2021028>`__

- `firewall - Ansible Roles for RHEL Firewall <https://bugzilla.redhat.com/show_bug.cgi?id=2021665>`__

- `firewall-system-role: add ability to add-source <https://bugzilla.redhat.com/show_bug.cgi?id=2021667>`__

- `firewall-system-role: allow user defined zones <https://bugzilla.redhat.com/show_bug.cgi?id=2021669>`__

- `firewall-system-role: allow specifying the zone <https://bugzilla.redhat.com/show_bug.cgi?id=2021670>`__

- `Support ansible-core 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2012298>`__

- `network role: Allow to specify PCI address to configure profiles <https://bugzilla.redhat.com/show_bug.cgi?id=1999162>`__

- `network - support wifi Enhanced Open (OWE) <https://bugzilla.redhat.com/show_bug.cgi?id=1993377>`__

- `network - support WPA3 Simultaneous Authentication of Equals(SAE) <https://bugzilla.redhat.com/show_bug.cgi?id=1993304>`__

- `network - [Network] RFE: Support ignoring default gateway retrieved by DHCP/IPv6-RA <https://bugzilla.redhat.com/show_bug.cgi?id=1978773>`__

- `logging - Add user and password <https://bugzilla.redhat.com/show_bug.cgi?id=1990490>`__

Bug Fix
~~~~~~~~~~~~

- `Vendoring non-builtin modules for Ansible 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2006076>`__

- `network - Update network system role to reflect that network teaming is deprecated in RHEL 9 <https://bugzilla.redhat.com/show_bug.cgi?id=1999770>`__

- `selinux - linux-system-roles.selinux fails linit rules role-name and unnamed-task <https://bugzilla.redhat.com/show_bug.cgi?id=2021675>`__

- `Replace `# {{ ansible_managed }}` with `{{ ansible_managed | comment }}` <https://bugzilla.redhat.com/show_bug.cgi?id=2006230>`__

- `logging role missing quotes for immark module interval value <https://bugzilla.redhat.com/show_bug.cgi?id=2021676>`__

- `logging - Logging - Performance improvement <https://bugzilla.redhat.com/show_bug.cgi?id=2004303>`__

- `nbde_client - add regenerate-all to the dracut command <https://bugzilla.redhat.com/show_bug.cgi?id=2021681>`__

- `certificates: "group" option keeps certificates inaccessible to the group <https://bugzilla.redhat.com/show_bug.cgi?id=2021025>`__

[1.9.0-2] - 2021-10-26
-------------------------

Bug Fix
~~~~~~~~~~~~

- `Vendoring non-builtin modules for Ansible 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2006076>`__

[1.9.0-1] - 2021-10-11
-------------------------

New Features
~~~~~~~~~~~~

- `logging - Add user and password <https://bugzilla.redhat.com/show_bug.cgi?id=1990490>`__

Bug Fix
~~~~~~~~~~~~

- `Replace `# {{ ansible_managed }}` with `{{ ansible_managed | comment }}` <https://bugzilla.redhat.com/show_bug.cgi?id=2006230>`__

- `Vendoring non-builtin modules for Ansible 2.11+ <https://bugzilla.redhat.com/show_bug.cgi?id=2006076>`__

[1.8.3-2] - 2021-08-26
-------------------------

Bug Fix
~~~~~~~~~~~~

- `selinux - some tests give USER_AVC denied errors <https://bugzilla.redhat.com/show_bug.cgi?id=1996315>`__

[1.8.3-1] - 2021-08-26
-------------------------

New Features
~~~~~~~~~~~~

- `storage - Request that VDO be added to the Ansible (redhat-system-roles) <https://bugzilla.redhat.com/show_bug.cgi?id=1978488>`__

[1.8.2-1] - 2021-08-24
-------------------------

Bug Fix
~~~~~~~~~~~~

- `logging - Update the certificates copy tasks <https://bugzilla.redhat.com/show_bug.cgi?id=1996777>`__

[1.8.1-1] - 2021-08-16
-------------------------

Bug Fix
~~~~~~~~~~~~

- `metrics role: the bpftrace role does not properly configure bpftrace agent <https://bugzilla.redhat.com/show_bug.cgi?id=1994180>`__

[1.8.0-1] - 2021-08-12
-------------------------

New Features
~~~~~~~~~~~~

- `drop support for Ansible 2.8 <https://bugzilla.redhat.com/show_bug.cgi?id=1989197>`__

Bug Fix
~~~~~~~~~~~~

- `sshd: failed to validate: error:Missing Match criteria for all Bad Match condition <https://bugzilla.redhat.com/show_bug.cgi?id=1991598>`__

[1.7.6-1] - 2021-08-10
-------------------------

Bug Fix
~~~~~~~~~~~~

- `storage - tests_create_lvmvdo_then_remove fails - Module dm-vdo not found <https://bugzilla.redhat.com/show_bug.cgi?id=1991062>`__

- `storage - [storage role] Get syntax errors in tests_lvm_errors.yml <https://bugzilla.redhat.com/show_bug.cgi?id=1991142>`__

[1.7.5-1] - 2021-08-06
-------------------------

New Features
~~~~~~~~~~~~

- `logging - Add a support for list value to server_host in the elasticsearch output <https://bugzilla.redhat.com/show_bug.cgi?id=1986460>`__

Bug Fix
~~~~~~~~~~~~

- `logging certificate - Instead of the archive module, use "tar" command for backup. <https://bugzilla.redhat.com/show_bug.cgi?id=1984182>`__

- `logging: tests_tests_relp.yml; Can't detect any of the required Python libraries cryptography (>= 1.2.3) or PyOpenSSL (>= 0.6) <https://bugzilla.redhat.com/show_bug.cgi?id=1989962>`__

[1.7.4-1] - 2021-08-06
-------------------------

Bug Fix
~~~~~~~~~~~~

- `metrics role: Grafana dashboard not working after metrics role run unless services manually restarted <https://bugzilla.redhat.com/show_bug.cgi?id=1984150>`__

[1.7.2-1] - 2021-08-03
-------------------------

Bug Fix
~~~~~~~~~~~~

- `sshd: Add support for RHEL-9: add vars/RedHat_9.yml <https://bugzilla.redhat.com/show_bug.cgi?id=1989221>`__

[1.7.1-1] - 2021-07-29
-------------------------

Bug Fix
~~~~~~~~~~~~

- `network/tests_provider_nm.yml fails with an error: Failure in test 'I can manage a veth interface with NM after I managed it with initscripts. <https://bugzilla.redhat.com/show_bug.cgi?id=1935919>`__

- `network: _initscripts tests fail because "No package network-scripts available." <https://bugzilla.redhat.com/show_bug.cgi?id=1935916>`__

- `network - [network-role] Test tests_bond_initscripts.yml failed to create interface <https://bugzilla.redhat.com/show_bug.cgi?id=1980870>`__

- `storage - covscan error - DEADCODE - vdopool if create_vdo else parent <https://bugzilla.redhat.com/show_bug.cgi?id=1985571>`__

[1.7.0-1] - 2021-07-28
-------------------------

New Features
~~~~~~~~~~~~

- `logging - Add a support for list value to server_host in the elasticsearch output <https://bugzilla.redhat.com/show_bug.cgi?id=1986460>`__

- `storage: support volume sizes as a percentage of pool <https://bugzilla.redhat.com/show_bug.cgi?id=1984583>`__

Bug Fix
~~~~~~~~~~~~

- `network 802_1x: No package hostapd available. <https://bugzilla.redhat.com/show_bug.cgi?id=1945348>`__

- `logging certificate - Instead of the archive module, use "tar" command for backup. <https://bugzilla.redhat.com/show_bug.cgi?id=1984182>`__

- `kernel_settings: Found errors checking kernel settings <https://bugzilla.redhat.com/show_bug.cgi?id=1944599>`__

[1.6.1-1] - 2021-07-23
-------------------------

Bug Fix
~~~~~~~~~~~~

- `network - Error: device becoming unmanaged and pytest not reproducible in tests_integration_pytest.yml <https://bugzilla.redhat.com/show_bug.cgi?id=1985382>`__

[1.6.0-1] - 2021-07-15
-------------------------

New Features
~~~~~~~~~~~~

- `ha_cluster - add pacemaker cluster properties configuration <https://bugzilla.redhat.com/show_bug.cgi?id=1982906>`__

[1.5.0-1] - 2021-07-15
-------------------------

New Features
~~~~~~~~~~~~

- `crypto_policies - rename 'policy modules' to 'subpolicies' <https://bugzilla.redhat.com/show_bug.cgi?id=1982896>`__

[1.4.2-1] - 2021-07-15
-------------------------

New Features
~~~~~~~~~~~~

- `storage: relabel doesn't support <https://bugzilla.redhat.com/show_bug.cgi?id=1982841>`__

[1.4.1-1] - 2021-07-09
-------------------------

Bug Fix
~~~~~~~~~~~~

- `network - Re-running the network system role results in "changed: true" when nothing has actually changed <https://bugzilla.redhat.com/show_bug.cgi?id=1980871>`__

- `network - [network-role] Test tests_bond_initscripts.yml failed to create interface <https://bugzilla.redhat.com/show_bug.cgi?id=1980870>`__

[1.4.0-1] - 2021-07-08
-------------------------

New Features
~~~~~~~~~~~~

- `storage - Request that VDO be added to the Ansible (redhat-system-roles) <https://bugzilla.redhat.com/show_bug.cgi?id=1978488>`__

[1.3.0-1] - 2021-06-23
-------------------------

New Features
~~~~~~~~~~~~

- `storage - Request that VDO be added to the Ansible (redhat-system-roles) <https://bugzilla.redhat.com/show_bug.cgi?id=1978488>`__

- `sshd - support for appending a snippet to configuration file <https://bugzilla.redhat.com/show_bug.cgi?id=1978752>`__

- `timesync support for Network Time Security (NTS) <https://bugzilla.redhat.com/show_bug.cgi?id=1978753>`__

Bug Fix
~~~~~~~~~~~~

- `ha_cluster - add pacemaker resources configuration <https://bugzilla.redhat.com/show_bug.cgi?id=1978726>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

- `postfix - Postfix RHEL system role README.md missing variables under the "Role Variables" section <https://bugzilla.redhat.com/show_bug.cgi?id=1978734>`__

- `logging README.html is rendered incorrectly <https://bugzilla.redhat.com/show_bug.cgi?id=1978758>`__

- `postfix - the postfix role is not idempotent <https://bugzilla.redhat.com/show_bug.cgi?id=1978760>`__

- `selinux task for semanage says Fedora in name but also runs on RHEL/CentOS 8 <https://bugzilla.redhat.com/show_bug.cgi?id=1978740>`__

- `metrics role task to enable logging for targeted hosts not working <https://bugzilla.redhat.com/show_bug.cgi?id=1978746>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

- `sshd ssh - Unable to set sshd_hostkey_group and sshd_hostkey_mode <https://bugzilla.redhat.com/show_bug.cgi?id=1978745>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

- `sshd ssh - Unable to set sshd_hostkey_group and sshd_hostkey_mode <https://bugzilla.redhat.com/show_bug.cgi?id=1978745>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

- `[Rebase] Rebase to latest upstream - 3 <https://bugzilla.redhat.com/show_bug.cgi?id=1978731>`__

[1.2.3-1] - 2021-06-16
-------------------------

New Features
~~~~~~~~~~~~

- `main.yml: Add EL 9 support for all roles <https://bugzilla.redhat.com/show_bug.cgi?id=1952887>`__

[1.2.0-1] - 2021-05-14
-------------------------

New Features
~~~~~~~~~~~~

- `network role: Support ethtool -G|--set-ring options <https://bugzilla.redhat.com/show_bug.cgi?id=1959649>`__

Bug Fix
~~~~~~~~~~~~

- `[Rebase] Rebase to latest upstream - 2 <https://bugzilla.redhat.com/show_bug.cgi?id=1957876>`__

- `postfix - the postfix role is not idempotent <https://bugzilla.redhat.com/show_bug.cgi?id=1960375>`__

- `postfix: Use FQRN in README <https://bugzilla.redhat.com/show_bug.cgi?id=1958963>`__

- `postfix - Documentation error in rhel-system-roles postfix readme file <https://bugzilla.redhat.com/show_bug.cgi?id=1866544>`__

- `storage: calltrace observed when set type: partition for storage_pools <https://bugzilla.redhat.com/show_bug.cgi?id=1854187>`__

- `ha_cluster - cannot read preshared key in binary format <https://bugzilla.redhat.com/show_bug.cgi?id=1952620>`__

[1.1.0-2] - 2021-05-13
-------------------------

Bug Fix
~~~~~~~~~~~~

- `Bug fixes for Collection/Automation Hub <https://bugzilla.redhat.com/show_bug.cgi?id=1954747>`__

[1.1.0-1] - 2021-04-14
-------------------------

New Features
~~~~~~~~~~~~

- `timesync - support for free form configuration for chrony <https://bugzilla.redhat.com/show_bug.cgi?id=1938023>`__

- `timesync - support for timesync_max_distance to configure maxdistance/maxdist parameter <https://bugzilla.redhat.com/show_bug.cgi?id=1938016>`__

- `timesync - support for ntp xleave, filter, and hw timestamping <https://bugzilla.redhat.com/show_bug.cgi?id=1938020>`__

- `selinux - Ability to install custom SELinux module via Ansible <https://bugzilla.redhat.com/show_bug.cgi?id=1848683>`__

- `network - support for ipv6_disabled to disable ipv6 for address <https://bugzilla.redhat.com/show_bug.cgi?id=1939711>`__

- `vpn - Release Ansible role for vpn in rhel-system-roles <https://bugzilla.redhat.com/show_bug.cgi?id=1943679>`__

Bug Fix
~~~~~~~~~~~~

- `[Rebase] Rebase to latest upstream <https://bugzilla.redhat.com/show_bug.cgi?id=1937938>`__

- `timesync - do not use ignore_errors in timesync role <https://bugzilla.redhat.com/show_bug.cgi?id=1938014>`__
