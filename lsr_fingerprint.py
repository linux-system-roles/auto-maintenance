#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright: (c) 2023, Red Hat, Inc.
# SPDX-License-Identifier: MIT
"""
Modify fingerprint in spec file to be system_role:$rolename

lsr_fingerprint.py -
scans files in the templates dir under ./role["lsrrolename"],
if the file contains a string role["reponame"]:role["rolename"],
replaces it with system_role:role["lsrrolename"].

E.g., in metrics, "performancecopilot:ansible-pcp" is replaced with
"system_role:metrics" in roles/bpftrace/templates/bpftrace.conf.j2.
"""

from os import listdir, walk
from os.path import join, isfile, isdir

roles = [
    {
        "reponame": "willshersystems",
        "rolename": "ansible-sshd",
        "lsrrolename": "sshd",
    },
    {
        "reponame": "performancecopilot",
        "rolename": "ansible-pcp",
        "lsrrolename": "metrics",
    },
]

# dirs in the current dir
dirs = [d for d in listdir(".") if isdir(d)]
for d in dirs:
    for role in roles:
        if role["lsrrolename"] == d:
            for root, subdirs, files in walk(d):
                for subdir in subdirs:
                    if subdir == "templates" or subdir == "meta":
                        dirpath = join(root, subdir)
                        tmpls = [
                            f for f in listdir(dirpath) if isfile(join(dirpath, f))
                        ]
                        for tmpl in tmpls:
                            tmplpath = join(dirpath, tmpl)
                            with open(tmplpath) as fp:
                                lines = fp.read()
                            newlines = lines.replace(
                                "{0}:{1}".format(role["reponame"], role["rolename"]),
                                "system_role:{0}".format(role["lsrrolename"]),
                            )
                            if lines != newlines:
                                with open(tmplpath, "w") as fp:
                                    fp.write(newlines)
