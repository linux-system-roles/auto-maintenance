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

changedlist = []
# dirs in the current dir
dirs = [d for d in listdir(".") if isdir(d)]
exit_code = 0
for d in dirs:
    for role in roles:
        if role["lsrrolename"] == d:
            oldpair = "{0}:{1}".format(role["reponame"], role["rolename"])
            newpair = "system_role:{0}".format(role["lsrrolename"])
            for root, subdirs, files in walk(d):
                for subdir in subdirs:
                    if subdir == "templates" or subdir == "meta":
                        dirpath = join(root, subdir)
                        tmpls = [
                            f for f in listdir(dirpath) if isfile(join(dirpath, f))
                        ]
                        for tmpl in tmpls:
                            tmplpath = join(dirpath, tmpl)
                            with open(tmplpath) as ifp:
                                lines = ifp.read()
                            if oldpair in lines:
                                with open(tmplpath) as ifp:
                                    lines = ifp.readlines()
                                newlines = []
                                changed = {}
                                for lineno, line in enumerate(lines):
                                    newline = line.replace(oldpair, newpair)
                                    if newline != line:
                                        if len(changed) > 0:
                                            dup = True
                                        else:
                                            dup = False
                                        changed = {
                                            "path": tmplpath,
                                            "linenumber": lineno,
                                            "oldline": line.strip(),
                                            "newline": newline.strip(),
                                            "duplicate": dup,
                                        }
                                        changedlist.append(changed)
                                    newlines.append(newline)
                                with open(tmplpath, "w") as ofp:
                                    ofp.writelines(newlines)
            print(
                "{0} role done. Made the following changes:".format(role["lsrrolename"])
            )
            for changed in changedlist:
                print(
                    "{0}{1}:{2}".format(
                        "DUPLICATED - " if changed["duplicate"] else "",
                        changed["path"],
                        changed["linenumber"],
                    )
                )
                if changed["duplicate"]:
                    print("  questionable line: {0}".format(changed["oldline"]))
                    exit_code = 1
                else:
                    print("  old line: {0}".format(changed["oldline"]))
                    print("  new line: {0}".format(changed["newline"]))
